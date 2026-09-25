# v0.31.0 – Security Step 2 / VPS production gate

A Step 1 teljes izolált release acceptance után a v0.31.0 bevezeti a fail-closed VPS production gate-et: aktuális CVE/secret/misconfiguration scan, host hardening, edge/TLS/rate-limit acceptance, audit-chain ellenőrzés, valamint offsite és fizikai restore drill. Részletesen: [SECURITY_STEP2_VPS_GATE_v0.31.0.md](SECURITY_STEP2_VPS_GATE_v0.31.0.md).

**A v0.31.0 forrásmódosítás miatt új `test-release.ps1 -Suite all` PASS szükséges; a v0.30.1 image lock nem vihető tovább.**

---

# v0.30.1 – security 1. lépés

A kiadási tesztfolyamat most saját tesztprojektet használ. A futtatási és frissítési útmutató: [STEP1_TEST_BASELINE_v0.30.1.md](STEP1_TEST_BASELINE_v0.30.1.md).

**Elsőként külön könyvtárban futtasd a `test-release.ps1 -Suite all` parancsot.** Ez nem production deploy és nem Android/aláírási átvétel. A korábbi dokumentumok security-PASS állításai nem helyettesítik az aktuális teljes tesztriportot.

A `deploy/vps/security-hardening-acceptance.sh`, `check-db-privileges.sh` és `check-db-role-provisioner.sh` most elkülönített tesztet indít, nem az éles DB-t módosítja. A `check-backend-migrate-identities.sh` külön, csak olvasó telepítési próba marad.

---

# Munkalap- és eszköznyilvántartó webalkalmazás

## 1. Rendszer célja

Ez a belső webes rendszer munkalapok, archivált munkalapfájlok, ügyfelek, helyszínek, eszközök, anyagfelhasználás, munkavégzési státuszok, HR szabadságkezelés, CRM értékesítési folyamatok, beszerzési igények és audit naplók kezelésére készült. A rendszer böngészőből használható, PostgreSQL adatbázissal dolgozik, és Docker Compose-zal indítható.

## Aktuális verzió

A jelenlegi kiadás: **0.31.0**.

## Privát induló adatok a forrásverziókövetésben

A `backend/app/data/company_profiles.json`, `customer_assets_20260616.json` és `hr_leave_2026_rlb.json` helyi, üzleti vagy személyes adatokat tartalmazó fájlok. A Git és a Docker build context kizárja őket; a meglévő helyi példány fájljai nem törlődnek. A három állomány használatát és a tiszta telepítéshez szükséges biztonságos adatbevitelt a [privát adatforrások leírása](docs/architecture/PRIVATE_DATA.md) tartalmazza. A tesztek kizárólag szintetikus mintákat használnak.


## 0.30.0 - Security Hardening I (P0)

- A restore, recovery-lock feloldás és felhasználói privilege módosítás friss MFA step-up megerősítést kér; az alapértelmezett érvényesség 300 másodperc.
- A `SecurityStepUpModal` TOTP- vagy recovery kódot fogad, és siker után legfeljebb egyszer küldi újra az eredeti műveletet.
- A FastAPI/push-worker `workapp_app`, az Alembic one-shot service `workapp_migrate` adatbázis-szereppel fut; az objektumok tulajdonosa a `NOLOGIN workapp_owner`.
- Meglévő PostgreSQL volume-on az idempotens `db-role-provisioner` rendezi az ownershipet, grantokat és default privilege-eket; adatbázis-újrainicializálás nem szükséges.
- A backend normál indulása már nem futtat Alembicet vagy seedet. Ezek a `migrate` service deployment gate-jei.
- A backend és a migrate service közvetlenül fix `10001:10001` non-root userrel indul, `cap_drop: ALL` és `no-new-privileges` mellett; nincs runtime `gosu`, `chown` vagy UID/GID-váltás.
- A backup-agent nem kap Docker socketet és nem tartalmaz Docker CLI-t. Az egyetlen socketes komponens a host port nélküli, belső `backup-runner`, amely nem fogad tetszőleges parancsot, container ID-t, image-et, volume-ot vagy host pathot.
- A production preflight és a security acceptance fail-closed módon ellenőrzi a DB-, MFA-, secret-, network-, runner- és restore-kontrollokat.
- Windowsos in-place frissítésnél a `start-v0.30.0-hotfix.ps1` indító használata javasolt. Explicit `compose.yaml` fájlt használ, így egy korábbi `compose.yaml`, `COMPOSE_FILE` vagy command-maradvány nem tudja visszahozni a régi `gosu app` indulási modellt. A migrate log első sora sikeres hotfix betöltésnél `migrate-entrypoint v0.30.0-hotfix2 uid=10001 gid=10001`.

Production frissítés előtt futtasd a `deploy/vps/preflight-production.sh` ellenőrzést. Teljes, destruktív restore drillhez külön, tudatosan add meg a `RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE=YES` változót, majd futtasd a `deploy/vps/security-hardening-acceptance.sh` gate-et.


## 0.29.0 - End-to-end Android release readiness

A v0.29.0 az Android/Firebase/VPS kiadasi folyamatot zarja le reprodukalhato, fail-closed acceptance kapukkal. Uj adatbazis-migracio nincs; az adatmodell tovabbra is a `0032_push_notifications` headen marad.

- Admin -> Felhasznalok alatt lathatok a regisztralt mobil eszkozok, push allapotuk es a legutobbi push delivery statusza FCM token megjelenitese nelkul.
- Admin biztonsagos teszt push-t indithat egy konkret, aktiv mobil eszkozre.
- Uj szerveroldali `push_smoke_test` CLI es VPS wrapper valodi FCM provider smoke teszthez.
- A production acceptance opcionlisan valodi push smoke tesztet futtat `PUSH_SMOKE_DEVICE_ID` megadasaval.
- Android release preflight ellenorzi a HTTPS API URL-t, package ID-t, Android SDK-t, `google-services.json` package/project egyezest es a signing cert fingerprintet.
- A release artifact gate ellenorzi a SHA-256 manifestet, az APK v2+ alairasat, az AAB JAR alairasat es opcionlisan `bundletool validate` futtatast.
- Opcionalis ADB install/launch smoke teszt egy valodi Android keszuleken.
- A release acceptance alairt APK/AAB artifactokrol secretmentes `release-manifest.json` fajlt keszit.
- A verzioszinkronizalo eszkozt kibovitettuk a mobil es production release fajlokra is.

Reszletes eljaras: `ANDROID_E2E_RELEASE_RUNBOOK_v0.29.0.md`, `SECURITY_RELEASE_CHECKLIST_v0.29.0.md` es `mobile/ANDROID_BUILD_SIGNING.md`.


## 0.28.0 - Push ertesitesek es Android signing pipeline

- Firebase Cloud Messaging HTTP v1 push worker tranzakcios PostgreSQL outboxszal.
- Mobil FCM token regisztracio, retry/deduplication es ervenytelen token automatikus letiltasa.
- Push scope: uj munkalap-hozzarendeles es erdemi tervezett idopont-modositas.
- Capacitor push notification, foreground banner es munkalap deep link.
- Debug APK, alairt release APK es Google Play AAB build pipeline kulso upload keystore-ral.
- `google-services.json`, keystore, signing env es native artifactok kizarva Gitbol, Docker contextbol es release ZIP-bol.
- Uj `0032_push_notifications` Alembic migracio es backup formatum 16.


## 0.27.0 - Android/Capacitor technikusi kliens

- Kulon `mobile/` React + Capacitor Android kliens.
- Mobil login/MFA, secure refresh-token tarolas, Mai munkaim, munkalap reszlet, munkakezdes, szamlalo, anyagfelhasznalas es befejezes.
- Kamera es munkalap-fotok EXIF/GPS eltavolitassal, malware scannel, JPEG normalizalassal es SHA-256-tal.
- Erintokepernyos ugyfelalairas es alairt PDF megnyitas/megosztas.
- Uj `0031_mobile_photos` migracio; a foto evidence fajlok backup/restore reszei.


## 0.26.0 - Mobil API es alairt munkalap backend

A v0.26.0 a publikus production alapokra epiti ra a kesobbi Android technikusi kliens szerveroldali reteget. Ez a release meg nem tartalmaz APK/AAB alkalmazast; a FastAPI mobil vegpontjai, az eszkozhoz kotott mobil munkamenetek, a munkalap-lezarasi snapshot, az ugyfel alairasa es az immutable alairt PDF keszultek el.

- Kulon `/api/mobile` API technikusoknak es Adminnak; a technikus csak a sajat hozzarendelt munkalapjait eri el.
- Rovid elettartamu mobile access JWT es rotalodo refresh token; refresh-token replay eseten a teljes mobil session visszavonasra kerul.
- Mobil eszkozregisztracio es tavoli eszkoz-visszavonas Adminnal.
- Mobil munkafolyamat: mai munkak, reszletek, inditas, szamlaloallas, anyagkereses, befejezes, alairas.
- Befejezeskor szerveroldali, kanonikus JSON completion snapshot es SHA-256 lenyomat keszul.
- Az ugyfel alairasa csak a legfrissebb, azota nem modositott munkalap-revisionhoz kotheto.
- Az alairas PNG tartalmilag validalt, malware-scannelt es ures canvas ellenorzest kap.
- A szerver automatikusan alairt PDF-et general, SHA-256 lenyomattal; a korabbi alairt revision kesobbi munkalap-modositasnal is megmarad.
- Az alairasi PNG es PDF a logikai backup resze; a backup formatum verzioja 14.
- Uj `0030_mobile_signatures` Alembic migracio.

Mobil backend security gate: `SECURITY_MOBILE_CHECKLIST_v0.26.0.md`. Az Android kliens a kovetkezo roadmap-fazis.


## 0.25.0 - Public Production Infrastructure

A v0.25.0 a v0.24.0 alkalmazasbiztonsagi alapjara epiti ra a publikus VPS uzemeltetesi reteget. Productionben csak a Caddy edge proxy publikal 80/443 host portot; a frontend, FastAPI, PostgreSQL, ClamAV es backup-agent Docker halozaton marad.

- Uj `docker-compose.production.yml` automatikus TLS edge proxyval (`caddy:2.11.4-alpine`) es perzisztens certificate storage-dzsal.
- A base Compose tobbe nem publikalja a frontend 3000-es portjat; a localhost-only fejlesztoi portok a `docker-compose.dev.yml` override-ban maradnak.
- Production secret-file bekotes PostgreSQL, backend session/MFA, bootstrap admin, backup-agent es offsite backup titkokhoz.
- A backup-agent Restic alapu, titkositott S3-kompatibilis offsite masolatot keszit minden normalis napi/manualis mentest kovetoen, kulon napi/heti/havi retentionnel.
- Az Admin backup felulet mutatja az offsite allapotot es a mentesi pontok offsite eredmenyet.
- Kulon management Docker network izolalja a Docker socketet hasznalo backup-agentet a frontend/edge halozattol.
- Uj VPS preflight, UFW, SSH hardening, deploy, TLS/port/security acceptance, offsite init/check/restore-stage es backup acceptance scriptek.
- Opcionais, localhost-only Uptime Kuma monitoring profil; ezen felul kulso VPS-en kivuli uptime monitor tovabbra is kotelezo.

Publikus telepiteshez lasd: `deploy/vps/README.md` es `SECURITY_PRODUCTION_CHECKLIST_v0.25.0.md`.


## 0.24.0 - Cloud Security Foundation

A kiadás a meglévő belső hálózati alkalmazást készíti elő későbbi publikus/VPS üzemre. **Ez a release önmagában még nem a publikus VPS deploy**; a TLS reverse proxy, DNS, offsite backup és külső monitoring a következő infrastruktúra-fázis része.

- A böngészős JWT kikerült a `localStorage`-ból: a webes munkamenet `HttpOnly` session cookie-t és külön CSRF cookie/header párost használ.
- A munkamenetek szerveroldali `auth_sessions` rekordot kapnak, idle és abszolút lejárattal, logout/revoke támogatással.
- Admin szerepkörnél productionben kötelező TOTP MFA kapcsolható; első belépéskor önkiszolgáló regisztráció és egyszer használható recovery kódok készülnek.
- Szerverkonzolos MFA-helyreállítás: `python -m app.reset_mfa --email user@example.com`.
- Adatbázis-alapú login throttling, Nginx auth/API rate limiting és sikertelen belépési security audit került be.
- A browser write kérések cross-site/Origin ellenőrzést és cookie-auth esetén CSRF-védelmet kapnak.
- Szűkített production CORS, CSP/HSTS és további HTTP security headerek kerültek be; productionben az API dokumentáció kötelezően kikapcsolandó.
- A fájlfeltöltések közös tartalomellenőrzést, OOXML ZIP-bomba/path-traversal védelmet és opcionális ClamAV ellenőrzést kapnak. Publikus `ENVIRONMENT=production` módban a ClamAV + fail-closed konfiguráció kötelező.
- A DB és a backend alapértelmezetten nem publikál host portot; külön `docker-compose.dev.yml` ad localhost-only fejlesztői portokat.
- A backend read-only konténerfájlrendszert, capability-minimalizálást és non-root alkalmazásfolyamatot használ; a frontend Nginx non-root userként fut.
- A backend nem bízik tetszőleges `X-Forwarded-*` fejlécekben; csak konfigurált proxy CIDR felől fogad forwarded kliens IP-t.
- Új `/api/health/live` és `/api/health/ready` végpontok ellenőrzik a DB-t, runtime írhatóságát és engedélyezett malware scanner elérhetőségét.
- A `production` mód fail-closed konfiguráció-ellenőrzéssel leáll gyenge/alapértelmezett titok, nem HTTPS publikus URL, nem Secure cookie, kikapcsolt Admin MFA, nem biztonságos CORS, bekapcsolt docs vagy hiányzó malware scan esetén.
- Új `0029_cloud_security` Alembic migráció hozza létre a session-, MFA- és login-throttling adatstruktúrákat.

A publikus kihelyezés előtt kötelezően olvasd el: `SECURITY_PRODUCTION_CHECKLIST_v0.24.0.md`.


## 0.23.0 - Beszerzés modul

