#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

DC="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"
PROFILE_ARGS="--profile security"
if [ "${ENABLE_LOCAL_MONITORING:-false}" = "true" ]; then
  PROFILE_ARGS="$PROFILE_ARGS --profile monitoring"
fi

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

# shellcheck disable=SC2086
$DC $PROFILE_ARGS ps >/dev/null

IMAGE_LOCK="$ROOT_DIR/release-images.lock.json"
[ -f "$IMAGE_LOCK" ] || fail "Missing tested-image lock"
# shellcheck disable=SC2086
$DC $PROFILE_ARGS config --format json | python3 "$ROOT_DIR/scripts/check_release_images.py" --running --lock "$IMAGE_LOCK" >/dev/null || fail "Running image identity gate"
pass "Running application images match Step 1 tested identities"

verify_runtime_image() {
  service=$1
  reference=$2
  expected=$(docker image inspect --format '{{.Id}}' "$reference" 2>/dev/null) || fail "Runtime image is unavailable locally: $reference"
  # shellcheck disable=SC2086
  container_id=$($DC $PROFILE_ARGS ps -q "$service")
  [ -n "$container_id" ] || fail "Runtime service is not running: $service"
  running=$(docker inspect --format '{{.Image}}' "$container_id")
  [ "$running" = "$expected" ] || fail "Running $service image does not match the current scanned/pulled $reference image"
}
verify_runtime_image edge caddy:2.11.4-alpine
verify_runtime_image clamav clamav/clamav:1.5.4-debian
if [ "${ENABLE_LOCAL_MONITORING:-false}" = "true" ]; then
  verify_runtime_image uptime-kuma louislam/uptime-kuma:2.5.4
fi
pass "Running runtime images match the current scanned/pulled image identities"

redirect=$(curl -sS --max-time 15 -o /dev/null -w '%{http_code} %{redirect_url}' "http://${APP_DOMAIN}/")
case "$redirect" in
  301\ https://"${APP_DOMAIN}"/*|302\ https://"${APP_DOMAIN}"/*|307\ https://"${APP_DOMAIN}"/*|308\ https://"${APP_DOMAIN}"/*) ;;
  *) fail "HTTP does not redirect to HTTPS: $redirect" ;;
esac
pass "HTTP redirects to HTTPS"

curl -fsS --max-time 15 "https://${APP_DOMAIN}/health" | grep -q '^ok' || fail "Public frontend health"
pass "Public HTTPS frontend health"

curl -fsS --max-time 15 "https://${APP_DOMAIN}/api/health/ready" | grep -q '"status":"ready"' || fail "Backend readiness"
pass "Backend readiness"

headers=$(curl -fsSI --max-time 15 "https://${APP_DOMAIN}/")
printf '%s\n' "$headers" | grep -qi '^strict-transport-security:.*max-age=31536000' || fail "HSTS header missing/weak"
printf '%s\n' "$headers" | grep -qi '^content-security-policy:' || fail "CSP header missing"
printf '%s\n' "$headers" | grep -qi '^x-content-type-options:.*nosniff' || fail "nosniff header missing"
printf '%s\n' "$headers" | grep -qi '^x-frame-options:.*DENY' || fail "X-Frame-Options missing"
printf '%s\n' "$headers" | grep -qi '^referrer-policy:' || fail "Referrer-Policy missing"
printf '%s\n' "$headers" | grep -qi '^permissions-policy:' || fail "Permissions-Policy missing"
if printf '%s\n' "$headers" | grep -qi '^server:'; then
  fail "Server header must be suppressed at the public edge"
fi
pass "Public edge security headers"

for path in /docs /redoc /api/openapi.json; do
  code=$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' "https://${APP_DOMAIN}${path}")
  [ "$code" = "404" ] || fail "Internal API documentation endpoint exposed: $path -> $code"
done
trace_code=$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' -X TRACE "https://${APP_DOMAIN}/")
[ "$trace_code" = "405" ] || fail "TRACE must be rejected with 405, found $trace_code"
pass "Internal docs hidden and TRACE blocked"

