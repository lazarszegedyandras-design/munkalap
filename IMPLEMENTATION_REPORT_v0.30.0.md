# IMPLEMENTATION REPORT – v0.30.0

## Release status

**Code status:** implemented security-hardening candidate.

No business-data migration was added. The Alembic application head remains `0032_push_notifications`.

## Implemented P0 controls

### High-risk MFA step-up

- `SENSITIVE_MFA_MAX_AGE_SECONDS`, production range `60..900`, default `300`.
- Dedicated step-up rate-limit namespace and configuration.
- `POST /api/auth/mfa/step-up` accepts TOTP or recovery codes, retains TOTP replay protection and updates only the current `AuthSession.mfa_verified_at`.
- Success and failure are audited without storing the submitted code.
- `RequireRecentMfa` protects physical restore, recovery-lock clearing, full ZIP restore, user creation/update and explicit permission assignment.
- A non-Admin principal with `admin.backup.restore` is now MFA-required during login as well.
- Reusable React `SecurityStepUpModal` retries the previously rejected action exactly once.

### PostgreSQL least privilege

- `workapp_owner`: `NOLOGIN`, owns the public application schema and application objects.
- `workapp_migrate`: non-superuser login role, member of `workapp_owner`, used only by the one-shot migration service.
- `workapp_app`: non-superuser runtime login role with schema usage and table/sequence DML only.
- Idempotent `backend/scripts/provision_db_roles.py` supports existing populated volumes, transfers existing object ownership and installs default privileges for future Alembic objects.
- PostgreSQL 16 compatibility: table-like objects are transferred before sequences; SERIAL/IDENTITY owned sequences are detected through `pg_depend` dependency types `a`/`i` and skipped, while standalone sequences are transferred explicitly.
- FastAPI and push-worker use only `database_url`/`workapp_app`.
- The `migrate` service alone receives `database_migration_url`; Alembic executes `SET ROLE workapp_owner`.
- The normal backend entrypoint runs only DB readiness and Uvicorn; no runtime DDL or seed.
- The shared backend image and the backend/migrate services run directly as fixed uid/gid `10001:10001`. Runtime `gosu`, `chown`, `chmod`, `CAP_SETUID` and `CAP_SETGID` are absent while `cap_drop: ALL` and `no-new-privileges` remain enforced.
- `check-db-privileges.py` verifies role flags, negative DDL/role creation and rollback-only CRUD/sequence access.

### Docker socket privilege separation

- `backup-agent` no longer mounts `/var/run/docker.sock` and its image no longer contains Docker CLI/Compose.
- `backup-runner` is the only Docker-socket service and has no published port.
- The backend cannot reach `privileged_net` and never receives `backup_runner_token`.
- The runner uses a separate constant-time compared token and typed, extra-field-forbidden request models.
- Supported operations are limited to allowlisted service metadata/lifecycle, pgBackRest actions, DB readiness, Alembic status, allowlisted image export and physical restore with runner-resolved image/volumes.
- No generic command, argv, container-ID, image, volume or host-path API exists.
- pgBackRest labels, PostgreSQL LSNs, services, timeouts and repository destinations are validated.

### Production gates

- Bootstrap creates separate admin/app/migration DB credentials plus distinct backup-agent and backup-runner tokens.
- Production preflight validates role usernames without printing URLs, token strength/separation, sensitive-MFA range, service presence, Docker-socket ownership, internal network boundary and secret exposure.
- Linux security acceptance includes backend, backup-agent and runner tests, frontend tests/build, Alembic single-head, live DB privileges, master/offsite backup and explicitly enabled physical restore drill.

## Security invariants

| Invariant | Required state |
|---|---|
| Backend Docker socket | NO |
| Backup-agent Docker socket | NO |
| Backup-runner Docker socket | YES – the only holder |
| Backend DB role | `workapp_app` |
| Runtime superuser / role creator / DB creator | false / false / false |
| Migration role | `workapp_migrate` with explicit `SET ROLE workapp_owner` |
| Recent MFA for restore/security writes | enforced |
| Runner reachability | only backup-agent over internal `privileged_net` |
| Generic runner command API | absent |

## Modified and added files