- Minden aktív, bejelentkezett felhasználó létrehozhat és követhet saját beszerzési igényt.
- Kötelező a tárgy, a beszerzés célja, a részletes leírás és az összérték; az igény automatikus `BESZ-YYYY-NNNN` azonosítót kap.
- Új `procurement.approve` jogosultsággal külön jóváhagyói lista érhető el; a jóváhagyó engedélyezheti vagy indoklással elutasíthatja a függő igényeket.
- Saját igény jóváhagyása vagy elutasítása backend oldalon is tiltott, Admin szerepkörrel is.
- Egy igényhez több PDF, DOCX, XLSX, CSV, JPG vagy PNG csatolmány tölthető fel, fájlonként legfeljebb 25 MiB méretben; a fájlok a runtime mentés részei.
- A kérelmező a még függő saját igényét visszavonhatja; lezárt igény nem törölhető.
- Jóváhagyási események, fájlműveletek és állapotváltozások auditálva vannak, a kérelmező/jóváhagyó értesítést kap.
- A frissítés `0028_procurement` adatbázis-migrációt tartalmaz.


## 0.22.0 - CRM aktivitásból egy kattintással lehetőség

- A CRM-aktivitások listáján a még lehetőséghez nem kapcsolt aktivitásból egyetlen gombnyomással új értékesítési lehetőség készíthető.
- Az új lehetőség automatikusan átveszi az aktivitás ügyfelét, kapcsolattartóját, felelősét, tárgyát és leírását; kezdő pipeline-szakasza `új`, devizája `HUF`.
- Az eredeti aktivitás megmarad, és automatikusan hozzákapcsolódik az elkészült lehetőséghez.
- A kapcsolt lehetőség közvetlenül megnyitható az aktivitásból; ugyanaz az aktivitás második lehetőséggé nem alakítható.
- Adatbázis-migráció nem szükséges.


## 0.21.0 - jóváhagyáshoz kötött szabadság-visszavonás

- A dolgozó a saját jóváhagyott szabadságára visszavonási kérelmet küldhet, opcionális indoklással.
- A kérelem a HR profilban kijelölt szabadság-jóváhagyóhoz kerül; más jóváhagyó nem dönthet róla.
- A szabadság az engedélyezésig jóváhagyott marad, ezért addig a keretet és a dashboard naptárát sem módosítja.
- Engedélyezéskor a szabadság visszavont lesz és a napok felszabadulnak; elutasításkor változatlanul érvényben marad.
- A funkció azoknak is elérhető, akik saját HR-adataikat láthatják, de új szabadságigényt nem küldhetnek be.
- A frissítés `0027_leave_cancel_approval` adatbázis-migrációt tartalmaz, amely a backend indulásakor automatikusan lefut.


## 0.20.1 - helyszín-inaktiválás az előzmények megőrzésével

- Admin jogosultsággal egy hivatkozott helyszín inaktiválható, majd szükség esetén visszaaktiválható.
- Az inaktív helyszín megmarad a korábbi munkalapokon, eszközökön, kapcsolattartókon és CRM szerződéseken.
- Új munkalaphoz, eszközhöz, kapcsolattartóhoz vagy CRM szerződéshez inaktív helyszín nem rendelhető.
- A hivatkozatlan, tévesen rögzített helyszín továbbra is végleg törölhető.
- A frissítés `0026_location_active_status` adatbázis-migrációt tartalmaz, amely a stack indulásakor automatikusan lefut.


## 0.20.0 - ügyfél-adminisztráció és technikusi szabadságnaptár

- Admin szerepkörrel az ügyfelek, helyszínek és kapcsolattartók minden üzleti adatmezője szerkeszthető, a nem hivatkozott rekordok pedig törölhetők.
- A hivatkozott helyszínek törlését a rendszer az eszköz-, munkalap-, kapcsolattartó- és CRM-előzmények védelmében blokkolja.
- A dashboard heti naptára az aktív technikusok jóváhagyott szabadságait külön egész napos sávban mutatja.
- A heti naptár a dashboard tetején, a karbantartási munkaszervezés előtt jelenik meg.
- Adatbázis-migráció nem szükséges.


## 0.19.8 - 25 MB-os archív feltöltési hotfix

- Az Nginx feltöltési korlátja összhangba került a backend 25 MB-os archív fájlkorlátjával.
- A proxy külön ráhagyást biztosít a multipart kérés technikai többletére, ezért a 25 MB-os fájlok is feltölthetők.
- A nagyobb globális import és rendszer-visszaállítás saját, magasabb korlátja megmaradt.


## 0.19.7 - egyedi backup státusz hotfix

- A backup-agent egyetlen mentési feladatot visszaadó `GET /backups/{backup_id}` végpontot biztosít.
- Az acceptance runner a létrehozott MASTER-t közvetlenül az azonosítója alapján várja meg, ezért a PowerShell nem bonthatja ki a teljes mentési listát hamis eredménnyé.
- Adatbázis-migráció nem szükséges.


## 0.19.6 - host PowerShell backup/restore hotfix

- A host backup és disaster-recovery restore integrált állapotellenőrzése Windows PowerShell 5.1-kompatibilis `python -c` argumentumot használ.
- Mindkét script kizárólag egyszeres Python-literálokat tartalmazó változóban adja át a kódot a Dockernek.
- A fizikai mentési formátum és a restore-logika nem változott; adatbázis-migráció nem szükséges.


## 0.19.5 - Windows PowerShell runtime probe hotfix

- Az acceptance runtime állapotjelzője `printf '%s'` használatával, sortörés és escape-szekvencia nélkül készül.
- Megszűnik a sikeres restore utáni hamis `master-state` / `master-state\\n` eltérés.
- A mentési és restore-logika nem változott; adatbázis-migráció nem szükséges.


## 0.19.4 - restore timeline és acceptance hotfix

- Az acceptance audit-eseménye a backend e-mail-validációjával kompatibilis tesztcímet használ.
- A kiválasztott backup és az automatikus rollback restore a backup saját aktuális timeline-ján marad (`--target-timeline=current`).
- A backend belső restore-eseményének HTTP-hibái a teljes választesttel jelennek meg a diagnosztikában.
- Adatbázis-migráció nem szükséges.


## 0.19.3 - Windows PowerShell acceptance hotfix

- Az inkrementális acceptance lépés Windows PowerShell 5.1 alatt is változatlanul adja át a Python szöveges argumentumait a `docker exec` folyamatnak.
- A runner a natív parancsok teljes hibakimenetét megőrzi, így sikertelen ellenőrzésnél a teljes traceback látható.
- A mentési és restore-logika nem változott; adatbázis-migráció nem szükséges.

## 0.19.2 - pgBackRest adatbázis-felhasználó hotfix

- A PostgreSQL konténer a konfigurált `POSTGRES_USER` értékét `PGUSER` változóként is átadja a pgBackRest folyamatoknak.
- Ez javítja az új backup repository automatikus inicializálását olyan telepítéseken, ahol nincs `postgres` nevű adatbázis-szerepkör, például az alapértelmezett `POSTGRES_USER=workapp` beállításnál.
- Nincs szükség külön `postgres` adatbázis-szerepkör létrehozására vagy kézi `stanza-create` futtatására.
- Frissítés után a `db` és `backup-agent` szolgáltatást újra kell létrehozni, majd a pgBackRest állapotát ellenőrizni:

```powershell
docker compose up -d --build --force-recreate db backup-agent
docker compose exec -T -u postgres db pgbackrest --stanza=workapp check
docker compose logs --tail=100 db backup-agent
```

## 0.19.1 - backup/restore stabilizáció és automatizált acceptance

- A mentési pont **Ellenőrzés** művelete a SHA-256/runtime lánc mellett a kiválasztott pgBackRest backup setre fizikai `pgbackrest verify --set=...` ellenőrzést is futtat.
- Restore után a PostgreSQL csak akkor minősül késznek, ha a `pg_isready` mellett `pg_is_in_recovery() = false`; ezzel a post-restore MASTER nem indulhat még hot-standby/recovery állapotú adatbázison.
- A backend restore-utóellenőrzése az Alembic `current/head` egyezés mellett a valódi `/api/health` végpont elérhetőségét is megvárja, mielőtt audit-eseményt ír.
- Új `acceptance-backup-restore.ps1` teljesen **izolált** Compose projektben automatizálja a fizikai MASTER → incremental → restore → rollback útvonalat, majd a host PowerShell backup/restore disaster-recovery folyamatot is. A script nem használja az éles projekt volume-jait.
- Sikeres acceptance futás után csak a `munkalap-acceptance-*` prefixű tesztprojekt volume-jait törli; hiba esetén a diagnosztikai környezetet szándékosan meghagyja.

### Teljes backup/restore acceptance futtatása

Frissítés vagy éles restore engedélyezése előtt a projekt gyökeréből futtasd:

```powershell
.\acceptance-backup-restore.ps1
```

A teszt külön ideiglenes projektmásolatot, külön Compose projektnevet, külön portokat és külön volume-okat készít. Valódi Docker daemon szükséges hozzá. Hiba esetén a script kiírja a megtartott tesztprojekt nevét és könyvtárát; siker esetén automatikusan takarít.

## 0.19.0 - integrált webes visszaállítás

- Az **Admin → Biztonsági mentések** oldalon `admin.backup.restore` jogosultsággal már kiválasztható és visszaállítható egy ellenőrzött integrált mentési pont.
- A restore előtt a teljes MASTER + inkrementális lánc validálódik, majd kötelező **pre-restore MASTER** készül az aktuális állapotról.
- A PostgreSQL a kiválasztott pgBackRest backup saját `stop LSN` értékére áll vissza, az `app_runtime` pedig staging területen rekonstruált MASTER + delta állapotból épül fel.
- Sikeres visszaállítás után kötelező **post-restore MASTER** készül; ez lesz a visszaállított PostgreSQL timeline új inkrementális alapja.
- Hiba esetén a backup-agent automatikusan megpróbál visszagörgetni a pre-restore MASTER-re, és sikeres rollback után külön rollback MASTER-rel nyit új inkrementális láncot. Bizonytalan vagy megszakadt restore után tartós recovery lock tiltja az új backup/restore műveleteket.
- A recovery lock csak ellenőrzött DB/backend/pgBackRest állapot mellett, pontos `HELYREALLITAS_KESZ` megerősítéssel oldható fel.
- A webes restore csak **azonos deployment fingerprint** mentéseire használható. Más alkalmazásverzió, Docker image vagy Compose-konfiguráció visszaállításához a host `restore-munkalap-app.ps1` marad a disaster-recovery eszköz.
- A restore külön `admin.backup.restore` jogosultságot igényel; a `admin.backup.manage` önmagában nem elegendő.
- Az Alembic head változatlanul `0025_admin_backup_permissions`; ehhez a körhöz nem szükséges új adatbázis-migráció.

### Kötelező backup-agent beállítás

Az `.env` fájlban állíts be hosszú, véletlen tokent. Ugyanazt a Compose adja át a backendnek és a backup-agentnek:

```env
BACKUP_AGENT_TOKEN=ide-egy-hosszu-veletlen-titok
BACKUP_TIMEZONE=Europe/Budapest
APP_VERSION=0.19.2
```

A `backup-agent` és a `backup-runner` sem publikál host portot. A Docker socket kizárólag a belső, külön tokennel védett `backup-runner` szolgáltatáshoz van csatolva; a normál FastAPI backend és a backup-agent nem kap Docker-szintű jogosultságot.

### Mentési modell

- napi fix időpont, alapértelmezett időzóna: `Europe/Budapest`;
- hónap utolsó naptári napja: **MASTER**;
- többi nap: valódi pgBackRest **incremental** + `app_runtime` fájldelta;
- manuális MASTER bármikor indítható;
- ha nincs érvényes MASTER vagy változott a deployment fingerprint, az ütemezett increment automatikusan MASTER-re emelkedik.

Docker volume-ok:

```text
postgres_data       PostgreSQL adatbázis
app_runtime         archívumok és runtime fájlok
backup_repository   pgBackRest repository + integrált mentési csomagok
backup_control      scheduler, job/restore történet és recovery állapot
```

**Soha ne használd a `docker compose down -v` parancsot.**

### Frissítés v0.18.0-ról

Frissítés előtt készíts teljes MASTER mentést. Ezután:

```powershell
docker compose down
docker compose build --no-cache db backup-agent backend frontend
docker compose up -d
docker compose logs --tail=200 db backup-agent backend
docker compose exec -T backend alembic heads
docker compose exec -T backend alembic current
```

Az `alembic heads` eredménye továbbra is pontosan egy head legyen: `0025_admin_backup_permissions`.

## 0.18.0 - integrált MASTER / inkrementális biztonsági mentés, első kör

- Bevezette az izolált `backup-agent` szolgáltatást, a napi MASTER/inkrementális ütemezést, a pgBackRest adatbázis-láncot és az `app_runtime` hash-alapú deltaláncot.
- Létrehozta az **Admin → Biztonsági mentések** oldalt és az `admin.access`, `admin.backup.manage`, `admin.backup.restore` jogosultságokat.
- A 0.18.0-ban a webes restore még nem volt engedélyezve; ezt a 0.19.0 valósítja meg.

## 0.17.2 - Alembic stale-file hotfix

- Javítja azt az esetet, amikor a 0.17.1 fájljait a 0.17.0 projektkönyvtárára másolva a régi `0024_contract_details_archives_hr_calendar.py` migráció ott maradt és második Alembic headet hozott létre.
- A backend indulás előtt eltávolítja ezt a kizárólag hibás 0.17.0 kiadásból származó, PostgreSQL-en soha nem commitálható migrációs fájlt.
- Új regressziós teszt ellenőrzi, hogy a tiszta kiadási migrációs gráfnak pontosan egy headje legyen.
- A helyes Alembic head továbbra is `0024_contract_archives_hrcal`.

## 0.17.1 - Alembic PostgreSQL hotfix

- A 0.17.0 `0024_contract_details_archives_hr_calendar` revision azonosítója túl hosszú volt a PostgreSQL Alembic alapértelmezett `VARCHAR(32)` verziómezőjéhez.
- A javított head: `0024_contract_archives_hrcal`.
- A 0024 migráció üzleti/adatbázis-tartalma nem változott.
- Ha a 0.17.0 indítás a revision azonosító mentésénél hibázott, a PostgreSQL tranzakció visszagörgette a migrációt, ezért a 0.17.1 közvetlenül telepíthető a megmaradt 0023 headre.

## 0.17.0 – részletes CRM szerződésadatok, PDF szerződésarchívum és HR naptár

