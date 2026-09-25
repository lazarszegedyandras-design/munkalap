## 0.30.1 - 2026-09-11 - Security step 1: isolated release-test baseline

- Standalone, manifest-verified test source snapshot; unique Compose test project; no production env/secrets/mounts/ports/socket.
- Disposable PostgreSQL 16 lifecycle: fresh install, upgrade from 0026, committed schema, role privileges, idempotency, synthetic data preservation, internal web smoke/restart.
- Explicit test entrypoints; normal backend/migrate reject unexpected command arguments before side effects.
- One versioned backend image for all five backend-derived services; exact test image IDs, optional promotion and deployment image lock.
- Destructive DB regression helpers now require a matching isolated test DB marker; only SQLSTATE 42501 counts as expected permission denial.
- Per-stage evidence, nonzero failures, timeout handling and project-only cleanup. Test PASS is not public production GO.
- No changes to work-order/signature business behavior. Remaining security-review findings are NOT closed by this step.
- Windows acceptance hotfix: the sanitized release-test environment now preserves only `ProgramFiles` from the Windows system-path variables so Docker CLI 29.x can discover the Compose plugin under `C:\Program Files\Docker\cli-plugins`. Application/Compose production variables remain filtered.
- Added a regression test that preserves `ProgramFiles` while explicitly rejecting `ProgramW6432`, `COMPOSE_FILE` and `DATABASE_URL` from the isolated runner environment.
- Acceptance follow-up hotfix: release-harness entrypoint tests no longer depend on executing freshly-created files from runtime tmpfs; controllable stubs are baked into the test image instead.
- Corrected two stale backend test expectations to the implemented security contract: replayed mobile refresh tokens return `401` and revoke the mobile session; replayed MFA step-up TOTP on an otherwise valid web session returns `400`.

# Változásnapló

A projekt verziózása a szemantikus verziózás elvét követi: `FŐVERZIÓ.ALVERZIÓ.JAVÍTÁS`.

A **0.5.0** az első formalizáltan követett kiadás; a korábbi állapotokhoz nem áll rendelkezésre hiteles, külön változásnapló.

- **FŐVERZIÓ**: visszafelé nem kompatibilis változás.
- **ALVERZIÓ**: új, visszafelé kompatibilis funkció.
- **JAVÍTÁS**: visszafelé kompatibilis hibajavítás.




## [0.31.0] - 2026-09-12

### Security Step 2 – VPS production gate

- Fail-closed Trivy v0.74.0 source/image CVE, secret és misconfiguration gate; immutable scanner manifest digest és Docker-socket nélküli tar scan. Minden CRITICAL CVE blokkol; javítható HIGH CVE blokkol; javítás nélküli HIGH külön risk evidence.
- UFW/SSH/Docker/seccomp/NTP/unattended-upgrades host acceptance.
- Plaintext production secret tiltás, exact reverse-proxy CIDR, edge-only host port publishing és bounded logging Compose gate.
- Bootstrap admin secret kizárólag a one-shot migrate service-ben; frontend `cap_drop: ALL`.
- Caddy TLS/security header/docs/method hardening, explicit forwarding-header felülírás és web+mobile Nginx auth rate limiting.
- Live HTTPS/TLS/header/rate-limit/X-Forwarded-For anti-spoof/audit-chain acceptance, plusz a futó runtime image ID-k egyezése az aktuálisan pullolt/scanelt image-ekkel.
- Restic offsite staged restore után kötelező SHA-256 artifact-integritás ellenőrzés és explicit fizikai restore drill.
- Uptime Kuma 2.5.4 security-fix release.
- Új `step2-production-security-gate.sh` evidence/report: Step 2 PASS esetén `vps_security_go=true`, de `production_go=false` marad az Android/device és signed-document gate-ek lezárásáig.

## [0.30.0] - 2026-09-10

### Migrate transaction hotfix 4

- Javítva az SQLAlchemy 2.x autobegin miatt rollbackelő Alembic migráció: a `SET ROLE workapp_owner` most az Alembic által birtokolt transactionön belül fut.
- A korábbi hiba megtévesztően kiírta a `0027`–`0032` upgrade logokat, majd a seedben `users.mfa_enabled does not exist` hibát okozott, mert a DDL nem commitolódott.
- Új regressziós teszt akadályozza meg, hogy `connection.execute()` ismét az Alembic transaction elé kerüljön.

- Hotfix 3: a migrate/backend DB-readiness helper modulindítással (`python -m scripts.wait_for_db`) fut, az image explicit `/app` Python import rootot kapott; ezzel megszűnik a `ModuleNotFoundError: No module named 'app'` indítási hiba.
- Hotfix 2: a migrate/backend indítás explicit Compose entrypointot kapott; új kanonikus `compose.yaml`, üres `compose.override.yaml`, indítási fingerprint és Windows launcher védi az in-place frissítést a régi Compose/command maradványoktól.

### Added
- Friss, legfeljebb 300 másodperces MFA step-up követelmény a fizikai és logikai restore, recovery-lock feloldás, valamint felhasználó- és jogosultságmódosítás előtt.
- Külön rate limitelt `POST /api/auth/mfa/step-up` végpont, TOTP replay-védelemmel, recovery-code támogatással és success/failure audittal.
- Újrahasznosítható `SecurityStepUpModal`, amely sikeres MFA után pontosan egyszer ismétli meg az előzőleg elutasított műveletet.
- Idempotens `db-role-provisioner`, külön `workapp_owner`, `workapp_migrate` és `workapp_app` PostgreSQL szerepekkel.
- Külön one-shot `migrate` service, runtime DB-jogosultság acceptance és `MIGRATION_SET_ROLE=workapp_owner` Alembic végrehajtás.
- Szűk, típusos, allowlistelt `backup-runner` API a Docker daemonhoz szükséges backup/restore műveletekhez.
- `security-hardening-acceptance.sh`, DB privilege check és Linux fizikai restore drill.

### Changed
- A FastAPI és a push-worker kizárólag a least-privilege `workapp_app` adatbázis-szerepet használja.
- Az Alembic és seed kikerült a backend normál entrypointjából; deploymentkor a külön `migrate` service futtatja.
- A backend image fix `10001:10001` non-root userrel indul. A backend és a migrate Compose service is ezt a felhasználót rögzíti, `cap_drop: ALL` és `no-new-privileges` mellett, runtime `gosu`/UID/GID-váltás nélkül.
- A backend build-time `COPY --chown` és runtime-könyvtár létrehozás biztosítja a szükséges fájljogokat; a normál entrypoint nem futtat `chown` vagy `chmod` műveletet.
- A PostgreSQL 16-kompatibilis role provisioner előbb adja át a table/partitioned table/materialized view ownershipöt, a `pg_depend` szerinti SERIAL (`a`) és IDENTITY (`i`) owned sequence-eket nem módosítja külön, és csak standalone sequence-re futtat `ALTER SEQUENCE ... OWNER` parancsot.
- A backup-agentből kikerült a Docker CLI és a Docker socket; a socketet kizárólag a belső `backup-runner` mountolja.
- A backup hálózati trust boundary `backup_api_net` és `privileged_net` hálózatokra vált szét; a backend nincs a privileged hálózaton.
- A production preflight ellenőrzi a DB identitásokat, a külön belső tokeneket, a Docker socket egyetlen tulajdonosát és a hálózati szeparációt.

### Verification
- Verziószinkron: PASS (`0.30.0`).
- Python AST/compile, shell syntax, YAML parse és statikus Compose security invariánsok: PASS.
- Frontend Node regressziós tesztek: 33/33 PASS; a Vite production build npm dependency hiány miatt nem futott.
- A teljes backend/container/restore acceptance ebben a buildkörnyezetben nem futott: hiányzik a Docker daemon és a projekt Python dependency készlete. A release ezért production GO szempontból `BLOCKED`, amíg a VPS/Windows acceptance gate-ek ténylegesen PASS eredménnyel le nem futnak.
- PostgreSQL 16 provisioner regressziós teszt került a security gate-be: SERIAL/IDENTITY és standalone sequence ownership, második idempotens futás, valamint a meglévő tesztadat változatlansága. A helyi környezet PostgreSQL hiánya miatt ennek élő futása `NOT VERIFIED`.
- A backend/migrate non-root Compose-regresszió 33/33 release-konfigurációs teszt részeként PASS; a valódi migrate exit/Alembic/DB-user konténerteszt a security gate része, de Docker hiányában helyben `NOT VERIFIED`.


## [0.29.0] - 2026-09-06

### Added
- Admin mobile-device operational view with push-enabled state, latest push delivery metadata, device revoke action and no FCM token exposure.
- Admin-only test-push endpoint for a selected active device, plus audited queueing without credential/token logging.
- `python -m app.push_smoke_test` and `deploy/vps/push-smoke-test.sh` for real FCM provider acceptance from the production push worker.
- Optional `PUSH_SMOKE_DEVICE_ID` production acceptance gate.
- Android release preflight validating HTTPS mobile API, Android SDK/build-tools, Firebase package/project configuration and optional signing certificate pin.
- APK/AAB artifact verification, SHA-256 manifest, optional bundletool validation, ADB install/launch smoke test and secret-free release manifest.
- Unified `mobile/scripts/release-acceptance.sh` flow for signed APK + AAB release acceptance.
- `ANDROID_E2E_RELEASE_RUNBOOK_v0.29.0.md`, `SECURITY_RELEASE_CHECKLIST_v0.29.0.md` and updated Android build/signing documentation.

### Changed
- Version synchronization tooling now covers mobile package/env/signing fallbacks and production Compose/preflight defaults.
- Production status reports active push devices and push-outbox health without exposing FCM registration tokens.

### Security and operations
- Firebase project/package mismatch, signing-certificate mismatch, missing SDK/build tools or invalid release signatures fail the Android release gate closed.
- Provider `sent` status is treated only as proof that FCM accepted the request; production runbook still requires human confirmation of phone delivery and deep-link behavior.
- No new Alembic migration; `0032_push_notifications` remains the single database head.

