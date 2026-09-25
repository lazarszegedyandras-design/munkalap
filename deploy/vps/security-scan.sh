#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
EVIDENCE_DIR=${SECURITY_EVIDENCE_DIR:-$ROOT_DIR/security-results/$(date -u +%Y%m%dT%H%M%SZ)-scan}
TRIVY_IMAGE=${TRIVY_IMAGE:-ghcr.io/aquasecurity/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969}
IMAGE_LOCK=${IMAGE_LOCK:-$ROOT_DIR/release-images.lock.json}

fail() { echo "ERROR: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[ -f "$ENV_FILE" ] || fail "Missing $ENV_FILE"
[ -f "$IMAGE_LOCK" ] || fail "Missing $IMAGE_LOCK. Promote a complete Step 1 PASS before scanning."
for cmd in docker python3 mktemp; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
done

docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is required"
[ ! -e "$EVIDENCE_DIR" ] || fail "Refusing to overwrite existing security evidence directory: $EVIDENCE_DIR"
mkdir -p "$EVIDENCE_DIR"
TMP_DIR=$(mktemp -d)
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT HUP INT TERM

# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"
PROFILE_ARGS="--profile security"
if [ "${ENABLE_LOCAL_MONITORING:-false}" = "true" ]; then
  PROFILE_ARGS="$PROFILE_ARGS --profile monitoring"
fi

# Verify that application images still match the exact Step 1 promotion lock.
# Effective Compose JSON is temporary because it may contain deployment settings.
COMPOSE_JSON="$TMP_DIR/compose.json"
# shellcheck disable=SC2086
$DC $PROFILE_ARGS config --format json > "$COMPOSE_JSON"
python3 "$ROOT_DIR/scripts/check_release_images.py" --lock "$IMAGE_LOCK" < "$COMPOSE_JSON"
pass "Exact Step 1 application image identities verified"

if [ "${TRIVY_SKIP_PULL:-false}" != "true" ]; then
  docker pull "$TRIVY_IMAGE" >/dev/null
fi
TRIVY_ID=$(docker image inspect --format '{{.Id}}' "$TRIVY_IMAGE" 2>/dev/null) || fail "Trivy image is unavailable: $TRIVY_IMAGE"
# Force a vulnerability-DB update at the beginning of every production gate.
# If the database cannot be refreshed, the scan fails closed rather than using
# a silently stale cache.
docker run --rm \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  -v "munkalap_trivy_cache:/root/.cache/" \
  "$TRIVY_IMAGE" image --timeout 10m --quiet --download-db-only >/dev/null
{
  echo "image=$TRIVY_IMAGE"
  echo "image_id=$TRIVY_ID"
  docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges \
    -v "munkalap_trivy_cache:/root/.cache/:ro" \
    "$TRIVY_IMAGE" --version
} > "$EVIDENCE_DIR/trivy-version.txt"

evaluate_trivy_result() {
  mode=$1
  raw=$2
  summary=$3
  target=$4
  if python3 "$ROOT_DIR/scripts/trivy_gate.py" --mode "$mode" --input "$raw" --summary "$summary" --target "$target"; then
    return 0
  else
    code=$?
  fi
  # Exit 1 means a policy blocker was recorded in the safe summary. Continue
  # scanning the remaining targets so the final evidence is complete. Any
  # parser/evaluator error (exit 2+) is an operational failure and stays fail-closed.
  [ "$code" -eq 1 ] || fail "Trivy gate evaluator failed for $target/$mode (exit $code)"
  return 0
}

run_trivy_fs() {
  mode=$1
  scanner=$2
  raw="$TMP_DIR/source-$mode.json"
  summary="$EVIDENCE_DIR/source-$mode.json"
  docker run --rm \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    -v "munkalap_trivy_cache:/root/.cache/" \
    -v "$ROOT_DIR:/workspace:ro" \
    -v "$TMP_DIR:/out" \
    "$TRIVY_IMAGE" fs \
      --timeout 20m \
      --quiet \
      --scanners "$scanner" \
      --format json \
      --output "/out/source-$mode.json" \
      --skip-dirs /workspace/.git \
      --skip-dirs /workspace/secrets \
      --skip-dirs /workspace/node_modules \
      --skip-dirs /workspace/test-results \
      --skip-dirs /workspace/security-results \
      --skip-dirs /workspace/security-artifacts \
      --skip-dirs /workspace/backups \
      --skip-dirs /workspace/pre-restore-backups \
      --skip-dirs /workspace/runtime \
      /workspace >/dev/null
  evaluate_trivy_result "$mode" "$raw" "$summary" source
}

run_trivy_fs vuln vuln
run_trivy_fs secret secret
run_trivy_fs misconfig misconfig
pass "Source vulnerability/secret/misconfiguration scans completed"

# Extract image references from the already validated effective model without
# copying environment values into evidence.
python3 - "$COMPOSE_JSON" "$IMAGE_LOCK" "$TMP_DIR/images.tsv" "${ENABLE_LOCAL_MONITORING:-false}" <<'PY'
import json, sys
compose_path, lock_path, out_path, monitoring = sys.argv[1:]
model = json.load(open(compose_path, encoding="utf-8"))
lock = json.load(open(lock_path, encoding="utf-8"))
rows = []
for kind, row in lock["images"].items():
    rows.append(("owned-" + kind, row["reference"]))
for service in ("edge", "clamav"):
    rows.append(("runtime-" + service, model["services"][service]["image"]))
if monitoring.lower() == "true":
    rows.append(("runtime-uptime-kuma", model["services"]["uptime-kuma"]["image"]))
with open(out_path, "w", encoding="utf-8") as handle:
    for label, reference in rows:
        if any(c in label + reference for c in "\r\n\t"):
            raise SystemExit("Unsafe image reference")
        handle.write(f"{label}\t{reference}\n")
PY

INVENTORY_TSV="$TMP_DIR/image-inventory.tsv"
: > "$INVENTORY_TSV"

scan_image() {
  label=$1
  reference=$2
  tar_path="$TMP_DIR/image.tar"
  raw="$TMP_DIR/$label-vuln.json"
  summary="$EVIDENCE_DIR/$label-vuln.json"
  rm -f "$tar_path" "$raw"
  case "$label" in
    runtime-*) docker pull "$reference" >/dev/null ;;
    *) docker image inspect "$reference" >/dev/null 2>&1 || fail "Locked application image is unavailable locally: $reference" ;;
  esac
  image_id=$(docker image inspect --format '{{.Id}}' "$reference")
  printf '%s\t%s\t%s\n' "$label" "$reference" "$image_id" >> "$INVENTORY_TSV"
  docker image save -o "$tar_path" "$reference"
  docker run --rm \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    -v "munkalap_trivy_cache:/root/.cache/" \
    -v "$TMP_DIR:/out" \
    "$TRIVY_IMAGE" image \
      --timeout 20m \
      --quiet \
      --scanners vuln \
      --format json \
      --output "/out/$label-vuln.json" \
      --input /out/image.tar >/dev/null
  rm -f "$tar_path"
  evaluate_trivy_result vuln "$raw" "$summary" "$label"
}