- A CRM Szerződések modul a `Szerződések adatai.xlsx` A–AD oszlopainak adatszerkezetét kezeli, a kapcsolattartói adatok nélkül. A vállalkozó külön `DRH` / `SP` / `GXR` választó.
- Új szerződés-snapshot mezők: szerződő név/székhely, szerződés tárgya, futamidő, számlázási gyakoriság, fizetési feltétel, számlázási név, TIG/munkalap, e-számla cím és díjmódosítás feltétele.
- Egy szerződéshez tetszőleges számú szerviz/eszköz sor rögzíthető: bérleti díj, üzemeltetési díj, klikkdíj, bennfoglalt mennyiség, üzemeltető, üzemeltetési cím, karbantartási ciklus, készülékcsoport, eszköz, gyáriszám, alkatrész, toner, kiszállás/munkadíj, hibajavítás, SLA és cseregép.
- Minden CRM szerződéshez több, kizárólag PDF formátumú papíralapú szerződés csatolható. Az archív azonosító formátuma `SZ-A-ÉV-SORSZÁM`.
- A PDF archívum CRM-hozzáféréssel előnézhető, nyomtatható és letölthető. Feltöltés `crm.contract.manage` jogosultságot kér; végleges törlés kizárólag Admin számára engedélyezett, pontos `TÖRÖL` megerősítéssel és auditnaplóval.
- A szerződés PDF-ek az `app_runtime/contract_archives` tárhelyen maradnak és bekerülnek a beépített teljes backup/restore körbe.
- A HR Összesítés új távolléti naptárt kapott heti, havi és éves nézettel, a munkalap-dashboardhoz illeszkedő jelmagyarázattal és munkavállalói színekkel. A naptár jóváhagyott és függő távolléteket mutat; betegszabadság külön jelölést kap.
- A HR naptár ugyanahhoz a külön `hr.summary.view` jogosultsághoz kötött, mint az összesítő. E jogosultság ezért ettől a verziótól a távollétek dátumainak megtekintését is engedélyezi; megjegyzéseket az API nem ad át.
- Alembic head: `0024_contract_archives_hrcal`. Új táblák: `crm_contract_service_lines`, `crm_contract_archives`; a `crm_contracts` új részletes mezőkkel bővült.
- A beépített teljes mentés formátuma **12**; az 1–11 formátumú korábbi mentések továbbra is támogatottak.
- A projekt továbbra is **0.x** verzióágon marad.

## 0.16.0 – 2026 RLB szabadságadatok betöltése

- A kiadás tartalmazza a felhasználó által átadott nyolc 2026-os RLB szabadságnyilvántartás strukturált forrásadatát. A forrásnap: **2026-08-02**.
- Az importált munkavállalói adatok: törzsszám, munkaviszony kezdete, beosztás, alapszabadság, gyermekek után járó szabadság, betegszabadságkeret, valamint a nyilvántartott szabadság- és betegszabadság-időszakok.
- A HR modell külön kezeli az `annual_leave` és `sick_leave` távolléttípust. A betegszabadság nem csökkenti az éves szabadságkeretet.
- A `leave_entitlements` külön `child_days` és `sick_leave_days` mezőt kapott; az éves szabadságkeret az alap + gyermekek után járó + áthozott + korrekció összege.
- Az importált múltbeli távollétek `approved` történeti rekordként kerülnek be, `rlb_pdf_2026` forrásjelöléssel; nem kerülnek új vezetői jóváhagyási sorba.
- A forrásrekordok automatikusan csak egyértelmű felhasználó-párosítás és konfliktusmentes HR-adatállapot esetén alkalmazódnak. Meglévő eltérő 2026-os HR adatot a rendszer nem ír felül csendben.
- A HR admin oldalon külön **Importált 2026. évi RLB szabadságadatok** tábla mutatja a betöltött, párosításra váró vagy ütköző rekordokat, és kézi felhasználó-párosítás is végezhető.
- A Saját szabadság nézet külön mutatja az éves szabadságot és a betegszabadság keret/felhasználás/maradék adatait, valamint jelzi az RLB-ből importált történeti sorokat.
- Alembic head: `0023_hr_leave_source_import`. Új staging táblák: `hr_leave_import_people`, `hr_leave_import_absences`; a HR profil, keret és távollét táblák új mezőkkel bővültek.
- A beépített teljes mentés formátuma **11**; az 1–10 formátumú korábbi mentések továbbra is támogatottak.
- A projekt továbbra is **0.x** verzióágon marad; ez az adatbetöltési kiadás nem 1.0.

## 0.15.0 – értesítések, riportok és exportok (6. fázis)

- Központi **Értesítések** nézet készült olvasatlan számlálóval és modulonkénti jelzéssel a Modulválasztóban.
- A rendszer személyre szabott értesítést készít a felhasználó jogosultságai és saját feladatai alapján: HR jóváhagyásra váró igények és saját döntések, saját CRM-határidők, lejáró CRM szerződések, valamint a felhasználóhoz rendelt mai/lejárt Szerviz munkalapok.
- A már megoldott, lezárt vagy más felhasználóhoz átadott cselekvést igénylő értesítések automatikusan lezáródnak, ezért nem maradnak bent téves olvasatlan jelzésként.
- Új **Szerviz riportok** nézet készült időszaki munkalap-, lezárás-, sürgősség-, munkaóra-, státusz-, munkatípus- és technikusi terhelés összesítéssel.
- Új, külön `hr.summary.view` jogosultsághoz kötött **HR riportok** nézet készült szervezeti egység és havi aggregált szabadságterhelés adatokkal. A riport nem ad hozzáférést más munkavállalók részletes szabadságdátumaihoz.
- Új **CRM riportok** nézet készült pipeline darabszám/érték, súlyozott pipeline, nyert/elvesztett darabszám, aktivitástípusok és időszaki szerződéslejáratok megjelenítésével.
- CSV export készült a Szerviz riporthoz, HR riporthoz/összesítéshez, CRM pipeline riporthoz, valamint külön a CRM lehetőségekhez, aktivitásokhoz és szerződésekhez. A CSV-k UTF-8 BOM-mal készülnek a jobb Excel-kompatibilitás érdekében.
- Az értesítési adatok a teljes mentés részei. A beépített backup-formátum **10**; az 1–9 formátumú korábbi mentések továbbra is támogatottak.
- Alembic head: `0022_notifications_reports`; új tábla: `notifications`.
- Ez a HR/CRM fejlesztési terv **6. fázisa**. Mind a hat tervezett fázis implementálva van; az 1.0 kiadás előtt külön elfogadási és éles PostgreSQL/Docker validáció javasolt.

## 0.14.0 – CRM szerződéskezelés és munkalap-integráció (5. fázis)

- Új CRM **Szerződések** menüpont készült. A szerződés ügyfélhez kapcsolódik, és tárolja a szerződésszámot, típust, kezdő/záró dátumot, státuszt, SLA-t, elszámolási modellt és megjegyzést.
- A szerződés hatálya opcionálisan konkrét telephelyekre és/vagy eszközökre korlátozható. Üres kapcsolati lista esetén az adott dimenzióban ügyfélszintű a hatály.
- Szerződés létrehozása és módosítása külön `crm.contract.manage` jogosultsághoz kötött; `crm.access` jogosultsággal a szerződéslista olvasható.
- A backend tiltja a kereszt-ügyfél telephely- és eszközkapcsolatokat. CRM szerződéshez kapcsolt telephely vagy eszköz a Szerviz modulból nem törölhető.
- A CRM ügyfél 360° nézet szerződéslistával bővült. A CRM dashboard aktív és 60 napon belül lejáró szerződésszámot is mutat.
- A munkalap opcionálisan `contract_id` mezővel CRM-szerződéshez kapcsolható. A Szerviz modul külön, korlátozott szerződés-opció API-t használ, ezért a munkalapkezelőnek nem szükséges teljes CRM-hozzáférés.
- Munkalaphoz csak azonos ügyfél szerződése rendelhető; telephely-/eszközhatály esetén a backend a kiválasztott helyszínt és eszközöket is ellenőrzi.
- Szerződés hozzárendelésekor a meglévő `contract_type` mező a CRM-szerződés típusának **történeti snapshotját** kapja. A szerződés későbbi átnevezése nem írja át visszamenőleg a korábbi munkalap nyomtatási adatát.
- Alembic head: `0021_crm_contracts`. Új táblák: `crm_contracts`, `crm_contract_locations`, `crm_contract_assets`; a `work_orders` új opcionális `contract_id` idegen kulcsot kapott.
- A beépített teljes mentés formátuma **9**; az 1–8 formátumú régi mentések továbbra is támogatottak.
- Ez a HR/CRM fejlesztési terv **5. fázisa**. Az 1.0 továbbra is csak minden tervezett fázis elkészülte után készül.

## 0.13.0 – CRM alap (4. fázis)

- A CRM a meglévő `Customer` / `CustomerContact` törzset használja, ezért a Szerviz és CRM modulban ugyanaz az ügyfél, telephely, eszköz és munkalap jelenik meg.
- A CRM áttekintő dashboard nyitott pipeline értéket/darabszámot, lejárt aktivitásokat, pipeline szakaszokat és legutóbbi eseményeket mutat.
- A CRM ügyféllista kereshető, az ügyfél 360° nézet pedig kapcsolattartókat, eszközöket, munkalapokat, lehetőségeket és aktivitásokat fog össze.
- Az értékesítési lehetőség pipeline szakaszai: `új`, `kapcsolatfelvétel`, `igényfelmérés`, `ajánlat`, `tárgyalás`, `nyert`, `elvesztett`. Tárolható várható érték/deviza, valószínűség, várható zárás, forrás, következő lépés és elvesztési ok.
- CRM aktivitást lehet telefon, e-mail, meeting, feladat vagy jegyzet típussal rögzíteni, és ügyfélhez, kapcsolattartóhoz, lehetőséghez vagy meglévő munkalaphoz kapcsolni.
- A CRM olvasás `crm.access`, a módosítás `crm.write` jogosultsághoz kötött. Az Admin továbbra is szuperfelhasználó.
- A backend nem enged kereszt-ügyfél kapcsolást: kapcsolattartó, lehetőség és munkalap csak a saját ügyfeléhez kapcsolható.
- CRM előzménnyel rendelkező ügyfél/kapcsolattartó törlése blokkolt, és a CRM módosítások a strukturált auditnaplóba kerülnek.
- Alembic head: `0020_crm_core`. Új táblák: `crm_opportunities`, `crm_activities`.
- A beépített teljes mentés formátuma **8**; az 1–7 formátumú régi mentések továbbra is visszaállíthatók.
- Ez a HR/CRM fejlesztési terv **4. fázisa**. Az 1.0 továbbra is csak minden tervezett fázis elkészülte után készül.

## 0.12.0 – HR szabadságkezelés (3. fázis)

- A HR modul már üzemszerű szabadságkezelést tartalmaz: saját éves keret, saját szabadságigények, új igény beküldése és függőben lévő saját igény visszavonása.
- Minden normál felhasználó kizárólag a saját szabadságadatait kérheti le a `/api/hr/me...` végpontokon; nincs tetszőleges felhasználóazonosítót fogadó sajátadat-végpont.
- A munkavállalói HR profil külön kezeli a vezetőt és a szabadság-jóváhagyót. A jóváhagyó csak a hozzá rendelt igényeket látja és döntheti el.
- A több munkavállalót tartalmazó éves HR összesítés külön `hr.summary.view` jogosultsághoz kötött. Az összesítés éves aggregátumokat mutat, nem ad hozzáférést más munkavállalók részletes szabadságlistájához.
- A `hr.admin` jogosultsággal kezelhetők a munkavállalói profilok, éves alap/áthozott/korrekciós szabadságkeretek és a munkanaptár-kivételek.
- A munkanapszámítás alapja hétfő–péntek; a HR admin külön munkaszüneti hétköznapokat és áthelyezett munkanapokat rögzíthet.
- A rendszer tiltja az átfedő függő/jóváhagyott igényeket, az évhatáron átnyúló egyetlen igényt és a rendelkezésre álló keretet meghaladó beküldést.
- A szabadságigények, jóváhagyások/elutasítások, HR profilok, éves keretek és munkanaptár-kivételek a strukturált auditnaplóba kerülnek. A szabadságigény audit snapshotja nem tartalmaz pontos szabadságdátumot vagy szabad szöveges HR-megjegyzést.
- Alembic head: `0019_hr_leave_management`. Új táblák: `employee_profiles`, `leave_entitlements`, `leave_requests`, `work_calendar_days`.
- A beépített teljes mentés formátuma **7**; az 1–6 formátumú régi mentések továbbra is visszaállíthatók.
- Ez a HR/CRM fejlesztési terv **3. fázisa**. A projekt továbbra is 0.x verzióágon marad; az 1.0 csak minden tervezett fázis elkészülte után készül.


## 0.11.0 – strukturált auditnapló és integritásvédelem

- A korábbi egyszerű auditnapló strukturált eseménynaplóvá bővült: actor snapshot, művelet, objektumtípus/azonosító, leírás, `before_data`, `after_data`, `changes`, request/correlation/session ID, IP, user-agent, eredmény és súlyosság kerülhet egy rekordba.
- Minden auditbejegyzés SHA-256 hash-chain része. Az Admin modul **Auditnapló** oldalán külön integritásvizsgálat ellenőrzi, hogy a lánc változatlan-e.
- PostgreSQL alatt az `audit_logs` tábla append-only adatbázis-triggerrel védett: normál alkalmazási UPDATE és DELETE nem engedélyezett.
- A JWT token session ID-t (`sid`) tartalmaz; a backend minden kéréshez `X-Request-ID` és `X-Correlation-ID` azonosítót ad.
- Sikeres és sikertelen login, jogosultságmegtagadás és szerepkör-megtagadás is auditálható, így a biztonsági eseményeknél az eredmény is megmarad.
- Jelszó, jelszóhash, hozzáférési token, Authorization/Cookie fejléc, API-kulcs és secret nem kerülhet strukturált audit snapshotba.
- A felhasználó-, jogosultság-, cégprofil- és kapcsolattartó-módosítások explicit előtte/utána állapotot rögzítenek, így a lényegi mezőváltozások visszakövethetők.
- Az Auditnapló API és kezelőfelület kizárólag Admin számára érhető el.
- Alembic head: `0018_structured_audit_log`. A migráció a meglévő v0.10.0 auditbejegyzéseket is visszamenőleg hash-chainbe rendezi.
- A beépített teljes mentés formátuma **6**; az 1–5 formátumú régi mentések továbbra is visszaállíthatók, és a régi auditrekordok automatikusan konvertálódnak.
- Ez a HR/CRM fejlesztési terv **2. fázisa**. A projekt továbbra is 0.x verzióágon marad; az 1.0 csak minden tervezett fázis elkészülte után készül.

