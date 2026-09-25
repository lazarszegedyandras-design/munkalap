#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
[ "${RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE:-}" = "YES" ] || {
  echo "BLOCKED: set RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE=YES for the physical restore drill" >&2
  exit 2
}
DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"

# The acceptance client runs inside the non-privileged backup-agent container;
# neither the runner token nor the Docker socket is exposed to this script.
# shellcheck disable=SC2086
$DC --profile security exec -T backup-agent python - <<'PY'
import json
import time
import urllib.request
from pathlib import Path

token = Path("/run/secrets/backup_agent_token").read_text().strip()
headers = {"X-Backup-Agent-Token": token, "Content-Type": "application/json"}
base = "http://127.0.0.1:8090"

def call(method, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)

def wait(path, success, failures, attempts=1440):
    for _ in range(attempts):
        row = call("GET", path)
        if row.get("status") == success:
            return row
        if row.get("status") in failures:
            raise SystemExit(f"Acceptance job failed: {row}")
        time.sleep(5)
    raise SystemExit(f"Acceptance job timed out: {path}")

backup = call("POST", "/backups/master", {})
backup_row = wait(f"/backups/{backup['job_id']}", "success", {"failed", "interrupted", "critical"})
backup_id = backup_row["id"]
validation = call("POST", f"/backups/{backup_id}/validate", {})
if not validation.get("valid") or not validation.get("pgbackrest_verified"):
    raise SystemExit(f"Backup validation failed: {validation}")

restore = call("POST", f"/backups/{backup_id}/restore", {"confirmation": "VISSZAALLIT"})
restore_row = wait(f"/restores/{restore['restore_id']}", "success", {"failed", "critical"})
if not restore_row.get("pre_restore_backup_id") or not restore_row.get("post_restore_backup_id"):
    raise SystemExit(f"Restore evidence is incomplete: {restore_row}")
if restore_row.get("rollback_status") not in (None, "not_required"):
    raise SystemExit(f"Unexpected rollback state: {restore_row}")
print("Physical backup/restore acceptance PASS:", restore_row["id"])
PY
