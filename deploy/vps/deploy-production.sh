#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
export ENV_FILE

"$ROOT_DIR/deploy/vps/preflight-production.sh"

# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"
PROFILE_ARGS="--profile security"
if [ "${ENABLE_LOCAL_MONITORING:-false}" = "true" ]; then
  PROFILE_ARGS="$PROFILE_ARGS --profile monitoring"
fi

# Application images must be promoted from a complete isolated test run.
# Do not rebuild here: a rebuild can resolve different dependencies/base images.
IMAGE_LOCK="$ROOT_DIR/release-images.lock.json"
[ -f "$IMAGE_LOCK" ] || { echo "Missing tested-image lock. Run test-release, then promote_tested_images.py. No deployment performed." >&2; exit 1; }
# shellcheck disable=SC2086
$DC $PROFILE_ARGS config --format json | python3 "$ROOT_DIR/scripts/check_release_images.py" --lock "$IMAGE_LOCK"
# shellcheck disable=SC2086
$DC $PROFILE_ARGS pull edge clamav >/dev/null
if [ "${ENABLE_LOCAL_MONITORING:-false}" = "true" ]; then
  # shellcheck disable=SC2086
  $DC $PROFILE_ARGS pull uptime-kuma >/dev/null
fi

# Block deployment on current source/image vulnerability, secret and
# misconfiguration policy. Runtime images were just pulled above; application
# images are content-address verified by release-images.lock.json.
TRIVY_SKIP_PULL=false SECURITY_EVIDENCE_DIR="${SECURITY_EVIDENCE_DIR:-$ROOT_DIR/security-results/$(date -u +%Y%m%dT%H%M%SZ)-predeploy}" \
  "$ROOT_DIR/deploy/vps/security-scan.sh"

# shellcheck disable=SC2086
$DC $PROFILE_ARGS config --format json | python3 "$ROOT_DIR/scripts/check_release_images.py" --lock "$IMAGE_LOCK"
# Never silently build a different image after identity verification.
# shellcheck disable=SC2086
$DC $PROFILE_ARGS up -d --no-build --remove-orphans
# shellcheck disable=SC2086
$DC $PROFILE_ARGS config --format json | python3 "$ROOT_DIR/scripts/check_release_images.py" --running --lock "$IMAGE_LOCK"

"$ROOT_DIR/deploy/vps/init-offsite-backup.sh"

attempt=0
until curl -fsS --max-time 10 "https://${APP_DOMAIN}/api/health/ready" | grep -q '"status":"ready"'; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "Public HTTPS readiness did not become healthy." >&2
    # shellcheck disable=SC2086
    $DC $PROFILE_ARGS ps >&2 || true
    # shellcheck disable=SC2086
    $DC $PROFILE_ARGS logs --tail=100 edge frontend backend push-worker >&2 || true
    exit 1
  fi
  sleep 5
done

"$ROOT_DIR/deploy/vps/acceptance-production.sh"

echo "Production deploy PASS: https://${APP_DOMAIN}"
echo "Run deploy/vps/run-backup-acceptance.sh before considering the offsite backup gate complete."