## 0.10.0 – moduláris alkalmazásalap és jogosultságkezelés

- Bejelentkezés és kötelező jelszócsere után külön **Modulválasztó** oldal jelenik meg.
- A rendszer moduljai: `Szerviz`, `HR`, `CRM`, valamint Admin szerepkörnél `Admin`.
- A Szerviz modul a meglévő munkalap-, eszköz-, ügyfél- és anyagfunkciókat változatlan adatmodellel használja, új `/service/...` frontend útvonalakon. A régi könyvjelzők kompatibilitási átirányítással tovább működnek.
- A HR és CRM modul üzleti funkciói még nincsenek implementálva; ebben a kiadásban a modul-hozzáférési és route-védelmi alap készült el.
- Új adatbázis-alapú modul- és funkciójogosultságok kerültek bevezetésre. A jogosultságok nem a JWT tokenből, hanem minden kérésnél az aktuális adatbázis-állapotból érvényesülnek.
- A Szerviz API backend-szinten `service.access` jogosultsághoz kötött; a meglévő Admin/Irodai/Technikus szerepkörök műveleti korlátozásai ezen felül továbbra is érvényesek.
- Az Admin szerepkör rendszerszintű szuperfelhasználó marad, és minden modulhoz hozzáfér.
- A Felhasználók admin oldalon modulonként kezelhetők a hozzáférések, köztük a későbbi HR szabadság-, HR összesítés- és CRM jogosultságok.
- Meglévő telepítés frissítésekor minden jelenlegi felhasználó automatikusan megtartja a Szerviz modul hozzáférését. HR/CRM hozzáférést a frissítés nem oszt ki automatikusan normál felhasználóknak.
- Alembic migráció: `0017_module_permissions`.
- A teljes HR és CRM fejlesztési program befejezéséig a projekt **0.x verzióágon marad**; az 1.0 csak minden tervezett fázis elkészülte után készül.


## 0.9.9 – nyomtatási munkalap mezősorrend és külső blokkfeliratok

- A `Tervezett nap / Szerződés típusa` sor alatt a `Tényleges kezdés` és `Tényleges befejezés` külön-külön teljes sort kap a nyomtatott munkalapon.
- A `Hiba / feladat leírása`, `Elvégzett munka` és `Végállapot` feliratok a hozzájuk tartozó keretes mezők fölé kerültek.
- Az Elvégzett munka és Végállapot v0.9.8-ban beállított nyomtatási mérete megmaradt.
- A nyomtatási elrendezés a reprezentatív A4 QA-esetben továbbra is egy oldal.
- Adatbázis-migráció nem szükséges.


## 0.9.8 – munkalap nyomtatási olvashatóság és eszközadatok

- A nyomtatott munkalap fejléc alatti általános betűmérete nagyobb; a metaadat-tábla mezőnevei normál betűsúlyúak.
- Az „Elvégzett munka” mező magasabb, a „Végállapot” mező pedig körülbelül háromszoros dobozmagasságot kapott.
- A Kapcsolódó eszközök nyomtatási táblából kikerült az Állapot és a Cégkód; helyettük az Utolsó karbantartás dátuma jelenik meg.
- A nyomtatott munkalap továbbra is 12 mm-es A4 margót és másolásbiztos 2 px-es kereteket használ.
- Adatbázis-migráció nem szükséges.

## 0.9.7 – nyomtatási finomhangolás és szerződéstípus

- A nyomtatási A4 margó 12 mm, így a tartalom biztonságosabban marad a nyomtatható területen.
- A fejléc betűméretei nagyobbak.
- Az „Elvégzett munka” blokk kisebb, az aláírások pedig az oldal alsó részéhez igazodnak.
- A nyomtatott munkalap üres értékei nem jelennek meg `-` jellel.
- A munkaidő alatt megjelenik a tervezett nap, mellette a munka típusa alatt a szerződés típusa.
- A munkalap opcionális, szabad szöveges `Szerződés típusa` mezőt tárol (max. 120 karakter).

## 0.9.6 – teljes A4-magasság és erősebb nyomtatási keretek

- A nyomtatott munkalap a 8 mm-es A4 margókon belül mindig legalább a teljes rendelkezésre álló, 281 mm-es oldalmagasságot kitölti.
- Az `Elvégzett munka` blokk rugalmasan kitölti a fennmaradó függőleges teret, ezért rövid munkalaptartalom esetén sem marad nagy üres terület az aláírások alatt vagy felett.
- A nyomtatási keretek vastagsága kétszeresére nőtt: az 1 px-es keretek 2 px-esek, a munkalap fejlécének 2 px-es választóvonala 4 px-es lett.
- A nyomtatási keretek sötétebb szürkét használnak, hogy fénymásolás és szkennelés után is jobban megmaradjanak.
- A normál, részletező és tömeges nyomtatási mód ugyanazt a teljes A4-magasságú flex elrendezést használja.
- Adatbázis-migráció nem szükséges.


## 0.9.5 – nyomtatási fejléc és egyoldalas A4 elrendezés

- A DRH, SP és GXR nyomtatott munkalap külön, szolgáltatási célú telefon- és helpdesk-email mezőket használ; ezek adminból szerkeszthetők az általános cégadatok módosítása nélkül.
- A munkalapi elérhetőségek a privát cégprofilban tárolhatók. A Git-bevezetés óta nincs forráskódba írt, cégkódonkénti elérhetőség.
- Korábbi `app_runtime/company_profiles.json` fájloknál, amelyek még nem tartalmazzák az új mezőket, a rendszer az általános profil-elérhetőséget használja.
- A nyomtatott szállítói blokkból kikerült a kapcsolattartó és a webcím.
- Az A4 nyomtatási stílus tömörebb lett: kisebb nyomtatási margó, kompaktabb blokkok és táblázatok, valamint kisebb, de továbbra is használható munkavégzési és aláírási tér segít egy oldalon tartani a munkalapot hosszabb fejléc és kétsoros kapcsolódóeszköz-sor mellett is.
- A kompatibilitási Excel munkalap ugyanazokat a szolgáltatási elérhetőségeket használja, és a szállítói kapcsolattartót ott sem tölti ki.
- Adatbázis-migráció nem szükséges.


## 0.9.4 – tömeges munkalap-státusz módosítás

- A Munkalapok listában kijelölt tételek tömeges szerkesztésénél a státusz is közösen módosítható.
- A státuszválasztás ugyanazokat az engedélyezett értékeket használja, mint az egyedi munkalapszerkesztő.
- `lezárva` státuszra váltáskor a rendszer a hiányzó lezárási időpontokat is rögzíti, és karbantartási munkalapnál lefuttatja a kapcsolt eszközök karbantartási frissítését.
- A módosítás optimista verzióellenőrzéssel, atomi tranzakcióban fut; adatbázis-migráció nem szükséges.

## 0.9.3 – beépített mentési és visszaállítási eszközök

- A projekt gyökerében megtalálható a `backup-munkalap-app.ps1` teljes mentési script.
- A projekt gyökerében megtalálható a `restore-munkalap-app.ps1` ellenőrzött visszaállítási script.
- A `BIZTONSAGI_MENTES_ES_VISSZAALLITAS.txt` részletes magyar használati leírást, parancsokat, ellenőrzéseket és hibaelhárítást tartalmaz.
- A visszaállító a mentés SHA-256 ellenőrzése után, működő célrendszernél automatikus vészmentést készít.
- A helyi `backups` és `pre-restore-backups` könyvtárak, valamint a nagy mentési archívumok nem kerülnek verziókövetésbe.
- A kiadás nem tartalmaz adatbázis-migrációt.

A mentési és visszaállítási parancsok részletesen:

```text
BIZTONSAGI_MENTES_ES_VISSZAALLITAS.txt
```

### 0.9.2 – munkalap gépadatok és nyomtatási szállítói fejléc

- A Munkalapok alaplistájában külön `Gép / gyári szám` oszlop látható.
- A munkalap Áttekintés nézetében a kapcsolt gépek típusa és gyári száma közvetlenül megjelenik, az eszköz adatlapjára kattintható hivatkozással.
- A nyomtatott munkalap szállítói fejléce a `Beállítások → Nyomtatási szállítói adatok` panel Admin által szerkesztett cégprofilját használja.
- A fejléc a címet, adószámot, cégjegyzékszámot, kapcsolattartót, telefonszámot, emailt és weboldalt is kezeli.
- A kiadás nem tartalmaz új adatbázis-migrációt.

A verzió központi forrása a projektgyökérben található:

```text
VERSION
```

A kiadások változásai a `CHANGELOG.md` fájlban követhetők. A rendszer szemantikus verziózást használ (`FŐVERZIÓ.ALVERZIÓ.JAVÍTÁS`). A backend Swagger dokumentációja, a `/api/version` végpont, a kezelőfelület és a teljes mentések manifestje ugyanazt az alkalmazásverziót jelzi.

Új kiadás előkészítése:

```bash
python scripts/set_version.py 0.12.0
python scripts/set_version.py --check
```

Ezután egészítsd ki a `CHANGELOG.md` fájlt, majd Git használata esetén készíts kiadási commitot és taget:

```bash
git add VERSION CHANGELOG.md frontend/package.json frontend/package-lock.json
git commit -m "release: v0.12.0"
git tag -a v0.12.0 -m "Munkalap rendszer v0.12.0"
```

## 2. Használt technológiák

- Backend: Python FastAPI
- ORM és migráció: SQLAlchemy 2 + Alembic
- Adatbázis: PostgreSQL 16
- Frontend: React + Vite, konténerben nginx statikus kiszolgálással
- Konténerizáció: Docker Compose
- Auth: JWT bearer token, bcrypt jelszóhash
- API dokumentáció: FastAPI Swagger/OpenAPI
- Tesztek: pytest + FastAPI TestClient
- Excel munkalap-sablon kitöltés: openpyxl

## 3. Környezeti változók

A projekt gyökerében található `.env.example` alapján kell létrehozni a `.env` fájlt.

```env
POSTGRES_DB=workapp
POSTGRES_USER=workapp
POSTGRES_PASSWORD=workapp
POSTGRES_PORT=5432
BACKEND_PORT=8000
APP_PORT=3000
SECRET_KEY=change-this-secret-before-production
ACCESS_TOKEN_EXPIRE_MINUTES=480
BACKEND_WORKERS=3
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=5
RUNTIME_DIR=/app/runtime
ARCHIVE_DIR=/app/runtime/work_order_archives
ARCHIVE_MAX_SIZE_MB=25
SUPPLIER_NAME=
SUPPLIER_ADDRESS=
SUPPLIER_PHONE=
SUPPLIER_EMAIL=
SUPPLIER_CONTACT=
```

Fontosabb változók:

- `POSTGRES_PORT`: lokális PostgreSQL port.
- `BACKEND_PORT`: backend API port, alapértelmezés szerint `8000`.
- `APP_PORT`: frontend port, alapértelmezés szerint `3000`.
- `SECRET_KEY`: JWT aláíró kulcs. Éles környezetben kötelező lecserélni.
- `BACKEND_WORKERS`: párhuzamos Uvicorn folyamatok száma; alapérték `3`.
- `DATABASE_POOL_SIZE`: egy backend worker állandó PostgreSQL-kapcsolatainak felső alapértéke; alapérték `5`.
- `DATABASE_MAX_OVERFLOW`: worker-enként ideiglenesen nyitható további adatbázis-kapcsolatok; alapérték `5`.
- `RUNTIME_DIR`: a tartós alkalmazásadatok könyvtára.
- `ARCHIVE_DIR`: az archivált munkalapfájlok könyvtára; Dockerben az `app_runtime` volume része.
- `ARCHIVE_MAX_SIZE_MB`: egy archiválható fájl maximális mérete, alapérték `25` MB.
- `SUPPLIER_NAME`, `SUPPLIER_ADDRESS`, `SUPPLIER_PHONE`, `SUPPLIER_EMAIL`, `SUPPLIER_CONTACT`: opcionális tartalék szállítói adatok. Az Excel munkalap elsődlegesen a beépített DRH / SP / GXR cégprofilokat használja a munkalap ügyfelén vagy kapcsolt eszközén lévő `company_code` alapján; ezek a változók csak akkor lépnek életbe, ha nincs felismerhető cégkód.


## Munkalap-archívum

A 0.6.0 verziótól PDF, JPG és PNG fájl archiválható:

- meglévő digitális munkalaphoz; ilyenkor a fájl automatikusan kapcsolódik a munkalap jelenlegi eszközeihez;
- közvetlenül egy eszközhöz, digitális munkalap létrehozása nélkül, a korábbi papíralapú nyilvántartás migrációjához.

Minden feltöltés egyedi `AR-ÉV-SORSZÁM` archiválási azonosítót kap. A fájlok csak bejelentkezett felhasználóként tölthetők le, és bekerülnek a teljes mentésbe. A közvetlen eszközarchiválás Admin vagy Irodai felhasználó számára érhető el. Az archív rekord és a fizikai fájl végleges törlését kizárólag Admin végezheti el, pontos `TÖRÖL` megerősítéssel.

A munkalap-archívum a **Munkalapok** oldal aloldala. A munkalaplista sorai kibonthatók, és a kapcsolt archív fájlok közvetlenül a munkalap alatt jelennek meg. A PDF-, JPG- és PNG-fájlok hitelesített előnézetben is megnyithatók.

API-végpontok:

```text
POST /api/work-orders/{work_order_id}/archives
GET  /api/work-orders/{work_order_id}/archives
POST /api/assets/{asset_id}/work-order-archives
GET  /api/assets/{asset_id}/work-order-archives
GET  /api/work-order-archives/paged
GET  /api/work-order-archives/{archive_id}/preview
GET  /api/work-order-archives/{archive_id}/download
DELETE /api/work-order-archives/{archive_id}
```

## 4. Indítás

```bash
cp .env.example .env
docker compose up --build
```

A backend Docker build a projektgyökér `VERSION` fájlját is beépíti az image-be.

Elérhetőségek:

- Frontend: `http://localhost:3000`
- Backend health check: `http://localhost:8000/api/health` vagy proxyn keresztül `http://localhost:3000/api/health`
- Swagger/OpenAPI dokumentáció: `http://localhost:8000/docs` vagy proxyn keresztül `http://localhost:3000/docs`

## 5. Első belépés

Alap admin felhasználó friss telepítésnél:

- Email: `admin@example.com`
- Kezdeti jelszó: üres

