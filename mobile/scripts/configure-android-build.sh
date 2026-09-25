#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
APP_GRADLE=android/app/build.gradle
[ -f "$APP_GRADLE" ] || { echo "HIBA: $APP_GRADLE nem található. Előbb generáld az Android projektet." >&2; exit 1; }
MARKER="scripts/release-signing.gradle"
if ! grep -q "$MARKER" "$APP_GRADLE"; then
  printf '\n// Munkalap reproducible versioning + optional release signing.\napply from: "../../scripts/release-signing.gradle"\n' >> "$APP_GRADLE"
fi
[ -f android/app/google-services.json ] || {
  echo "HIBA: android/app/google-services.json hiányzik. Állítsd be a FIREBASE_GOOGLE_SERVICES_JSON változót." >&2
  exit 1
}
echo "Android Firebase/version/signing konfiguráció kész."
