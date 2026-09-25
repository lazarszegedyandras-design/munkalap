# Munkalap-Eszköz App v0.24.0 – Implementációs riport

## Scope

Kiinduló verzió: `0.23.0`

Cél: **Cloud Security Foundation** – a belső hálózati alkalmazáskód felkészítése egy későbbi biztonságos publikus/VPS üzemre.

Nem része ennek a release-nek a tényleges internetes publikálás, a külső TLS reverse proxy/DNS/VPS firewall, az offsite backup infrastruktúra és a külső monitoring. Ezek a következő fázis production-infrastruktúra feladatai.

## Fő változások

### 1. Webes autentikáció és session

- A webes JWT kikerült a `localStorage`-ból.
- Login JSON nem ad vissza JavaScript által olvasható access tokent.
- A browser session `HttpOnly` cookie-t használ.
- Új szerveroldali `auth_sessions` registry készült.
- Idle és absolute session expiry támogatott.
- Logout, jelszóváltoztatás, admin reset és biztonságérzékeny usermódosítás session revoke-ot végez.
- Backend Bearer-token támogatás megmaradt a későbbi dedikált mobil-auth flow számára.

### 2. CSRF / browser origin védelem

- Cookie-auth unsafe kéréseknél double-submit CSRF token szükséges.
- `Sec-Fetch-Site: cross-site` unsafe kérések tiltva.
- Megadott `Origin` unsafe kérésnél csak explicit engedélyezett origin lehet.
- A login/MFA endpointokra is érvényes cross-site/origin ellenőrzés.
- Production CORS explicit HTTPS originre szűkíthető, wildcard nincs.

### 3. MFA

- TOTP MFA került be.
- Admin MFA productionben kötelező konfigurációs gate.
- Első belépéses self-enrollment.
- Egyszer használható recovery kódok.
- Recovery kódok csak hash formában tárolódnak.
- TOTP replay ellen `mfa_last_counter` védelem.
- MFA titok Fernet-titkosítással tárolódik, külön MFA encryption key alapján.
- Konzolos `reset_mfa.py` recovery eszköz készült.

### 4. Login brute-force védelem

- Adatbázis-alapú user- és IP-bucket throttling.
- Több backend worker mellett is közös állapot.
- Retry-After válasz 429 esetén.
- Ismeretlen usernél dummy password verification csökkenti az account-enumeration timing eltérést.
- Sikertelen loginok security auditba kerülnek.

### 5. HTTP / reverse proxy hardening

- API security headerek.
- Frontend Nginx security headerek.
- CSP/HSTS/nosniff/frame/referrer/permissions kontrollok.
- Uvicorn `--forwarded-allow-ips="*"` megszüntetve.
- Kliens IP forwarded headerből csak konfigurált trusted proxy CIDR esetén fogadható el.
- `/api/health/live` és `/api/health/ready` endpointok.

### 6. Upload hardening

- Közös XLSX content validation.
- ZIP path traversal, backslash/colon és symlink tiltás.
- ZIP file-count, total uncompressed size és compression-ratio limitek.
- Archive/procurement/contract/import/restore feltöltések malware scan integrációt kaptak.
- ClamAV INSTREAM provider készült.
- Production startup ClamAV + fail-closed konfigurációt követel.

### 7. Docker / hálózat

- PostgreSQL és FastAPI alap Compose-ból nem publikál host portot.
- Fejlesztői portok külön `docker-compose.dev.yml` override-ban, localhoston érhetők el.
- Backend read-only filesystem, tmpfs, capability drop és `no-new-privileges`.
- Backend alkalmazás non-root userként fut; entrypoint kompatibilisen rendezi a korábbi runtime volume ownershipot.
- Frontend Nginx non-root userként fut read-only filesystemmel.
- ClamAV külön internal `security_net` hálózatot kapott.
- `backup-agent` továbbra is Docker socketet használ; ez dokumentált privileged kivétel és későbbi hardening pont.

