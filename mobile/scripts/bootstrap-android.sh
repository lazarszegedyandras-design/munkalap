#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "HIBA: mobile/.env hiányzik. Másold a .env.example fájlt és állítsd be a VITE_API_BASE_URL HTTPS címet." >&2; exit 1; }
case "$(grep '^VITE_API_BASE_URL=' .env | cut -d= -f2-)" in
  https://*) ;;
  *) echo "HIBA: VITE_API_BASE_URL production Android buildnél HTTPS legyen." >&2; exit 1 ;;
esac
npm install
npm run test
npm run build
if [ ! -d android ]; then npx cap add android; fi
if [ -n "${FIREBASE_GOOGLE_SERVICES_JSON:-}" ]; then
  [ -f "$FIREBASE_GOOGLE_SERVICES_JSON" ] || { echo "HIBA: FIREBASE_GOOGLE_SERVICES_JSON nem található." >&2; exit 1; }
  cp "$FIREBASE_GOOGLE_SERVICES_JSON" android/app/google-services.json
fi
./scripts/harden-android.sh
if [ -f android/app/google-services.json ]; then ./scripts/configure-android-build.sh; fi
npx cap sync android
printf '\nAndroid projekt elkészült. Debug APK: npm run android:build:debug\n'
