#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 1
fi

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a
  . "$ENV_FILE"
  set +a
fi

ADMIN_SSH_CIDR=${ADMIN_SSH_CIDR:-}
SSH_PORT=${SSH_PORT:-22}
[ -n "$ADMIN_SSH_CIDR" ] || { echo "Set ADMIN_SSH_CIDR, for example 203.0.113.10/32" >&2; exit 2; }

command -v ufw >/dev/null 2>&1 || {
  apt-get update
  apt-get install -y ufw
}

ufw default deny incoming
ufw default allow outgoing
ufw allow from "$ADMIN_SSH_CIDR" to any port "$SSH_PORT" proto tcp comment 'restricted SSH'
ufw allow 80/tcp comment 'Caddy HTTP ACME and redirect'
ufw allow 443/tcp comment 'Caddy HTTPS'
ufw --force enable
ufw status verbose
