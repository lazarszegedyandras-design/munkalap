#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE" >&2; exit 1; }
DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"

# Run the request and polling client inside the backup-agent container so the
# privileged control API never needs a published host port.
# shellcheck disable=SC2086
$DC --profile security exec -T backup-agent python - <<'PY'
import json
import time
import urllib.request
from pathlib import Path

token = Path("/run/secrets/backup_agent_token").read_text().strip()
headers = {"X-Backup-Agent-Token": token, "Content-Type": "application/json"}
req = urllib.request.Request(
    "http://127.0.0.1:8090/backups/master",
    data=b"{}",
    headers=headers,
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as response:
    payload = json.load(response)
job_id = payload["job_id"]
print("Started:", job_id)

for _ in range(720):
    time.sleep(5)
    req = urllib.request.Request(
        f"http://127.0.0.1:8090/backups/{job_id}",
        headers=headers,
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        row = json.load(response)
    status = row.get("status")
    if status in {"failed", "interrupted", "critical"}:
        raise SystemExit(f"Backup failed: {row.get('error') or row}")
    if status == "success" and row.get("offsite_status") == "success":
        print("Local and offsite backup PASS:", row.get("id"), row.get("offsite_snapshot_id"))
        raise SystemExit(0)
    if status == "success" and row.get("offsite_status") == "failed":
        raise SystemExit(f"Offsite backup failed: {row.get('offsite_error')}")
raise SystemExit("Backup acceptance timed out")
PY
