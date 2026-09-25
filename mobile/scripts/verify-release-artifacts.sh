#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

fail() { echo "HIBA: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }
command -v node >/dev/null 2>&1 || fail "Node.js szükséges"
command -v keytool >/dev/null 2>&1 || fail "keytool szükséges"
command -v jarsigner >/dev/null 2>&1 || fail "jarsigner szükséges"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum szükséges"

VERSION=$(node -p "require('./package.json').version")
APP_ID=$(node --input-type=module - <<'NODE'
import config from './capacitor.config.js'
console.log(config.appId)
NODE
)
DIST=${MUNKALAP_NATIVE_DIST:-native-dist}
[ -d "$DIST" ] || fail "Artifact könyvtár nem található: $DIST"
[ -s "$DIST/SHA256SUMS.txt" ] || fail "SHA256SUMS.txt hiányzik"
(cd "$DIST" && sha256sum -c SHA256SUMS.txt)
pass "Artifact SHA-256 manifest"

SDK_ROOT=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}
[ -n "$SDK_ROOT" ] || fail "ANDROID_SDK_ROOT vagy ANDROID_HOME szükséges"
BUILD_TOOLS=$(find "$SDK_ROOT/build-tools" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -V | tail -1 || true)
[ -n "$BUILD_TOOLS" ] || fail "Android build-tools nem található"
APKSIGNER="$BUILD_TOOLS/apksigner"
[ -x "$APKSIGNER" ] || fail "apksigner nem található"

APK="$DIST/Munkalap-Technikus-${VERSION}-release.apk"
AAB="$DIST/Munkalap-Technikus-${VERSION}-release.aab"
FOUND=0
if [ -s "$APK" ]; then
  FOUND=1
  OUT=$($APKSIGNER verify --verbose --print-certs "$APK" 2>&1) || { printf '%s\n' "$OUT" >&2; fail "APK signature verification"; }
  printf '%s\n' "$OUT" | grep -q 'Verified using v2 scheme (APK Signature Scheme v2): true' || fail "APK nincs v2 vagy újabb aláírással hitelesítve"
  CERT=$(printf '%s\n' "$OUT" | sed -n 's/^Signer #1 certificate SHA-256 digest: //p' | head -1 | sed 's/../&:/g;s/:$//' | tr '[:lower:]' '[:upper:]')
  if [ -n "${MUNKALAP_EXPECTED_SIGNING_CERT_SHA256:-}" ]; then
    EXPECTED=$(printf '%s' "$MUNKALAP_EXPECTED_SIGNING_CERT_SHA256" | tr '[:lower:]' '[:upper:]')
    [ "$CERT" = "$EXPECTED" ] || fail "APK signing cert eltér. kapott=$CERT"
  fi
  pass "Signed APK: $APK cert=$CERT"

  APKANALYZER=$(find "$SDK_ROOT" -type f -path '*/cmdline-tools/*/bin/apkanalyzer' -perm -u+x 2>/dev/null | sort | tail -1 || true)
  if [ -n "$APKANALYZER" ]; then
    PKG=$($APKANALYZER manifest application-id "$APK" 2>/dev/null || true)
    VER=$($APKANALYZER manifest version-name "$APK" 2>/dev/null || true)
    [ -z "$PKG" ] || [ "$PKG" = "$APP_ID" ] || fail "APK package id eltér: $PKG"
    [ -z "$VER" ] || [ "$VER" = "$VERSION" ] || fail "APK versionName eltér: $VER"
    pass "APK manifest package/version"
  fi
fi

if [ -s "$AAB" ]; then
  FOUND=1
  jarsigner -verify -strict "$AAB" >/dev/null 2>&1 || fail "AAB JAR signature verification"
  pass "Signed AAB: $AAB"
  if [ -n "${BUNDLETOOL_JAR:-}" ]; then
    [ -s "$BUNDLETOOL_JAR" ] || fail "BUNDLETOOL_JAR nem található: $BUNDLETOOL_JAR"
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT HUP INT TERM
    java -jar "$BUNDLETOOL_JAR" validate --bundle="$AAB" >/dev/null || fail "bundletool validate"
    pass "bundletool AAB validation"
  fi
fi

[ "$FOUND" -eq 1 ] || fail "Nincs release APK vagy AAB a $DIST könyvtárban"
echo "Android release artifact verification PASS"
