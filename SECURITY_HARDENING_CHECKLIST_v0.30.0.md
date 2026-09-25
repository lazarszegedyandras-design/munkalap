# SECURITY HARDENING CHECKLIST – v0.30.0

## P0 code controls

- [x] High-risk permission list includes `admin.backup.restore`.
- [x] High-risk permission forces MFA setup during login.
- [x] Rate-limited `POST /api/auth/mfa/step-up` exists.
- [x] Step-up updates only the current server-side session.
- [x] TOTP replay protection and recovery-code consumption remain active.
- [x] Restore, recovery clear, settings ZIP restore and user privilege writes require recent MFA.
- [x] Frontend retries a sensitive request at most once after successful step-up.
- [x] Runtime, migration and owner PostgreSQL roles are separated.
- [x] Existing-volume role provisioner is idempotent and uses parameterized/quoted SQL.
- [x] PostgreSQL 16 owned sequence detection uses `pg_depend` dependency types `a` and `i`; only standalone sequences receive explicit ownership transfer.
- [x] The security gate contains a two-run PostgreSQL provisioner regression with unchanged fixture business data verification.
- [x] Backend and push-worker do not receive admin/migration DB secrets.
- [x] Backend runtime entrypoint does not run Alembic.
- [x] Backend and migrate start directly as fixed uid/gid `10001:10001`; neither entrypoint performs runtime privilege switching.
- [x] Backend and migrate retain `cap_drop: ALL` and `no-new-privileges` without `CAP_SETUID`/`CAP_SETGID`.
- [x] Backend image ownership is established at build time; entrypoints perform no runtime `chown`/`chmod`.
- [x] Backup-agent does not mount Docker socket or contain Docker CLI.
- [x] Backup-runner is the only Docker-socket service.
- [x] Runner has no host-published port and is isolated on `privileged_net`.
- [x] Backend is absent from `privileged_net` and does not receive runner token.
- [x] Runner exposes only typed, allowlisted operations; no generic command/argv endpoint exists.
- [x] Production preflight covers new MFA, DB, token, socket and network invariants.

## Verification evidence in build workspace

- [x] Version synchronization PASS: `0.30.0`.
- [x] Python syntax/AST PASS.
- [x] Shell syntax PASS.
- [x] Compose YAML parse PASS.
- [x] Static Compose trust-boundary checks PASS.
- [x] Release configuration tests – 33/33 PASS.
- [ ] Full backend regression – BLOCKED in current environment.
- [ ] Full backup-agent regression – BLOCKED in current environment.
- [ ] Backup-runner unit tests – BLOCKED in current environment.
- [x] Frontend Node regressziós tesztek – 33/33 PASS.
- [ ] Frontend production build – BLOCKED in current environment.
- [ ] Effective production Compose validation – BLOCKED in current environment.
- [ ] Live `workapp_app` negative DDL / positive CRUD acceptance – BLOCKED in current environment.
- [ ] Fresh existing-volume migration/provisioning acceptance – BLOCKED in current environment.
- [ ] PostgreSQL 16 SERIAL/IDENTITY/standalone sequence provisioner regression – BLOCKED in current environment.
- [ ] Live migrate non-root exit 0, Alembic head and `workapp_migrate` identity gate – BLOCKED in current environment.
- [ ] Live backend non-root and `workapp_app` identity gate – BLOCKED in current environment.
- [ ] MASTER + incremental + validation + restore + rollback acceptance – BLOCKED in current environment.
- [ ] Offsite backup/restore-stage acceptance – BLOCKED in current environment.

## Production GO decision

- [ ] `deploy/vps/security-hardening-acceptance.sh` prints `SECURITY HARDENING v0.30.0: PASS` on the real target environment.
- [ ] The complete Windows isolated `acceptance-backup-restore.ps1` run remains PASS.
- [ ] Evidence output is retained with the release ZIP SHA-256.

Until every unchecked P0 item is complete, status is **FAIL / BLOCKED for public production GO**.