A bejelentkezési mezők nincsenek előre kitöltve. Az első admin belépéshez kézzel add meg az email címet, a jelszómezőt hagyd üresen. A rendszer a belépés után azonnal kötelező jelszócserére irányít, és addig más funkció nem használható.

Minta technikus:

- Email: `technikus@example.com`
- Ideiglenes jelszó: `Technikus!123`

Minta irodai felhasználó:

- Email: `iroda@example.com`
- Ideiglenes jelszó: `Iroda!123`

A frissen létrehozott és az admin által új jelszót kapó felhasználóknak az első belépéskor saját jelszót kell választaniuk. Minden felhasználó az oldalsáv **Jelszó módosítása** pontjában változtathatja meg a saját jelszavát a jelenlegi jelszó megadásával. Az új jelszó legalább 8 karakteres, legalább egy nagybetűt és egy speciális karaktert tartalmaz.

### Elfelejtett jelszó helyreállítása VS Code-ból

A jelszó-visszaállítás szándékosan nem érhető el webes API-n. Csak a szerveren, a projekt könyvtárából futtatható helyi parancsként használható.

A backend konténer futása közben VS Code-ban:

1. Nyisd meg a **Terminal → Run Task...** menüt.
2. Válaszd az **Admin jelszó helyreállítása** feladatot.
3. Add meg kétszer az új ideiglenes jelszót. A karakterek gépelés közben nem jelennek meg.
4. Jelentkezz be az ideiglenes jelszóval. A rendszer azonnal kötelező saját jelszócserére irányít.

Ugyanez közvetlenül a VS Code terminálból:

```powershell
docker compose exec backend python -m app.reset_password --email admin@example.com --activate
```

Más felhasználó jelszavának visszaállítása:

```powershell
docker compose exec backend python -m app.reset_password --email felhasznalo@example.com
```

A jelszó legalább 8 karakteres, legalább egy nagybetűt és egy speciális karaktert tartalmaz. A parancs nem írja ki és nem naplózza a jelszót. A művelet auditbejegyzést készít, és `must_change_password` állapotot kapcsol be. Az `--activate` kapcsoló csak akkor használandó, ha a helyreállítandó fiókot egyben aktiválni is kell.

### Jelszókezelési API

```text
GET  /api/auth/me
POST /api/auth/change-password
```

A jelszócsere kérés `current_password` és `new_password` mezőt fogad. Kötelező jelszócsere állapotban a `/api/auth/me` és `/api/auth/change-password` kivételével minden hitelesített végpont blokkolt.

## 6. Migráció és seed futtatása

A backend konténer induláskor automatikusan lefuttatja:

```bash
alembic upgrade head
python -m app.seed
```

Kézi futtatás, ha már futnak a konténerek:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

A seed script idempotens jellegű: az alap szerepköröket és felhasználókat nem duplikálja, a példa adatokat csak üres üzleti adatbázis esetén tölti be.


### Szállítói cégprofilok

A munkalap nyomtatási nézete és a kompatibilitási Excel-export a telepített cégprofilokat használja. A program a munkalap ügyfelének `company_code` mezője, majd a kapcsolt eszközök `company_code` mezője alapján választja ki, melyik cégadat kerüljön a szállítói részbe.

Támogatott kódok:

| Kód | Céges és munkalapi adatok forrása |
|---|---|
| DRH / DRh | Helyben telepített privát cégprofil |
| SP | Helyben telepített privát cégprofil |
| GXR | Helyben telepített privát cégprofil |

A korábbi helyi fájl vagy a `RUNTIME_DIR` alatti fájl adja a részletes mezőket:

```text
backend/app/data/company_profiles.json
```

API végpont bejelentkezett felhasználóval:

```text
GET /api/settings/companies
```

A `Beállítások` oldalon külön táblázat mutatja a betöltött cégprofilokat. Admin jogosultsággal az általános cégadatoktól független `Munkalapi szolgáltatási telefon` és `Munkalapi helpdesk email` mezők is szerkeszthetők. A nyomtatott szállítói blokk nem jeleníti meg a cégprofil kapcsolattartóját és webcímét.


### Egységes globális Excel-import

Az admin felületen egyetlen importfunkció használható: **Beállítások → Globális Excel-import**. A globális munkafüzet három importált munkalapot kezel:

- `Eszközök`: ügyfél, helyszín, elsődleges kapcsolattartó, eszköztörzs, utolsó karbantartás és szerződéses karbantartási ciklus;
- `Kapcsolattartók`: ügyfelenként és helyszínenként több, Szerviz / Sales / Egyéb típusú kapcsolattartó;
- `Számlálók`: több történeti összes, FF, színes és scan számlálóállás eszközönként.

A mintafájl a felületen az importmező mellett tölthető le, és a projektben is megtalálható:

```text
imports/globalis_import_minta.xlsx
```

A **Jelenlegi adatok exportálása** gomb a futó adatbázisból ugyanilyen szerkezetű, közvetlenül visszaimportálható Excel-fájlt készít. Az export tartalmazza az összes eszközt és karbantartási mezőjét, a kapcsolattartókat, valamint a teljes összes, FF, színes és scan számlálótörténetet. Az export adminisztrátori funkció.

Használat:

1. Új adatbevitelhez töltsd le a **Mintafájl letöltése** gombbal a sablont, vagy mentéshez kattints a **Jelenlegi adatok exportálása** gombra.
2. Töltsd ki vagy szükség esetén módosítsd az `Eszközök`, `Kapcsolattartók` és `Számlálók` lapot.
3. Töltsd fel a fájlt.
4. Futtasd az **Import ellenőrzése** műveletet.
5. Ha nincs kritikus hiba, indítsd el a **Globális importot**.

Az import idempotens. Az eszközazonosítás sorrendje: belső azonosító, gyári szám + cégkód, majd egyedi gyári szám. Az üres cellák nem törlik a meglévő adatot. Újabb karbantartási dátumot régebbi importérték nem ír felül, az összes számláló monoton sorrendjét sértő sor pedig ütközésként jelenik meg. Az azonos időponthoz tartozó korábbi összes számlálósor FF, színes és scan értékekkel utólag kiegészíthető.

API végpontok:

```text
GET  /api/imports/global/template
GET  /api/imports/global/export
POST /api/imports/global/preview
POST /api/imports/global/run
```

A korábbi külön ügyfél/eszköz-, számláló-, karbantartási dátum- és ciklusimport végpontok csak visszamenőleges kompatibilitás miatt maradtak meg; az admin felületen már nem jelennek meg.

### Excel ügyfél- és eszközlista import

A helyi telepítés tartalmazhatja az `Ügyfél_lista_20260616 másolata.xlsx` fájl adataiból készített, privát importállományt: `backend/app/data/customer_assets_20260616.json`. A Git és a Docker-kép ezt nem tartalmazza. A nem production seed csak akkor tölti be / frissíti az adatokat, ha a fájl külön telepítve van.

Importált mennyiség:

- 255 érvényes Excel adatsor,
- 124 egyedi szerződött ügyfélnév, 125 importált ügyfélrekord cégkód szerinti bontásban,
- 255 eszköz,
- cégkódok: DRh, SP, GXR, Priz.

Az Excel oszlopok megfeleltetése:

| Excel oszlop | Rendszer mező |
|---|---|
| Cég | ügyfél `company_code` és eszköz `company_code` |
| Ügyfél neve - szerződött | ügyfél neve |
| Cím | ügyfél címe, illetve helyszíncím, ha nincs külön telephelycím |
| Telephely név | helyszín neve |
| Telephely cím | helyszín címe |
| Név | ügyfél kapcsolattartója |
| Telefonszám | ügyfél telefonszáma |
| email cím | ügyfél email címe és külön `Szerviz` kapcsolattartó |
| Gép típusa | eszköz típusa, gyártó/modell/kategória alapkitöltéssel |
| Gyáriszám | eszköz gyári száma |

Mivel az Excelben nincs külön belső eszközazonosító, az import stabil, soralapú belső azonosítót generál:

```text
IMP-20260616-0002
```

ahol az utolsó négy szám az eredeti Excel sor száma. Ez azért biztonságosabb, mert a gyári szám nem minden esetben egyedi.

Kézi újrafuttatás parancssorból:

```bash
docker compose exec backend python -m app.import_customer_assets
```

Böngészőből is ellenőrizhető és újrafuttatható:

1. Jelentkezz be admin felhasználóval.
2. Nyisd meg: `http://localhost:3000/settings`.
3. Az **Excel import: ügyfelek, helyszínek és eszközök** panelen látható az importált eszközök száma, a cégenkénti bontás és néhány minta rekord.
4. Kattints az **Excel adatok importálása / frissítése** gombra.
5. Utána az adatok az `Ügyfelek` és `Eszközök` menüpontban látszanak.

API végpontok admin felhasználóval:

```text
GET  /api/imports/customer-assets/status
POST /api/imports/customer-assets/run
```

Az import nem duplikál: meglévő `IMP-20260616-....` eszközöket frissít, új sorokat létrehoz.

Az import technikai adatai nem kerülnek az eszköz **Megjegyzés** mezőjébe. Ismételt import vagy frissítés során a korábbi automatikus import-megjegyzésblokkokat és az önálló `IMP-...` megjegyzéssorokat eltávolítja, miközben a kézzel rögzített megjegyzéseket megőrzi.

## 7. Fő funkciók

### Felhasználók, modulok és jogosultságok

- Bejelentkezés JWT tokennel; sikeres belépés után modulválasztó jelenik meg.
- Meglévő szerepkörök: Admin, Irodai felhasználó, Technikus / szerelő. Ezek továbbra is a Szerviz modul műveleti jogosultságait szabályozzák.
- Külön adatbázis-alapú modul- és funkciójogok: `service.access`, `hr.access`, `hr.leave.self`, `hr.leave.request`, `hr.leave.approve`, `hr.summary.view`, `hr.admin`, `crm.access`, `crm.write`, `crm.contract.manage`, `crm.admin`.
- Az Admin szerepkör minden modulhoz és funkcióhoz hozzáfér. Normál felhasználónál a backend minden kérésnél az adatbázisból ellenőrzi az aktuális jogosultságot; a jogosultsági lista nincs a JWT-be beégetve.
- Az Admin felhasználókat hozhat létre, módosíthat és törölhet, valamint modul- és funkciójogokat rendelhet hozzájuk.
- A frontend route-védelem csak UX-réteg; a Szerviz végpontok backend-szinten is `service.access` jogot kérnek.
- Jelszavak bcrypt hash formában tárolódnak.

### Ügyfelek, helyszínek és kapcsolattartók

- Ügyfél CRUD.
- Több helyszín egy ügyfélhez.
- Helyszínek külön listázhatók és ügyfélhez kapcsolva kezelhetők.
- Egy ügyfélhez több kapcsolattartó rögzíthető.
- Kapcsolattartó kategóriák: `Szerviz`, `Sales`, `Egyéb`.
- Kapcsolattartó opcionálisan konkrét helyszínhez is köthető.
- Egy kategórián belül megjelölhető elsődleges kapcsolattartó.
- Az Excel import a régi egy soros kapcsolattartói adatokat külön `Szerviz` kapcsolattartóként is létrehozza.

### Eszköznyilvántartás

- Eszköz CRUD.
- Keresés és szűrés azonosító, gyári szám, típus, ügyfél, helyszín és státusz alapján.
- Eszköztörténet: létrehozás, státuszváltozás, helyszínváltozás, munkalaphoz kapcsolás és munkalapról leválasztás naplózása.
- Az Eszközök oldalon a **Történet** gomb megnyitja az eszköz összes aktuális vagy korábbi kapcsolódó munkalapját teljes tartalommal: feladatleírás, státusz, dátumok, technikus, elvégzett munka, megjegyzések, kapcsolt eszközök és anyagfelhasználás.

### Nyomtatók számláló- és alkatrészkövetése

Az Eszközök oldalon a **Számláló / alkatrész** gomb nyitja meg a nyomtatókövetési adatlapot. A funkció bármely eszköznél használható, ezért a meglévő importált nyomtatókat nem kell újra létrehozni.

Funkciók:

- összes, FF, színes és scan számláló kézi rögzítése dátummal, munkalappal és technikussal;
- az összes számláló monoton validációja; a részletes csatornák eszköz- vagy vezérlőcsere után újraindulhatnak;
- a munkalap Áttekintés és Szerkesztés nézetéből közvetlenül rögzíthető összes, FF, színes és scan számláló;
- a munkalap részletező és böngészős nyomtatási nézetén az utolsó ismert számlálók a mérés dátumával együtt jelennek meg;
- követett alkatrészek felvétele cikkszámmal és várható oldalkapacitással;
- utolsó csere dátumának és cserekori számlálójának tárolása;
- alkatrészcsere rögzítése az eszközoldalról vagy közvetlenül a kapcsolódó munkalapról;
- csereelőzmények technikussal, felhasznált anyaggal és munkalapszámmal;
- átlagos havi használat számítása az utolsó legfeljebb 180 nap számlálóadataiból, 30 napos normalizált hónappal;
- hátralévő oldalszám és várható csereidő kiszámítása;
- Dashboard figyelmeztetés esedékes, 30 napon belül várható és elavult számlálóadatokra.

Az előrejelzés legalább két növekvő számlálóállást, valamint az alkatrész várható élettartamát és utolsó cserekori számlálóját igényli. Hiányos adatoknál a rendszer nem talál ki dátumot, hanem **Nincs elegendő adat** állapotot mutat.

API végpontok:

```text
GET    /api/assets/{asset_id}/printer-tracking
POST   /api/assets/{asset_id}/meter-readings
DELETE /api/assets/{asset_id}/meter-readings/{reading_id}
POST   /api/assets/{asset_id}/components
PUT    /api/assets/{asset_id}/components/{component_id}
DELETE /api/assets/{asset_id}/components/{component_id}
POST   /api/assets/{asset_id}/component-replacements
GET    /api/dashboard/printer-maintenance
```

### Munkalapok