### Verification
- Backend API regression: 115/115 PASS using release-external auth compatibility shims only; production dependencies were not replaced.
- Release/configuration guards: 29/29 PASS.
- Web frontend: 32/32 PASS. Mobile client: 7/7 PASS.
- Clean Alembic upgrade PASS with single head `0032_push_notifications`.
- Release preflight was functionally checked with structurally valid synthetic SDK/Firebase inputs and correctly rejected a mismatched Firebase project id.


## [0.28.0] - 2026-09-06

### Added
- Firebase Cloud Messaging HTTP v1 push delivery with a transactional per-device outbox and dedicated `push-worker`.
- Mobile FCM registration/removal endpoints, work-order assignment and schedule-change push events, retry/deduplication and invalid-token cleanup.
- Capacitor push permission/channel handling, foreground notification banner and notification-tap work-order deep links.
- Android debug APK, signed release APK and Play AAB build pipeline with external upload keystore.
- Backup redaction for FCM registration tokens and exclusion of transient push delivery rows.
- Production acceptance validates that the push-worker can read the Firebase secret and mint an OAuth token without sending a notification.
- `0032_push_notifications` Alembic migration and backup format v16.

### Security
- v0.28 lock-screen push scope is limited to work-order assignment and schedule changes; HR/CRM/procurement notification text remains in-app.
- `google-services.json`, Android upload keystore/signing environment and native artifacts are excluded from both Git and Docker build context.

## [0.27.0] - 2026-09-06

### Added
- Külön React + Capacitor 8 Android technikusi kliens `mobile/` alatt.
- Mobil login/MFA, natív secure refresh-token tárolás, automatikus tokenrotáció és eszközazonosítás.
- Mai munkák, munkalaprészlet, munkakezdés, számláló, anyagfelhasználás, befejezés, ügyfél signature pad és aláírt PDF megnyitás/megosztás.
- Kamera-alapú munkalap-fotók Előtte/Utána/Sérülés/Számláló/Egyéb kategóriákkal.
- `WorkOrderPhoto` modell és `0031_mobile_photos` Alembic migráció.
- `GET /api/mobile/config` a mobil elfogadó nyilatkozat és biztonsági klienskonfiguráció lekéréséhez.
- `SECURITY_ANDROID_CHECKLIST_v0.27.0.md` és `IMPLEMENTATION_REPORT_v0.27.0.md`.

### Changed
- A munkalap-fotókat a backend EXIF/GPS-mentes JPEG-re normalizálja és SHA-256 lenyomattal tárolja.
- A completion snapshot a kapcsolt fényképek bizonyítéki metaadatait és hash-eit is tartalmazza.
- A logikai backup formátum 15-re nőtt és a `work_order_photos` fájlokat is teljesen menti/visszaállítja.

### Security
- Refresh token production mobilon Android Keystore-védett SecureStorage-ban, access token csak memóriában.
- Fotó upload magic-byte, Pillow verify, pixelszám/méret limit, ClamAV és szerveroldali újrakódolás alatt áll.
- Kész/lezárt munkalap fotói nem módosíthatók; az aláírt revision fotóhash-ei utólag nem cserélhetők észrevétlenül.

## [0.26.0] - 2026-09-06

### Added
- Kulon technikusi mobil API `/api/mobile` alatt, sajat munkalap-hozzaferessel es Admin felulbiralasi lehetoseggel.
- Eszkozhoz kotott `MobileDevice` es `MobileSession` modell rovid elettartamu access tokennel, rotalodo refresh tokennel es refresh-replay visszavonassal.
- Mobil eszkozlista es tavoli visszavonas felhasznaloi/Admin biztonsagi muveletkent.
- Munkalap-inditas, szamlaloallas, anyagkereses, befejezes es ugyfelalairas mobil vegpontok.
- `WorkOrderCompletionSnapshot`: kanonikus JSON snapshot, revision es SHA-256 a pontosan alairt munkalaptartalom bizonyithatosagahoz.
- `WorkOrderSignature`: alairo neve/szerepe, elfogado szoveg verzioja, alairaskep- es alairt-PDF-lenyomat, idopont, technikus, mobil eszkoz es kliens IP.
- PNG alairas tartalmi ellenorzes, meret/pixelszam limit, ures canvas detektalas, malware scan es szerveroldali ujrakodolas.
- ReportLab-alapu, Unicode fontot hasznalo alairt munkalap-PDF generalas es immutable evidence storage.
- Webes/API hozzaferes a munkalap alairasi elozmenyeihez es alairt PDF-jeihez.
- Uj `0030_mobile_signatures` Alembic migracio.
- `SECURITY_MOBILE_CHECKLIST_v0.26.0.md` es `IMPLEMENTATION_REPORT_v0.26.0.md`.

### Changed
- A logikai backup formatum 14-re nott; a mobil eszkozok, completion snapshotok, alairasok, PNG-k es PDF-ek a mentessel egyutt utaznak.
- A mobil sessionok ephemeral security state-kent nem allnak vissza backupbol; fizikai restore utan is invalidalva vannak.
- A backend runtime image `reportlab==4.4.9` es DejaVu Unicode font tamogatast kapott a szerveroldali PDF-hez.
- A production konfiguracio kulon mobil access/refresh elettartamot, alairasmeret-limitet, business timezone-t es elfogado szoveg-verziot kapott.

### Security
- A mobil JWT `typ=mobile_access` kulon tokenosztaly, es csak aktiv, nem visszavont mobil session + eszkoz mellett ervenyes.
- Egy korabbi refresh token bizonyitott ujrafelhasznalasa azonnal visszavonja a hozza tartozo mobil sessiont.
- Alairas csak a legfrissebb completion snapshotra teheto, es a backend elutasitja, ha a munkalap version kozben megvaltozott.
- Lezart/alairt munkalap kesobbi modositasa nem irja at a bizonyiteki snapshotot vagy PDF-et; az alairas `is_current` allapota hamissa valik.

### Verification
- Mobil celzott API tesztek: 5/5 PASS.
- Teljes backend API regresszio: 105/105 PASS release-en kivuli auth-kompatibilitasi teszt shim-ekkel; production dependency nem lett shimmel helyettesitve.
- Backup-agent/release tesztek: 47/47 PASS.
- Tiszta Alembic upgrade `0001_initial -> ... -> 0030_mobile_signatures (head)` PASS, egyetlen head maradt.


## [0.25.0] - 2026-09-06

### Added
- Publikus production Compose overlay Caddy TLS edge proxyval; a production hoston kizárólag a 80/443 port kerül publikálásra.
- Automatikus HTTPS-t támogató, perzisztens Caddy certificate state és külön production Caddy konfiguráció.
- Production secret-file készlet és bootstrap script független PostgreSQL-, alkalmazás-, MFA-, backup-agent- és Restic titkok generálására.
- VPS preflight, deploy, UFW, SSH-hardening, production acceptance és státusz scriptek.
- S3-kompatibilis, Restic-alapú titkosított offsite backup támogatás a backup-agentben snapshotazonosítóval, hibastátusszal és retentionnel.
- Offsite backup init/check/acceptance és destruktív felülírás nélküli restore-stage scriptek.
- Opcionális, localhost-only Uptime Kuma profil és külső monitoring telepítési dokumentáció.
- `SECURITY_PRODUCTION_CHECKLIST_v0.25.0.md` és `IMPLEMENTATION_REPORT_v0.25.0.md`.

### Changed
- A frontend alapértelmezett host 3000 publikálása megszűnt; fejlesztésben külön localhost-only Compose override biztosít hozzáférést.
- A backup-agent külön belső management hálózatra került, és nincs az alkalmazás publikus proxyhálózatán.
- Nginx a Caddy által továbbított kliens IP-t és HTTPS sémát őrzi meg a backend felé; a rate limit kulcsa is a valódi kliens IP.
- Docker logok bounded `local` driver rotációt használnak.
- A backup Admin UI és státusz API megjeleníti az offsite mentés állapotát.
- A release és Docker build context explicit kizárja a `.env.production` és `secrets/` tartalmat.

### Security and operations
- Productionben a PostgreSQL, FastAPI, frontend, ClamAV és backup-agent közvetlen host-port nélkül, Docker-hálózaton marad.
- A production proxy-lánc fix belső IP-címeket használ, hogy a FastAPI kizárólag a frontend proxy forwarded headerjeit tekintse megbízhatónak.
- Az offsite restore tooling csak staging volume-ba állít vissza, és nem írja automatikusan felül az éles rendszert.
- A Docker socketet használó backup-agent magas jogosultságú kivételként dokumentált és hálózatilag izolált.
- Az offsite titkosítás mellett provider oldali Object Lock/versioning/append-only védelem szükségessége külön production gate lett.

### Verification
- Backup-agent/release tesztek: 45/45 PASS.
- Frontend regressziós tesztek: 31/31 PASS.
- Célzott migration/backup-permission/release futás: 27/27 PASS; ez részben átfed a fenti release tesztekkel.
- Backend API regresszió: 99/99 PASS release-en kívüli auth-kompatibilitási teszt shim-ekkel; a production dependency-k nem módosultak.
- Tiszta Alembic upgrade `0001_initial -> ... -> 0029_cloud_security (head)` PASS, egyetlen head maradt.
- Shell syntax, Compose YAML parse és Python compile ellenőrzés PASS.
- A jelenlegi futtatókörnyezetben Docker Engine nem érhető el, ezért a valós Compose build/up, publikus TLS, ClamAV, PostgreSQL/pgBackRest és S3/Restic acceptance csak a tényleges VPS-en futtatható; a release ezekhez fail-closed preflight/acceptance scripteket tartalmaz.


## [0.24.0] - 2026-09-06

### Added
- Szerveroldali webes session registry idle/abszolút lejárattal, logout/revoke támogatással és új `0029_cloud_security` migrációval.
- TOTP MFA és egyszer használható recovery kódok; productionben Admin MFA kötelezővé tehető és a production gate megköveteli.
- Adatbázis-alapú login throttling, Nginx auth/API rate limiting és új security audit események.
- CSRF double-submit védelem, cross-site browser write tiltás és szűkített CORS policy.
- Egységes upload content validation, biztonságos OOXML ZIP ellenőrzés és ClamAV INSTREAM integráció.
- `/api/health/live` és `/api/health/ready` endpoint DB/runtime/malware-scanner readiness ellenőrzéssel.
- Docker secret-file kompatibilitás a fő titkokhoz, non-root backend/frontend folyamatok és read-only konténerfájlrendszer.

