#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}

fail() { echo "ERROR: $*" >&2; exit 1; }
warn() { echo "WARN: $*" >&2; }
info() { echo "OK: $*"; }

[ -f "$ENV_FILE" ] || fail "Missing $ENV_FILE"
# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

for cmd in docker curl openssl getent grep awk sed stat ip ss python3 df; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
done
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is required"

[ "${ENVIRONMENT:-}" = "production" ] || fail "ENVIRONMENT must be production"
[ "${APP_VERSION:-}" = "0.31.0" ] || fail "APP_VERSION must be 0.31.0"
[ -n "${APP_DOMAIN:-}" ] || fail "APP_DOMAIN is required"
[ -n "${TLS_EMAIL:-}" ] || fail "TLS_EMAIL is required"
[ "${PUBLIC_BASE_URL:-}" = "https://${APP_DOMAIN}" ] || fail "PUBLIC_BASE_URL must equal https://${APP_DOMAIN}"
[ "${CORS_ORIGINS:-}" = "https://${APP_DOMAIN}" ] || fail "CORS_ORIGINS must equal https://${APP_DOMAIN}"
[ "${SESSION_COOKIE_SECURE:-}" = "true" ] || fail "SESSION_COOKIE_SECURE must be true"
[ "${ADMIN_MFA_REQUIRED:-}" = "true" ] || fail "ADMIN_MFA_REQUIRED must be true"
require_sensitive_age=${SENSITIVE_MFA_MAX_AGE_SECONDS:-300}
[ "${DOCS_ENABLED:-}" = "false" ] || fail "DOCS_ENABLED must be false"
[ "${MALWARE_SCAN_ENABLED:-}" = "true" ] || fail "MALWARE_SCAN_ENABLED must be true"
[ "${MALWARE_SCAN_FAIL_CLOSED:-}" = "true" ] || fail "MALWARE_SCAN_FAIL_CLOSED must be true"
[ "${OFFSITE_BACKUP_ENABLED:-}" = "true" ] || fail "OFFSITE_BACKUP_ENABLED must be true"
[ "${PUSH_NOTIFICATIONS_ENABLED:-}" = "true" ] || fail "PUSH_NOTIFICATIONS_ENABLED must be true"
case "${FCM_PROJECT_ID:-}" in ""|REPLACE_*) fail "FCM_PROJECT_ID must be configured" ;; esac
[ "${TRIVY_IMAGE:-ghcr.io/aquasecurity/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969}" = "ghcr.io/aquasecurity/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969" ] || fail "TRIVY_IMAGE must be the reviewed ghcr.io/aquasecurity/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969 scanner"

case "${ADMIN_SSH_CIDR:-}" in ""|REPLACE_*) fail "ADMIN_SSH_CIDR must restrict SSH to the administrator CIDR" ;; esac

require_int_range() {
  name=$1
  value=$2
  min=$3
  max=$4
  case "$value" in
    ''|*[!0-9]*) fail "$name must be an integer between $min and $max" ;;
  esac
  [ "$value" -ge "$min" ] && [ "$value" -le "$max" ] || fail "$name must be between $min and $max"
}
require_int_range MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES "${MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES:-15}" 1 30
require_int_range MOBILE_REFRESH_TOKEN_EXPIRE_DAYS "${MOBILE_REFRESH_TOKEN_EXPIRE_DAYS:-30}" 1 90
require_int_range MOBILE_SIGNATURE_MAX_SIZE_KB "${MOBILE_SIGNATURE_MAX_SIZE_KB:-1024}" 1 4096
require_int_range MOBILE_PHOTO_MAX_SIZE_MB "${MOBILE_PHOTO_MAX_SIZE_MB:-8}" 1 25
require_int_range MOBILE_PHOTO_MAX_PIXELS "${MOBILE_PHOTO_MAX_PIXELS:-12000000}" 1000000 40000000
require_int_range MOBILE_PHOTO_MAX_DIMENSION "${MOBILE_PHOTO_MAX_DIMENSION:-2048}" 640 4096
require_int_range SENSITIVE_MFA_MAX_AGE_SECONDS "$require_sensitive_age" 60 900
require_int_range LOGIN_RATE_LIMIT_ATTEMPTS "${LOGIN_RATE_LIMIT_ATTEMPTS:-5}" 3 10
require_int_range LOGIN_IP_RATE_LIMIT_ATTEMPTS "${LOGIN_IP_RATE_LIMIT_ATTEMPTS:-50}" 10 200
require_int_range LOGIN_RATE_LIMIT_WINDOW_SECONDS "${LOGIN_RATE_LIMIT_WINDOW_SECONDS:-300}" 60 1800
require_int_range LOGIN_RATE_LIMIT_BLOCK_SECONDS "${LOGIN_RATE_LIMIT_BLOCK_SECONDS:-900}" 300 86400
require_int_range SSH_PORT "${SSH_PORT:-22}" 1 65535
[ -n "${WORK_ORDER_ACCEPTANCE_TEXT_VERSION:-}" ] || fail "WORK_ORDER_ACCEPTANCE_TEXT_VERSION is required"
[ -n "${WORK_ORDER_ACCEPTANCE_TEXT:-}" ] || fail "WORK_ORDER_ACCEPTANCE_TEXT is required"