- Authentication and authorization: `backend/app/config.py`, `deps.py`, `schemas.py`, `routers/auth.py`, `routers/backups.py`, `routers/settings.py`, `routers/users.py`, `services/auth_security.py`, `backend/tests/test_api.py`.
- Database separation: `backend/Dockerfile`, `backend/entrypoint.sh`, `backend/migrate-entrypoint.sh`, `backend/migrations/env.py`, `backend/scripts/wait_for_db.py`, `provision_db_roles.py`, `check_db_privileges.py`, `check_db_role_provisioner.py`, `backend/tests/test_provision_db_roles.py`.
- Privileged runner: `backup_runner/Dockerfile`, `requirements.txt`, `runner.py`, `tests/test_runner.py`; `backup_agent/Dockerfile`, `runner_client.py`, `agent.py` and affected tests.
- Deployment: `docker-compose.yml`, `docker-compose.production.yml`, environment examples and the affected `deploy/vps` bootstrap, preflight, deploy, DB privilege/provisioner, restore and security acceptance scripts.
- Frontend: `SecurityStepUpModal.jsx`, `Backups.jsx`, `Settings.jsx`, `Users.jsx`, `frontend/tests/modules.test.js`.
- Release metadata and documentation: version-bearing files, `README.md`, `CHANGELOG.md`, production documentation/checklists and this report.

## New secrets

- `database_admin_url`
- `database_url`
- `database_migration_url`
- `database_app_password`
- `database_migrate_password`
- `backup_runner_token`

No secret value is included in this report.

## Migration

- Business-data Alembic migration: **not required**.
- Alembic head: `0032_push_notifications` (unchanged).
- Existing-volume DB role conversion: the new idempotent `db-role-provisioner` must complete before `migrate`.

## Verification executed in this workspace

| Command/check | Result |
|---|---|
| `python3 scripts/set_version.py --check` | PASS – `0.30.0` |
| `python3 -m compileall -q backend backup_agent backup_runner` and AST parse | PASS |
| `sh -n deploy/vps/*.sh backend/*.sh` | PASS |
| PyYAML parse of base and production Compose | PASS |
| Static Compose trust-boundary assertion harness | PASS |
| No-direct-Docker static assertion for backup-agent | PASS |
| No-argument functions from `backup_agent/tests/test_release_configuration.py` | PASS – 33/33 |
| `node --test frontend/tests/*.test.js` | PASS – 33/33 |
| PostgreSQL provisioner Python/shell syntax | PASS |

## Not verified in this workspace

- **NOT VERIFIED:** backend pytest – project runtime dependencies are unavailable locally.
- **NOT VERIFIED:** full backup-agent pytest – project runtime dependencies are unavailable locally.
- **NOT VERIFIED:** backup-runner pytest – FastAPI/pytest runtime is unavailable locally.
- **NOT VERIFIED:** frontend Vite production build – `npm ci --offline` could not resolve the incomplete package cache and registry access is unavailable.
- **NOT VERIFIED:** effective `docker compose config` and container builds – Docker is unavailable.
- **NOT VERIFIED:** Alembic single-head against the built migration service – Docker is unavailable.
- **NOT VERIFIED:** live runtime DB negative DDL and positive CRUD acceptance – Docker/PostgreSQL is unavailable.
- **NOT VERIFIED:** existing populated-volume provisioning/migration – Docker/PostgreSQL is unavailable.
- **NOT VERIFIED:** PostgreSQL 16 SERIAL/IDENTITY/standalone sequence integration and second provisioner run – Docker/PostgreSQL is unavailable; `deploy/vps/check-db-role-provisioner.sh` now performs this gate.
- **NOT VERIFIED:** real migrate service exit 0, Alembic head and effective `workapp_migrate` identity – Docker is unavailable; the security gate runs these checks.
- **NOT VERIFIED:** effective backend uid/gid and `workapp_app` secret identity – Docker is unavailable; `deploy/vps/check-backend-migrate-identities.sh` performs this gate.
- **NOT VERIFIED:** physical MASTER/incremental restore/rollback and offsite acceptance – Docker is unavailable.

The blocked checks are not recorded as PASS. Run `deploy/vps/security-hardening-acceptance.sh` in the target Docker-capable environment. The destructive restore stage intentionally refuses to run unless `RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE=YES` is set.

## Operational migration notes

