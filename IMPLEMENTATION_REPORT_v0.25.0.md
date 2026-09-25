# Munkalap v0.25.0 - Implementation Report

Date: 2026-09-06

## Scope

v0.25.0 implements the second phase of the public-access roadmap: production VPS infrastructure on top of the v0.24.0 Cloud Security Foundation. This release does not add new business modules and does not add the Android client yet.

## Implemented

### Public TLS edge

- Added `docker-compose.production.yml`.
- Added a pinned Caddy edge service (`caddy:2.11.4-alpine`).
- Production host ports are limited to 80/443 at the edge layer.
- Caddy data/config are persistent so automatic certificate state survives container replacement.
- Caddy admin API is disabled.
- Public `/docs`, `/redoc` and OpenAPI paths are rejected at the edge in addition to `DOCS_ENABLED=false` in the backend.
- Added JSON edge access logging with bounded Docker local log rotation.

### Network exposure

- Removed the default frontend host port publication from base Compose.
- Development access is retained in `docker-compose.dev.yml`, bound to `127.0.0.1`.
- PostgreSQL and FastAPI remain internal-only.
- Added `management_net` and isolated backup-agent from `app_net`.
- `data_net`, `security_net` and `management_net` are internal Docker networks.
- Production uses a fixed application subnet and fixed frontend/backend/edge addresses so FastAPI can trust only the known frontend proxy IP.

### Proxy chain correctness

- Frontend nginx now preserves Caddy's sanitized client address and HTTPS scheme when proxying to FastAPI.
- Nginx rate limiting uses the forwarded client address rather than the Caddy container address.
- FastAPI production trust remains limited to the fixed frontend proxy address.

### Production secrets

- Added `.env.production.example`.
- Added production Docker secret files for PostgreSQL, database URL, application secret, MFA encryption key, backup-agent token, bootstrap Admin password, Restic password and S3 credentials.
- Added `deploy/vps/bootstrap-production-config.sh` to generate independent random application secrets with restrictive filesystem permissions.
- `.gitignore` and `.dockerignore` explicitly exclude production environment/secrets.

### VPS deployment tooling

Added:

- `deploy/vps/prepare-ubuntu-vps.sh`
- `deploy/vps/bootstrap-production-config.sh`
- `deploy/vps/configure-ufw.sh`
- `deploy/vps/harden-ssh.sh`
- `deploy/vps/preflight-production.sh`
- `deploy/vps/deploy-production.sh`
- `deploy/vps/acceptance-production.sh`
- `deploy/vps/production-status.sh`

The production preflight checks required commands, production security flags, secret-file permissions, DNS resolution, optional public-IP match, Docker network collision warning, Compose/Caddy configuration and minimum free disk space.

### Offsite encrypted backup

- Added Restic to the backup-agent image.
- Added S3-compatible offsite repository configuration.
- Local successful backup jobs can be copied into an encrypted Restic repository.
- Offsite state is persisted per backup job: status, snapshot ID, completion time and error.
- Backup status API and Admin backup page show offsite state.
- Added configurable retention defaults: 14 daily / 8 weekly / 12 monthly.
- Added a consistent backup-agent control SQLite snapshot before Restic backup.
- Added:
  - `deploy/vps/init-offsite-backup.sh`
  - `deploy/vps/run-backup-acceptance.sh`
  - `deploy/vps/offsite-check.sh`
  - `deploy/vps/offsite-restore-stage.sh`
- Offsite restore tooling is stage-only and does not overwrite production automatically.

### Monitoring

- Added public edge/frontend liveness and backend readiness deployment checks.
- Added an optional Uptime Kuma production profile bound only to localhost.
- Added `deploy/monitoring/README.md` and explicitly requires an external monitor outside the VPS for full host/provider/DNS outage detection.

### Container hardening / operations

- Added bounded Docker log rotation.
- Maintained read-only/non-root/no-new-privileges controls from v0.24.0 where applicable.
- Caddy uses read-only root filesystem and a minimal capability set.
- Backup-agent Docker-socket access is documented as an explicit privileged trust-boundary exception and is network-isolated.

## Database migration

No new business/database schema migration was required for v0.25.0. The Alembic head remains:

`0029_cloud_security (head)`

A clean SQLite migration run completed from `0001_initial` through `0029_cloud_security` with one head.

## Verification in this build environment

### PASS

- VPS shell scripts: POSIX shell syntax check PASS.
- Compose source files: YAML parsing PASS.
- Python compile check for backend and backup-agent PASS.
- Backup-agent/release tests: **45/45 PASS**.
- Frontend unit/regression tests: **31/31 PASS**.
- Targeted migration/backup-permission/release run: **27/27 PASS** (contains overlap with the release tests above and is not added to the total).
- Backend API regression: **99/99 PASS** using test-only compatibility shims outside the release archive.
- Clean Alembic migration to `0029_cloud_security`: PASS.
- Alembic single head: PASS.

### Environment limitations

Docker Engine is not available in the current execution environment. Therefore the following cannot honestly be marked PASS here:

- actual `docker compose config` merge validation by Docker Compose;
- image build;
- container startup/healthchecks;
- Caddy live certificate issuance;
- real ClamAV container readiness;
- real PostgreSQL/pgBackRest container acceptance;
- real S3/Restic upload/check/restore;
- VPS firewall/DNS/provider controls.

The release includes VPS-side preflight and acceptance scripts specifically to make these mandatory before go-live.

The current environment also lacks the pinned production packages `python-jose`, `passlib/bcrypt` and `psycopg2`. The 99 backend API tests therefore used temporary compatibility shims stored outside the project/release archive and SQLite as the test DB, matching the v0.24.0 verification constraint. Production code and dependency pins were not replaced by those shims.

## Residual risks / required live controls

1. **Docker socket:** backup-agent needs Docker control for destructive restore orchestration. Compromise of this service can have host impact. It has no published port and is isolated on an internal management network, but this remains a high-impact trust boundary.
2. **Offsite immutability:** Restic encryption does not make a repository immutable. Enable provider-side Object Lock/versioning/retention or the strongest append-only equivalent available, and avoid keeping break-glass delete credentials on the VPS.
3. **External monitoring:** optional local Uptime Kuma cannot detect total VPS/provider outage. At least one monitor must live outside this VPS.
4. **Provider controls:** DNS, provider firewall and object-storage settings must be applied and independently checked in the real environment.
5. **Live acceptance:** public access must not be enabled for users until all P0 items in `SECURITY_PRODUCTION_CHECKLIST_v0.25.0.md` pass.

## Release decision

**Code/infrastructure package status: READY FOR VPS ACCEPTANCE.**

**Public production status: NOT YET APPROVED** until the actual VPS executes preflight/deploy/backup/offsite/restore/monitoring gates successfully.
