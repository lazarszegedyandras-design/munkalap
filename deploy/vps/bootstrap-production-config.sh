#!/bin/sh
set -eu

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <app-domain> <tls-email> [bootstrap-admin-email]" >&2
  exit 2
fi

APP_DOMAIN_VALUE=$1
TLS_EMAIL_VALUE=$2
ADMIN_EMAIL_VALUE=${3:-$TLS_EMAIL_VALUE}
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
SECRETS_DIR_VALUE="$ROOT_DIR/secrets"
ENV_FILE="$ROOT_DIR/.env.production"

case "$APP_DOMAIN_VALUE" in
  http://*|https://*|*/*|*:* )
    echo "APP domain must be a plain DNS hostname without scheme, path or port." >&2
    exit 2
    ;;
esac

mkdir -p "$SECRETS_DIR_VALUE"
chmod 700 "$SECRETS_DIR_VALUE"

random_secret() {
  openssl rand -hex 32
}

write_secret() {
  name=$1
  value=$2
  umask 077
  printf '%s\n' "$value" > "$SECRETS_DIR_VALUE/$name"
  chmod 600 "$SECRETS_DIR_VALUE/$name"
}

POSTGRES_PASSWORD_VALUE=$(random_secret)
DATABASE_APP_PASSWORD_VALUE=$(random_secret)
DATABASE_MIGRATE_PASSWORD_VALUE=$(random_secret)
BOOTSTRAP_PASSWORD_VALUE=$(openssl rand -base64 24 | tr -d '\n')
write_secret postgres_password "$POSTGRES_PASSWORD_VALUE"
write_secret database_app_password "$DATABASE_APP_PASSWORD_VALUE"
write_secret database_migrate_password "$DATABASE_MIGRATE_PASSWORD_VALUE"
write_secret secret_key "$(random_secret)"
write_secret mfa_encryption_key "$(random_secret)"
write_secret backup_agent_token "$(random_secret)"
write_secret backup_runner_token "$(random_secret)"
write_secret bootstrap_admin_password "$BOOTSTRAP_PASSWORD_VALUE"
write_secret restic_password "$(random_secret)"

# The S3 credentials must be supplied by the object-storage provider.
: > "$SECRETS_DIR_VALUE/aws_access_key_id"
: > "$SECRETS_DIR_VALUE/aws_secret_access_key"
: > "$SECRETS_DIR_VALUE/firebase_service_account.json"
chmod 600 "$SECRETS_DIR_VALUE/aws_access_key_id" "$SECRETS_DIR_VALUE/aws_secret_access_key" "$SECRETS_DIR_VALUE/firebase_service_account.json"

DATABASE_URLS=$(python3 - "$POSTGRES_PASSWORD_VALUE" "$DATABASE_APP_PASSWORD_VALUE" "$DATABASE_MIGRATE_PASSWORD_VALUE" <<'PY'
import sys
from urllib.parse import quote
admin, app, migrate = (quote(value, safe='') for value in sys.argv[1:4])
print(f"postgresql://workapp:{admin}@db:5432/workapp")
print(f"postgresql+psycopg2://workapp_app:{app}@db:5432/workapp")
print(f"postgresql+psycopg2://workapp_migrate:{migrate}@db:5432/workapp")
PY
)
DATABASE_ADMIN_URL_VALUE=$(printf '%s\n' "$DATABASE_URLS" | sed -n '1p')
DATABASE_URL_VALUE=$(printf '%s\n' "$DATABASE_URLS" | sed -n '2p')
DATABASE_MIGRATION_URL_VALUE=$(printf '%s\n' "$DATABASE_URLS" | sed -n '3p')
write_secret database_admin_url "$DATABASE_ADMIN_URL_VALUE"
write_secret database_url "$DATABASE_URL_VALUE"
write_secret database_migration_url "$DATABASE_MIGRATION_URL_VALUE"

cp "$ROOT_DIR/.env.production.example" "$ENV_FILE"
python3 - "$ENV_FILE" "$APP_DOMAIN_VALUE" "$TLS_EMAIL_VALUE" "$ADMIN_EMAIL_VALUE" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
domain = sys.argv[2]
tls_email = sys.argv[3]
admin_email = sys.argv[4]
s = path.read_text()
s = s.replace('APP_DOMAIN=app.example.hu', f'APP_DOMAIN={domain}')
s = s.replace('TLS_EMAIL=admin@example.hu', f'TLS_EMAIL={tls_email}')
s = s.replace('PUBLIC_BASE_URL=https://app.example.hu', f'PUBLIC_BASE_URL=https://{domain}')
s = s.replace('CORS_ORIGINS=https://app.example.hu', f'CORS_ORIGINS=https://{domain}')
s = s.replace('BOOTSTRAP_ADMIN_EMAIL=admin@example.hu', f'BOOTSTRAP_ADMIN_EMAIL={admin_email}')
path.write_text(s)
PY
chmod 600 "$ENV_FILE"

cat <<OUT
Production configuration created:
  $ENV_FILE
  $SECRETS_DIR_VALUE/

Bootstrap admin password (store it securely, then rotate after first login):
  $BOOTSTRAP_PASSWORD_VALUE

Before deployment:
  1. Set RESTIC_REPOSITORY in .env.production.
  2. Put the S3 access key into secrets/aws_access_key_id.
  3. Put the S3 secret key into secrets/aws_secret_access_key.
  4. Set FCM_PROJECT_ID in .env.production.
  5. Put the Firebase service-account JSON into secrets/firebase_service_account.json.
  6. Point the DNS A/AAAA record to the VPS.
  7. Run deploy/vps/preflight-production.sh.
OUT
