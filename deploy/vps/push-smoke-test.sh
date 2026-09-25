#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
[ -f "$ENV_FILE" ] || { echo "HIBA: $ENV_FILE hiányzik" >&2; exit 1; }
# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a
DEVICE_ID=${1:-${PUSH_SMOKE_DEVICE_ID:-}}
[ -n "$DEVICE_ID" ] || { echo "Használat: $0 <mobile_device_id>" >&2; exit 2; }
case "$DEVICE_ID" in *[!0-9]*|'') echo "HIBA: device_id egész szám legyen" >&2; exit 2;; esac
DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"
# shellcheck disable=SC2086
$DC --profile security exec -T push-worker python -m app.push_smoke_test --device-id "$DEVICE_ID" --wait "${PUSH_SMOKE_WAIT_SECONDS:-45}"
echo "FONTOS: a PASS azt igazolja, hogy az FCM provider elfogadta az üzenetet. A telefonon vizuálisan is ellenőrizd a kézbesítést és a deep linket."