case "${RESTIC_REPOSITORY:-}" in
  ""|REPLACE_*|*"<"*|*">"*) fail "RESTIC_REPOSITORY must point to the real offsite repository" ;;
esac

EXPECTED_PROXY="${FRONTEND_INTERNAL_IP:-172.30.250.20}/32"
[ "${TRUSTED_PROXY_CIDRS:-}" = "$EXPECTED_PROXY" ] || fail "TRUSTED_PROXY_CIDRS must equal the exact frontend proxy address: $EXPECTED_PROXY"

python3 - "${ADMIN_SSH_CIDR}" <<'PYCIDR'
import ipaddress, sys
try:
    network = ipaddress.ip_network(sys.argv[1], strict=True)
except ValueError as exc:
    raise SystemExit(f"ERROR: invalid ADMIN_SSH_CIDR: {exc}")
if network.num_addresses > 256:
    raise SystemExit("ERROR: ADMIN_SSH_CIDR is too broad; restrict SSH to an administrator host/small management network")
PYCIDR

# Sensitive values must come from Docker secret files, never plaintext .env entries.
for name in POSTGRES_PASSWORD DATABASE_URL DATABASE_MIGRATION_URL DB_ADMIN_URL DATABASE_ADMIN_URL DATABASE_APP_PASSWORD DATABASE_MIGRATE_PASSWORD SECRET_KEY MFA_ENCRYPTION_KEY BACKUP_AGENT_TOKEN BACKUP_RUNNER_TOKEN BOOTSTRAP_ADMIN_PASSWORD RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
  eval "value=\${$name-}"
  [ -z "$value" ] || fail "$name must be empty in .env.production; use its Docker secret file"
done
info "Production .env contains no plaintext sensitive values"

