# SECURITY ANDROID CHECKLIST v0.27.0

## Release gate

- [ ] A `VITE_API_BASE_URL` kizárólag publikus `https://` URL.
- [ ] Production Android build nem használ `server.url` távoli webapp-betöltést; a web assetek az APK/AAB részei.
- [ ] Refresh token csak Android Keystore által védett SecureStorage-ban perzisztálható.
- [ ] Access token csak memóriában él; böngészős preview nem perzisztál credentialt.
- [ ] Android cleartext HTTP tiltott.
- [ ] Release build debug tiltott és release signing key külön, titkosított CI/keystore tárban van.
- [ ] Elveszett eszköz Adminból visszavonható; revokált eszköz access + refresh tokenje használhatatlan.
- [ ] Kameraengedély csak explicit felhasználói műveletre kérhető.
- [ ] A szerver a feltöltött fényképet újrakódolja, EXIF/GPS metaadatot eltávolítja, méretet/pixelszámot validál és malware-scan alá vonja.
- [ ] Fényképek SHA-256 azonosítóval bekerülnek az immutable completion snapshotba.
- [ ] Aláírás előtt a pontos elfogadó nyilatkozat megjelenik.
- [ ] Üres aláírás kliens- és szerveroldalon blokkolt.
- [ ] Aláírt PDF hitelesített mobil API-n keresztül kérhető le.
- [ ] Mobil app log nem tartalmaz jelszót, access/refresh tokent, aláírásképet vagy ügyféladat dumpot.
- [ ] Android backup policy és screenshot policy release előtt natív projektben ellenőrzött.
- [ ] Dependency audit és Android lint/Gradle release build CI-ben PASS.
- [ ] OWASP MASVS STORAGE/AUTH/NETWORK/PLATFORM alapkontrollok kézi acceptance-je dokumentált.

## Native build acceptance

A forráscsomag nem tekinthető Play-ready release-nek addig, amíg egy hálózatos Android build környezetben legalább az alábbiak nem futottak le:

```bash
cd mobile
cp .env.example .env
# VITE_API_BASE_URL beállítása
./scripts/bootstrap-android.sh
npm test
npm run build
npx cap sync android
cd android
./gradlew lint
./gradlew assembleRelease
```

A release APK/AAB aláírása és Play Console feltöltése külön üzemeltetési lépés.