- A munkalaplista, a részletező nézet, a létrehozás és a szerkesztés külön böngészős oldalakon érhető el.
- Munkalap létrehozás, szerkesztés, sztornózás és lezárás.
- Ügyfélhez tartozó kapcsolattartó kiválasztható a munkalapon; a lista ügyfélre és helyszínre szűrődik.
- Ha nincs kézzel kiválasztott kapcsolattartó, a rendszer a helyszínhez illő elsődleges `Szerviz`, majd `Sales`, majd `Egyéb` kapcsolattartót használja.
- A nyomtatási kép és az Excel munkalap a kiválasztott vagy automatikusan feloldott kapcsolattartó nevét, telefonját és e-mail-címét használja.
- Automatikus munkalapszám: `ML-ÉV-SORSZÁM` formátum. PostgreSQL-adatbázis-szekvencia biztosítja, hogy párhuzamos létrehozáskor se keletkezzen azonos munkalapszám.
- Optimista zárolás védi a munkalapokat: minden rekord verziószámot kap. Ha valaki egy időközben más által módosított munkalapot próbál menteni, a rendszer `409 Conflict` választ ad, megakadályozza a felülírást, és a frontend betölti a legfrissebb változatot.
- Több eszköz kapcsolható egy munkalaphoz.
- Egy munkalaphoz elsődleges és opcionális második technikus rendelhető; mindkét technikus jogosult a saját munkalap lezárására.
- Több külön anyagsor rögzíthető és szerkeszthető egy munkalapon.
- Lista szűrőkkel: státusz, dátumintervallum, ügyfél, technikus, prioritás, eszköz.
- Böngészőből nyomtatható, külön munkalap-részletező oldal.
- A munkalap részletező fő műveletei: szerkesztés, lezárás, archiválás és nyomtatás.
- A korábbi Excel munkalap gomb kikerült a felületről. A kitöltött `.xlsx` export kompatibilitási célból továbbra is elérhető az API-n.

Kompatibilitási Excel munkalap API végpont:

```text
GET /api/work-orders/{order_id}/worksheet.xlsx
```

Kapcsolattartó API végpontok:

```text
GET    /api/customers/{customer_id}/contacts
POST   /api/customers/{customer_id}/contacts
PUT    /api/customers/{customer_id}/contacts/{contact_id}
DELETE /api/customers/{customer_id}/contacts/{contact_id}
```

A kompatibilitási Excel-export a sablonba tölti a cégkód alapján kiválasztott DRH / SP / GXR szállítói adatokat, az ügyfél/helyszín adatokat, munkalapszámot, prioritást, státuszt, kapcsolt eszközöket, feladatleírást, mindkét technikust, tényleges kezdés/befejezés időpontját, felhasznált anyagokat, elvégzett munkát, végállapotot és megjegyzéseket.

### Anyagok

- Egyszerű anyagnyilvántartás.
- Cikkszám, név, mennyiségi egység, egységár, készlet és megjegyzés kezelése.

### Naplózás

Audit log készül fontos műveletekre:

- létrehozás,
- módosítás,
- törlés / sztornózás,
- státuszváltás,
- lezárás.

### Dashboard

A nyitóoldal mutatói:

- nyitott munkalapok száma,
- sürgős munkalapok száma,
- ma esedékes munkalapok,
- lejárt / esedékes karbantartások,
- hibás vagy javítás alatt lévő eszközök.

### Export / nyomtatás

- Eszközlista CSV export.
- Munkalaplista CSV export.
- Munkalap részletező böngészőből nyomtatható.
- Munkalap Excel export a csatolt, paraméterezhető sablon alapján.

## 8. Rövid architektúra

```text
munkalap-eszkoz-app/
├── backend/
│   ├── app/
│   │   ├── routers/       API modulok
│   │   ├── services/      audit, cégprofilok, munkalap-sablon és üzleti segédfüggvények
│   │   ├── importers/     Excelből előállított ügyfél/eszköz import
│   │   ├── data/          importált ügyfél- és eszközadatok JSON formában
│   │   ├── templates/     Excel munkalap sablon
│   │   ├── models.py      SQLAlchemy modellek
│   │   ├── schemas.py     Pydantic validációs sémák
│   │   ├── security.py    jelszóhash és JWT
│   │   ├── seed.py        seed adatok
│   │   └── main.py        FastAPI alkalmazás
│   ├── migrations/        Alembic migrációk
│   └── tests/             backend API tesztek
├── frontend/
│   ├── src/pages/         React oldalak
│   ├── src/components/    közös komponensek
│   └── src/styles/        CSS
├── docker-compose.yml
└── .env.example
```

A frontend nginx statikus kiszolgálóként fut, és a `/api/*` kéréseket Docker hálózaton belül a backend konténer felé proxizza. Így a böngészőnek elég a `http://localhost:3000` címet elérnie, és nem függ külön a backend host-port böngészőoldali elérésétől. A backend kizárólag PostgreSQL-ből dolgozik; a mintaadatok seed scriptből kerülnek az adatbázisba.

## 9. Fejlesztői megjegyzések

### Backend tesztek futtatása

Konténeren belül:

```bash
docker compose exec backend pytest
```

Lokális Python környezetben:

```bash
cd backend
pip install -r requirements.txt
pytest
```


### VS Code `.env` figyelmeztetés

Ha VS Code ezt írja:

```text
An environment file is configured but terminal environment injection is disabled. Enable "python.terminal.useEnvFile" to use environment variables from .env files in terminals.
```

ez nem alkalmazáshiba, hanem a VS Code Python bővítmény figyelmeztetése. A projekt tartalmaz egy `.vscode/settings.json` fájlt, amely engedélyezi a root `.env` fájl terminálba injektálását:

```json
{
  "python.envFile": "${workspaceFolder}/.env",
  "python.terminal.useEnvFile": true
}
```

A beállítás érvényesítéséhez zárd be a régi integrált terminált, majd nyiss újat. Docker Compose használatakor a compose továbbra is a projektgyökérben lévő `.env` fájlt használja.

### Új migráció készítése fejlesztés közben

```bash
docker compose exec backend alembic revision --autogenerate -m "valtozas leirasa"
docker compose exec backend alembic upgrade head
```

### Stabilitási döntések

- A PDF generálás nem került beépítésre, mert a böngészős nyomtatási nézet stabilabb és kevesebb mozgó alkatrészt igényel.
- A munkalap-sztornózás logikai státuszváltással történik, nem fizikai törléssel. Ez auditálhatóbb és üzleti rendszernél biztonságosabb.
- A frontend konténer többfázisú buildet használ: Vite elkészíti a statikus React buildet, majd nginx szolgálja ki a `3000`-es konténerporton. Ez stabilabb, mint a Vite dev szerver konténeres futtatása.
- A frontend API-hívásai alapértelmezetten relatív `/api` útvonalon mennek. Az nginx ezt a backend konténer `http://backend:8000/api` címére továbbítja, ezért nincs külön böngészőoldali CORS- vagy backend-port függés.
- A React alkalmazás kapott hibahatár-komponenst. Ha böngészőoldali renderelési hiba történik, üres fehér képernyő helyett látható hibapanel jelenik meg.


## Hibaelhárítás

### Frontend nem érhető el a `http://localhost:3000` címen

Ellenőrizd, hogy a frontend konténer ténylegesen fut-e:

```bash
docker compose ps
docker compose logs frontend
```

A frontend nginx alapú statikus kiszolgálóként fut a konténerben. Ha korábbi Vite dev szerveres image maradt cache-ben, építsd újra cache nélkül:

```bash
docker compose down
docker compose build --no-cache frontend
docker compose up
```

Ha a `.env` fájlban az `APP_PORT` értékét átírtad, akkor nem feltétlenül a `3000`-es porton lesz elérhető. Példa: `APP_PORT=3100` esetén a cím `http://localhost:3100`.


### A frontend log szerint 200-as válasz van, de a böngésző üres oldalt mutat

A projektben erre két védelem van:

1. Az `index.html` azonnali betöltési szöveget mutat, amíg a React elindul.
2. A React hibahatár látható hibapanelt jelenít meg, ha a böngészőoldali renderelés hibára fut.

Cache-elt régi frontend image vagy régi böngésző cache esetén futtasd:

```bash
docker compose down
docker compose build --no-cache frontend
docker compose up
```

Utána a böngészőben nyomj teljes frissítést: `Ctrl+F5`. Ha továbbra is üres, ellenőrizd:

```bash
curl http://localhost:3000/health
curl http://localhost:3000/api/health
```

Mindkettőnek választ kell adnia.

### `error reading bcrypt version` vagy `password cannot be longer than 72 bytes` induláskor

Ez a `passlib` és az újabb `bcrypt` csomagverziók ismert inkompatibilitása. A projekt a `backend/requirements.txt` fájlban explicit módon a stabil `bcrypt==4.0.1` verziót használja. Ha korábbi image épült már fel, futtasd újra cache nélkül:

```bash
docker compose down
docker compose build --no-cache backend
docker compose up
```

Ha a seed korábban félbeszakadt, **ne töröld a volume-okat**. Előbb készíts biztonsági mentést, majd ellenőrizd a backend logot és az Alembic állapotot:

```bash
docker compose logs --tail=200 backend
docker compose exec -T backend alembic heads
docker compose exec -T backend alembic current
```

A `docker compose down -v` éles vagy megőrzendő adatokkal rendelkező környezetben tiltott, mert törli a tartós volume-okat.


### Nem látszanak az Excelből importált ügyfelek / eszközök

Ellenőrizd először az import státuszt a böngészőben:

```text
http://localhost:3000/settings
```

Az **Excel import: ügyfelek, helyszínek és eszközök** panelnek mutatnia kell az importált eszközök számát. Ha 0, futtasd ugyanott az **Excel adatok importálása / frissítése** gombot.

Parancssoros ellenőrzés:

```bash
docker compose exec backend python -m app.import_customer_assets
docker compose exec db psql -U workapp -d workapp -c "select import_batch, count(*) from assets group by import_batch;"
```

Ha a parancs 255 körüli importált eszközt mutat, de a böngészőben nem frissül, nyomj `Ctrl+F5`-öt, vagy lépj ki és jelentkezz be újra. Ha a lekérdezés 0-t mutat, akkor a backend nem az új verziójú kódból fut; ilyenkor építsd újra a backendet:

```bash
docker compose down
docker compose build --no-cache backend frontend
docker compose up
```

### Frontend build megáll `RUN npm install` / `RUN npm ci` lépésnél

A frontend Docker build internetkapcsolatot igényel az npm csomagok letöltéséhez. A projektben a lockfile publikus npm registry URL-eket használ. Ha vállalati hálózat/proxy blokkolja az npm registry-t, a build ezen a ponton várakozhat.

Ellenőrzés:

```bash
cd frontend
npm ping --registry=https://registry.npmjs.org/
```

Ha ez sem válaszol, a Docker build sem fog tudni csomagokat letölteni. Ilyenkor proxy vagy DNS beállítás szükséges Docker Desktopban / a hálózaton.

### Hibaelhárítás: `React is not defined`

Ha a böngészőben az jelenik meg, hogy `React is not defined`, akkor a frontend régi buildből fut vagy a JSX transzformáció nem a megfelelő React runtime-mal készült. A projekt tartalmaz `frontend/vite.config.js` konfigurációt és minden JSX fájl explicit React importot használ. Javítás után cache nélküli frontend build szükséges:

```bash
docker compose down
docker compose build --no-cache frontend
docker compose up
```

Böngészőben teljes frissítés: `Ctrl + F5`.

## Változás: ügyfél-helyszín-eszköz összetartozás munkalap létrehozáskor

A `http://localhost:3000/work-orders` oldalon a munkalap űrlap már az importált Excel sorlogikáját követi:

- ügyfél kiválasztása után csak az adott ügyfél helyszínei választhatók,
- eszközlistában csak a kiválasztott ügyfélhez tartozó eszközök jelennek meg,
- ha helyszínt is választasz, a lista tovább szűkül az adott helyszín eszközeire,
- eszköz választásakor a felület automatikusan kitölti / megtartja a hozzá tartozó ügyfél- és helyszínkapcsolatot,
- az űrlap külön ellenőrző kártyán mutatja a kapcsolt ügyfél-, helyszín-, kapcsolattartó- és eszközadatokat,
- a munkalaplista szűrőinél az eszközszűrő is igazodik a kiválasztott ügyfélhez.

A szabály backend oldalon is érvényesül: az API `400` hibát ad, ha más ügyfél eszközét vagy más helyszínhez tartozó eszközt próbálnak munkalaphoz kapcsolni. Ez azért fontos, mert így nem csak a böngészős felület, hanem a közvetlen API-hívás sem tud inkonzisztens munkalapot létrehozni.

## Változás: cégadatok a böngészős nyomtatási képen

A munkalap részletező oldalon a `Nyomtatás` gomb már nem az egyszerű részletező kártyát nyomtatja. A böngészős nyomtatási nézet külön munkalap-formátumot kapott:

- bal oldalon a szállító / szolgáltató adatai jelennek meg,
- jobb oldalon a vevő / megrendelő adatai jelennek meg,
- a szállítói cégadatok a Beállításokban Admin által szerkeszthető profilokból töltődnek, a munkalap ügyfelének vagy kapcsolt eszközének `company_code` mezője alapján,
- támogatott kódok: `DRH` / `DRh`, `SP`, `GXR`,
- látható a munkalapszám, státusz, prioritás, legfeljebb két technikus, tényleges munkavégzési idő, eszközök, elvégzett munka, végállapot és aláírási blokk;
- a kiállítás dátuma és a belső tervezett idő nem jelenik meg a nyomtatott munkalapon.
- a Munkalapok alaplistája és az Áttekintés nézet közvetlenül mutatja a kapcsolt gépek típusát és gyári számát.

Használat:

1. Nyisd meg: `http://localhost:3000/work-orders`
2. Egy munkalapnál kattints: `Részletek`
3. Kattints: `Nyomtatás`

A böngészős `Nyomtatás` a támogatott, felhasználói munkalap-kimenet. A régi Excel export csak kompatibilitási API-ként maradt meg.

## Frissítés: eszközválasztás törlése munkalapon

A `Munkalapok` oldalon az új/szerkesztett munkalap űrlapon a `Kapcsolódó eszközök` mező alatt elérhető az `Eszközválasztás törlése` gomb. A gomb egy kattintással törli a kiválasztott eszközöket, törli a helyszínszűrőt is, és a kapcsolódó eszközök listáját visszaállítja az ügyfélhez tartozó teljes eszközlistára. Az ügyfél kiválasztása megmarad.

Ez a javítás azért szükséges, mert a kapcsolódó eszközlista szűrése a `location_id` mezőből számolódik. Ha a helyszín megmarad, a lista továbbra is helyszínre szűrt maradna, akkor is, ha az eszközválasztás már üres.

## 10. Technikuskezelés a Beállítások oldalon

Admin felhasználó a `http://localhost:3000/settings` oldalon külön **Technikusok** panelt lát.

Itt lehet:

