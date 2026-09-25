#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"
# shellcheck disable=SC2086
$DC --profile security exec -T backup-agent python - <<'PY'
import agent
errors = agent.offsite_configuration_errors()
if errors:
    raise SystemExit("Offsite configuration error: " + "; ".join(errors))
env = agent.restic_environment()
agent.run(["restic", "check"], env=env, timeout=21600, capture=False)
print("Offsite Restic repository check PASS")
PY
