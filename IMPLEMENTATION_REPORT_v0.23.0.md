# Munkalap-Eszköz App v0.23.0 – implementációs riport

Dátum: 2026-09-05
Kiinduló verzió: v0.22.0
Célverzió: v0.23.0

## Elkészült

- Új Beszerzés modul minden aktív, bejelentkezett felhasználó számára.
- Saját beszerzési igény létrehozása, listázása, megnyitása és visszavonása.
- Kötelező tárgy, beszerzési cél, részletes leírás és pozitív összérték; pénznem alapértelmezésben HUF.
- Éves, tranzakcióbiztos `BESZ-YYYY-NNNN` azonosító.
- Külön `procurement.approve` jogosultság, amely az Admin / Felhasználók jogosultsági felületéről kiosztható.
- Jóváhagyói lista kérelmezővel, tárggyal, összeggel, státusszal és dátummal, kereséssel és szűréssel.
- Jóváhagyás és elutasítás; elutasításkor kötelező indoklás.
- Saját igény jóváhagyása/elutasítása backend oldalon is tiltott, Admin szerepkörrel is.
- Optimista version check és PostgreSQL sorzár a kettős döntés ellen.
- Több csatolmány: PDF, DOCX, XLSX, CSV, JPG/JPEG, PNG; maximum 25 MiB/fájl.
- A frontend a csatolmányokat fájlonként tölti fel, hogy a meglévő Nginx 26 MiB/kérés proxykorlát mellett több 25 MiB-os fájl is használható legyen.
- Collision-safe runtime fájltárolás, SHA-256 lenyomat, path traversal védelem és fájltípus-validáció.
- Beszerzési értesítések a jóváhagyóknak és a kérelmezőnek.
- Strukturált audit események létrehozásra, módosításra, visszavonásra, döntésre és csatolmány-műveletekre.
- Beszerzési előzménnyel rendelkező felhasználó végleges törlésének védelme; inaktiválás használható.
- Új `0028_procurement` Alembic migráció.
- Verziófrissítés 0.23.0-ra a VERSION, backend, frontend, backup-agent, Compose és acceptance konfigurációkban.

## Adatbázis

Új táblák:

- `procurement_request_sequences`
- `procurement_requests`
- `procurement_attachments`

Új jogosultság:

- `procurement.approve`

Alembic head:

- `0028_procurement`

## Ellenőrzések

### Backend

A teljes 99 darab backend pytest teszt két izolált futtatási batchben lefutott:

- 50/50 sikeres
- 49/49 sikeres
- összesen 99/99 sikeres

A futtató környezetből hiányzott a projektben deklarált `python-jose` és `passlib`, ezért kizárólag a tesztfuttatáshoz, a release könyvtáron kívül kompatibilitási shim készült. Ez nem része a kiadási ZIP-nek. A módosított production auth-kódhoz nem nyúlt a fejlesztés.

A három célzott beszerzés API-regressziós teszt külön is sikeres.

### Frontend

- datetime regresszió: 3/3 sikeres
- work order regresszió: 10/10 sikeres
- modul/jogosultság regresszió: 18/18 sikeres
- összes frontend saját teszt: 31/31 sikeres
- TypeScript parserrel szintaktikailag ellenőrzött frontend JS/JSX forrás: 50/50 sikeres

A `vite build` ebben a környezetben nem futott végig, mert a frontend `node_modules` nincs telepítve, az offline npm cache pedig nem tartalmaz minden szükséges csomagot (`yallist-3.1.1`). Ez környezeti korlát; a release ZIP nem tartalmaz `node_modules` könyvtárat.

### Migráció

- tiszta adatbázis migrációja headig: sikeres
- v0.22.0 schema head (`0027_leave_cancel_approval`) -> `0028_procurement`: sikeres
- `alembic current`: `0028_procurement (head)`
- `alembic heads`: egyetlen head, `0028_procurement`

### Docker

A végrehajtási környezetben Docker CLI/daemon nem állt rendelkezésre, ezért a Docker Compose image build és a teljes konténeres acceptance futás itt nem volt végrehajtható.

## Főbb új/módosított fájlok

Backend:

- `backend/app/routers/procurement.py`
- `backend/app/services/procurement_numbers.py`
- `backend/app/services/procurement_storage.py`
- `backend/migrations/versions/0028_procurement.py`
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/access_control.py`
- `backend/app/deps.py`
- `backend/app/services/audit.py`
- `backend/app/services/notifications.py`
- `backend/app/routers/users.py`
- `backend/tests/test_api.py`
- `backend/tests/test_backup_permissions.py`

Frontend:

- `frontend/src/pages/ProcurementRequests.jsx`
- `frontend/src/pages/ProcurementNew.jsx`
- `frontend/src/pages/ProcurementDetail.jsx`
- `frontend/src/pages/ProcurementApprovals.jsx`
- `frontend/src/App.jsx`
- `frontend/src/components/Layout.jsx`
- `frontend/src/pages/ModuleSelector.jsx`
- `frontend/src/pages/Users.jsx`
- `frontend/src/utils/permissions.js`
- `frontend/src/styles/app.css`
- `frontend/tests/modules.test.js`

Dokumentáció/verzió:

- `MUNKALAP_v0.23.0_BESZERZES_MODUL_CODEX_SPEC.md`
- `README.md`
- `CHANGELOG.md`
- `VERSION`
- `.env.example`

## Telepítési megjegyzés

A meglévő projekt indulási folyamatát kell használni. A backend indulásakor az Alembic migráció a projekt jelenlegi mechanizmusa szerint fut le. Éles adatbázis frissítése előtt a meglévő MASTER backup/restore eljárás szerinti mentés továbbra is szükséges.