### Changed
- A böngészős JWT többé nem kerül `localStorage`-ba vagy login JSON válaszba; `HttpOnly` cookie viszi a sessiont.
- A PostgreSQL és FastAPI host portjai alapértelmezetten nincsenek publikálva; a localhost-only debug portok külön `docker-compose.dev.yml` override-ba kerültek.
- Az Uvicorn nem bízik automatikusan minden forwarded headerben; a kliens IP csak konfigurált proxy CIDR felől fogadható el.
- Jelszóváltoztatás, admin jelszó-reset és biztonságérzékeny user-módosítás visszavonja a további aktív sessionöket.
- Production seed nem hoz létre demo technikust/ügyfelet/munkalapot; tiszta production adatbázishoz explicit bootstrap admin jelszó kell.

### Security
- Production startup fail-closed ellenőrzi a titkokat, HTTPS publikus URL-t, Secure cookie-t, Admin MFA-t, CORS originöket, session időkorlátokat, kikapcsolt docsot és fail-closed malware scant.
- API és frontend security headerek: HSTS, CSP, X-Content-Type-Options, frame védelem, Referrer-Policy és Permissions-Policy.
- Fájlfeltöltés webrooton kívüli collision-safe storage key-jel, size/type/signature validációval és kártevővizsgálattal.

### Verification
- Frontend regressziós tesztek: 31/31 PASS; 50 JS/JSX forrás parse ellenőrzése: 0 syntax error.
- Release/configuration + migration + backup-permission tesztek: 23/23 PASS.
- Tiszta Alembic upgrade: `0001_initial -> ... -> 0029_cloud_security (head)` PASS; egyetlen head maradt.
- Python compileall és verziószinkron ellenőrzés: PASS.
- Backend alkalmazáslogikai API-suite: 99/99 PASS két részletben, kizárólag release-en kívüli teszt shim-ekkel, mert a futtatókörnyezetből hiányzott a rögzített `python-jose`, `passlib/bcrypt` és `psycopg2`, és hálózati pip letöltés nem állt rendelkezésre. Ez nem helyettesíti a valódi requirements + PostgreSQL + Docker acceptance-et.
- A Vite production build a hiányzó `node_modules` és nem teljes offline npm cache miatt ebben a környezetben nem volt hitelesen futtatható; saját Node teszt és teljes JSX parse sikeres.


## [0.23.0] - 2026-09-05

### Added
- Új Beszerzés modul minden aktív felhasználónak saját beszerzési igény létrehozására és követésére.
- Kötelező tárgy, beszerzési cél, részletes igényleírás és pozitív összérték; automatikus, éves `BESZ-YYYY-NNNN` azonosító.
- Új `procurement.approve` funkciójogosultság az összes igény listázására, jóváhagyására és elutasítására.
- Többcsatolmányos fájlkezelés PDF/DOCX/XLSX/CSV/JPG/PNG formátumokra, fájlonként 25 MiB limittel, SHA-256 lenyomattal és runtime tárolással.
- Jóváhagyási és elutasítási értesítések, valamint beszerzési audit események.
- Új `0028_procurement` Alembic migráció a beszerzési igényekhez, sorszámozáshoz, csatolmányokhoz és jogosultsághoz.

### Security and integrity
- Saját beszerzési igény jóváhagyása és elutasítása Admin szerepkörrel is tiltott.
- Jóváhagyási döntés optimista verzióellenőrzést és PostgreSQL sorzárat használ a kettős döntés megakadályozására.
- Csatolmány letöltése objektumszintű jogosultság-ellenőrzött; a tárolt fájlnevek collision-safe kulcsot használnak, path traversal elleni védelemmel.
- Tiltott/futtatható és makrós Office fájlok nem tölthetők fel.
- A normál felhasználó kizárólag saját igényeit látja, a teljes jóváhagyói lista külön jogosultsághoz kötött.

### Verification
- Célzott API-tesztek ellenőrzik a teljes request/approve/reject/withdraw folyamatot, a saját jóváhagyás tiltását és a csatolmány-hozzáférést.
- Az Alembic migráció tiszta adatbázison `0028_procurement (head)` állapotig sikeresen lefutott.
- A frontend modul-, munkalap- és dátumregressziós tesztek sikeresek.
- A Vite production build ebben a fejlesztői környezetben nem volt futtatható, mert a Node függőségek nem voltak telepítve és az offline npm cache hiányos; az új JSX fájlok szintaktikai parse ellenőrzése sikeres.


## [0.22.0] - 2026-09-03

### Added
- A CRM-aktivitásokon új `Lehetőség létrehozása` művelet érhető el `crm.write` jogosultsággal.
- A művelet az aktivitás ügyfeléből, kapcsolattartójából, felelőséből, tárgyából és leírásából azonnal `új` pipeline-szakaszú lehetőséget készít, majd az aktivitást visszakapcsolja hozzá.
- Az aktivitáslistáról a már kapcsolt lehetőség közvetlenül megnyitható.

### Security and integrity
- A konverzió írási jogosultsághoz és optimista verzióellenőrzéshez kötött.
- PostgreSQL sorzár és a meglévő aktivitás–lehetőség kapcsolat együtt akadályozza meg a párhuzamos vagy ismételt létrehozást.
- Külön auditbejegyzés készül a lehetőség létrehozásáról és az aktivitás hozzákapcsolásáról.
- Adatbázis-migráció és mentésiformátum-változás nem szükséges.

### Verification
- API-regressziós teszt fedi az automatikus adatátvételt, a visszakapcsolást, az írási jogosultságot, a verziónövelést, a duplikációvédelmet és az auditnaplót.
- Frontend- és kiadási regressziós ellenőrzések rögzítik az egykattintásos műveletet és a backend védelmeket.


## [0.21.0] - 2026-09-03

### Added
- Minden saját HR-adatokhoz hozzáférő munkavállaló kérheti egy jóváhagyott szabadság visszavonását, külön új szabadságigény-létrehozási jogosultság nélkül is.
- A visszavonási kérelem a munkavállaló aktuálisan kijelölt szabadság-jóváhagyójához kerül, aki külön engedélyezheti vagy elutasíthatja azt.
- A saját szabadság oldalon opcionális indoklással indítható a visszavonás, és látható a visszavonási döntés állapota.
- A jóváhagyói oldal és az értesítések megkülönböztetik az új szabadságigényt a már jóváhagyott szabadság visszavonásától.
- Új `0027_leave_cancel_approval` adatbázis-migráció tárolja a visszavonási folyamat állapotát, jóváhagyóját, időpontjait és megjegyzéseit.

### Changed
- A jóváhagyott szabadság a visszavonás engedélyezéséig érvényben marad: továbbra is beleszámít a kiadott napokba, átfedést képez, és technikus esetén látható marad a dashboard naptárában.
- Engedélyezett visszavonáskor a szabadság `cancelled` állapotba kerül és felszabadul a keret; elutasításkor a szabadság jóváhagyott marad, és később új visszavonási kérelem indítható.
- A még el nem bírált, workflow-forrású szabadságigény saját kezű azonnali visszavonása változatlanul megmaradt.
- Függő visszavonási kérelemmel rendelkező jóváhagyó nem inaktiválható, nem törölhető, és HR-jóváhagyási joga sem vonható vissza a döntés lezárásáig.
- A korábbi alkalmazásverziókból készült teljes mentések visszaállításakor az új visszavonási mezők biztonságosan üres alapértéket kapnak.

### Verification
- API-regressziós teszt fedi a saját visszavonást, a kijelölt jóváhagyó kizárólagos döntését, az elutasítás utáni újrakérelmezést, a keret döntésig történő megőrzését és a végleges felszabadítást.
- Frontend- és kiadási regressziós ellenőrzések rögzítik a külön visszavonási űrlapot, döntési útvonalakat, migrációt, értesítéseket és régi mentési kompatibilitást.


## [0.20.1] - 2026-09-03

### Added
- Az Admin a hivatkozott ügyfélhelyszíneket inaktiválhatja és később visszaaktiválhatja. Az inaktív helyszín és minden korábbi kapcsolata megmarad az üzleti előzményekben.
- Új `locations.is_active` mező és `0026_location_active_status` adatbázis-migráció.

### Changed
- Inaktív helyszín nem választható új munkalaphoz, eszközhöz, kapcsolattartóhoz vagy CRM szerződéshez sem a kezelőfelületen, sem közvetlen API-hívással.
- A már inaktív helyszínre hivatkozó régi rekordok továbbra is megnyithatók, módosíthatók és lezárhatók; a helyszín neve mellett egyértelmű `inaktív` jelölés látható.
- A teljesen hivatkozatlan, tévesen felvitt helyszín végleges törlése továbbra is elérhető Admin jogosultsággal.
- Tömeges karbantartási munkalap létrehozásakor a megszűnt helyszín nem kerül új munkalapra.
- Az Excel-import nem kapcsol új vagy frissített adatot inaktív helyszínhez; a helyszínt előbb Admin jogosultsággal vissza kell aktiválni.

### Verification
- API-regressziós teszt ellenőrzi az inaktiválást, a történeti hivatkozások megőrzését, az új hozzárendelések blokkolását és a visszaaktiválást.
- Függőségmentes kiadási és frontend tesztek rögzítik a migrációt, a backend védelmeket és az összes érintett helyszínválasztó szűrését.


## [0.20.0] - 2026-09-03

### Added
- Az Admin szerepkör az ügyféllistán külön szerkesztheti és törölheti az ügyfél-, helyszín- és kapcsolattartó-adatokat. A helyszín neve, címe, GPS-koordinátái és megjegyzése is módosítható.
- A dashboard heti naptára élőben lekéri és egész napos távolléti sávban megjeleníti az aktív technikusok jóváhagyott szabadságait és betegszabadságait. Függőben lévő vagy nem technikusi szabadság nem kerül a szerviznaptárba.

### Changed
- Az ügyfél-, helyszín- és kapcsolattartó-módosítás és -törlés backend oldalon is Admin szerepkörhöz kötött. Az új adatok létrehozásának korábbi irodai/admin jogosultsága változatlan.
- A dashboardon a heti naptár a karbantartási munkaszervezés elé került.
- Hivatkozott helyszín nem törölhető: eszköz, munkalap, kapcsolattartó vagy CRM szerződés esetén a rendszer érthető hibával megőrzi az üzleti előzményt.

