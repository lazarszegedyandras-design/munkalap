#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE" >&2; exit 1; }

DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"
# shellcheck disable=SC2086
$DC --profile security exec -T backup-agent python - <<'PY'
import agent
errors = agent.offsite_configuration_errors()
if errors:
    raise SystemExit("Offsite configuration error: " + "; ".join(errors))
env = agent.restic_environment()
probe = agent.run(["restic", "snapshots", "--json"], check=False, env=env, timeout=120)
if probe.returncode == 0:
    print("Offsite Restic repository already initialized.")
else:
    agent.run(["restic", "init"], env=env, timeout=120)
    print("Offsite Restic repository initialized.")
PY
