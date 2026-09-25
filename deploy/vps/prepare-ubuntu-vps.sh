#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl jq openssl ufw unattended-upgrades
systemctl enable --now docker 2>/dev/null || true

dpkg-reconfigure -f noninteractive unattended-upgrades 2>/dev/null || true

echo "Base VPS packages prepared. Docker Engine and the Docker Compose plugin must be installed before deployment."