### Verification
- Új API-tesztek fedik az admin-only ügyfél/helyszín/kapcsolattartó műveleteket, a hivatkozott helyszín védelmét és a kizárólag jóváhagyott technikusi távollétek dashboard-szinkronját.
- Frontend regressziós teszt rögzíti a naptár elsőbbségi sorrendjét, a távolléti sávot és az admin kezelőgombokat.
- Adatbázis-migráció nem szükséges.

## [0.19.8] - 2026-08-31

### Fixed
- A frontend Nginx proxy már nem az alapértelmezett 1 MiB-os kéréskorlátnál utasítja el a munkalap- és szerződésarchívumokat. Az alkalmazás által meghirdetett és a backend által ellenőrzött 25 MiB-os fájlkorlát ténylegesen használható.
- A proxy egy MiB technikai ráhagyást biztosít a multipart kérés keretére, ezért egy pontosan 25 MiB-os fájl sem akad el a backend-validáció előtt.
- A globális import 50 MiB-os és a rendszer-visszaállítás 500 MiB-os meglévő backendkorlátja külön Nginx-felülbírálást kapott, így az archív hotfix nem szűkíti ezeket 25 MiB-ra.

### Verification
- Új kiadási regressziós teszt ellenőrzi a 25/50/500 MiB-os backendkorlátokhoz tartozó 26/51/501 MiB-os proxyplafonokat és a kérés URI-jának változatlan továbbítását.

## [0.19.7] - 2026-08-27

### Fixed
- A backup-agent új egyedi `GET /backups/{backup_id}` státuszvégpontot kapott.
- Az acceptance runner a végső MASTER állapotát már ezen az egyedi végponton pollolja, nem a teljes backup-listát szűri PowerShellben. Így sok korábbi mentés után sem értelmezi a teljes `master/incremental` gyűjteményt egyetlen feladat eredményeként, és nem ellenőrzi a még `queued` MASTER-t idő előtt.

### Verification
- Új agent teszt ellenőrzi, hogy az egyedi státuszvégpont kizárólag a kért backup-rekordot adja vissza.
- Új kiadási regressziós teszt tiltja a listás `/backups?limit=...` pollolás visszakerülését a `Wait-BackupJob` függvénybe.
- A reprodukciós `v0.19.6` acceptance futásban a teljes host MASTER és disaster-recovery restore sikeresen befejeződött; a hiba kizárólag a 10/10 végső MASTER listás PowerShell-kiértékelésében jelentkezett.

## [0.19.6] - 2026-08-27

### Fixed
- A host `backup-munkalap-app.ps1` integrált backup/restore állapotellenőrzése Windows PowerShell 5.1 alatt is érvényes `python -c` argumentumot ad át a backup-agentnek.
- A host `restore-munkalap-app.ps1` azonos előellenőrzése ugyanilyen PowerShell-biztos argumentumformát kapott, így a disaster-recovery visszaállítás sem akad el később ugyanazon idézőjelhibán.

### Verification
- Új regressziós teszt mindkét host script Python-kódját kinyeri, Python AST-ként ellenőrzi, tiltja a PowerShell által elveszíthető beágyazott dupla idézőjeleket, és ellenőrzi a változóalapú argumentumátadást.
- A reprodukciós `v0.19.5` acceptance futásban a MASTER, inkrementális restore és az automatikus rollback sikeresen átment; a hiba a host MASTER 2/7 lépésének argumentumátadásánál jelentkezett.

## [0.19.5] - 2026-08-27

### Fixed
- Az acceptance runtime probe most sortörés és escape-szekvencia nélkül írja ki a tesztértéket. Windows PowerShell 5.1 alatt sem kerül többé szó szerinti `\\n` a fájl végére, ezért a sikeres MASTER restore utáni állapot-összehasonlítás nem ad hamis eltérést.

### Verification
- Új regressziós teszt rögzíti a platformfüggetlen `printf '%s'` parancsot, és tiltja a korábbi dupla backslash-es formátum visszakerülését.
- A reprodukciós acceptance futás a `v0.19.4` verzióban már sikeresen befejezte a MASTER restore-t; a hiba kizárólag az azt követő runtime probe összehasonlításban jelentkezett.

## [0.19.4] - 2026-08-27

### Fixed
- Az acceptance runner a backend `EmailStr` validációjával kompatibilis tesztcímet küld, ezért a sikeres fizikai restore utáni audit esemény nem áll le többé `422 Unprocessable Entity` hibával.
- A kijelölt pgBackRest backup stop LSN-jére történő restore és az automatikus rollback is `--target-timeline=current` beállítással fut. Így egy korábbi restore által létrehozott új timeline nem térítheti el a pre-restore MASTER visszaállítását.
- A backup-agent a backend `HTTPError` választestét is megőrzi, ezért a `401`, `409` és `422` hibák valódi FastAPI-részlete bekerül a restore diagnosztikájába.

### Verification
- Új regressziós teszt ellenőrzi a timeline-rögzítést, a backend HTTP-hibatest megőrzését és a backend által elfogadható acceptance e-mailt.
- A fizikai Windows/Docker acceptance teljes újrafuttatása továbbra is szükséges az éles restore engedélyezése előtt.

## [0.19.3] - 2026-08-26

### Fixed
- Az `acceptance-backup-restore.ps1` inkrementális ellenőrzése Windows PowerShell 5.1 alatt is helyesen adja át a beágyazott Python-kód szöveges argumentumait; az `incremental` és `acceptance` literálok idézőjelei nem vesznek el többé.
- A natív parancsok hibakimenetét a runner teljes egészében összegyűjti, majd az exit code alapján kezeli, ezért egy Python traceback nem csak az első sorával jelenik meg.

### Verification
- A reprodukciós Windows PowerShell környezetben a javított egysoros parancs valódi `effective_kind=incremental`, `status=success` mentést készített a korábbi MASTER láncán.
- Új regressziós tesztek ellenőrzik a PowerShell 5.1-kompatibilis argumentumformát és a teljes natív stderr begyűjtését.

## [0.19.2] - 2026-08-26

### Fixed
- A PostgreSQL konténer most a konfigurált `POSTGRES_USER` értékét `PGUSER` környezeti változóként is átadja a pgBackRest folyamatoknak. Így nem a konténert futtató `postgres` operációs rendszer-felhasználó nevével próbálnak adatbázis-kapcsolatot nyitni olyan telepítéseken, ahol a klasztert például `POSTGRES_USER=workapp` hozta létre.
- Új repository esetén a backup-agent automatikus `stanza-create` és `check` inicializálása nem akad el többé a `FATAL: role "postgres" does not exist` hibával.

### Verification
- Új regressziós teszt ellenőrzi, hogy a Compose `db` szolgáltatása dinamikusan, mereven rögzített adatbázis-felhasználónév nélkül adja át a `PGUSER` értékét.
- A kiadási verzióellenőrzés most már a backup-agent, a Compose, az acceptance runner és a `.env.example` összes `APP_VERSION` alapértékét is ellenőrzi és frissíti.
- A hiba reprodukciós környezetében `PGUSER="$POSTGRES_USER"` mellett a `stanza-create`, a repository-ellenőrzés és a WAL-szegmens archiválása sikeresen lefutott.

## [0.19.1] - 2026-08-24

### Added
- Izolált `acceptance-backup-restore.ps1` acceptance runner, amely külön ideiglenes Compose projektben végigteszteli a fizikai MASTER, inkrementális mentés, MASTER restore, inkrementális restore, automatikus rollback és host PowerShell disaster-recovery folyamatot.
- Az acceptance rollback teszt szándékosan hibás backend–backup-agent tokent használ, így destruktív restore után valódi automatikus pre-restore rollbacket kényszerít ki anélkül, hogy az éles projektet érintené.

### Changed
- A mentési pont validáció most `pgbackrest verify --set=<label>` fizikai repository-ellenőrzést is futtat a fájl-SHA-256 és runtime láncellenőrzés mellett.
- Restore utáni PostgreSQL readiness csak akkor sikeres, ha az adatbázis már nem recovery módban fut (`pg_is_in_recovery() = false`).
- Restore utáni backend readiness az Alembic `current/head` egyezés mellett megvárja a `/api/health` sikeres HTTP válaszát is.

### Fixed
- Megszűnt az a versenyhelyzet, amelyben a PostgreSQL már elfogadott kapcsolatot hot-standby/recovery közben, ezért a backup-agent túl korán próbálhatott post-restore MASTER-t készíteni.
- Megszűnt az a hamis restore-hiba, amikor az Alembic már elérhető volt a backend konténerben, de a FastAPI HTTP szolgáltatás még nem állt készen a restore audit-esemény fogadására.

### Verification
- Backup-agent regressziós tesztek kibővítve a pgBackRest verify, primary-state DB readiness és HTTP backend readiness ellenőrzésével.
- A teljes fizikai Docker/PostgreSQL acceptance továbbra is Docker daemon-t igényel; ehhez most már a kiadás része az automatizált, éles volume-októl izolált tesztrunner.

## [0.19.0] - 2026-08-24

### Added
- Teljes, jogosultsághoz kötött webes restore az **Admin → Biztonsági mentések** oldalon az integrált pgBackRest + `app_runtime` mentési pontokra.
- Kötelező `VISSZAALLIT` megerősítés, teljes mentésilánc-validáció és azonos deployment-fingerprint ellenőrzés a destruktív művelet előtt.
- Kötelező **pre-restore MASTER** az aktuális állapot védelmére, majd sikeres visszaállítás után **post-restore MASTER**, amely új inkrementális láncot nyit a visszaállított PostgreSQL timeline-on.
- Restore-job történet cél mentési ponttal, pre/post MASTER azonosítóval, rollback állapottal és hibainformációval.
- Megszakadt vagy bizonytalan restore után tartós recovery lock; a zárolás csak `HELYREALLITAS_KESZ` megerősítéssel és DB/backend/pgBackRest ellenőrzések után oldható fel.
- Backend belső restore-esemény végpont audit hash-chain ellenőrzéssel, hogy a sikeres vagy visszagörgetett restore az aktuális adatbázis auditnaplójába is bekerüljön.