1. Back up the current v0.29 deployment before updating.
2. Generate or add the new secret files: `database_admin_url`, `database_url`, `database_migration_url`, `database_app_password`, `database_migrate_password`, and `backup_runner_token`.
3. Do not delete or recreate the existing PostgreSQL volume.
4. Run production preflight.
5. Deploy; `db-role-provisioner` must finish successfully before `migrate`, and `migrate` before backend/push-worker.
6. Run DB privilege acceptance and the complete security hardening acceptance.
7. Do not expose `backup-runner:8091` or attach the backend to `privileged_net`.

## Production decision

**NO-GO**

Reason: the decisive P0 controls—existing-volume role conversion, effective container boundaries, live runtime DB privileges, and physical restore/rollback—have not been verified in a real Docker/PostgreSQL environment. Run `RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE=YES deploy/vps/security-hardening-acceptance.sh` on the target environment and retain its output with the ZIP checksum before changing this decision.

## Migrate launch hotfix 2

- A feltöltött forrásban a migrate már `10001:10001` userrel futott és nem tartalmazott `gosu`/`su-exec`/`setpriv` hívást, ezért a hoston látott `failed switching to "app"` üzenet stale/effective Compose vagy régi image/config használatára utalt.
- A backend, provisioner, migrate és push-worker explicit Compose `entrypoint`-ot kapott.
- Készült kanonikus `compose.yaml`, üres `compose.override.yaml` és `start-v0.30.0-hotfix.ps1` indító, amely explicit Compose fájlt használ.
- A migrate/backend log startup fingerprintet ír ki, így bizonyítható, melyik release entrypoint fut.
- Docker runtime acceptance ebben a buildkörnyezetben továbbra is **NOT VERIFIED**, mert Docker daemon nem érhető el.



## Migrate import-path hotfix 3

- A valós Windows/Docker indítás bizonyította, hogy a migrate már `uid=10001(app)` identitással futott, de a `python scripts/wait_for_db.py` közvetlen scriptindítás miatt az `/app` application root nem volt megbízhatóan importálható, ezért `ModuleNotFoundError: No module named 'app'` keletkezett.
- A backend és migrate entrypoint most `python -m scripts.wait_for_db` formában indítja a readiness modult.
- A `backend/scripts` explicit Python package lett, a backend image pedig `PYTHONPATH=/app` értéket kapott a deployment helper scriptek robusztus importjaihoz.
- A non-root modell változatlan: `10001:10001`, `cap_drop: ALL`, `no-new-privileges`; `gosu`, `SETUID` és `SETGID` nem került vissza.
- A hotfix helyi statikus/pytest ellenőrzése dokumentáltan futtatandó; a valós Docker/Alembic végrehajtás csak a célgépen igazolható.


## Migrate transaction hotfix 4

- A valós Docker/PostgreSQL futás igazolta, hogy az Alembic logban lefutott `0027`–`0032` revisionök után a seed még a régi sémát látta (`users.mfa_enabled does not exist`).
- Gyökérok: a `backend/migrations/env.py` a `SET ROLE workapp_owner` statementet az Alembic transaction megnyitása előtt futtatta. SQLAlchemy 2.x autobegin így egy külső tranzakciót nyitott, amely connection-close során rollbackelt.
- Javítás: a `SET ROLE` az Alembic `context.begin_transaction()` blokkjába került, ezért a role-váltás, DDL és `alembic_version` ugyanabban a commitolt tranzakcióban fut.
- Új regressziós teszt: `backend/tests/test_alembic_transaction_scope.py`.
- Docker/PostgreSQL runtime végrehajtás ebben a buildkörnyezetben továbbra is **NOT VERIFIED**; a célgépen a migrate lognak `0032_push_notifications` állapotban, seed hiba nélkül kell `exit 0`-val befejeződnie.

## Hotfix5 – runtime volume ownership
A Windows/Docker Desktop indítás során igazolt hiba: a backend uid=10001 mellett nem tudta írni a korábban root tulajdonban létrejött `app_runtime` volume-ot. A javítás külön, hálózat nélküli one-shot permission initializert ad, miközben a backend non-root security profilja változatlan marad. A restore workflow ownership-normalizálást is kapott.


## Hotfix6 – localhost frontend access

A launcher korábban csak a base `compose.yaml` fájlt használta, ezért a frontend `expose: 3000` portja nem volt elérhető a Windows hostról. A launcher most a base compose mellett a repository meglévő `docker-compose.dev.yml` fájlját is explicit betölti. A dev override loopback-only port bindinget használ (`127.0.0.1`), így nem növeli a LAN/publikus támadási felületet.
