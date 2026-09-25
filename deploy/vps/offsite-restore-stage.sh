#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
SNAPSHOT=${1:-latest}
DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"
# shellcheck disable=SC2086
$DC --profile security exec -T -e SNAPSHOT="$SNAPSHOT" backup-agent python - <<'PY'
import os
from pathlib import Path
from datetime import datetime, timezone
import agent

snapshot = os.environ.get("SNAPSHOT", "latest")
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
target = Path("/offsite-restore") / f"stage-{stamp}"
target.mkdir(parents=True, exist_ok=False)
agent.run(["restic", "restore", snapshot, "--target", str(target)], env=agent.restic_environment(), timeout=21600, capture=False)

# Verify the application-level checksums contained inside the restored /repo
# tree. This proves that the staged offsite restore is not merely readable by
# restic but also preserves the backup artifact integrity contract.
import hashlib
checksum_files = sorted(target.rglob("checksums.sha256"))
if not checksum_files:
    raise SystemExit("Restored snapshot contains no checksums.sha256 files")
checked = 0
for checksum_file in checksum_files:
    base = checksum_file.parent.resolve()
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            expected, relative = line.split(" *", 1)
        except ValueError as exc:
            raise SystemExit(f"Invalid checksum line in {checksum_file}") from exc
        if len(expected) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in expected):
            raise SystemExit(f"Invalid checksum digest in {checksum_file}: {relative}")
        path = (base / relative).resolve()
        if path != base and base not in path.parents:
            raise SystemExit(f"Unsafe checksum path in {checksum_file}: {relative}")
        if not path.is_file():
            raise SystemExit(f"Restored checksum target missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest.lower() != expected.lower():
            raise SystemExit(f"Restored checksum mismatch: {path}")
        checked += 1
if checked == 0:
    raise SystemExit("Restored checksum manifests contained no files")
print(f"Offsite staged restore checksum PASS: {checked} file(s) across {len(checksum_files)} manifest(s)")
print(f"Restore staged at {target}")
print("No production data was overwritten.")
PY