cert_file=$(mktemp)
trap 'rm -f "$cert_file"' EXIT HUP INT TERM
echo | openssl s_client -servername "$APP_DOMAIN" -connect "$APP_DOMAIN:443" 2>/dev/null | openssl x509 -outform PEM > "$cert_file"
expiry=$(openssl x509 -in "$cert_file" -noout -enddate | cut -d= -f2-)
[ -n "$expiry" ] || fail "TLS certificate could not be read"
openssl x509 -in "$cert_file" -checkend 1209600 -noout >/dev/null 2>&1 || fail "TLS certificate expires within 14 days"
pass "TLS certificate valid beyond 14 days ($expiry)"

for port in 3000 5432 8000 8090 8091 3310; do
  if ss -lnt | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
    fail "Internal service is listening on host port $port"
  fi
done
pass "No internal application/database/security service is published on host ports"

# Exercise the edge limiter while deliberately changing a forged
# X-Forwarded-For value on every request. Caddy must overwrite the spoofed
# header, therefore nginx must still group the requests by the real client and
# return 429. No valid credentials are used.
rate_limited=false
i=1
while [ "$i" -le 20 ]; do
  code=$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -H "X-Forwarded-For: 198.51.100.${i}" \
    -d '{}' "https://${APP_DOMAIN}/api/auth/login")
  if [ "$code" = "429" ]; then
    rate_limited=true
    break
  fi
  i=$((i + 1))
done
[ "$rate_limited" = "true" ] || fail "Public login limiter/X-Forwarded-For anti-spoof gate did not return 429"
pass "Public login rate limiting and forwarding-header anti-spoof gate"

# shellcheck disable=SC2086
$DC $PROFILE_ARGS exec -T backend python - <<'PY'
from app.config import get_settings, production_security_errors
settings = get_settings()
errors = production_security_errors(settings)
if errors:
    raise SystemExit("; ".join(errors))
print("Backend production security gate PASS")
PY
pass "Backend production security gate"

# shellcheck disable=SC2086
$DC $PROFILE_ARGS exec -T backend python - <<'PY'
from app.database import SessionLocal
from app.services.audit import verify_audit_chain
with SessionLocal() as db:
    result = verify_audit_chain(db)
if not result.get("valid"):
    raise SystemExit(f"Audit chain invalid: {result}")
print(f"Audit chain PASS: {result.get('checked_count', 0)} entries")
PY
pass "Audit log hash-chain integrity"

# Verify that the dedicated push worker is running with the mounted Firebase
# credential and can mint a short-lived OAuth token. No notification is sent.
# shellcheck disable=SC2086
$DC $PROFILE_ARGS exec -T push-worker python - <<'PY'
from pathlib import Path
from app.config import get_settings
from app.services.push_notifications import _load_fcm_credentials
settings = get_settings()
if not settings.push_notifications_enabled:
    raise SystemExit("Push notifications are disabled")
path = Path(settings.fcm_service_account_file)
if not path.is_file() or path.stat().st_size == 0:
    raise SystemExit(f"Firebase service-account secret is not readable: {path}")
token = _load_fcm_credentials(settings)
if not token:
    raise SystemExit("Could not obtain Firebase OAuth token")
print("Push worker Firebase credential PASS")
PY
pass "Push worker and Firebase OAuth credential"


if [ -n "${PUSH_SMOKE_DEVICE_ID:-}" ]; then
  "$ROOT_DIR/deploy/vps/push-smoke-test.sh" "$PUSH_SMOKE_DEVICE_ID"
  pass "Real FCM push smoke test queued and accepted"
else
  echo "WARN: PUSH_SMOKE_DEVICE_ID nincs beállítva; valódi eszközös FCM smoke test kihagyva." >&2
fi

# shellcheck disable=SC2086
$DC $PROFILE_ARGS exec -T backup-agent python - <<'PY'
import agent
state = agent.offsite_status_payload()
if not state.get("enabled") or not state.get("configured"):
    raise SystemExit(f"Offsite backup not configured: {state}")
print(state)
PY
pass "Offsite backup configuration"

echo "Production infrastructure acceptance PASS"