### Changed
- A backup-agent indulása már nem függ a PostgreSQL healthcheck sikerétől, így hibás vagy félbeszakadt adatbázis-helyreállítás után is elérhető marad a recovery vezérlés.
- A PostgreSQL restore a kiválasztott pgBackRest backup `stop LSN` értékére áll vissza (`--type=lsn --target=...`), nem a repository WAL-folyamának későbbi végére.
- A runtime restore biztonságos staging könyvtárban rekonstruálja a MASTER + inkrementális deltaláncot, ellenőrzi a kiválasztott állapot fájlmanifestjét, majd atomi jellegű könyvtárcserével telepíti.
- Destruktív lépés utáni hiba esetén a rendszer automatikusan megpróbál visszagörgetni a pre-restore MASTER adatbázis- és runtime-állapotára; sikeres rollback után külön rollback MASTER nyit új, helyes inkrementális láncot. Sikertelen rollback esetén recovery lock marad aktív.
- A webes restore kizárólag az aktuális deployment fingerprintjével azonos mentési pontot fogad el. Alkalmazásverzió/image/config rollback továbbra is a host PowerShell disaster-recovery restore feladata.
- A host PowerShell backup/restore ellenőrzi az integrált backup/restore aktivitást és a recovery lockot, hogy a két helyreállítási mechanizmus ne írja ugyanazokat a volume-okat párhuzamosan.

### Security
- A restore továbbra is külön `admin.backup.restore` jogosultsághoz kötött; a normál backup-kezelési jog önmagában nem enged visszaállítást.
- A runtime TAR kicsomagolás elutasítja a path traversal, symlink, hardlink és device bejegyzéseket.
- A restore előtt és után az audit hash-chain integritása ellenőrzésre kerül; sikertelen utóellenőrzés restore-hibának minősül.

### Known limitations
- A teljes Docker/image/config verziórollback nem történik weben. Más deploymenthez tartozó mentéshez a host `restore-munkalap-app.ps1` használható.
- A Docker/PostgreSQL fizikai restore acceptance teszt továbbra is valódi Docker daemon-t igényel; a fejlesztői környezetben az agent restore-folyamata izolált integrációs tesztekkel van lefedve.


## [0.18.0] - 2026-08-24

### Added
- Külön, egy workerrel futó `backup-agent` szolgáltatás a rendszerszintű mentések ütemezéséhez és végrehajtásához; a normál backend nem kap Docker socket hozzáférést.
- Admin → Biztonsági mentések oldal napi fix időponttal, Europe/Budapest alapértelmezett időzónával, manuális MASTER indítással, mentési pont listával és integritásellenőrzéssel.
- PostgreSQL pgBackRest alapú teljes/inkrementális mentési lánc; a hónap utolsó naptári napján automatikus MASTER, más napokon inkrementális mentés.
- `app_runtime` MASTER TAR és hash-alapú inkrementális delta új/módosult/törölt fájlok követésével.
- Új jogosultságok: `admin.access`, `admin.backup.manage`, `admin.backup.restore`; nem Admin felhasználó csak a neki engedélyezett backup adminfelületet látja.
- Alembic migráció: `0025_admin_backup_permissions`.

### Changed
- A PostgreSQL image pgBackRest-tel bővült, az adatbázis WAL-archiválása a dedikált `backup_repository` volume-ba történik.
- A MASTER mentés a runtime és adatbázis mellett Docker image-eket, `.env`/Compose/VERSION/CHANGELOG fájlokat, effektív Compose-konfigurációt, Docker/Compose verzióinformációt, manifestet és SHA-256 ellenőrzőösszegeket is rögzít.
- Az integrált mentés a DB/runtime konzisztencia érdekében rövid időre leállítja a backend és frontend szolgáltatást, majd az eredeti futási állapotot automatikusan visszaállítja; a PostgreSQL futva marad.
- Sikertelen automatikus mentés ugyanazon a napon nem indul újra 30 másodpercenként; az automatikus próbálkozás és a sikeres napi lefedettség külön állapot.
- Ha nincs használható MASTER vagy megváltozott a deployment fingerprint, a kért inkrementális mentés automatikusan MASTER-re emelkedik.
- A pgBackRest mentésekhez ebben a körben nincs automatikus retention/törlés; a szabad tárhely az Admin felületen látható.

### Security
- A backup-agent nem publikál host portot; a backend és az agent külön megosztott tokennel kommunikál.
- A Docker socket kizárólag a dedikált backup-agenthez van csatolva.
- A restore jogosultság külön van választva a mentéskezelési jogosultságtól.

### Known limitations
- Az új pgBackRest/runtime láncból történő webes rendszerszintű visszaállítás még nincs engedélyezve ebben az első fejlesztési körben; a meglévő v0.17.x alkalmazás-ZIP restore és a PowerShell host restore megmarad.
- A valódi Docker/PostgreSQL backup/restore acceptance teszt Docker daemon nélküli fejlesztői futtatókörnyezetben nem hajtható végre; telepítés előtt Dockeres teszt szükséges.


## [0.17.2] - 2026-08-17

### Fixed
- Frissítéskor bent maradó v0.17.0 `0024_contract_details_archives_hr_calendar.py` fájl automatikus eltávolítása a backend indulásakor, így nem keletkezik több Alembic head.
- Migrációs regressziós teszt most már a revision ID hossz mellett az egyetlen headet és a duplikált revision ID-k hiányát is ellenőrzi.

## [0.17.1] - 2026-08-17

### Javítva
- Kritikus PostgreSQL/Alembic frissítési hiba javítva: a 0024-es migráció revision azonosítója 32 karakternél hosszabb volt, ezért a PostgreSQL `alembic_version.version_num` VARCHAR(32) mezője elutasította.
- A 0024-es revision új, kompatibilis azonosítója: `0024_contract_archives_hrcal` (27 karakter).
- A migráció tartalma változatlan; a sikertelen 0.17.0 frissítés tranzakciója PostgreSQL-en visszagörgetésre kerül, ezért 0023-ról a javított csomag közvetlenül újrafuttatható.
- Kiadási ellenőrzés került be az Alembic revision azonosítók legfeljebb 32 karakteres hosszára.

## [0.17.0] - 2026-08-17

### Added
- A `Szerződések adatai.xlsx` szerződés-, számlázási és szervizmezőinek rögzítése, a kontakt adatok szándékos kihagyásával.
- Ismételhető CRM szerződés-szerviz/eszköz sorok a többeszközös szerződések adatvesztés nélküli kezeléséhez.
- DRH / SP / GXR vállalkozóválasztó a CRM szerződéseknél és cégkód szerinti szűrés.
- Szerződésenkénti PDF archívum előnézettel, nyomtatással, letöltéssel és Admin-only, `TÖRÖL` megerősítéses törléssel.
- `app_runtime/contract_archives` tárhely és teljes backup/restore támogatás a szerződés PDF-ekhez.
- HR Összesítés heti, havi és éves távolléti naptárral.
- Alembic migráció: `0024_contract_archives_hrcal`.

### Changed
- A beépített backup formátum 12-es verzióra nőtt; az 1–11 formátumok továbbra is támogatottak.
- A CRM szerződés CSV export a részletes szerződés- és számlázási mezőkkel bővült.
- A `hr.summary.view` jogosultság az összesítő táblán túl a jóváhagyott/függő távollétek dátumait tartalmazó naptárhoz is hozzáférést ad; HR szabad szöveges megjegyzéseket a naptár API nem ad vissza.

### Security
- Szerződésarchívumba kizárólag valódi PDF-tartalom tölthető fel, a fájlméret a meglévő archív limitet követi.
- Szerződés PDF törlése kizárólag Admin jogosultsággal és pontos `TÖRÖL` megerősítéssel lehetséges; feltöltés/előnézet/letöltés/törlés auditált.

## [0.16.0] - 2026-08-17

### Added
- A felhasználó által átadott nyolc 2026-os RLB szabadságnyilvántartás strukturált, verziózott forrásadata (`backend/app/data/hr_leave_2026_rlb.json`).
- HR forrásimport staging és párosítás: `hr_leave_import_people`, `hr_leave_import_absences`, automatikus egyértelmű párosítás és HR admin kézi párosítás.
- `job_title` HR profilmező, `child_days` éves gyermekek után járó szabadságkeret és `sick_leave_days` betegszabadságkeret.
- Távolléttípus és forrásjelölés a HR történetben: `annual_leave`, `sick_leave`, `workflow`, `rlb_pdf_2026`.
- Saját HR nézetben külön betegszabadság keret/felhasználás/maradék és importforrás-jelzés.
- HR admin felületen forrásimport státusz, párosított felhasználó, beosztás, éves/beteg keret és kiadott napok.
- Alembic migráció: `0023_hr_leave_source_import`.

### Changed
- Az éves szabadságkeret az alapszabadság + gyermekek után járó + áthozott + korrekció összege.
- A betegszabadság külön jogcímként számolódik, és nem csökkenti az éves szabadságmaradékot.
- Történeti importnál a jóváhagyó opcionális; az importált rekord nem generál jóváhagyási feladatot.
- A HR riportok éves szabadságterhelése csak az éves szabadságot számolja, a betegszabadság külön aggregátum.
- A beépített teljes mentés formátuma 11-es verzióra nőtt; az 1–10 formátumú régi mentések továbbra is támogatottak.
- Verzió: `0.16.0`; az 1.0 továbbra is külön éles elfogadási kör után készülhet el.

### Safety
- Meglévő eltérő HR törzsszámot, 2026-os keretet vagy nem egyező történeti távollétet az automatikus import nem ír felül. Az ilyen rekord `conflict` állapotba kerül HR admin felülvizsgálatra.
- Az import idempotens: ugyanaz a forrásrekord `source_reference` alapján nem duplikálható.

## [0.15.0] - 2026-08-17

