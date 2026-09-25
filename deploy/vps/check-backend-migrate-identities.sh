#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
# This is an explicit, read-only live-configuration check, not a test suite.
# It is deliberately NOT called by the isolated release-test launcher.
dc() {
    docker compose --env-file "$ENV_FILE" -f "$ROOT_DIR/compose.yaml" -f "$ROOT_DIR/docker-compose.production.yml" "$@"
}
check_identity='import os; from urllib.parse import urlsplit; from app.config import get_settings; actual=urlsplit(get_settings().database_url.replace("postgresql+psycopg2://", "postgresql://", 1)).username; expected=os.environ["EXPECTED_DB_USER"]; assert os.getuid()==10001 and os.getgid()==10001; assert actual==expected, "Unexpected DB user"; print("Non-root identity and configured DB user verified")'
# COMMAND alone does not replace an entrypoint. This explicitly bypasses both
# web startup and migration/seed; --no-deps prevents dependency side effects.
dc run --rm --no-deps -T --entrypoint python -e EXPECTED_DB_USER=workapp_migrate migrate -c "$check_identity"
dc run --rm --no-deps -T --entrypoint python -e EXPECTED_DB_USER=workapp_app backend -c "$check_identity"
echo "Read-only configured identities PASS (no DB connectivity/grant claim)"