SECRETS_DIR_VALUE=${SECRETS_DIR:-$ROOT_DIR/secrets}
case "$SECRETS_DIR_VALUE" in
  /*) ;;
  *) SECRETS_DIR_VALUE="$ROOT_DIR/${SECRETS_DIR_VALUE#./}" ;;
esac

for name in postgres_password database_url database_migration_url database_admin_url database_app_password database_migrate_password secret_key mfa_encryption_key backup_agent_token backup_runner_token bootstrap_admin_password restic_password aws_access_key_id aws_secret_access_key firebase_service_account.json; do
  path="$SECRETS_DIR_VALUE/$name"
  [ -s "$path" ] || fail "Missing or empty secret: $path"
  mode=$(stat -c '%a' "$path")
  case "$mode" in
    600|400) ;;
    *) fail "Secret $path must have mode 600 or 400, found $mode" ;;
  esac
done

python3 - "$SECRETS_DIR_VALUE/database_url" "$SECRETS_DIR_VALUE/database_migration_url" \
  "$SECRETS_DIR_VALUE/backup_agent_token" "$SECRETS_DIR_VALUE/backup_runner_token" <<'PYSEC'
from pathlib import Path
from urllib.parse import urlparse
import sys

runtime_url = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
migration_url = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
agent_token = Path(sys.argv[3]).read_text(encoding="utf-8").strip()
runner_token = Path(sys.argv[4]).read_text(encoding="utf-8").strip()

def username(url):
    normalized = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    return urlparse(normalized).username

if username(runtime_url) != "workapp_app":
    raise SystemExit("ERROR: runtime database URL must use workapp_app")
if username(migration_url) != "workapp_migrate":
    raise SystemExit("ERROR: migration database URL must use workapp_migrate")
if runtime_url == migration_url:
    raise SystemExit("ERROR: runtime and migration database URLs must differ")
for label, value in (("BACKUP_AGENT_TOKEN", agent_token), ("BACKUP_RUNNER_TOKEN", runner_token)):
    if len(value) < 32 or value.startswith("change-"):
        raise SystemExit(f"ERROR: {label} must be a unique secret of at least 32 characters")
if agent_token == runner_token:
    raise SystemExit("ERROR: backup agent and runner tokens must differ")
PYSEC
info "Database identities and internal service tokens are separated"

python3 - "$SECRETS_DIR_VALUE/firebase_service_account.json" "$FCM_PROJECT_ID" <<'PYFCM'
import json, sys
path, project = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception as exc:
    raise SystemExit(f"ERROR: invalid Firebase service-account JSON: {exc}")
for key in ("type", "project_id", "private_key", "client_email"):
    if not data.get(key):
        raise SystemExit(f"ERROR: Firebase service-account JSON missing {key}")
if data.get("type") != "service_account":
    raise SystemExit("ERROR: Firebase credential must be a service_account")
if data.get("project_id") != project:
    raise SystemExit(f"ERROR: Firebase service-account project_id {data.get('project_id')} != FCM_PROJECT_ID {project}")
PYFCM
info "Firebase service-account JSON is valid"

mode=$(stat -c '%a' "$ENV_FILE")
case "$mode" in
  600|400) ;;
  *) fail "$ENV_FILE must have mode 600 or 400, found $mode" ;;
esac

if ! getent ahostsv4 "$APP_DOMAIN" >/dev/null 2>&1 && ! getent ahostsv6 "$APP_DOMAIN" >/dev/null 2>&1; then
  fail "DNS does not resolve for $APP_DOMAIN"
fi
info "DNS resolves for $APP_DOMAIN"

PUBLIC_IPV4=$(curl -4 -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)
DNS_IPV4=$(getent ahostsv4 "$APP_DOMAIN" 2>/dev/null | awk 'NR==1 {print $1}' || true)
if [ -n "$PUBLIC_IPV4" ] && [ -n "$DNS_IPV4" ] && [ "$PUBLIC_IPV4" != "$DNS_IPV4" ]; then
  fail "DNS A record ($DNS_IPV4) does not match VPS public IPv4 ($PUBLIC_IPV4)"
fi
[ -n "$PUBLIC_IPV4" ] && info "DNS A record matches VPS IPv4 $PUBLIC_IPV4"

if ip route show | grep -F "${APP_NETWORK_SUBNET:-172.30.250.0/24}" >/dev/null 2>&1; then
  warn "APP_NETWORK_SUBNET is already present in the routing table. This is expected after first deploy; verify there is no non-Docker overlap."
fi

COMPOSE="docker compose --env-file $ENV_FILE -f $ROOT_DIR/docker-compose.yml -f $ROOT_DIR/docker-compose.production.yml"
PROFILE_ARGS="--profile security"
if [ "${ENABLE_LOCAL_MONITORING:-false}" = "true" ]; then
  PROFILE_ARGS="$PROFILE_ARGS --profile monitoring"
fi
# Word splitting is intentional for the fixed compose command/profile list assembled above.
# shellcheck disable=SC2086
$COMPOSE $PROFILE_ARGS config -q
info "Docker Compose production configuration is valid"

COMPOSE_JSON=$(mktemp)
trap 'rm -f "$COMPOSE_JSON"' EXIT HUP INT TERM
# shellcheck disable=SC2086
$COMPOSE $PROFILE_ARGS config --format json > "$COMPOSE_JSON"
python3 - "$COMPOSE_JSON" "${ENABLE_LOCAL_MONITORING:-false}" <<'PYCOMPOSE'
import json, sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
monitoring = sys.argv[2].lower() == "true"
services = data.get("services", {})
for required in ("backend", "db-role-provisioner", "migrate", "backup-agent", "backup-runner", "frontend", "edge", "clamav"):
    if required not in services:
        raise SystemExit(f"ERROR: production Compose missing service: {required}")
if monitoring and "uptime-kuma" not in services:
    raise SystemExit("ERROR: monitoring is enabled but uptime-kuma is missing")
if not monitoring and "uptime-kuma" in services:
    raise SystemExit("ERROR: uptime-kuma must not be active when monitoring is disabled")

def networks(service):
    value = services[service].get("networks", {})
    return set(value if isinstance(value, list) else value.keys())

def secret_sources(service):
    result = set()
    for value in services[service].get("secrets", []) or []:
        result.add(value if isinstance(value, str) else value.get("source"))
    return result

def environment_keys(service):
    value = services[service].get("environment") or {}
    if isinstance(value, dict):
        return set(value)
    return {str(row).split("=", 1)[0] for row in value}

def socket_mounts(service):
    hits = []
    for volume in services[service].get("volumes", []) or []:
        if isinstance(volume, str):
            source, _, target = volume.partition(":")
        else:
            source, target = volume.get("source"), volume.get("target")
        if source == "/var/run/docker.sock" or target == "/var/run/docker.sock":
            hits.append((source, target))
    return hits

def published_ports(service):
    rows = []
    for port in services[service].get("ports", []) or []:
        if isinstance(port, str):
            rows.append(port)
        else:
            rows.append({
                "target": port.get("target"),
                "published": str(port.get("published") or ""),
                "host_ip": str(port.get("host_ip") or ""),
            })
    return rows

def logging_ok(service):
    logging = services[service].get("logging") or {}
    options = logging.get("options") or {}
    return logging.get("driver") == "local" and str(options.get("max-size")) == "20m" and str(options.get("max-file")) == "5"

for service in ("backend", "migrate"):
    if str(services[service].get("user")) != "10001:10001":
        raise SystemExit(f"ERROR: {service} must run as fixed non-root uid/gid 10001:10001")
    if set(services[service].get("cap_drop") or []) != {"ALL"}:
        raise SystemExit(f"ERROR: {service} must drop all Linux capabilities")
    if services[service].get("cap_add"):
        raise SystemExit(f"ERROR: {service} must not add Linux capabilities")

if set(services["frontend"].get("cap_drop") or []) != {"ALL"}:
    raise SystemExit("ERROR: frontend must drop all Linux capabilities")
if set(services["edge"].get("cap_drop") or []) != {"ALL"} or set(services["edge"].get("cap_add") or []) != {"NET_BIND_SERVICE"}:
    raise SystemExit("ERROR: edge must drop all capabilities except NET_BIND_SERVICE")

socket_owners = [name for name in services if socket_mounts(name)]
if socket_owners != ["backup-runner"]:
    raise SystemExit(f"ERROR: Docker socket must be mounted only by backup-runner; owners={socket_owners}")
if "privileged_net" in networks("backend"):
    raise SystemExit("ERROR: backend must not join privileged_net")
if "privileged_net" not in networks("backup-agent") or "privileged_net" not in networks("backup-runner"):
    raise SystemExit("ERROR: backup-agent and backup-runner must join privileged_net")
if services["backup-runner"].get("ports"):
    raise SystemExit("ERROR: backup-runner must not publish a host port")
if not data.get("networks", {}).get("privileged_net", {}).get("internal"):
    raise SystemExit("ERROR: privileged_net must be internal")

backend_secrets = secret_sources("backend")
for forbidden in ("database_migration_url", "database_admin_url", "backup_runner_token", "bootstrap_admin_password"):
    if forbidden in backend_secrets:
        raise SystemExit(f"ERROR: backend must not receive secret {forbidden}")
for forbidden in ("BOOTSTRAP_ADMIN_PASSWORD", "BOOTSTRAP_ADMIN_PASSWORD_FILE"):
    if forbidden in environment_keys("backend"):
        raise SystemExit(f"ERROR: backend must not receive environment key {forbidden}")
if "bootstrap_admin_password" not in secret_sources("migrate"):
    raise SystemExit("ERROR: migrate must receive bootstrap_admin_password secret")

# Edge is the only Internet-facing service. Monitoring, if enabled, is loopback-only.
for name, service in services.items():
    ports = published_ports(name)
    if not ports:
        continue
    if name == "edge":
        text = json.dumps(ports)
        if '"80"' not in text or '"443"' not in text:
            raise SystemExit("ERROR: edge must publish only HTTP/HTTPS")
        if len(ports) != 2:
            raise SystemExit("ERROR: edge has unexpected published ports")
    elif name == "uptime-kuma" and monitoring:
        text = json.dumps(ports)
        if "127.0.0.1" not in text or "3001" not in text:
            raise SystemExit("ERROR: uptime-kuma must be loopback-only")
    else:
        raise SystemExit(f"ERROR: unexpected host port publishing by {name}: {ports}")

for name, service in services.items():
    if service.get("restart") == "unless-stopped" and not logging_ok(name):
        raise SystemExit(f"ERROR: long-running service {name} must use bounded local logging")

if services["edge"].get("image") != "caddy:2.11.4-alpine":
    raise SystemExit("ERROR: unreviewed Caddy image")
if services["clamav"].get("image") != "clamav/clamav:1.5.4-debian":
    raise SystemExit("ERROR: unreviewed ClamAV image")
if "uptime-kuma" in services and services["uptime-kuma"].get("image") != "louislam/uptime-kuma:2.5.4":
    raise SystemExit("ERROR: unreviewed Uptime Kuma image")
PYCOMPOSE
info "Compose trust-boundary checks passed"

docker run --rm \
  -e APP_DOMAIN="$APP_DOMAIN" \
  -e TLS_EMAIL="$TLS_EMAIL" \
  -v "$ROOT_DIR/deploy/caddy:/etc/caddy:ro" \
  caddy:2.11.4-alpine \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
info "Caddy configuration is valid"

free_kb=$(df -Pk "$ROOT_DIR" | awk 'NR==2 {print $4}')
[ "${free_kb:-0}" -ge 10485760 ] || fail "At least 10 GiB free disk space is required before production deploy"
info "Disk space preflight passed"

echo "Production preflight PASS"