### Added
- Központi, felhasználónkénti értesítési központ olvasatlan számlálóval, moduljelzésekkel és olvasott/olvasatlan kezeléssel.
- HR értesítések jóváhagyásra váró igényekhez és saját jóváhagyott/elutasított szabadságigényekhez.
- CRM értesítések saját lejárt/hamarosan esedékes aktivitásokhoz és 30 napon belül lejáró aktív szerződésekhez.
- Szerviz értesítések a felhasználóhoz rendelt mai és lejárt tervezett munkalapokhoz.
- Szerviz, HR és CRM riportoldalak időszaki/éves aggregátumokkal.
- CSV export Szerviz riporthoz, HR riporthoz, CRM pipeline riporthoz, valamint CRM lehetőség-, aktivitás- és szerződéslistához.
- Alembic migráció: `0022_notifications_reports`; új `notifications` tábla.

### Security
- A HR riport külön `hr.summary.view` jogosultsághoz kötött, és csak aggregált adatot közöl; más munkavállaló részletes szabadságdátumait nem szolgáltatja.
- CRM riport/export `crm.access`, Szerviz riport `service.access` jogosultságot kér; a moduljogosultságok nem mosódnak össze.
- Az értesítési API kizárólag az autentikált felhasználó saját értesítéseit listázza és módosítja.

### Changed
- A már megoldott HR-jóváhagyás, teljesített CRM-aktivitás, lezárt/átadott munkalap vagy inaktív/lejárt szerződés cselekvést igénylő értesítése automatikusan olvasottra záródik.
- A beépített teljes mentés formátuma 10-es verzióra nőtt; az 1–9 mentési formátumok továbbra is támogatottak.
- A projekt v0.15.0 marad; az 1.0 kiadás külön elfogadási és éles validációs lépés után készíthető el.

## [0.14.0] - 2026-08-17

### Added
- CRM szerződéskezelés külön `crm.contract.manage` jogosultsággal.
- Szerződésszám, típus, időszak, státusz, SLA, elszámolási modell és megjegyzés kezelése.
- Szerződés–telephely és szerződés–eszköz kapcsolatok, backend oldali ügyfélkonzisztencia-ellenőrzéssel.
- CRM ügyfél 360° nézet szerződésekkel, CRM dashboard aktív és 60 napon belül lejáró szerződés mutatókkal.
- Munkalap `contract_id` kapcsolat és Szerviz modulból elérhető, korlátozott szerződés-opció végpont.
- Alembic migráció: `0021_crm_contracts`.

### Security
- A szerződés létrehozása/módosítása külön `crm.contract.manage` joghoz kötött; a CRM olvasási jog önmagában nem enged szerződésmódosítást.
- A backend tiltja más ügyfél telephelyének/eszközének szerződéshez kapcsolását és a szerződés hatályán kívüli munkalap-hozzárendelést.
- CRM szerződéshez kapcsolt telephely/eszköz törlése blokkolt.
- Szerződés létrehozása és módosítása a strukturált auditnaplóba kerül.

### Changed
- A munkalap `Szerződés típusa` mezője CRM-szerződés hozzárendelésekor történeti snapshotként automatikusan kitöltődik; későbbi szerződésmódosítás nem írja át visszamenőleg.
- A beépített teljes mentés formátuma 9-es verzióra nőtt; az 1–8 mentési formátumok továbbra is támogatottak.
- A projekt továbbra is 0.x verzióágon marad; az 1.0 csak a teljes HR/CRM program lezárása után készül.

## [0.13.0] - 2026-08-17

### Added
- Működő CRM alapmodul a meglévő közös `customers` / `customer_contacts` ügyféltörzsre építve; nem jön létre párhuzamos CRM-ügyféladatbázis.
- CRM áttekintő dashboard ügyfélszámmal, nyitott pipeline darabszámmal/értékkel, lejárt aktivitásokkal, szakaszonkénti pipeline összesítéssel és legutóbbi eseményekkel.
- CRM ügyféllista kereséssel és 360° ügyfélnézettel, amely ugyanazon az oldalon mutatja a kapcsolattartókat, telephelyi/eszköz- és munkalapkapcsolatokat, értékesítési lehetőségeket és CRM aktivitásokat.
- Értékesítési lehetőségek (`crm_opportunities`) ügyfélhez, opcionális kapcsolattartóhoz és CRM-felelőshöz kapcsolva; pipeline szakasz, várható érték/deviza, valószínűség, várható zárás, forrás, következő lépés és elvesztési ok mezőkkel.
- CRM aktivitások (`crm_activities`) telefon, e-mail, meeting, feladat és jegyzet típusokkal; ügyfélhez, kapcsolattartóhoz, lehetőséghez és opcionálisan meglévő munkalaphoz kapcsolhatók.
- CRM ügyfél és kapcsolattartó létrehozás/módosítás `crm.write` jogosultsággal, ugyanazon alapadatmodelleken, amelyeket a Szerviz modul is használ.
- Optimista verzióellenőrzés az értékesítési lehetőségek és aktivitások módosításánál.
- Alembic migráció: `0020_crm_core`; új `crm_opportunities` és `crm_activities` táblák.

### Security
- A teljes CRM router backend-szinten `crm.access` jogosultsághoz kötött; módosító művelethez külön `crm.write` szükséges.
- CRM-felelősként csak aktív, CRM-hozzáféréssel rendelkező felhasználó vagy Admin választható.
- A backend ellenőrzi, hogy a kiválasztott kapcsolattartó, lehetőség és munkalap ugyanahhoz az ügyfélhez tartozzon; kereszt-ügyfél kapcsolat nem hozható létre.
- CRM előzménnyel rendelkező ügyfél vagy kapcsolattartó a Szerviz modulból sem törölhető, így az értékesítési történet nem veszhet el.
- CRM létrehozási és módosítási események a strukturált hash-chain auditnaplóba kerülnek.

### Changed
- A Modulválasztó CRM kártyája már működő üzleti modulra mutat; a helykitöltő CRM oldal megszűnt.
- A beépített teljes mentés formátuma 8-as verzióra nőtt; az 1–7 mentési formátumok továbbra is támogatottak.
- A projekt továbbra is 0.x verzióágon marad; az 1.0 csak a teljes HR/CRM fejlesztési program minden fázisának elkészülte után készül.

## [0.12.0] - 2026-08-17

### Added
- HR szabadságkezelési MVP saját szabadságoldallal, éves keretkimutatással, szabadságigényléssel és függőben lévő saját igény visszavonásával.
- Munkavállalói HR profil törzsszámmal, cégkóddal, szervezeti egységgel, vezetővel, külön szabadság-jóváhagyóval és munkaviszony-dátumokkal.
- Éves szabadságkeret alap-, áthozott- és korrekciós napokkal.
- Vezetői jóváhagyási lista: a jóváhagyó kizárólag a hozzá rendelt függő igényeket látja, és optimista verzióellenőrzéssel hagyhatja jóvá vagy utasíthatja el őket.
- Külön `hr.summary.view` jogosultsághoz kötött HR összesítés munkavállalónkénti éves keret/jóváhagyott/függő/maradék adatokkal.
- `hr.admin` HR adminisztrációs oldal munkavállalói profilokhoz, éves keretekhez és munkanaptár-kivételekhez.
- Konfigurálható munkanaptár-kivételek a hétfő–péntek alapú munkanapszámítás felülírására.
- Alembic migráció: `0019_hr_leave_management`; új `employee_profiles`, `leave_entitlements`, `leave_requests`, `work_calendar_days` táblák.

### Security
- A saját HR API-k kizárólag az autentikált felhasználó saját HR profilját és szabadságigényeit szolgálják ki; nincs felhasználóazonosítóval más munkavállaló részletes szabadságadatait lekérő végpont.
- A vezetői jóváhagyási végpontok rekord-szinten is ellenőrzik az `approver_user_id` egyezést; más vezető igényének létezését sem fedik fel.
- A HR összesítés külön jogosultsághoz kötött, és csak aggregált éves adatokat ad vissza.
- A `hr.leave.request` jogosultság csak `hr.leave.self` jogosultsággal együtt osztható ki.
- A szabadságigény audit snapshotja státusz- és döntési nyomot őriz, de nem tartalmaz pontos szabadságdátumot vagy munkavállalói/vezetői szabad szöveges HR-megjegyzést.

### Changed
- A HR modul a modulválasztóban már nem előkészített helykitöltő, hanem működő szabadságkezelési modul.
- A beépített teljes mentés formátuma 7-es verzióra nőtt; az 1–6 mentési formátumok továbbra is támogatottak.
- A projekt továbbra is 0.x verzióágon marad; az 1.0 csak a teljes HR/CRM fejlesztési program lezárása után készül.

## [0.11.0] - 2026-08-17

### Added
- Strukturált, append-only auditnapló actor snapshot mezőkkel (`actor_user_id`, név, email, szerepkör), objektumazonosítóval, `before_data` / `after_data` / `changes` JSON adatokkal, request/correlation/session azonosítókkal, IP- és user-agent adatokkal, eredménnyel és súlyossággal.
- SHA-256 hash-chain minden auditbejegyzéshez (`previous_hash`, `entry_hash`) és külön láncállapot-rekord a párhuzamos PostgreSQL írások sorosításához.
- PostgreSQL append-only adatbázis-trigger, amely alkalmazási UPDATE/DELETE műveletet nem enged az auditnaplón; kizárólag a törölt felhasználó legacy `user_id` FK-nullázása megengedett.
- Kérésenként generált `X-Request-ID` és `X-Correlation-ID` válaszfejlécek; a JWT token külön session ID (`sid`) claimet kap.
- Sikertelen bejelentkezés, érvénytelen/inaktív tokenfelhasználó, szerepkör- és jogosultságmegtagadás strukturált biztonsági auditja.
- Admin → Auditnapló oldal szűrhető eseménylistával, before/after/changes részletekkel, request/session/IP adatokkal és hash-chain integritásjelzővel.
- Admin-only `/api/audit-logs/integrity` végpont a teljes auditlánc ellenőrzésére.
- Alembic migráció: `0018_structured_audit_log`; a meglévő egyszerű auditrekordokat frissítéskor snapshot mezőkkel és visszamenőlegesen felépített hash-chainnel egészíti ki.

### Security
- A strukturált audit-adatok rekurzív szűrése kizárja a jelszó-, jelszóhash-, token-, authorization/cookie-, API-kulcs- és secret mezőket.
- Felhasználó-, jogosultság-, cégprofil- és kapcsolattartó-módosítások explicit before/after snapshotot kapnak; jelszó vagy hash nem kerül az auditba.
- Az auditlista és integritásvizsgálat kizárólag Admin szerepkörrel érhető el.