- új technikust létrehozni névvel, email címmel és jelszóval;
- technikust aktiválni vagy inaktiválni;
- nevet, email címet és jelszót módosítani;
- technikust törölni.

Az itt létrehozott felhasználó automatikusan a `Technikus / szerelő` szerepkört kapja. A funkció frontend- és backend-oldalon is Admin jogosultsághoz kötött.

API végpontok:

```text
GET    /api/settings/technicians
POST   /api/settings/technicians
PATCH  /api/settings/technicians/{technician_id}
DELETE /api/settings/technicians/{technician_id}
```

## 11. Teljes adatbázis- és beállításmentés

A **Beállítások** oldalon Admin jogosultsággal letölthető egy teljes ZIP mentés. A csomag tartalma:

- az alkalmazás összes adatbázistáblája és minden rekordja;
- felhasználók, szerepkörök és jelszóhashek;
- ügyfelek, helyszínek és kapcsolattartók;
- eszközök, eszköztörténet és munkalapok;
- anyagok, anyagfelhasználás és auditnapló;
- alkalmazásbeállítások, beleértve a JWT titkos kulcsot;
- DRH / SP / GXR cégprofilok;
- az aktuális Excel munkalap-sablon;
- ellenőrzőösszegek és mentési jegyzék.

A mentési fájl bizalmas, mert felhasználói és biztonsági adatokat is tartalmaz.

### Teljes visszaállítás

1. Nyisd meg Admin felhasználóval a `Beállítások` oldalt.
2. Válaszd ki a korábban exportált ZIP fájlt.
3. Írd be pontosan: `VISSZAÁLLÍTÁS`.
4. Indítsd el a teljes visszaállítást.
5. A művelet után futtasd:

```bash
docker compose restart backend
```

6. Jelentkezz be a mentésben szereplő felhasználói adatokkal.

A visszaállítás a jelenlegi alkalmazásadatokat teljesen lecseréli. A PostgreSQL elérési adatai és a Docker host-portok nem kerülnek felülírásra; ezeket továbbra is a célgép `.env` fájlja szabályozza. Ez szándékos biztonsági döntés, mert egy másik gépről származó adatbázis-URL vagy portbeállítás indíthatatlanná tehetné a konténert.

A visszaállított alkalmazásbeállításokat és fájlokat az `app_runtime` Docker volume tartja meg, ezért azok a backend image újraépítése után is megmaradnak.

API végpontok:

```text
GET  /api/settings/backup
POST /api/settings/restore
```

A visszaállítás csak a program által létrehozott, sértetlen és az aktuális adatbázissémával kompatibilis mentést fogadja el.

## 12. Admin által szerkeszthető nyomtatási szállítói adatok

A `Beállítások → Nyomtatási szállítói adatok` panelen Admin jogosultsággal szerkeszthetők a `DRH`, `SP` és `GXR` cégprofilok. Módosítható többek között:

- rövid és teljes cégnév;
- cégkód-aliasok;
- adószám és cégjegyzékszám;
- székhely és kapcsolati cím;
- telefon, mobiltelefon, email és weboldal;
- kapcsolattartó és tevékenység;
- belső forrásmegjegyzés.

A módosítások az `app_runtime` Docker volume-ban tárolódnak, ezért image-újraépítéskor nem vesznek el. Az új adatok azonnal használatba kerülnek a böngészős munkalap-nyomtatásban és az Excel munkalap-exportban. A teljes rendszermentés a szerkesztett cégprofilokat is tartalmazza.

API:

```text
GET /api/settings/companies
PUT /api/settings/companies/{company_code}
```

A módosító végpont kizárólag Admin szerepkörrel érhető el.

## 13. Heti Outlook-jellegű munkalap-naptár

A Dashboardon megjelenik az aktuális hét óránkénti naptára. Az `Előző hét`, `Aktuális hét` és `Következő hét` gombokkal más hetek is megtekinthetők.

A naptár működése:

- minden technikus külön színt kap;
- a kijelöletlen munkalapok szürke színnel jelennek meg;
- a nyitott vagy tervezett munkalapok tömör színű kártyák;
- a lezárt munkalapok halványabb, csíkozott és pipával jelölt kártyák;
- sürgős, még nyitott munkalapok piros kiemelést kapnak;
- az egymást átfedő munkalapok egymás mellett jelennek meg;
- az aktuális időt piros vízszintes vonal mutatja.

A munkalap új időmezői:

- `Tervezett kezdés`;
- `Tervezett befejezés`;
- `Tényleges kezdés`;
- `Tényleges befejezés`.

Nyitott munkalapnál a naptár elsősorban a tervezett időtartamot mutatja. Lezárt munkalapnál a tényleges kezdés–befejezés jelenik meg. Régi munkalap esetén, ahol csak tervezett nap áll rendelkezésre, a rendszer 09:00–10:00 közötti ideiglenes blokkot mutat, hogy a rekord látható és később pontosítható legyen.

API:

```text
GET /api/dashboard/calendar?week_start=2026-07-13
```

## Frissítés erre a verzióra

A meglévő adatbázist ne töröld. A backend induláskor automatikusan lefuttatja az összes hiányzó migrációt. A `0014_user_password_policy` a kötelező jelszócsere állapotát, a `0015_secondary_technician` az opcionális második technikust, a `0016_work_order_contract_type` a munkalap opcionális szerződéstípusát, a `0017_module_permissions` pedig a modul- és funkciójogosultsági táblákat adja hozzá. A `0017` frissítéskor minden meglévő felhasználónak automatikusan megőrzi a Szerviz hozzáférését. A munkalaptípusok a meglévő `work_type` mezőt használják:

```powershell
cd C:\Users\alazar.DELFIN\Downloads\munkalap-eszkoz-app
docker compose down
docker compose build --no-cache backend frontend
docker compose up
```

A böngészőben ezután nyomj `Ctrl + F5`-öt. A `docker compose down -v` parancsot ne használd, mert az törölné az adatbázist és az alkalmazásbeállításokat tároló volume-okat.


## Dashboard naptárból munkalap megnyitása

A heti naptárban egy munkalapkártyára kattintva a rendszer közvetlenül az adott munkalap külön részletező oldalára navigál. A kártyák billentyűzettel is megnyithatók Enter vagy Szóköz használatával.


### Importált eszközök technikai azonosítói

Az Excel-import által használt `IMP-YYYYMMDD-NNNN` technikai kulcsok kizárólag a háttérben szolgálják az idempotens frissítést. Nem jelennek meg az eszközlistában, a munkalapokon, a nyomtatási képen, az Excel munkalapon, a CSV exportban vagy az import státusz mintalistájában. Az importált eszközök a típusuk, gyártójuk és gyári számuk alapján jelennek meg.

## Nyomtatott munkalap mezői

- A munkalapokon a `Munka típusa` választható: karbantartás, javítás, eseti javítás, kiszállítás vagy üzembe helyezés.
- A böngészős nyomtatási képen a rögzített tényleges kezdés, befejezés és munkaidő jelenik meg.
- A kiállítás dátuma, a tervezett kezdés és a tervezett befejezés nem jelenik meg a nyomtatási képen.
- A Hiba / feladat leírása mező kétszeres minimális magasságú.

## Nyomtatott munkalap elrendezése

A nyomtatási nézet és az Excel munkalap az alábbi szabályokat követi:

- az ügyfélnek látható megjegyzés mező nem jelenik meg, és az új/szerkesztett munkalap űrlapon sem használható;
- a felhasznált anyagok az alkalmazásban továbbra is rögzíthetők és megtekinthetők, de nyomtatásban nem jelennek meg;
- az Elvégzett munka mező nagyobb nyomtatási területet kapott;
- a technikusi adatoknál mindkét kijelölt technikus neve megjelenik.


## Nyomtatási elrendezés

- Az **Elvégzett munka** mező a böngészős és Excel munkalapon is megnövelt kézi kitöltési területet kap.
- A **Végállapot** és az aláírások között nagyobb függőleges tér marad.
- Az Excel export nyomtatási területe automatikusan az aláírások soráig terjed.


## Többfelhasználós működés és konkurenciavédelem

A backend alapértelmezés szerint három Uvicorn workerrel indul. A PostgreSQL-kapcsolatkezelés worker-enként külön connection poolt használ, így több felhasználó párhuzamos kérései nem egyetlen Python folyamaton sorakoznak.

A három beépített védelem:

1. **Adatbázis-szekvenciás munkalapszám** – PostgreSQL `work_order_number_seq` állítja elő a sorszámot. A `MAX(id) + 1` alapú versenyhelyzet megszűnt.
2. **Optimista zárolás** – a `work_orders.version` mező minden mentésnél növekszik. Szerkesztés, lezárás és sztornózás csak az ügyfél által megnyitott verzióval hajtható végre. Elavult verzió esetén a rendszer nem írja felül más munkáját.
3. **Több backend worker** – az alapérték `BACKEND_WORKERS=3`; kisebb belső rendszerhez ez megfelelő kiindulás. A teljes elméleti adatbázis-kapcsolati maximum az alapbeállításokkal `3 × (5 + 5) = 30`.

A migráció neve:

```text
0006_work_order_concurrency
```

Meglévő telepítés frissítése:

```bash
docker compose down
docker compose build --no-cache backend frontend
docker compose up
```

Az adatbázis-volume-ot ne töröld. A migráció automatikusan létrehozza a verziómezőt és a PostgreSQL-szekvenciát, majd a meglévő munkalapszámok alapján a következő szabad sorszámra állítja. A teljes mentés/visszaállítás a régebbi, verziómező nélküli mentéseket is `version=1` értékkel tudja visszatölteni.

## Aktív munkalap-szerkesztés jelzése

A rendszer a mentéskori optimista zárolás mellett már a szerkesztés megkezdésekor is jelzi a párhuzamos munkát.

- A **Szerkesztés** gomb megnyomásakor a backend rögzíti az aktív szerkesztési jelenlétet.
- Ha ugyanazt a munkalapot egy másik felhasználó is szerkeszti, az űrlap tetején sárga figyelmeztetés jelenik meg a felhasználó nevével és e-mail-címével.
- A már szerkesztő felhasználó legfeljebb 5 másodpercen belül értesül arról, hogy valaki más is megnyitotta ugyanazt a munkalapot.
- A jelenlét 5 másodpercenként frissül, és 25 másodperc aktivitás nélkül automatikusan lejár. Ez kezeli azt az esetet is, amikor a böngészőt vagy a számítógépet szabálytalanul zárják be.
- A figyelmeztetés nem kemény zárolás: mindkét fél dolgozhat tovább. A mentéskori verzióellenőrzés továbbra is megakadályozza, hogy az egyik felhasználó csendben felülírja a másik módosítását.

Az adatbázis-migráció neve:

```text
0007_work_order_edit_presence
```

A szerkesztési jelenlét átmeneti adat, ezért nem kerül bele a teljes adatbázis- és beállításmentésbe.

## Eszközök oldal – listaorientált felület

Az Eszközök modul főoldala külön listanézetet használ. Az új eszköz és a szerkesztés külön útvonalon nyílik meg, ezért a ritkábban használt törzsadatűrlap nem foglal helyet a napi keresés és számlálórögzítés elől.

Fő útvonalak:

```text
/assets                 Eszközlista
/assets/new             Új eszköz
/assets/{id}            Eszköz-adatlap
/assets/{id}/edit       Eszköz szerkesztése
```

A cégkód alapértelmezetten megjelenik az eszközlistában és az eszköz-adatlap fejlécében. Az eszközlista sorai kattinthatók, a hárompontos menüből pedig elérhető a szerkesztés, a gyors számlálórögzítés, az új munkalap és Admin számára a törlés.

Az eszköz-adatlap fülei:

- Áttekintés
- Számláló és alkatrészek
- Munkalapok
- Történet
- Törzsadatok

A Dashboard nyomtatófigyelmeztetései közvetlenül az új eszköz-adatlap Számláló és alkatrészek fülére navigálnak. Az eszközből indított új munkalap automatikusan kitölti az ügyfelet, helyszínt és az eszközt.

## Eszközoldal – második használhatósági kör

Az Eszközök főoldal részletes, összecsukható szűrőpanelt kapott. Szűrhető:

- állapot, cégkód, ügyfél és helyszín;
- gyártó, típus és kategória;
- karbantartási állapot;
- számlálóadat frissessége;
- alkatrészcsere-előrejelzés.

A szűrések az URL-ben maradnak, ezért a szűrt lista könyvjelzőzhető és megosztható. Példa:

```text
/assets?company_code=DRh&status=aktív&meter_state=needs_update
```

A lista új információi:

- aktuális számlálóállás és annak kora;
- következő karbantartás vagy alkatrészcsere;
- vizuális állapot- és figyelmeztető címkék;
- kattintható összesítő mutatók.

Az eszköz adatlapján a kapcsolódó munkalapok kompakt, státuszcímkés listában jelennek meg.

## Eszközoldal – harmadik teljesítménykör

Az Eszközök főoldal a nagyobb adatállományok kezeléséhez szerveroldali lapozást és rendezést használ.

Új API:

```text
GET /api/assets/paged?page=1&page_size=50&sort=company_code&order=asc
```

Támogatott oldalméretek:

```text
25 / 50 / 100 / 200 sor
```

A táblázat fejlécére kattintva szerveroldalon rendezhető:

- állapot;
- cégkód;
- eszköznév;
- ügyfél;
- gyári szám;
- számlálóállás;
- következő karbantartási vagy alkatrészesemény.

A keresőmező 350 ms késleltetést használ, ezért gépelés közben nem indít minden karakterre külön API-kérést. A lap, oldalméret, rendezés és szűrés az URL-ben marad, így a nézet könyvjelzőzhető.

Az adatbázis a gyakori eszközlista-szűrésekhez és rendezésekhez új egyedi és összetett indexeket kapott. Az Alembic migráció neve:

```text
0009_asset_list_performance
```

## Korábbi külön számlálóimport (kompatibilitási végpont)

Admin jogosultsággal a **Beállítások → Excel import: nyomtató-számlálóállások** panelen történeti számlálóállások tölthetők be `.xlsx` fájlból.

A projektcsomag tartalmazza az előkészített mintafájlt is: `imports/szamlalo_adatok_import.xlsx`.

A javasolt folyamat:

1. Válaszd ki a `szamlalo_adatok_import.xlsx` fájlt.
2. Kattints az **Import ellenőrzése** gombra.
3. Ellenőrizd az importálható, változatlan, ütköző és nem azonosítható sorok számát.
4. Kattints a **Számlálóadatok importálása** gombra.

