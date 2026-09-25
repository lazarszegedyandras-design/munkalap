#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ENV_FILE=${ENV_FILE:-$ROOT_DIR/.env.production}

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[ "$(id -u)" -eq 0 ] || fail "Host security check must run as root"
[ -f "$ENV_FILE" ] || fail "Missing $ENV_FILE"
# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

for cmd in docker ufw sshd ss stat timedatectl systemctl dpkg-query grep awk; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Required host command missing: $cmd"
done

SSH_PORT=${SSH_PORT:-22}
case "$SSH_PORT" in ''|*[!0-9]*) fail "SSH_PORT must be numeric" ;; esac
[ "$SSH_PORT" -ge 1 ] && [ "$SSH_PORT" -le 65535 ] || fail "SSH_PORT must be between 1 and 65535"
[ -n "${ADMIN_SSH_CIDR:-}" ] || fail "ADMIN_SSH_CIDR is required"

UFW_STATUS=$(ufw status verbose)
printf '%s\n' "$UFW_STATUS" | grep -qi '^Status: active' || fail "UFW is not active"
printf '%s\n' "$UFW_STATUS" | grep -Eqi '^Default:[[:space:]]+deny[[:space:]]+\(incoming\)' || fail "UFW default incoming policy must be deny"
UFW_ADDED=$(ufw show added)
EXPECTED_SSH_RULE="ufw allow from ${ADMIN_SSH_CIDR} to any port ${SSH_PORT} proto tcp"
printf '%s\n' "$UFW_ADDED" | grep -F "$EXPECTED_SSH_RULE" >/dev/null || \
  fail "Restricted SSH UFW rule for ADMIN_SSH_CIDR is missing"
# Reject any additional allow command for the SSH port, including rules with
# comments or alternate UFW syntax. The expected restricted rule is the sole exception.
UNEXPECTED_SSH=$(printf '%s\n' "$UFW_ADDED" | \
  grep -E "^[[:space:]]*ufw allow([[:space:]]+${SSH_PORT}(/tcp)?([[:space:]]|$)|.*[[:space:]]port[[:space:]]+${SSH_PORT}([[:space:]]|$))" | \
  grep -Fv "$EXPECTED_SSH_RULE" || true)
[ -z "$UNEXPECTED_SSH" ] || fail "Unexpected/unrestricted SSH UFW allow rule is present: $UNEXPECTED_SSH"
if printf '%s\n' "$UFW_ADDED" | grep -E "^[[:space:]]*ufw allow[[:space:]]+['\"]?OpenSSH['\"]?([[:space:]]|$)" >/dev/null; then
  fail "Unrestricted OpenSSH UFW application-profile rule is present"
fi
printf '%s\n' "$UFW_ADDED" | grep -F 'ufw allow 80/tcp' >/dev/null || fail "HTTP UFW rule missing"
printf '%s\n' "$UFW_ADDED" | grep -F 'ufw allow 443/tcp' >/dev/null || fail "HTTPS UFW rule missing"
pass "UFW active, default-deny inbound, public edge and restricted SSH rules"

SSHD_EFFECTIVE=$(sshd -T)
require_sshd() {
  key=$1
  expected=$2
  actual=$(printf '%s\n' "$SSHD_EFFECTIVE" | awk -v k="$key" '$1==k {print $2; exit}')
  [ "$actual" = "$expected" ] || fail "sshd $key must be $expected (found ${actual:-missing})"
}
require_sshd passwordauthentication no
require_sshd kbdinteractiveauthentication no
require_sshd permitrootlogin no
require_sshd pubkeyauthentication yes
max_auth=$(printf '%s\n' "$SSHD_EFFECTIVE" | awk '$1=="maxauthtries" {print $2; exit}')
case "$max_auth" in ''|*[!0-9]*) fail "sshd maxauthtries is invalid" ;; esac
[ "$max_auth" -le 3 ] || fail "sshd MaxAuthTries must be <= 3"
pass "SSH effective configuration"

if ss -lnt | awk '{print $4}' | grep -Eq '(^|:)(2375|2376)$'; then
  fail "Docker daemon TCP port 2375/2376 is listening"
fi
[ -S /var/run/docker.sock ] || fail "Docker socket is missing"
owner=$(stat -c '%U' /var/run/docker.sock)
[ "$owner" = "root" ] || fail "Docker socket owner must be root"
if find /var/run/docker.sock -perm -0002 -print | grep -q .; then
  fail "Docker socket must not be world-writable"
fi
docker info --format '{{json .SecurityOptions}}' | grep -qi 'seccomp' || fail "Docker default seccomp security option missing"
pass "Docker daemon/socket exposure and seccomp"

for port in 3000 5432 8000 8090 8091 3310; do
  if ss -lnt | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
    fail "Internal service is listening on host port $port"
  fi
done
if [ "${ENABLE_LOCAL_MONITORING:-false}" = "true" ]; then
  if ss -lnt | awk '$4 ~ /:3001$/ {print $4}' | grep -Ev '^(127\.0\.0\.1|\[::1\]):3001$' | grep -q .; then
    fail "Monitoring port 3001 is not loopback-only"
  fi
fi
pass "Internal service host-port isolation"

[ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null || true)" = "yes" ] || fail "NTP is not synchronized"
dpkg-query -W -f='${Status}' unattended-upgrades 2>/dev/null | grep -q 'install ok installed' || fail "unattended-upgrades package missing"
if ! systemctl is-enabled --quiet apt-daily-upgrade.timer 2>/dev/null && ! systemctl is-enabled --quiet unattended-upgrades.service 2>/dev/null; then
  fail "Automatic security update mechanism is not enabled"
fi
pass "Time synchronization and unattended security updates"

echo "Host security check PASS"