while IFS="$(printf '\t')" read -r label reference; do
  [ -n "$label" ] || continue
  scan_image "$label" "$reference"
done < "$TMP_DIR/images.tsv"

set +e
python3 - "$EVIDENCE_DIR" "$TRIVY_IMAGE" "$TRIVY_ID" "$INVENTORY_TSV" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json, sys
root, image, image_id, inventory_path = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
rows = []
for path in sorted(root.glob("*.json")):
    if path.name == "security-scan-report.json":
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    rows.append({
        "file": path.name,
        "mode": data.get("mode"),
        "target": data.get("target"),
        "result": data.get("result"),
        "blocker_count": data.get("blocker_count", 0),
        "nonblocking_unfixed_high_critical_count": data.get("nonblocking_unfixed_high_critical_count", 0),
    })
inventory = []
for line in inventory_path.read_text(encoding="utf-8").splitlines():
    if not line:
        continue
    label, reference, ident = line.split("\t", 2)
    inventory.append({"target": label, "reference": reference, "image_id": ident})
summary = {
    "format": 1,
    "status": "PASS" if all(row["result"] == "PASS" for row in rows) else "FAIL",
    "scanner_image": image,
    "scanner_image_id": image_id,
    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    "image_inventory": inventory,
    "results": rows,
}
(root / "security-scan-report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
if summary["status"] != "PASS":
    raise SystemExit(1)
PY
aggregate_code=$?
set -e
[ "$aggregate_code" -eq 0 ] || fail "Trivy Step 2 security policy blockers found; evidence=$EVIDENCE_DIR/security-scan-report.json"

pass "Trivy Step 2 security scan PASS; evidence=$EVIDENCE_DIR"
