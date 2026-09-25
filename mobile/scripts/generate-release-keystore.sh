#!/bin/sh
set -eu
command -v keytool >/dev/null 2>&1 || { echo "HIBA: keytool/JDK szükséges." >&2; exit 1; }
OUT_DIR=${1:-"$HOME/.config/munkalap-android"}
mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
KEYSTORE="$OUT_DIR/munkalap-upload.p12"
ENV_FILE="$OUT_DIR/signing.env"
[ ! -e "$KEYSTORE" ] || { echo "HIBA: A keystore már létezik: $KEYSTORE" >&2; exit 1; }
PASSWORD=${MUNKALAP_KEYSTORE_PASSWORD:-$(openssl rand -base64 36 | tr -d '\n/=+' | cut -c1-32)}
ALIAS=${MUNKALAP_KEY_ALIAS:-munkalap-upload}
DNAME=${MUNKALAP_KEY_DNAME:-"CN=Munkalap Android Upload,O=Luna IT,C=HU"}
umask 077
keytool -genkeypair -v -storetype PKCS12 -keystore "$KEYSTORE" -storepass "$PASSWORD" -keypass "$PASSWORD" -alias "$ALIAS" -keyalg RSA -keysize 4096 -validity 10000 -dname "$DNAME"
cat > "$ENV_FILE" <<EOF
export MUNKALAP_KEYSTORE_PATH='$KEYSTORE'
export MUNKALAP_KEYSTORE_PASSWORD='$PASSWORD'
export MUNKALAP_KEY_ALIAS='$ALIAS'
export MUNKALAP_KEY_PASSWORD='$PASSWORD'
EOF
chmod 600 "$KEYSTORE" "$ENV_FILE"
echo "Upload keystore elkészült: $KEYSTORE"
echo "Signing env: $ENV_FILE"
echo "Betöltés: . '$ENV_FILE'"
