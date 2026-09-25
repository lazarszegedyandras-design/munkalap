#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"
# shellcheck disable=SC2086
$DC --profile security --profile monitoring ps
# shellcheck disable=SC2086
$DC --profile security logs --tail=30 edge backend db backup-agent clamav

# Push operational summary without exposing FCM tokens.
# shellcheck disable=SC2086
$DC --profile security exec -T backend python - <<'PY'
from app.database import SessionLocal
from app.models import MobileDevice, PushDeliveryOutbox
db=SessionLocal()
try:
    active=db.query(MobileDevice).filter(MobileDevice.revoked_at.is_(None), MobileDevice.push_enabled.is_(True), MobileDevice.push_token.is_not(None)).count()
    pending=db.query(PushDeliveryOutbox).filter(PushDeliveryOutbox.status.in_(["pending","processing"])).count()
    failed=db.query(PushDeliveryOutbox).filter(PushDeliveryOutbox.status.in_(["failed","failed_permanent"])).count()
    print(f"Push devices active={active} pending={pending} failed={failed}")
finally:
    db.close()
PY