A rendszer a `Számláló import` munkalapot keresi. Kötelező oszlopok:

- `mérés időpontja`
- `számlálóállás`
- `gyári szám`, vagy az `import_batch` és `import_row` oszloppár

Támogatott további oszlopok:

- `cégkód`
- `ügyfél`
- `eszköz`
- `FF záró` vagy `FF számlálóállás`
- `színes záró` vagy `színes számlálóállás`
- `scan záró` vagy `scan számlálóállás`
- `forrás munkalap`
- `forrás sor`
- `megjegyzés`

Az eszközazonosítás sorrendje:

1. `import_batch` + `import_row`
2. gyári szám + cégkód
3. egyedi gyári szám

Az import idempotens. Az azonos eszközhöz és időponthoz tartozó, azonos összes számlálójú rekord hiányzó FF, színes és scan értékei kiegészíthetők. Eltérő összes értéket vagy az összes számláló monoton sorrendjét sértő sort nem ír felül, hanem az importeredményben jelzi.

API végpontok:

```text
POST /api/imports/meter-readings/preview
POST /api/imports/meter-readings/run
```

Mindkét végpont `multipart/form-data` feltöltést vár `import_file` mezőnévvel, és kizárólag Admin szerepkörrel használható.

## Tömeges karbantartási munkalapok és nyomtatás

Az **Ügyfelek** oldalon Admin vagy Irodai felhasználó az ügyfél sorában található **Karbantartási munkalapok** gombbal egy műveletben külön munkalapot hozhat létre az ügyfél minden eszközéhez.

A létrehozott munkalapok alapértékei:

- munkatípus: `karbantartás`;
- státusz: `új`;
- prioritás: `normál`;
- feladatleírás: `Tervezett karbantartás`;
- helyszín: az eszköz aktuális helyszíne;
- kapcsolattartó: a helyszínhez vagy ügyfélhez tartozó elsődleges Szerviz kapcsolattartó, ha van.

Azok az eszközök kimaradnak, amelyekhez már tartozik nyitott karbantartási munkalap. A létrehozás után a rendszer a **Munkalapok** oldalra navigál, és automatikusan kijelöli az új munkalapokat.

A Munkalapok táblázatában jelölőnégyzetekkel egy vagy több munkalap választható ki. A **Kijelöltek nyomtatása** gomb egyetlen böngészős nyomtatási folyamatban, munkalaponként külön oldalon nyomtatja a kijelölt dokumentumokat.

## Munkalapok tömeges szerkesztése

A **Munkalapok** oldalon Admin és Irodai felhasználó több munkalapot kijelölhet, majd a **Kijelöltek szerkesztése** gombbal közös adatokat alkalmazhat rájuk.

Tömegesen módosítható:

- tervezett nap;
- felelős technikus, beleértve a kijelölés törlését is.

Tömegesen nem módosítható:

- ügyfél;
- helyszín;
- kapcsolattartó;
- kapcsolódó eszközök.

A tervezett nap módosításakor a már megadott tervezett kezdési és befejezési időpont órája és perce megmarad, csak a dátum kerül az új napra.

A művelet tranzakciós és verzióellenőrzött. Ha bármely kijelölt munkalapot időközben más felhasználó módosított, a teljes tömeges mentés megszakad, és egyik munkalap sem íródik felül.

API végpont:

```text
POST /api/work-orders/bulk-update
```

## Automatikus utolsó karbantartási dátum

`karbantartás` típusú munkalap első lezárásakor a rendszer minden kapcsolt eszköznél automatikusan frissíti az `Utolsó karbantartás` dátumát.

- A dátum forrása a munkalap tényleges befejezési időpontja (`completed_at`).
- Ha nincs megadott tényleges befejezés, a lezárás aktuális időpontja kerül felhasználásra.
- Egy régebbi munkalap utólagos lezárása nem írhat felül egy már újabb karbantartási dátumot.
- Minden első lezárás külön `karbantartás elvégezve` bejegyzést készít az eszköztörténetben, a kapcsolódó munkalap azonosítójával.
- Javítás, eseti javítás, kiszállítás és üzembe helyezés típusú munkalap nem módosítja az utolsó karbantartási dátumot.

A működéshez új adatbázis-migráció nem szükséges, mert az `assets.last_maintenance_date` mező már korábban is létezett.

## Korábbi külön karbantartásidátum-import (kompatibilitási végpont)

Admin jogosultsággal a **Beállítások → Excel import: utolsó karbantartási dátumok** panelen eszközönként betölthető vagy frissíthető az `Utolsó karbantartás dátuma` mező.

A projektcsomag tartalmazza az előkészített importfájlt:

```text
imports/utolso_karbantartas_import.xlsx
```

Használat:

1. Nyisd meg a Beállítások oldalt Admin felhasználóval.
2. Válaszd ki az `utolso_karbantartas_import.xlsx` fájlt.
3. Kattints az **Import ellenőrzése** gombra.
4. Ellenőrizd a frissíthető, változatlan, ütköző és nem azonosítható sorokat.
5. Kattints a **Karbantartási dátumok importálása** gombra.

A rendszer a `Karbantartás import` munkalapot keresi. Kötelező oszlop:

- `utolsó karbantartás dátuma`

Az eszköz azonosításához szükséges:

- `gyári szám`, vagy
- `import_batch` + `import_row`.

Az azonosítás sorrendje:

1. `import_batch` + `import_row`;
2. gyári szám + cégkód;
3. egyedi gyári szám.

Az import biztonsági szabályai:

- azonos dátumnál nem módosít;
- az adatbázisban már szereplő újabb dátumot nem írja felül régebbivel;
- minden tényleges frissítés eszköztörténeti bejegyzést készít;
- az import összesítője bekerül az auditnaplóba;
- csak Admin szerepkörrel használható.

API-végpontok:

```text
POST /api/imports/maintenance-dates/preview
POST /api/imports/maintenance-dates/run
```

## Szerződéses karbantartási ciklus és munkaszervezés

Az eszközök külön szerződéses karbantartási ciklust tárolhatnak hónapban. A következő karbantartási időpont elsődleges számítása:

```text
utolsó karbantartás dátuma + szerződéses ciklus hónapjai
```

A számítás naptári hónapokat használ. Például január 31. + 1 hónap február utolsó napja, nem egyszerűen 30 nappal későbbi dátum.

Az Eszközök listájában alapértelmezetten látható:

- utolsó karbantartás dátuma és az azóta eltelt napok;
- szerződéses karbantartási ciklus;
- ciklusból számított következő karbantartás;
- esedékességi állapot: lejárt, 30 napon belül, később esedékes vagy hiányzó utolsó karbantartás.

A Dashboard **Karbantartási munkaszervezés** panelje külön mutatja:

- lejárt karbantartásokat;
- 30 napon belül esedékes karbantartásokat;
- azokat az eszközöket, amelyeknél van szerződéses ciklus, de nincs utolsó karbantartási dátum.

A panelről közvetlenül indítható előre kitöltött `Karbantartás` típusú munkalap.

### Korábbi külön karbantartásiciklus-import (kompatibilitási végpont)

Admin jogosultsággal a **Beállítások → Excel import: szerződéses karbantartási ciklusok** panelen tölthetők be a ciklusok.

A projektcsomag tartalmazza az előkészített, egyértelműen párosított importfájlt:

```text
imports/karbantartasi_ciklus_import.xlsx
```

A forrástábla `G` oszlopa, a **Karb. Ciklus** mező szolgáltatja a ciklust. Támogatott példák:

- `1 hó`, `2 hó`, `3 hó`, `4 hó`, `6 hó`;
- `1 év`;
- `-`, amelynél nincs rögzített periodikus ciklus;
- szabad szöveg, például `megrendelés alapján megyünk`, amely megjegyzésként tárolódik, de nem képez automatikus következő dátumot.

Használat:

1. Nyisd meg a Beállítások oldalt Admin felhasználóval.
2. Válaszd ki az `imports/karbantartasi_ciklus_import.xlsx` fájlt.
3. Kattints az **Import ellenőrzése** gombra.
4. Ellenőrizd az azonosított, változatlan, nem periodikus és hibás sorokat.
5. Kattints a **Karbantartási ciklusok importálása** gombra.

Az eszköz azonosításának sorrendje:

1. `import_batch` + `import_row`;
2. gyári szám + cégkód;
3. egyedi gyári szám;
4. kontrollált környezeti egyezés ügyfél, cím és géptípus alapján.

Az import idempotens: ismételt futtatáskor a már azonos értéken lévő eszközök változatlanok maradnak. A tényleges módosítás eszköztörténeti és auditbejegyzést készít.

API-végpontok:

```text
POST /api/imports/maintenance-cycles/preview
POST /api/imports/maintenance-cycles/run
```


## Munkalapok új oldalstruktúrája

A munkalap-kezelés külön útvonalakra van bontva:

```text
/work-orders                 munkalaplista, szűrés és tömeges műveletek
/work-orders/new             új munkalap létrehozása
/work-orders/{id}            munkalap részletező és nyomtatási nézete
/work-orders/{id}/edit       munkalap szerkesztése
```

A listaoldalon a munkalapsor teljes felülete kattintható. A sor végi hárompontos menüből elérhető a megnyitás, szerkesztés, lezárás, archiválás és sztornózás. A tömeges szerkesztés és nyomtatás csak kijelölt munkalapok esetén jelenik meg.

A szerkesztési jelenlét és az optimista zárolás az új szerkesztési oldalon is változatlanul működik. Sikeres mentés után a rendszer az adott munkalap részletező oldalára tér vissza.

## Munkalapok oldal – 2. átalakítási kör

A munkalap-adatlap füles elrendezést kapott:

- **Áttekintés** – feladat, elvégzett munka, ügyfél, kapcsolattartó, lezárási adatok és közvetlen számlálórögzítés. Nyitott munkalapnál a tervezett idő, kész vagy lezárt munkalapnál a tényleges munkavégzés időpontja jelenik meg.
- **Eszközök** – kompakt eszközlista utolsó karbantartással, az utolsó ismert összes / FF / színes / scan számlálókkal és azok dátumával, valamint a munkalaphoz kapcsolt számláló- és alkatrészrögzítés.
- **Anyagok** – több felhasznált tétel és nettó összesítés.
- **Idő és munkavégzés** – tervezett és tényleges időpontok, időtartamok, elsődleges és opcionális második technikus.
- **Történet** – audit- és eszköztörténeti események idővonalon.

A lezárás külön útvonalon történik:

```text
/work-orders/{id}/close
```

A lezárási felület kizárólag az elvégzett munkát, végállapotot, tényleges kezdést és befejezést, munkaidőt, elsődleges és opcionális második technikust kéri. A mentéskori verzióellenőrzés és a karbantartási munkalaphoz tartozó eszközfrissítés továbbra is működik.

## Munkalaplista – 3. kör

A Munkalapok lista nagyobb adatmennyiséghez szerveroldali működésre váltott.

- A lista 25, 50, 100 vagy 200 soros oldalakon jeleníthető meg.
- A rendezés a backendben történik a táblázat fejlécére kattintva.
- A keresés 350 ms késleltetéssel indul, ezért gépelés közben nem küld minden karakterre külön kérést.
- A szűrők, a rendezés, az oldalméret és a látható oszlopok az URL-ben maradnak, így a nézet könyvjelzőzhető és megosztható.
- Az Oszlopok menüben személyre szabható a munkalaptáblázat.
- A felhasználók saját mentett nézeteket hozhatnak létre, törölhetnek, és egy nézetet alapértelmezettként jelölhetnek.
- A mentett nézetek felhasználónként az adatbázisban tárolódnak, és a teljes adatbázis-mentés részét képezik.

Új API-k:

```text
GET    /api/work-orders/paged
GET    /api/work-orders/saved-views
POST   /api/work-orders/saved-views
PUT    /api/work-orders/saved-views/{view_id}
DELETE /api/work-orders/saved-views/{view_id}
```

Az új adatbázis-migráció:

```text
0011_work_order_list_views
```

- Közvetlen archív munkalap-feltöltés az Archívum aloldalról és a munkalap lezárási oldaláról.

## v0.27.0 – Android technikusi alkalmazás

A projekt külön `mobile/` React + Capacitor klienssel rendelkezik. Az Android alkalmazás a `/api/mobile` publikus HTTPS API-t használja; közvetlen adatbázis-hozzáférése nincs.

Fő mobil funkciók:

- bejelentkezés és MFA;
- Mai munkáim;
- munkalap és kapcsolattartó adatai;
- munkakezdés;
- számlálóállás;
- anyagfelhasználás;
- munkalap-fotó a telefon kamerájával;
- munkavégzés befejezése;
- ügyfél aláírása érintőképernyőn;
- aláírt PDF megnyitása/megosztása.

A production Android buildhez:

```bash
cd mobile
cp .env.example .env
# .env: VITE_API_BASE_URL=https://app.sajatdomain.hu/api/mobile
./scripts/bootstrap-android.sh
npm test
npm run android:open
```

A refresh token natív Androidon Keystore-védett SecureStorage-ba kerül; az access token csak process memóriában él. A böngészős Vite preview kizárólag fejlesztői használatra szolgál, ott hitelesítő adat nem kerül tartós tárolóba.

A telefonról feltöltött JPEG/PNG fényképet a backend újrakódolja, eltávolítja az EXIF/GPS metaadatokat, malware-scannek veti alá, majd SHA-256 lenyomattal a munkalap bizonyítéki állapotához köti. A munkalap lezárásakor ezek a hash-ek a completion snapshot részévé válnak.

## v0.28.0 – Android push és aláírt build

A technikusi Android kliens Firebase Cloud Messaging értesítést kap új munkalap-hozzárendelésről és érdemi időpontmódosításról. A push küldés külön `push-worker` szolgáltatásból, FCM HTTP v1 API-val történik, ezért Firebase hiba nem blokkolja a munkalap mentését.

Production szerverhez állítsd be a `FCM_PROJECT_ID` értéket és másold a Firebase service-account JSON-t a `secrets/firebase_service_account.json` fájlba. Az Android buildgéphez külön `google-services.json` szükséges. Részletes build/aláírás: `mobile/ANDROID_BUILD_SIGNING.md`.

Debug APK: `cd mobile && npm run android:build:debug`. Release előtt egyszer generálj upload-keystore-t: `./scripts/generate-release-keystore.sh`, töltsd be a generált `signing.env` fájlt, majd `npm run android:build:release` vagy `npm run android:bundle:release`.