### Changed
- A beépített teljes mentés formátuma 6-os verzióra nőtt, és már az audit hash-chain állapotát is tartalmazza.
- A visszaállítás továbbra is fogadja az 1–5 mentési formátumokat; a v0.10.x és régebbi auditrekordokat restore során automatikusan az új strukturált/hash-chain formára alakítja.
- A munkalap történetében törölt felhasználó esetén az actor snapshot neve marad látható.
- A projekt továbbra is 0.x verzióágon marad; az 1.0 csak a teljes HR/CRM fejlesztési program lezárása után készül.

## [0.10.0] - 2026-08-17

### Added
- Bejelentkezés utáni modulválasztó `Szerviz`, `HR`, `CRM` és Admin szerepkörnél `Admin` modullal.
- Adatbázis-alapú modul- és funkciójogosultsági modell `permissions` és `user_permissions` táblákkal.
- Jogosultsági katalógus a későbbi HR szabadságigénylés, vezetői jóváhagyás, HR összesítés és CRM funkciók számára.
- Admin felhasználókezelőben modul- és funkciójogosultság szerkesztése.
- Frontend modul-route guardok és kompatibilitási átirányítások a korábbi Szerviz URL-ekhez.
- Backend `service.access` védelem a Szerviz modul API-végpontjain.
- Alembic migráció: `0017_module_permissions`; frissítéskor a meglévő felhasználók megtartják a Szerviz-hozzáférést.

### Changed
- A meglévő Szerviz felület új `/service/...` útvonalakon is elérhető.
- A felhasználói `/api/auth/me` válasz tartalmazza az aktuális `permissions` és `modules` listát.
- A jogosultságok nem kerülnek JWT-be: a backend kérésenként az adatbázis aktuális állapotát használja, ezért jogosultságadás vagy -visszavonás új token nélkül érvényesül.
- Az Admin szerepkör rendszerszintű szuperfelhasználó marad.
- A HR és CRM üzleti funkciók ebben a fázisban még csak előkészített modulhelyet kapnak; az 1.0 verzió csak minden tervezett HR/CRM fázis elkészülte után készül.

## [0.9.9] - 2026-08-16

### Changed
- A nyomtatott metaadat-táblában a `Tervezett nap / Szerződés típusa` sor után a `Tényleges kezdés` és `Tényleges befejezés` külön teljes sort kap.
- A `Hiba / feladat leírása`, `Elvégzett munka` és `Végállapot` feliratok kikerültek a keretes mezőkből, és közvetlenül a boxok fölött jelennek meg.
- A v0.9.8 nyomtatási mezőmagasságok megmaradtak; adatbázis-migráció nem szükséges.

## [0.9.8] - 2026-08-16

### Changed
- A nyomtatott munkalap fejléc alatti általános betűmérete nagyobb lett.
- A munkalap metaadat-táblájának mezőnevei (Munkalapszám, Státusz, Prioritás stb.) normál betűsúlyúak.
- Az „Elvégzett munka” blokk 56 mm-es, a „Végállapot” blokk 24 mm-es minimális magasságot kapott.
- A Kapcsolódó eszközök nyomtatási táblából kikerült az Állapot és a Cégkód, és bekerült az eszköz utolsó karbantartási dátuma.
- Adatbázis-migráció nem szükséges.

## [0.9.7] - 2026-08-16

### Changed
- Nyomtatási margó 12 mm-re nőtt a nyomtatóbarát biztonsági zóna érdekében.
- Nagyobb fejléc-betűméretek a nyomtatott munkalapon.
- Kisebb „Elvégzett munka” mező; az aláírásblokk az A4 oldal alsó részéhez igazodik.
- Üres nyomtatási mezőkben nincs többé `-` helykitöltő.
- A nyomtatási metaadat-táblában új `Tervezett nap` és `Szerződés típusa` sor van.

### Added
- Opcionális `contract_type` mező a munkalap adatmodelljében, API-jában, szerkesztőjében és CSV exportjában.
- Alembic migráció: `0016_work_order_contract_type`.

## [0.9.6] - 2026-08-16

### Teljes A4-magasság és másolásbiztosabb keretek

- A nyomtatott munkalap a 8 mm-es lapmargók mellett legalább 281 mm magas, így rövid tartalom esetén is kitölti az A4 teljes hasznos magasságát.
- Az `Elvégzett munka` blokk flex elrendezéssel felveszi a fennmaradó függőleges helyet; az aláírási rész az oldal alján marad.
- A nyomtatási táblázatok, szolgáltató-/vevőblokkok, munkalapblokkok és aláírásvonalak 1 px helyett 2 px vastag keretet használnak; a fejléc 2 px-es választóvonala 4 px-re nőtt.
- A nyomtatási keretszín sötétebb lett, hogy fénymásoláskor és szkenneléskor jobban megmaradjon.
- A részletező és tömeges nyomtatási CSS-felülírások megtartják a teljes A4-magassághoz szükséges flex elrendezést.
- Új frontend regressziós teszt ellenőrzi az A4 minimális magasságát, a rugalmas munkavégzési blokkot és a kétszeres nyomtatási keretvastagságot.
- Adatbázis-migráció nem szükséges.

## [0.9.5] - 2026-08-16

### Nyomtatási szolgáltatói fejléc és egyoldalas munkalap

- Külön `worksheet_phone` és `worksheet_email` mező került a DRH/SP/GXR cégprofilokba, így a nyomtatási szolgáltatási elérhetőség elválik az általános cégkapcsolati adatoktól.
- A munkalapi telefon és email a cégprofil külön mezőibe került. A Git-bevezetéskor a konkrét elérhetőségek kikerültek a forráskódból, és privát telepítési adattá váltak.
- Régi, az új `worksheet_*` mezőket még nem tartalmazó runtime cégprofilok a Git-bevezetés óta az általános profil-elérhetőségeket használják; a kívánt eltérő munkalapi adatokat a privát cégprofilban kell megadni.
- A böngészős nyomtatott munkalap szállítói blokkjából kikerült a `Kapcsolattartó` és a `Web` sor.
- A kompatibilitási Excel munkalap is a munkalapi telefon/helpdesk mezőket használja, és nem tölti ki a szállítói kapcsolattartót.
- A nyomtatási CSS A4-en kompaktabb margókat, fejlécet, táblázatokat, munkavégzési blokkot és aláírási térközt használ, hogy hosszabb szállítói fejléc és kétsoros kapcsolódóeszköz-adat mellett se csússzon át az aláírás a második oldalra.
- Új regressziós tesztek ellenőrzik a munkalapi elérhetőségek prioritását, a régi runtime profilok visszafelé kompatibilis alapértékeit és a kompatibilitási Excel fejlécét.
- Adatbázis-migráció nem szükséges.

## [0.9.4] - 2026-08-16

### Tömeges munkalap-státusz módosítás

- A kijelölt munkalapok tömeges szerkesztési ablakában a státusz is közösen módosítható.
- A backend tömeges módosítási API-ja új `apply_status` és `status` mezőket kezel, kizárólag érvényes munkalap-státuszokkal.
- Tömeges `lezárva` státuszra váltáskor ugyanazok a lezárási mellékhatások futnak le, mint egyedi szerkesztésnél: a hiányzó befejezési és lezárási idő rögzül, karbantartási munkalapnál pedig frissülnek a kapcsolt eszközök karbantartási adatai.
- A tömeges módosítás auditbejegyzése munkalaponként tartalmazza a régi és az új státuszt.
- Új backend regressziós teszt ellenőrzi a tömeges lezárási státusz mellékhatásait; adatbázis-migráció nem szükséges.

## [0.9.3] - 2026-08-03

### Beépített teljes mentés és visszaállítás

- A projekt gyökerébe bekerült a `backup-munkalap-app.ps1`, amely PostgreSQL custom dumpot, teljes `app_runtime` TAR-mentést, három Docker-image mentést, telepítési konfigurációt, manifestet és SHA-256 ellenőrzőösszegeket készít.
- A projekt gyökerébe bekerült a `restore-munkalap-app.ps1`, amely támogatja a csak ellenőrzéses futást, a visszaállítás előtti automatikus vészmentést, az üres tesztgépes helyreállítást és a megszakadt visszaállítás folytatását.
- Új `BIZTONSAGI_MENTES_ES_VISSZAALLITAS.txt` dokumentum készült a pontos PowerShell-parancsokkal, magyarázatokkal, visszaállítás utáni ellenőrzésekkel és hibaelhárítással.
- A mentési kimeneti könyvtárak és nagy archívumfájlok bekerültek a `.gitignore` fájlba.
- Adatbázis-migráció nem szükséges.

## [0.9.2] - 2026-08-03

### Gépadatok a munkalapnézetekben és teljes szállítói fejléc

- A Munkalapok alaplistája új, alapértelmezetten látható `Gép / gyári szám` oszlopot kapott; több kapcsolt eszköz külön sorokban jelenik meg.
- A munkalap Áttekintés nézetében a géptípus és gyári szám összefoglaló kártyán és külön, kattintható kapcsolt-gép blokkban is látható.
- A nyomtatott munkalap szállítói fejlécének minden adata a Beállításokban Admin által szerkeszthető cégprofilból származik.
- A nyomtatási fejléc a cégnév, adószám, cégjegyzékszám, telefon és email mellett címet, kapcsolattartót és weboldalt is megjelenít.
- A cégprofil API külön `display_name` és `address_for_worksheet` mezőket ad vissza, így a nyomtatási nézet ugyanazt a normalizált adatot használja, mint a munkalap-sablon.
- Adatbázis-migráció nem szükséges.

## [0.9.1] - 2026-07-31

### Helyi jelszó-visszaállítás VS Code-ból

- Új `python -m app.reset_password` helyreállító parancs készült elveszett felhasználói jelszavak biztonságos visszaállításához.
- A parancs rejtett bevitelként kétszer kéri be az ideiglenes jelszót, és ugyanazt a jelszószabályt ellenőrzi, mint a webes felület.
- A visszaállított felhasználónál kötelező következő jelszócsere áll be; az admin helyreállító feladat szükség esetén a fiókot is újraaktiválja.
- A művelet rendszereredetű auditbejegyzést készít, de jelszó vagy jelszóhash nem kerül a naplóba.
- Két VS Code-feladat került a projektbe: `Admin jelszó helyreállítása` és `Felhasználói jelszó visszaállítása`.
- Két célzott backendteszt ellenőrzi a visszaállítást, a kötelező jelszócserét, az auditot, a jelszószabályt és az ismeretlen felhasználó elutasítását.

