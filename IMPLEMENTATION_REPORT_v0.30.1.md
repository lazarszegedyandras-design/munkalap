# Implementation report - v0.30.1 / Security step 1

## Decision

Implementation delivered. Host-side test results are recorded below. Full Docker/PostgreSQL/PowerShell execution is NOT VERIFIED in this authoring environment. Public VPS / digital-signature production decision remains **NO-GO** pending the subsequent security steps and target-environment acceptance.

## Baseline

- Input: `munkalap-eszkoz-app-v0.30.0-localhost-port-hotfix6.zip`
- Input SHA-256: `5584017545d91e3378fde398922a06253ac0a46d5abbf3fdab6c518056724a5c`
- Source release: 0.30.1. Alembic revisions and application business logic are unchanged.
- Scope: F07/reliable test execution, source/image identity, isolated test database, auditable test results.

## Implemented controls

1. Separate, generated Compose project with frozen hash-checked source, no production .env/secrets/volumes/ports/socket and a fresh run ID.
2. Disposable PostgreSQL 16 on tmpfs; fresh install and synthetic 0026 upgrade paths; separate-process schema-commit check, role-grant checks, serial/identity fixture, idempotency and internal backend/frontend restart smoke tests.
3. Tests have explicit entrypoints. Ordinary backend/migrate scripts reject unexpected arguments before touching a database or runtime directory.
4. Shared backend image across backend/migrate/provisioner/runtime-permissions/push-worker. Images are pinned by actual local ID for the test run.
5. Optional full-PASS promotion tags those exact IDs and creates a deployment lock; production deployment no longer silently rebuilds project images. This lock does not certify security or replace the remaining public-release gates.
6. DB regression helpers refuse non-test targets and require a matching run marker. The negative DDL probe accepts only SQLSTATE 42501, not arbitrary SQL errors.
7. Per-stage command/exit-code/log records, ephemeral credential redaction, timeouts and project-scoped cleanup. Missing prerequisites/tests do not produce a successful gate result.

## Actually executed in the authoring environment

| Check | Result | Scope / limitation |
|---|---:|---|
| New release harness unittest cases | 47 PASS | Real shell-entrypoint execution with safe program stubs; orchestration/guards/image tests use mocks, not Docker |
| Selected existing Python tests | 71 PASS | Host dependencies, not the release's complete pinned environment |
| Frontend Node unit tests | 33 PASS | Node 22.16.0; not browser E2E |
| Mobile Node unit tests | 7 PASS | Not Android-device testing |
| Total successful cases | 158 | 47 + 71 + 33 + 7 |
| Python AST syntax | 141 files PASS | Not full dependency/import validation |
| Bash syntax | 32 scripts PASS | Not actual script execution |
| Modified POSIX shell syntax | 8 scripts PASS | `sh -n` |
| YAML parse / canonical mirror | 5 files PASS | Not actual Compose merge/runtime |
| Full backend suite attempt | BLOCKED at collection | Missing python-jose and psycopg2 in host environment |
| Docker/PG16 integration | NOT VERIFIED | Docker/psql unavailable |
| PowerShell 5.1 execution | NOT VERIFIED | pwsh unavailable |

The full backend attempt exited 2; this is not reclassified as a test PASS. The Docker launcher is also run against the actual authoring environment to prove that an absent Docker produces BLOCKED, not a successful acceptance. Its machine-readable result is delivered separately with the evidence.

## Reproducible target commands

Windows: `test-release.ps1 -Suite all` in a separate source directory.<br>
Linux: `sh test-release.sh --suite all`.

A successful `--plan` is **PLAN_ONLY**, not a test result. A partial `unit` or `pg` run is not promotable. Reports are stored under `test-results/<run>/` and contain exact image IDs and source-manifest hash.

## Known limitations deliberately kept open

- Backend API tests still use SQLite; PG16 tests in this step cover deployment lifecycle/privileges/readiness, not MFA/refresh/signature concurrency.
- Backup unit suites run in the backend-derived test environment; the agent/runner project images are built but physical backup/restore is not tested here.
- Bundled import JSON already present in the source is retained and may be read by original tests/backend startup into the isolated DB. This is NOT a source-data anonymization release; source/images remain internal company material. No live database is mounted/copied.
- No production secrets, bootstrap-rotation, egress or signed-evidence integrity fixes in this step.
- No Android build/device, scanner/FCM/offsite, TLS/public-port, SAST/DAST/CVE or restore acceptance claim.
- No new transitive Python/base-image dependency lock: actual resolved packages and image IDs are recorded. The mobile project has no npm lockfile, so its new gate covers Node unit tests only.
- Evidence and source/image manifests are integrity records, not cryptographically signed attestations.
- Existing component startup fingerprints retain the earlier hotfix names; release identity now comes from VERSION, image labels and exact image IDs, not those old log strings.

