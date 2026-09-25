#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 1
fi
[ "${CONFIRM_SSH_HARDENING:-}" = "YES" ] || {
  echo "Refusing to change SSH. Verify key-based login in a second session, then set CONFIRM_SSH_HARDENING=YES." >&2
  exit 2
}

mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/99-munkalap-cloud-hardening.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
MaxAuthTries 3
X11Forwarding no
CONF
sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd

echo "SSH hardening applied. Keep the current session open until a new key-based login succeeds."
