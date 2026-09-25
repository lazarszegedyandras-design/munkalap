#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
./scripts/preflight-release.sh
./scripts/build-android.sh release
./scripts/build-android.sh bundle
./scripts/verify-release-artifacts.sh
./scripts/generate-release-manifest.sh
if [ "${MUNKALAP_INSTALL_SMOKE:-false}" = "true" ]; then
  ./scripts/install-smoke-test.sh
fi
echo "Android release acceptance PASS"
echo "Artifactok: mobile/native-dist/"
