# Android build es alairas - v0.29.0

Ez a dokumentum a Munkalap Technikus Android kliens reprodukalhato debug/release buildjet, Firebase konfiguraciojat es release acceptance folyamatait irja le. A release gate fail-closed: hianyzo SDK, hibas Firebase project/package, ervenytelen alairas vagy eltero signing cert eseten a kiadas leall.

## 1. Kovetelmenyek

- Node.js + npm
- JDK 21 vagy kompatibilis JDK, `keytool` es `jarsigner`
- Android SDK, `platform-tools/adb`, build-tools + `apksigner`
- valodi Firebase Android app `hu.munkalap.technician` package nevvel
- `google-services.json` biztonsagos, repositoryn kivuli helyen
- release upload keystore es jelszavak repositoryn kivul
- production API: `https://<domain>/api/mobile`

## 2. Mobil environment

```bash
cd mobile
cp .env.example .env
```

A `.env` legalabb ezt tartalmazza:

```text
VITE_API_BASE_URL=https://app.example.hu/api/mobile
VITE_APP_VERSION=0.29.0
```

A release preflight nem enged HTTP API URL-t.

## 3. Firebase Android konfiguracio

A Firebase Console Android alkalmazasanak package neve:

```text
hu.munkalap.technician
```

A `google-services.json` ne keruljon Gitbe, Docker build contextbe vagy release ZIP-be. Build elott:

```bash
export FIREBASE_GOOGLE_SERVICES_JSON=/secure/path/google-services.json
export MUNKALAP_FIREBASE_PROJECT_ID=my-firebase-project
```

A preflight ellenorzi, hogy a JSON-ban szereplo Android package es Firebase project id egyezik a release elvarassal.

## 4. Upload keystore

Egyszeri generalas:

```bash
./scripts/generate-release-keystore.sh
```

Ez alapertelmezetten kulso konfiguracios helyre kesziti a kulcsot es a `signing.env` fajlt. A keystore-t es a hozza tartozo jelszavakat kulon, titkositott backupban kell megorizni.

Release shellben:

```bash
. "$HOME/.config/munkalap-android/signing.env"
```

A signing cert SHA-256 fingerprintje kulon release-elvaraskent rogzitendo:

```bash
export MUNKALAP_EXPECTED_SIGNING_CERT_SHA256='AA:BB:CC:...'
```

## 5. Release preflight

```bash
npm run android:preflight
```

Ellenorzi:

- app/package verzio egyezest;
- HTTPS `/api/mobile` URL-t;
- Capacitor appId-t;
- Android SDK/adb/apksigner jelenletet;
- Firebase package/project egyezest;
- signing keystore/alias/jelszo ervenyesseget;
- opcionlisan a signing cert SHA-256 fingerprintet;
- telepitett node_modules mellett a Capacitor doctor eredmenyet.

## 6. Debug APK

```bash
npm run android:build:debug
```

## 7. Alairt release APK

```bash
. "$HOME/.config/munkalap-android/signing.env"
export FIREBASE_GOOGLE_SERVICES_JSON=/secure/path/google-services.json
export MUNKALAP_FIREBASE_PROJECT_ID=my-firebase-project
export MUNKALAP_EXPECTED_SIGNING_CERT_SHA256='AA:BB:CC:...'
npm run android:build:release
```

## 8. Google Play AAB

```bash
npm run android:bundle:release
```

Ha a `BUNDLETOOL_JAR` valtozo meg van adva, az artifact gate `bundletool validate` ellenorzest is futtat.

## 9. Teljes release acceptance

A javasolt production build parancs:

```bash
npm run android:release:acceptance
```

Sorrend:

1. release preflight;
2. signed APK build;
3. signed AAB build;
4. SHA-256 manifest ellenorzes;
5. APK digitalis alairas + v2 vagy ujabb signature scheme ellenorzes;
6. AAB JAR-signature ellenorzes;
7. opcionlis bundletool validation;
8. secretmentes `native-dist/release-manifest.json`;
9. opcionlis valodi eszkoz install/launch smoke.

Valodi telefonos smoke teszthez:

```bash
export MUNKALAP_INSTALL_SMOKE=true
npm run android:release:acceptance
```

Pontosan egy `adb` allapotu Android eszkoz legyen csatlakoztatva.

## 10. Kimenetek

A `mobile/native-dist/` konyvtarban jelennek meg:

- `Munkalap-Technikus-0.29.0-release.apk`
- `Munkalap-Technikus-0.29.0-release.aab`
- `SHA256SUMS.txt`
- `release-manifest.json`

A `native-dist/` build artifact, nem forraskod; nem kerul a projekt release ZIP-be.

## 11. Production push acceptance

Az app telepitese es legalabb egyszeri bejelentkezes utan az Admin -> Felhasznalok -> Mobil eszkozok nezetben olvashato a mobil eszkoz ID. A VPS-en:

```bash
deploy/vps/push-smoke-test.sh <device_id>
```

A szerveroldali PASS azt igazolja, hogy az FCM provider elfogadta a push uzenetet. Ezutan a telefonon manualisan is ellenorizni kell:

- megjelenik-e az ertesites;
- erintesre megnyilik-e az Android app;
- a deep link a megfelelo munkalapot nyitja-e meg.

## 12. Titkok es tiltott artifactok

Soha ne commitold vagy add at a forras ZIP-ben:

- `google-services.json`;
- Firebase service-account JSON;
- Android upload/release keystore;
- `signing.env`;
- keystore jelszavak;
- `mobile/.env`;
- `mobile/native-dist/`;
- generalt Android build artifactok.