## [0.9.0] - 2026-07-31

### Két technikus, közvetlen számlálórögzítés és munkalap-felület javításai

- Egy munkalaphoz elsődleges és opcionális második technikus rendelhető; ugyanaz a felhasználó nem választható mindkét helyre.
- A második technikus megjelenik a listákban, részletezőben, szűrésben, nyomtatásban és kompatibilitási exportokban, továbbá jogosult a hozzá rendelt munkalap lezárására.
- Új `0015_secondary_technician` Alembic migráció készült az opcionális második technikus tárolásához.
- A munkalap Áttekintés és Szerkesztés nézetéből közvetlenül elérhető az összes, FF, színes és scan számláló rögzítése, betöltési állapottal és kézi frissítéssel.
- A munkalapszerkesztő több dinamikus anyagsort kezel; szerkesztéskor az összes meglévő anyag betöltődik és visszamenthető.
- Kész vagy lezárt munkalap Áttekintés nézetében a tervezett idő helyett a tényleges munkavégzés kezdete és befejezése jelenik meg.
- A nyomtatott munkalapról kikerült a kiállítás dátuma és a belső tervezett idő; a tényleges munkavégzés és mindkét technikus megjelenik.
- Öt új API-regressziós teszt készült; a backend tesztcsomag 62 tesztre bővült. A tesztek a naptári megjelenítést, a technikus törlését és a 0.8.x mentések visszaállítását is lefedik.

## [0.8.2] - 2026-07-30

### Archív fájl törlése és közvetlen munkalap-archiválás

- Admin felhasználó az archívum bármely megjelenési helyéről véglegesen törölheti a feltöltött archív fájlt.
- A törléshez pontosan a `TÖRÖL` szót kell begépelni; a jogosultságot és a megerősítést a backend is ellenőrzi.
- A törlés eltávolítja az archív rekordot, az eszközkapcsolatokat és a fizikai fájlt, miközben audit- és eszköztörténeti bejegyzést hagy.
- A munkalap részletező fő műveletei közé bekerült az `Archiválás` gomb.
- A munkalaplista műveleti menüjében az Excel munkalap helyét az archiválás vette át.
- Az `Excel munkalap` gomb minden munkalap-felületről kikerült; a kompatibilitási API-végpont egyelőre megmaradt.
- Adatbázis-migráció nem szükséges.

## [0.8.1] - 2026-07-30

### Munkalapidők időzóna-kezelésének javítása

- A szerkesztő többé nem alakítja UTC-re a backend időzóna nélküli, helyi munkalapidőit.
- A tervezett kezdés, tervezett befejezés, tényleges kezdés és tényleges befejezés szerkesztéskor változatlan idővel töltődik vissza.
- A munkalap lezárása a `datetime-local` mezők helyi idejét közvetlenül küldi a backendnek, így nem keletkezik újabb UTC-eltolás.
- Külön regressziós tesztek fedik a téli és nyári időszámítás alatti helyi időket, valamint a valóban időzónával jelölt bemeneteket.
- Adatbázis-migráció nem szükséges.

## [0.8.0] - 2026-07-28

### Új munkalaptípusok és jelszóbiztonság

- A munkalapok munka típusa két új értékkel bővült: `kiszállítás` és `üzembe helyezés`.
- A két új típus létrehozáskor, szerkesztéskor, szűréskor, részletezéskor, nyomtatáskor és Excel exportban is használható.
- A bejelentkezési email- és jelszómezők többé nincsenek előre kitöltve.
- Friss telepítésnél az `admin@example.com` felhasználó kezdeti jelszava üres, és az első belépés után kötelező azonnal új jelszót beállítani.
- A kötelező jelszócsere backendoldalon is blokkolja az alkalmazás többi végpontját.
- Minden felhasználó saját maga módosíthatja a jelszavát a jelenlegi jelszó ismeretében.
- Az új jelszó legalább 8 karakteres, legalább egy nagybetűt és egy speciális karaktert tartalmaz.
- Az admin által létrehozott felhasználók és jelszó-visszaállítások kötelező első jelszócserét kapnak.
- Új `0014_user_password_policy` Alembic migráció készült; a korábbi teljes mentések felhasználói sémája visszafelé kompatibilisen visszaállítható.
- Három új API-teszt; a backend tesztcsomag 56 tesztre bővült.

## [0.7.2] - 2026-07-27

### Archív feltöltés az archívum aloldalról és lezáráskor

- A Munkalapok → Archívum aloldal közvetlen „Archív munkalap feltöltése” gombot kapott.
- A globális feltöltésnél az eszköz kötelező, a kapcsolódó digitális munkalap opcionálisan kiválasztható.
- A digitális munkalap választó csak a kijelölt eszközhöz kapcsolódó munkalapokat mutatja.
- A munkalap lezárási oldaláról közvetlenül feltölthető az aláírt vagy beszkennelt archív példány.
- Új jogosultságvédett globális archívfeltöltési API-végpont és célzott API-teszt készült.

## [0.7.1] - 2026-07-27

### Beágyazott munkalap-archívum és előnézet

- A munkalap-archívum a Munkalapok oldal aloldalaként érhető el; a külön oldalsáv-menüpont megszűnt.
- A munkalaplista sorai kibonthatók, és közvetlenül alattuk megjelennek a kapcsolt archív fájlok.
- A kibontott archívumból új fájl közvetlenül a kiválasztott munkalaphoz tölthető fel.
- A PDF-, JPG- és PNG-archívumok hitelesített modális előnézetet kaptak.
- Új, inline tartalomkezelésű `/preview` API-végpont és előnézeti auditbejegyzés készült.
- A korábbi `/work-order-archives` útvonal kompatibilitási átirányítással az új `/work-orders/archives` aloldalra vezet.

## [0.7.0] - 2026-07-27

### Részletes nyomtató-számlálók

- Az eszközök számlálótörténete az összes érték mellett opcionális FF, színes és scan számlálókat tárol.
- A globális Excel-import és -export új számlálóoszlopokat kezel, és a meglévő, azonos időpontú összes számlálósorokat duplikáció nélkül egészíti ki.
- A korábbi külön számlálóimport felismeri az `FF záró`, `Színes záró` és `Scan záró` oszlopokat is.
- A gyors számlálórögzítés, az eszköz adatlapja és a munkalap szervizfelülete kezeli a részletes csatornákat.
- A munkalap részletező, böngészős nyomtatási és Excel nézetén az utolsó ismert számlálók a mérés dátumával együtt jelennek meg.
- Új `0013_meter_channels` Alembic migráció és bővített globális importminta.
- Két új API-teszt; a backend tesztcsomag 52 tesztre bővült.

## [0.6.1] - 2026-07-26

### Munkalap-archívum megjelenítés

- Az archív munkalapok táblázatában a fájlnév és fájlméret helyett a feltöltéskor megadott megjegyzés jelenik meg.
- A hitelesített letöltési művelet és az eredeti letöltési fájlnév változatlan maradt.

## [0.6.0] - 2026-07-26

### Munkalap-archívum

- Egyedi `AR-ÉV-SORSZÁM` archiválási azonosító minden feltöltött fájlhoz.
- PDF, JPG és PNG fájl feltöltése meglévő digitális munkalaphoz.
- A munkalaphoz feltöltött archív fájl automatikus hozzárendelése a munkalap aktuális eszközeihez.
- Korábbi papíralapú munkalap közvetlen archiválása az eszköz adatlapjáról, digitális munkalap létrehozása nélkül.
- Globális, kereshető munkalap-archívum és hitelesített fájlletöltés.
- Feltöltési és letöltési auditnapló, valamint eszköztörténeti bejegyzések.
- Az archív fájlok bevonása az 5-ös verziójú teljes mentésbe és visszaállításba.
- Új Alembic migráció, konfigurálható archív tárhely és fájlméretkorlát.
- Öt új API-teszt; a backend tesztcsomag 50 tesztre bővült.

## [0.5.0] - 2026-07-23

### Főbb funkciók

- Többfelhasználós munkalap- és eszköznyilvántartás szerepkörökkel.
- Ügyfél-, helyszín-, kapcsolattartó-, eszköz-, anyag- és munkalapkezelés.
- Munkalaplista külön részletező, szerkesztési és lezárási aloldalakkal.
- Szerveroldali lapozás, rendezés, szűrés és mentett munkalapnézetek.
- Tömeges munkalap-létrehozás, szerkesztés és nyomtatás.
- Optimista zárolás és aktív szerkesztési jelenlét több felhasználóhoz.
- Nyomtatószámláló-, alkatrész- és karbantartási cikluskövetés.
- Karbantartási előrejelzések és Dashboard munkaszervezési nézetek.
- Egységes globális Excel import/export.
- Teljes adatbázis- és beállításmentés, valamint visszaállítás.
- Böngészős és Excel munkalapnyomtatás.

### Verziókövetés

- Központi `VERSION` fájl.
- Backend `/api/version` végpont.
- Verzió megjelenítése a kezelőfelületen és a Swagger dokumentációban.
- Alkalmazásverzió rögzítése a teljes mentések manifestjében.
- Kiadást előkészítő `scripts/set_version.py` segédprogram.

### v0.30.0 hotfix5 - runtime volume ownership
- Non-root backendhez idempotens `runtime-permissions` one-shot service került be.
- Meglévő `app_runtime` volume adatvesztés nélkül `10001:10001` tulajdonra rendezhető.
- Physical restore után a backup-agent normalizálja a runtime ownershipet.


## v0.30.0 hotfix6 – local development port wiring

- A `start-v0.30.0-hotfix.ps1` most explicit módon betölti a meglévő `docker-compose.dev.yml` override-ot.
- A frontend localhost portja így `127.0.0.1:3000` címen publikálódik lokális indításkor.
- Production port exposure nem változott; a publikus edge továbbra is a production Caddy konfiguráció feladata.
