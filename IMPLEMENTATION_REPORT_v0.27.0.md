# IMPLEMENTATION REPORT v0.27.0

## Cél

Android/Capacitor technikusi MVP a v0.26 mobil API-ra, kiegészítve munkalap-fotó bizonyítékréteggel.

## Elkészült

### Mobil kliens
- külön `mobile/` React + Capacitor 8 projekt;
- mobil login és MFA challenge;
- natív refresh-token tárolás SecureStorage/Android Keystore használatával;
- access token memória-only;
- rotálódó refresh és automatikus egyszeri 401 retry;
- perzisztens, nem titkos eszközazonosító Preferences-ben;
- „Mai munkáim” lista;
- munkalap részletek, közvetlen telefonhívás;
- munkakezdés;
- számlálóállás rögzítés;
- anyagkeresés és felhasználás;
- munkavégzés lezárási űrlap;
- kamera/fotó kategóriával és megjegyzéssel;
- ügyfél signature pad + elfogadó nyilatkozat;
- aláírt PDF natív cache-be mentése és rendszer Share/Open sheet;
- böngészős preview esetén auth token nem kerül localStorage-ba.

### Backend fotóbizonyíték
- `WorkOrderPhoto` modell és `0031_mobile_photos` migráció;
- JPEG/PNG upload, méret/magic-byte/pixelszám ellenőrzés;
- ClamAV scan a nyers és újrakódolt képre;
- Pillow alapú EXIF/GPS eltávolítás és JPEG normalizálás;
- SHA-256 + méret + felbontás bizonyítéki metaadat;
- technikusi hozzáférés és lezárás utáni módosítási tiltás;
- fénykép hash-ek a completion snapshotban és az aláírt PDF bizonyítéki részében;
- logikai backup/restore támogatás a `work_order_photos` runtime fájlokra;
- backup formátum 15.

### Mobil konfiguráció
- `GET /api/mobile/config` az elfogadó szöveg, verzió, fotólimit, kategóriák és üzleti időzóna biztonságos lekérésére.

## Biztonsági döntések
- A mobil app nem kap adatbázis-hozzáférést.
- Production API HTTPS kötelező.
- Production APK nem távoli WebView-URL-t tölt be, hanem bundolt web asseteket használ.
- Access token nem perzisztált.
- Refresh token csak natív SecureStorage-ban perzisztált; web preview memória-only.
- A szerver a telefon által készített kép metaadataiban nem bízik és újrakódolja azt.
- Az aláírás és a munkalap-fotók a pontos immutable munkalap revisionhöz kötődnek.

## Verifikációs korlátok
- A futtatókörnyezetben nincs hálózati npm telepítés és nincs Android SDK/Gradle toolchain, ezért tényleges `npm install`, Vite/Capacitor native sync és APK/AAB build itt nem igazolható.
- A Python környezetben nincs production `python-jose/passlib/bcrypt/psycopg2`; backend API tesztekhez kizárólag `/mnt/data` alatti, release-en kívüli kompatibilitási shim használható. Ezek nem kerülnek a ZIP-be.
- Docker Engine ebben a környezetben nem elérhető; container acceptance továbbra is a VPS gate része.

## Verification eredmény

- Backend API regresszió: **106/106 PASS** két, 53 tesztes futásban; a v0.27 célzott mobil/config/fotó tesztek külön is PASS.
- Fotó backup + fizikai restore regresszió: PASS.
- Backup-agent/release guard: **48/48 PASS**.
- Meglévő web frontend regresszió: **31/31 PASS**.
- Mobil saját Node tesztek: **5/5 PASS**.
- Mobil JS/JSX TypeScript-parser ellenőrzés: **16 fájl, 0 syntax error**.
- Python compileall: PASS.
- VPS/mobile shell syntax: PASS.
- Compose YAML parse: PASS.
- Tiszta Alembic upgrade: PASS; egyetlen head: `0031_mobile_photos`.
- Offline `npm install`: nem futtatható, mert a szükséges Capacitor/SecureStorage csomagok nincsenek a helyi npm cache-ben (`ENOTCACHED`). Emiatt Android native sync/Gradle APK build ebben a környezetben nem igazolható.