## Change inventory

### Modified existing files
- `.dockerignore`
- `.env.example`
- `.env.production.example`
- `.gitignore`
- `CHANGELOG.md`
- `README.md`
- `VERSION`
- `acceptance-backup-restore.ps1`
- `backend/app/version.py`
- `backend/entrypoint.sh`
- `backend/migrate-entrypoint.sh`
- `backend/scripts/check_db_privileges.py`
- `backend/scripts/check_db_role_provisioner.py`
- `backup_agent/agent.py`
- `backup_agent/tests/test_release_configuration.py`
- `compose.yaml`
- `deploy/vps/check-backend-migrate-identities.sh`
- `deploy/vps/check-db-privileges.sh`
- `deploy/vps/check-db-role-provisioner.sh`
- `deploy/vps/deploy-production.sh`
- `deploy/vps/preflight-production.sh`
- `deploy/vps/security-hardening-acceptance.sh`
- `docker-compose.production.yml`
- `docker-compose.yml`
- `frontend/package-lock.json`
- `frontend/package.json`
- `mobile/.env.example`
- `mobile/package.json`
- `mobile/scripts/release-signing.gradle`
- `mobile/src/services/device.js`
- `scripts/set_version.py`
- `start-v0.30.0-hotfix.ps1`

### New files (before this report and generated manifest)
- `IMPLEMENTATION_REPORT_v0.30.1.md`
- `STEP1_TEST_BASELINE_v0.30.1.md`
- `backend/scripts/isolated_test_guard.py`
- `deploy/testing/Dockerfile`
- `deploy/testing/Dockerfile.dockerignore`
- `deploy/testing/Node.Dockerfile`
- `deploy/testing/Node.Dockerfile.dockerignore`
- `deploy/testing/pg_checks.py`
- `deploy/testing/pytest.ini`
- `release-source-manifest.json`
- `scripts/check_release_images.py`
- `scripts/promote_tested_images.py`
- `scripts/release_support.py`
- `scripts/release_tests.py`
- `test-release.ps1`
- `test-release.sh`
- `tests/release/test_orchestration.py`
- `tests/release/test_privilege_probe.py`
- `tests/release/test_release_harness.py`

Also added: this implementation report and `release-source-manifest.json`. Cached Python/pytest files are excluded from the release package.

## Windows Compose plugin discovery hotfix

A target Windows acceptance run exposed a launcher-only failure before any application test: `docker version` passed, while the sanitized runner environment made `docker compose version` return `unknown command: docker compose`. Direct PowerShell, CMD and Python subprocess calls all resolved Docker Compose v5.1.1 correctly. An A/B reproduction with the exact `clean_environment()` output proved that restoring `ProgramFiles` alone makes Compose discovery succeed.

The fix adds only `PROGRAMFILES` to the release runner allowlist. `ProgramW6432`, production Compose variables and application/database settings remain excluded. A regression test covers this exact boundary. No backend business logic, database migration, production Compose model or container privilege setting is changed by this hotfix.

Post-hotfix authoring verification: the isolated release-harness unittest suite runs **48/48 PASS**. Full Docker/PostgreSQL acceptance still has to be rerun on the target Windows host; this package does not convert the previous BLOCKED result into production GO.


## Target Windows acceptance follow-up: unit-test contract fixes

The first full target-host run after the Compose discovery hotfix completed 62 stages: 60 PASS and 2 unit stages FAIL. The Docker build, fresh PostgreSQL lifecycle, upgrade-from-0026 lifecycle, migrations, DB-role/ownership checks, backend/frontend smoke and restart checks all passed.

The backend suite failures were stale assertions rather than application failures: the mobile refresh replay path intentionally returns HTTP 401 while revoking the compromised mobile session, and the MFA step-up replay path returns HTTP 400 because the authenticated web session remains valid while the already-consumed TOTP code is invalid. The tests now assert those implemented contracts.

The release-harness failures all returned exit 126 from the shell-entrypoint execution tests. Those tests created executable command stubs inside the container runtime temporary filesystem; relying on runtime temporary storage being executable is not compatible with the hardened test-container model. The Python test image now bakes controllable, non-production command stubs into `/opt/release-entrypoint-test-bin` at image build time. Direct POSIX host execution retains the previous temporary-stub fallback. Production backend/migrate images, entrypoints, privileges and Compose services are unchanged.

This follow-up still does not claim production GO until a new target-host `-Suite all` run passes completely.

Follow-up authoring verification: the 48 release-harness unittests pass with the baked-stub branch exercised in a simulated image-filesystem location, and a static contract check confirms that the two corrected backend assertions match the existing application responses. The full pinned backend pytest suite was not rerun in this authoring environment because its exact dependency set is not locally available and outbound package installation is unavailable.
