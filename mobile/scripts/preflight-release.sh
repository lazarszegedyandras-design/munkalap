#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

fail() { echo "HIBA: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[ -f package.json ] || fail "mobile/package.json hiányzik"
[ -f .env ] || fail "mobile/.env hiányzik"
command -v node >/dev/null 2>&1 || fail "Node.js szükséges"
command -v npm >/dev/null 2>&1 || fail "npm szükséges"
command -v java >/dev/null 2>&1 || fail "JDK szükséges"
command -v keytool >/dev/null 2>&1 || fail "keytool szükséges"
command -v python3 >/dev/null 2>&1 || fail "python3 szükséges"

VERSION=$(node -p "require('./package.json').version")
ENV_VERSION=$(grep '^VITE_APP_VERSION=' .env | cut -d= -f2- || true)
API_URL=$(grep '^VITE_API_BASE_URL=' .env | cut -d= -f2- || true)
[ "$ENV_VERSION" = "$VERSION" ] || fail "VITE_APP_VERSION ($ENV_VERSION) nem egyezik a package verzióval ($VERSION)"
case "$API_URL" in
  https://*/api/mobile) ;;
  *) fail "VITE_API_BASE_URL publikus HTTPS /api/mobile végpont legyen" ;;
esac
pass "Mobil verzió és HTTPS API konfiguráció"

APP_ID=$(node --input-type=module - <<'NODE'
import config from './capacitor.config.js'
console.log(config.appId)
NODE
)
[ -n "$APP_ID" ] || fail "Capacitor appId hiányzik"
pass "Capacitor appId: $APP_ID"

SDK_ROOT=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}
[ -n "$SDK_ROOT" ] || fail "ANDROID_SDK_ROOT vagy ANDROID_HOME nincs beállítva"
[ -d "$SDK_ROOT" ] || fail "Android SDK könyvtár nem található: $SDK_ROOT"
[ -x "$SDK_ROOT/platform-tools/adb" ] || fail "adb nem található az Android SDK-ban"
BUILD_TOOLS=$(find "$SDK_ROOT/build-tools" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -V | tail -1 || true)
[ -n "$BUILD_TOOLS" ] || fail "Android build-tools nincs telepítve"
[ -x "$BUILD_TOOLS/apksigner" ] || fail "apksigner nem található: $BUILD_TOOLS/apksigner"
pass "Android SDK/build-tools: $BUILD_TOOLS"

GS=${FIREBASE_GOOGLE_SERVICES_JSON:-android/app/google-services.json}
[ -s "$GS" ] || fail "google-services.json hiányzik: $GS"
python3 - "$GS" "$APP_ID" "${MUNKALAP_FIREBASE_PROJECT_ID:-}" <<'PY'
import json, sys
path, app_id, expected_project = sys.argv[1:4]
try:
    data = json.load(open(path, encoding='utf-8'))
except Exception as exc:
    raise SystemExit(f'HIBA: hibás google-services.json: {exc}')
project = (data.get('project_info') or {}).get('project_id') or ''
packages = []
app_ids = []
for client in data.get('client') or []:
    info = client.get('client_info') or {}
    android = info.get('android_client_info') or {}
    if android.get('package_name'):
        packages.append(android['package_name'])
    if info.get('mobilesdk_app_id'):
        app_ids.append(info['mobilesdk_app_id'])
if app_id not in packages:
    raise SystemExit(f'HIBA: google-services.json package_name nem tartalmazza ezt: {app_id}; kapott={packages}')
if expected_project and project != expected_project:
    raise SystemExit(f'HIBA: Firebase project_id ({project}) != MUNKALAP_FIREBASE_PROJECT_ID ({expected_project})')
if not project:
    raise SystemExit('HIBA: Firebase project_id hiányzik')
if not app_ids:
    raise SystemExit('HIBA: mobilesdk_app_id hiányzik')
print(f'PASS: Firebase Android config project={project} package={app_id}')
PY

if [ -n "${MUNKALAP_KEYSTORE_PATH:-}" ]; then
  [ -f "$MUNKALAP_KEYSTORE_PATH" ] || fail "Keystore nem található: $MUNKALAP_KEYSTORE_PATH"
  for var in MUNKALAP_KEYSTORE_PASSWORD MUNKALAP_KEY_ALIAS MUNKALAP_KEY_PASSWORD; do
    eval "value=\${$var:-}"
    [ -n "$value" ] || fail "Signing változó hiányzik: $var"
  done
  keytool -list -keystore "$MUNKALAP_KEYSTORE_PATH" -storepass "$MUNKALAP_KEYSTORE_PASSWORD" -alias "$MUNKALAP_KEY_ALIAS" >/dev/null 2>&1 || fail "Keystore/alias/jelszó ellenőrzés sikertelen"
  FINGERPRINT=$(keytool -list -v -keystore "$MUNKALAP_KEYSTORE_PATH" -storepass "$MUNKALAP_KEYSTORE_PASSWORD" -alias "$MUNKALAP_KEY_ALIAS" 2>/dev/null | sed -n 's/^[[:space:]]*SHA256:[[:space:]]*//p' | head -1 | tr '[:lower:]' '[:upper:]')
  [ -n "$FINGERPRINT" ] || fail "Signing cert SHA-256 fingerprint nem olvasható"
  if [ -n "${MUNKALAP_EXPECTED_SIGNING_CERT_SHA256:-}" ]; then
    EXPECTED=$(printf '%s' "$MUNKALAP_EXPECTED_SIGNING_CERT_SHA256" | tr '[:lower:]' '[:upper:]')
    [ "$FINGERPRINT" = "$EXPECTED" ] || fail "Signing cert fingerprint eltér. kapott=$FINGERPRINT"
  fi
  pass "Release signing keystore: SHA256 $FINGERPRINT"
else
  echo "WARN: Signing keystore nincs betöltve; debug preflightként folytatódik." >&2
fi

if [ -d node_modules ]; then
  npx cap doctor android >/dev/null 2>&1 || fail "Capacitor doctor hibát jelzett"
  pass "Capacitor doctor"
else
  echo "WARN: node_modules nincs telepítve; Capacitor doctor kihagyva." >&2
fi

echo "Android release preflight PASS"
