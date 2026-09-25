#!/bin/sh
set -eu
MODE=${1:-debug}
case "$MODE" in debug|release|bundle) ;; *) echo "Használat: $0 debug|release|bundle" >&2; exit 2;; esac
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "HIBA: mobile/.env hiányzik." >&2; exit 1; }
API_URL=$(grep '^VITE_API_BASE_URL=' .env | cut -d= -f2-)
case "$API_URL" in https://*) ;; *) echo "HIBA: Android buildhez HTTPS VITE_API_BASE_URL szükséges." >&2; exit 1;; esac

command -v node >/dev/null 2>&1 || { echo "HIBA: Node.js szükséges." >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "HIBA: npm szükséges." >&2; exit 1; }
command -v java >/dev/null 2>&1 || { echo "HIBA: JDK szükséges." >&2; exit 1; }

./scripts/preflight-release.sh
npm install
npm run test
npm run build
if [ ! -d android ]; then npx cap add android; fi

if [ -n "${FIREBASE_GOOGLE_SERVICES_JSON:-}" ]; then
  [ -f "$FIREBASE_GOOGLE_SERVICES_JSON" ] || { echo "HIBA: FIREBASE_GOOGLE_SERVICES_JSON fájl nem található." >&2; exit 1; }
  cp "$FIREBASE_GOOGLE_SERVICES_JSON" android/app/google-services.json
fi
[ -s android/app/google-services.json ] || { echo "HIBA: Firebase google-services.json szükséges a push buildhez." >&2; exit 1; }

./scripts/harden-android.sh
./scripts/configure-android-build.sh
npx cap sync android

VERSION=$(node -p "require('./package.json').version")
VERSION_CODE=$(node -e "const [a,b,c]=process.argv[1].split('.').map(Number);console.log(a*1000000+b*1000+c)" "$VERSION")
export MUNKALAP_VERSION_NAME="$VERSION"
export MUNKALAP_VERSION_CODE="$VERSION_CODE"

if [ "$MODE" != debug ]; then
  for var in MUNKALAP_KEYSTORE_PATH MUNKALAP_KEYSTORE_PASSWORD MUNKALAP_KEY_ALIAS MUNKALAP_KEY_PASSWORD; do
    eval "value=\${$var:-}"
    [ -n "$value" ] || { echo "HIBA: release buildhez hiányzik: $var" >&2; exit 1; }
  done
  [ -f "$MUNKALAP_KEYSTORE_PATH" ] || { echo "HIBA: keystore nem található: $MUNKALAP_KEYSTORE_PATH" >&2; exit 1; }
fi

mkdir -p native-dist
case "$MODE" in
  debug)
    (cd android && ./gradlew --no-daemon clean assembleDebug)
    cp android/app/build/outputs/apk/debug/app-debug.apk "native-dist/Munkalap-Technikus-${VERSION}-debug.apk"
    ;;
  release)
    (cd android && ./gradlew --no-daemon clean assembleRelease)
    cp android/app/build/outputs/apk/release/app-release.apk "native-dist/Munkalap-Technikus-${VERSION}-release.apk"
    ;;
  bundle)
    (cd android && ./gradlew --no-daemon clean bundleRelease)
    cp android/app/build/outputs/bundle/release/app-release.aab "native-dist/Munkalap-Technikus-${VERSION}-release.aab"
    ;;
esac
sha256sum native-dist/Munkalap-Technikus-${VERSION}-* | tee native-dist/SHA256SUMS.txt
if [ "$MODE" != debug ]; then ./scripts/verify-release-artifacts.sh; fi
echo "Android build PASS: mobile/native-dist/"
