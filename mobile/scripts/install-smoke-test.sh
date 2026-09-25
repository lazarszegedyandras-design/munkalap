#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
fail() { echo "HIBA: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }
command -v node >/dev/null 2>&1 || fail "Node.js szükséges"
SDK_ROOT=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}
[ -n "$SDK_ROOT" ] || fail "ANDROID_SDK_ROOT vagy ANDROID_HOME szükséges"
ADB="$SDK_ROOT/platform-tools/adb"
[ -x "$ADB" ] || fail "adb nem található"
VERSION=$(node -p "require('./package.json').version")
APP_ID=$(node --input-type=module - <<'NODE'
import config from './capacitor.config.js'
console.log(config.appId)
NODE
)
APK=${1:-"native-dist/Munkalap-Technikus-${VERSION}-release.apk"}
[ -s "$APK" ] || fail "APK nem található: $APK"
DEVICE_COUNT=$($ADB devices | awk 'NR>1 && $2=="device" {n++} END {print n+0}')
[ "$DEVICE_COUNT" -eq 1 ] || fail "Pontosan 1 online adb eszköz szükséges; kapott=$DEVICE_COUNT"
$ADB install -r "$APK" >/dev/null || fail "APK telepítés sikertelen"
PKG=$($ADB shell dumpsys package "$APP_ID" 2>/dev/null || true)
printf '%s\n' "$PKG" | grep -q "versionName=$VERSION" || fail "Telepített versionName nem $VERSION"
$ADB shell monkey -p "$APP_ID" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || fail "App launch sikertelen"
sleep 2
$ADB shell pidof "$APP_ID" >/dev/null 2>&1 || fail "Az app nem fut a smoke launch után"
pass "Telepítés és launch: $APP_ID v$VERSION"
echo "Android device smoke test PASS"
