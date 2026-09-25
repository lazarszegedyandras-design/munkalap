# Munkalap-Eszköz App v0.24.0 – Production Security Checklist

## Cél

A v0.24.0 **Cloud Security Foundation** kiadás az alkalmazáskódot készíti elő a későbbi publikus/VPS üzemre. Ez a verzió önmagában még **nem tekinthető internetre publikálható végállapotnak**: a külső TLS reverse proxy, DNS, VPS firewall, offsite backup, monitoring és production acceptance a következő infrastruktúra-fázis feladata.

## 1. Kötelező production konfiguráció

A publikus környezetben legalább az alábbi értékeket kell beállítani. A backend `ENVIRONMENT=production` esetén fail-closed módon megtagadja az indulást, ha a biztonsági minimumok nem teljesülnek.

```env
APP_VERSION=0.24.0
ENVIRONMENT=production
PUBLIC_BASE_URL=https://app.example.hu
CORS_ORIGINS=https://app.example.hu
SESSION_COOKIE_SECURE=true
PASSWORD_MIN_LENGTH=12
SESSION_IDLE_TIMEOUT_MINUTES=60
SESSION_ABSOLUTE_TIMEOUT_MINUTES=720
ADMIN_MFA_REQUIRED=true
DOCS_ENABLED=false
MALWARE_SCAN_ENABLED=true
MALWARE_SCAN_FAIL_CLOSED=true
```

Kötelező továbbá egyedi, legalább 32 karakteres véletlen érték:

- `SECRET_KEY` vagy `SECRET_KEY_FILE`
- `MFA_ENCRYPTION_KEY` vagy `MFA_ENCRYPTION_KEY_FILE`
- `BACKUP_AGENT_TOKEN` vagy `BACKUP_AGENT_TOKEN_FILE`
- nem alapértelmezett PostgreSQL jelszó

Tiszta production adatbázis esetén explicit bootstrap admin jelszó szükséges:

- `BOOTSTRAP_ADMIN_PASSWORD` vagy
- `BOOTSTRAP_ADMIN_PASSWORD_FILE`

## 2. Admin MFA

Productionben az Admin MFA kötelező.

Első sikeres jelszavas Admin belépéskor a rendszer TOTP-beállítást kér. A megjelenített titkos kulcsot authenticator alkalmazásban kell rögzíteni, majd 6 számjegyű kóddal megerősíteni.

A generált recovery kódokat egyszer kell biztonságos helyen elmenteni. A rendszer csak hash formában tárolja őket.

Szükséghelyzeti MFA-reset kizárólag szerverkonzolról:

```bash
cd /app
python -m app.reset_mfa --email user@example.com
```

A reset az adott felhasználó aktív sessionjeit is visszavonja.

## 3. Session és CSRF

A webes kliens nem tárol JWT-t `localStorage`-ban. A session token `HttpOnly` cookie-ban található.

Production ellenőrzések:

- `Secure` cookie kötelező;
- unsafe browser műveletekhez CSRF cookie/header pár szükséges;
- cross-site `Sec-Fetch-Site` kérések tiltva;
- megadott `Origin` csak explicit CORS origin lehet;
- logout visszavonja a szerveroldali sessiont;
- password reset/change és biztonságérzékeny usermódosítás session revoke-ot végez;
- logical/physical restore után a korábbi sessionök nem maradhatnak érvényesek.

## 4. Forwarded header / kliens IP

Az Uvicorn nem fogad el automatikusan tetszőleges `X-Forwarded-*` fejléceket.

`TRUSTED_PROXY_CIDRS` csak azokat a hálózatokat tartalmazza, ahonnan a saját reverse proxy ténylegesen csatlakozhat a backendhez.

Publikus klienshálózatot vagy `0.0.0.0/0` értéket ne adj meg trusted proxyként.

## 5. Fájlfeltöltés és ClamAV

Productionben ClamAV kötelező, fail-closed módban.

A compose security profillal indítandó:

```bash
docker compose --profile security up -d --build
```

A `/api/health/ready` csak akkor adjon sikeres választ, ha az engedélyezett malware scanner elérhető.

A feltöltési réteg ellenőrzi:

- méretlimitet;
- allowlist kiterjesztést/MIME típust;
- fájlszignatúrát;
- OOXML struktúrát;
- ZIP path traversalt és symlinket;
- kibontott méretet;
- gyanús tömörítési arányt;
- ClamAV eredményt.

## 6. Hálózat

A v0.24.0 Compose alapkonfigurációjában:

- PostgreSQL: csak belső Docker hálózat;
- FastAPI: csak belső Docker hálózat;
- ClamAV: csak belső security hálózat;
- backup-agent: nincs publikált port.

A fejlesztői DB/backend portok kizárólag a `docker-compose.dev.yml` override-ban, `127.0.0.1` címre jelennek meg.

**Publikus VPS-en ne a frontend 3000-es portját tedd közvetlenül internetre.** A következő fázisban TLS reverse proxy mögé kell helyezni, és a belső frontend portot host-loopbackhez vagy privát container hálózathoz kell kötni.

## 7. HTTP security headerek

A frontend és az API többek között az alábbi kontrollokat adja:

- `Strict-Transport-Security`
- `Content-Security-Policy`
- `X-Content-Type-Options: nosniff`
- frame/clickjacking védelem
- `Referrer-Policy`
- `Permissions-Policy`

Production TLS ellenőrzést a v0.25 infrastruktúra-gate-ben kell tényleges külső HTTPS kapcsolaton elvégezni.

## 8. Docker hardening

A backend/frontend:

- read-only root filesystemet használ;
- non-root alkalmazásfolyamatként fut;
- `no-new-privileges` beállítást kap;
- a backend capability-k minimumra vannak csökkentve;
- írható területek explicit volume/tmpfs területek.

A backend entrypoint rootként kizárólag a meglévő runtime volume ownership kompatibilitást rendezi, utána `gosu app` segítségével non-root folyamatra vált.

### Ismert privileged kivétel

A `backup-agent` jelenleg a Docker socketet mountolja a backup/restore orchestráció miatt. Ez host-control képességet jelent. Nincs publikált portja és külön token védi, de **a v0.25 infrastruktúra-fázisban ezt külön hardening/rearchitecture pontként kell kezelni**.

## 9. Backup és restore

A v0.24 logical backup formátuma: **13**.

Biztonsági változás:

- `auth_sessions` és `security_rate_limits` ephemerális táblák;
- logical restore nem állítja vissza őket;
- physical restore után is explicit törlés történik;
- restore után új autentikáció szükséges.

Publikus szolgáltatás előtt továbbra is kötelező:

- VPS-en kívüli offsite backup;
- titkosítás;
- MASTER + incremental policy;
- tényleges restore acceptance.

## 10. Health endpointok

```text
GET /api/health/live
GET /api/health/ready
```

`live`: process elérhetőség.

`ready`: DB, runtime és engedélyezett malware scanner readiness.

Productionben a readiness belső hiba részleteit nem adja vissza a kliensnek.

## 11. Production deploy előtti kötelező gate

A publikus DNS átállítás előtt minden pont legyen PASS:

- [ ] erős production secrets
- [ ] nem alapértelmezett DB-jelszó
- [ ] HTTPS publikus URL
- [ ] Secure session cookie
- [ ] Admin MFA beállítva és tesztelve
- [ ] explicit production CORS origin
- [ ] docs kikapcsolva
- [ ] ClamAV fut és fail-closed
- [ ] DB/backend nem publikus
- [ ] trusted proxy CIDR pontosan konfigurálva
- [ ] TLS reverse proxy kész
- [ ] VPS firewall kész
- [ ] security headerek külső HTTPS-en ellenőrizve
- [ ] login rate limiting ellenőrizve
- [ ] CSRF ellenőrizve
- [ ] fájl upload malware teszt ellenőrizve
- [ ] Alembic egyetlen head: `0029_cloud_security`
- [ ] backend teljes teszt valós production dependency-készlettel PASS
- [ ] frontend `npm ci && npm run build` PASS
- [ ] Docker Compose build/smoke PASS
- [ ] MASTER backup PASS
- [ ] restore acceptance PASS
- [ ] offsite backup PASS
- [ ] monitoring/alerting kész

**Ha bármely P0 gate hiányzik, a rendszert ne publikáld internetre.**