### 8. Production fail-closed konfiguráció

`ENVIRONMENT=production` indulás blokkolódik többek között az alábbiaknál:

- rövid/alapértelmezett `SECRET_KEY`;
- rövid/alapértelmezett backup token;
- alapértelmezett DB-jelszó;
- nem Secure cookie;
- 12 karakternél rövidebb password minimum;
- kikapcsolt Admin MFA;
- hiányzó/külön nem megfelelő MFA encryption key;
- nem HTTPS public URL;
- hiányzó vagy unsafe CORS origin;
- túl laza session timeout;
- kikapcsolt vagy fail-open malware scan;
- bekapcsolt API docs.

### 9. Backup/restore security

- Logical backup formátum `12 -> 13`.
- `auth_sessions` és `security_rate_limits` ephemerális adatok, nem kerülnek vissza logical restore-ból.
- Physical restore után explicit session/rate-limit törlés történik.
- Restore után régi sessionnel történő hozzáférés 401-et ad; új autentikáció szükséges.
- Backup ZIP feldolgozás további path/symlink/size/compression védelmet kapott.

### 10. Adatbázis-migráció

Új head:

```text
0029_cloud_security
```

Új struktúrák:

- `users` MFA mezők;
- `auth_sessions`;
- `security_rate_limits`.

## Ellenőrzési eredmények

### Sikeres

- Alembic clean upgrade: `0001_initial -> ... -> 0029_cloud_security (head)` – PASS.
- Egyetlen Alembic head: `0029_cloud_security` – PASS.
- Release/configuration + migration + backup permission tesztek: **23/23 PASS**.
- Frontend regressziós tesztek: **31/31 PASS**.
- Frontend JS/JSX parser ellenőrzés: **50 fájl / 0 syntax error**.
- Python `compileall`: PASS.
- Verziószinkron `scripts/set_version.py --check`: PASS.
- Backend alkalmazáslogikai API-suite két részben: **60/60 + 39/39 = 99/99 PASS**, tesztcélú külső shim-ekkel.

### Fontos tesztkorlát

A jelenlegi ChatGPT futtatókörnyezetben a projekt által rögzített valódi `python-jose`, `passlib/bcrypt` és `psycopg2` csomagok nem voltak telepítve, és a környezetből nem volt hálózati pip letöltés. Emiatt a 99 API-teszt futtatásához **kizárólag a release könyvtáron kívüli teszt shim-eket** használtunk a JWT/password/DB-driver importok pótlására.

Ez az alkalmazáslogika regresszióját erősen ellenőrzi, de **nem helyettesíti** a valódi requirements-szel és PostgreSQL-lel végzett Docker acceptance-et.

A release ZIP nem tartalmazza a shim-eket.

### Frontend build korlát

A production Vite build nem volt hitelesen futtatható, mert a lokális `node_modules` hiányzott és az offline npm cache nem tartalmazta az összes lockfile dependency tarballt. A frontend saját Node tesztjei és a teljes JS/JSX syntax parse sikeresek.

## Kötelező következő production gate

Publikus elérés előtt saját Docker környezetben:

```bash
docker compose --profile security build --no-cache
docker compose --profile security up -d
```

majd legalább:

```bash
docker compose exec -T backend alembic heads
docker compose exec -T backend alembic current
docker compose exec -T backend pytest -q
```

és frontend production build/smoke, MASTER backup + restore acceptance.

A részletes publikus kihelyezési gate: `SECURITY_PRODUCTION_CHECKLIST_v0.24.0.md`.

## Release döntés

A v0.24.0 **alkalmazáskód-szintű első fázis elkészült**, de **nem jelenti azt, hogy a szolgáltatás most már közvetlenül internetre nyitható**. A következő fázisnak a VPS/TLS/firewall/offsite backup/monitoring és valós Docker acceptance kialakítását kell lezárnia.
