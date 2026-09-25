#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
VERSION=$(cat "$ROOT_DIR/VERSION")
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=${STEP2_EVIDENCE_DIR:-$ROOT_DIR/security-results/${STAMP}-step2-v${VERSION}}
STAGES="$OUT/stages.tsv"
REPORT="$OUT/report.json"
[ ! -e "$OUT" ] || { echo "Refusing to overwrite existing Step 2 evidence directory: $OUT" >&2; exit 2; }
mkdir -p "$OUT"
: > "$STAGES"

write_report() {
  overall=$1
  python3 - "$STAGES" "$REPORT" "$ROOT_DIR" "$VERSION" "$overall" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, sys
stages_path, report_path, root, version, overall = map(str, sys.argv[1:])
rows = []
for line in Path(stages_path).read_text(encoding="utf-8").splitlines():
    if not line:
        continue
    name, code, status, log = line.split("\t", 3)
    rows.append({"name": name, "exit_code": int(code), "status": status, "log": log})
manifest = Path(root) / "release-source-manifest.json"
manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.exists() else None
report = {
    "format": 1,
    "version": version,
    "status": overall,
    "vps_security_go": overall == "PASS_STEP2_VPS_SECURITY_GATE",
    "production_go": False,
    "source_manifest_sha256": manifest_sha,
    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    "stages": rows,
    "remaining_production_gates": [
        "Android physical-device E2E and release-signing acceptance",
        "signed-document integrity/concurrency gate",
    ],
}
Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
PY
}

run_stage() {
  name=$1
  shift
  log="$OUT/$name.log"
  echo "[RUN] $name"
  set +e
  "$@" >"$log" 2>&1
  code=$?
  set -e
  if [ "$code" -eq 0 ]; then
    status=PASS
  elif [ "$code" -eq 2 ]; then
    status=BLOCKED
  else
    status=FAIL
  fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$code" "$status" "$(basename "$log")" >> "$STAGES"
  echo "[$status] $name; log=$log"
  if [ "$code" -ne 0 ]; then
    if [ "$code" -eq 2 ]; then
      write_report "BLOCKED"
    else
      write_report "FAIL"
    fi
    echo "Step 2 gate stopped at $name. Evidence: $OUT" >&2
    exit "$code"
  fi
}

[ "$(id -u)" -eq 0 ] || {
  echo "Step 2 VPS gate must run as root (host firewall/SSH checks are included)." >&2
  exit 2
}
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE" >&2; exit 2; }
export ENV_FILE

run_stage preflight "$ROOT_DIR/deploy/vps/preflight-production.sh"
run_stage host-security "$ROOT_DIR/deploy/vps/host-security-check.sh"
run_stage security-scan env SECURITY_EVIDENCE_DIR="$OUT/security-scan" "$ROOT_DIR/deploy/vps/security-scan.sh"
run_stage live-acceptance "$ROOT_DIR/deploy/vps/acceptance-production.sh"
run_stage backup-acceptance "$ROOT_DIR/deploy/vps/run-backup-acceptance.sh"
run_stage offsite-repository-check "$ROOT_DIR/deploy/vps/offsite-check.sh"
run_stage offsite-staged-restore "$ROOT_DIR/deploy/vps/offsite-restore-stage.sh" latest

if [ "${RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE:-}" != "YES" ]; then
  log="$OUT/physical-restore-acceptance.log"
  echo "BLOCKED: physical restore drill requires RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE=YES" > "$log"
  printf '%s\t%s\t%s\t%s\n' "physical-restore-acceptance" "2" "BLOCKED" "$(basename "$log")" >> "$STAGES"
  write_report "BLOCKED"
  echo "Step 2 is BLOCKED until the physical restore drill is explicitly authorized. Evidence: $OUT" >&2
  exit 2
fi
run_stage physical-restore-acceptance env RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE=YES "$ROOT_DIR/deploy/vps/run-restore-acceptance.sh"

write_report "PASS_STEP2_VPS_SECURITY_GATE"
echo "Step 2 VPS security gate PASS"
echo "Evidence: $OUT"
echo "VPS security gate is complete; overall production_go remains false until Android/device and signed-document gates pass."
