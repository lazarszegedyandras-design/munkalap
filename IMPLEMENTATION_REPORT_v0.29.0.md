# IMPLEMENTATION REPORT - v0.29.0

## Scope

A v0.29.0 az elozo Cloud Security, public VPS, mobile API, Android client es FCM push retegre epulo end-to-end release-readiness fazis. Uj uzleti adatmodell nem kerult be, ezert nincs uj Alembic migracio.

## Implementalt funkciok

### Admin mobile operations

- Regisztralt mobil eszkozok listaja felhasznalonkent.
- Push aktiv/inaktiv statusz es token frissitesi idopont FCM token visszaadasa nelkul.
- Legutobbi push delivery statusz/attempt/error metaadat.
- Admin teszt push queue endpoint.
- Meglevo tavoli eszkoz-visszavonas UI-bol is elerheto.

### FCM provider smoke

- `backend/app/push_smoke_test.py`: valodi outbox + push-worker provider smoke.
- `deploy/vps/push-smoke-test.sh`: production wrapper.
- `PUSH_SMOKE_DEVICE_ID` es `PUSH_SMOKE_WAIT_SECONDS` production acceptance konfiguracio.
- Production status push device/outbox health szamlalokkal, token megjelenites nelkul.

### Android release gate

- `mobile/scripts/preflight-release.sh`
- `mobile/scripts/verify-release-artifacts.sh`
- `mobile/scripts/install-smoke-test.sh`
- `mobile/scripts/generate-release-manifest.sh`
- `mobile/scripts/release-acceptance.sh`
- `.release.env.example` non-secret expected release ertekekhez.

A gate ellenorzi az API URL-t, Android SDK-t, Firebase project/package egyezest, signing keystore-t/cert fingerprintet, APK alairast, AAB alairast, artifact SHA-256-ot es opcionlisan valodi eszkoz install/launch tesztet.

### Version tooling

A `scripts/set_version.py` most mar a mobil package/env/signing fallback es production Compose/preflight verzioit is szinkronban tartja.

## Adatbazis

Nincs uj migracio.

Aktualis single head:

```text
0032_push_notifications
```

## Verification

- Backend API: 115/115 PASS.
- Backend API + backup-permission + migration-revision tests: 119/119 PASS.
- Full backup-agent test suite: 51/51 PASS.
- Release/configuration guards: 29/29 PASS.
- Web frontend: 32/32 PASS.
- Mobile tests: 7/7 PASS.
- Clean Alembic upgrade: PASS.
- Single Alembic head: `0032_push_notifications`.
- Python compile / shell syntax: PASS.
- Version sync: PASS.
- Android release preflight pozitiv strukturalt synthetic SDK/Firebase konfiguracioval: PASS.
- Firebase project id mismatch negative gate: helyesen FAIL exit 1.

A backend API tesztek a futtatokornyezetbol hianyzo `python-jose/passlib` miatt release-en kivuli compatibility shimekkel futottak. Ezek a release-be nem kerulnek, production dependency nem lett shimmel helyettesitve.

## Korlatozasok

A jelenlegi buildkornyezetben nincs teljes Android SDK/npm dependency keszlet, valodi production Firebase projekt/service account, production VPS es valodi regisztralt Android keszulek. Emiatt itt nem allithato hitelesen, hogy:

- valodi signed production APK/AAB artifact elkészült;
- valodi Firebase provider uzenet keszulekre megerkezett;
- valodi Android install/launch smoke lefutott;
- publikus VPS end-to-end acceptance lefutott.

Ezekhez a v0.29 release fail-closed runbookot es automatizalt gate-eket tartalmaz.

## Release decision

Kod/release-readiness: PASS.

Production GO csak a `ANDROID_E2E_RELEASE_RUNBOOK_v0.29.0.md` es `SECURITY_RELEASE_CHECKLIST_v0.29.0.md` valodi kornyezetben torteno P0 teljesitese utan.
