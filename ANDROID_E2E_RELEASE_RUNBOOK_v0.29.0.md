# Munkalap v0.29.0 - Android/Firebase/VPS end-to-end release runbook

## Cel

Ez az eljaras a v0.29.0 release production elotti vegso acceptance folyamata. A cel nem pusztan egy APK/AAB eloallitasa, hanem annak bizonyitasa, hogy ugyanaz a release helyes production API-ra mutat, megfelelo Firebase projekthez tartozik, a vart kulccsal van alairva, valodi telefonra telepitheto, es a VPS -> FCM -> telefon push lanc mukodik.

## A. Firebase elo-feltetelek

1. Hozz letre vagy valaszd ki a production Firebase projektet.
2. Android app package: `hu.munkalap.technician`.
3. Toltsd le a production `google-services.json` fajlt egy biztonsagos buildgep-konyvtarba.
4. A szerveroldali push workerhez kulon service-account credentialt hasznalj a VPS secret taroloban.
5. A kliens `google-services.json` es a szerver service-account JSON ne legyen ugyanaz a fajl es ne keruljon a repositoryba.

## B. Android buildgep elo-feltetelek

Ellenorizd:

```bash
java -version
node --version
npm --version
$ANDROID_SDK_ROOT/platform-tools/adb version
```

Toltsd be a signing kornyezetet:

```bash
cd mobile
. "$HOME/.config/munkalap-android/signing.env"
export FIREBASE_GOOGLE_SERVICES_JSON=/secure/path/google-services.json
export MUNKALAP_FIREBASE_PROJECT_ID=my-production-project
export MUNKALAP_EXPECTED_SIGNING_CERT_SHA256='AA:BB:CC:...'
```

A `mobile/.env` production ertekei:

```text
VITE_API_BASE_URL=https://app.example.hu/api/mobile
VITE_APP_VERSION=0.29.0
```

## C. Android release acceptance

```bash
npm ci
npm run android:release:acceptance
```

Elvart eredmeny:

```text
Android release acceptance PASS
```

A `native-dist/` kimenetben legyen APK, AAB, SHA256SUMS es release-manifest.

Telefonos install/launch gate:

```bash
export MUNKALAP_INSTALL_SMOKE=true
npm run android:release:acceptance
```

Az acceptance hibaval alljon le, ha a Firebase project/package vagy signing cert eltér a varttol.

## D. VPS production deploy

A szerveren a v0.25+ production deployment alapelvei maradnak ervenyben. Deploy elott:

```bash
deploy/vps/preflight-production.sh
deploy/vps/deploy-production.sh
deploy/vps/acceptance-production.sh
```

Ellenorizd a `push-worker` futasat es a Firebase credentialt.

## E. Telefon regisztracio

1. Telepitsd a release APK-t teszttelefonra vagy Play internal testingbol az AAB buildet.
2. Jelentkezz be egy teszt technikus felhasznaloval.
3. Engedelyezd az Android notification permissiont.
4. Admin -> Felhasznalok -> Mobil eszkozok alatt ellenorizd, hogy az eszkoz `push_enabled=true`.
5. Jegyezd fel a belso mobil eszkoz ID-t; FCM token nem jelenik meg az Admin UI-ban.

## F. Valodi FCM smoke

Admin UI-bol hasznalhatod a `Teszt push` gombot, vagy VPS-en:

```bash
deploy/vps/push-smoke-test.sh <device_id>
```

Alternativan a teljes production acceptance reszekent `.env.production`:

```text
PUSH_SMOKE_DEVICE_ID=<device_id>
PUSH_SMOKE_WAIT_SECONDS=45
```

majd:

```bash
deploy/vps/acceptance-production.sh
```

Szerveroldali PASS utan KOTELEZO telefonon ellenorizni a tenyleges megjelenest.

## G. Valodi munkalap deep-link acceptance

1. Hozz letre vagy rendelj egy teszt munkalapot a technikushoz.
2. Ellenorizd, hogy az Android eszkoz push uzenetet kap.
3. Erintsd meg az ertesitest.
4. Ellenorizd, hogy a mobil app a megfelelo munkalap reszletet nyitja.
5. Modositsd a tervezett idopontot es ismeteld meg a push/deep-link tesztet.

## H. Alairas end-to-end acceptance

A teszttelefonon:

1. munkalap megnyitasa;
2. munka megkezdese;
3. szamlalo/material/foto rogzitese;
4. munkavegzes befejezese;
5. completion snapshot;
6. ugyfel neve es signature pad;
7. alairas es lezaras;
8. alairt PDF megnyitasa.

Weben ellenorizd, hogy az alairasi revision es PDF elerheto, a snapshot/PDF hash rogzitett, es utolagos munkalap-modositas nem irja at a korabbi evidence-et.

## I. Backup/restore gate

```bash
deploy/vps/run-backup-acceptance.sh
deploy/vps/offsite-check.sh
```

Kulon stage restore-nal ellenorizd az alairasi PNG/PDF es munkalap-foto evidence visszaallitasat. Push tokenek es transient push outbox nem allhatnak vissza.

## J. Release dontes

Production release csak akkor GO, ha:

- web security/production acceptance PASS;
- offsite backup es restore acceptance PASS;
- Android signed artifact acceptance PASS;
- valodi telefon install/launch PASS;
- valodi FCM push es work-order deep link PASS;
- teljes alairasi folyamat es PDF PASS;
- nincs secret a release ZIP-ben vagy artifact manifestben.

Barmely P0 hiba eseten NO-GO.
