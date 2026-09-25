# Munkalap v0.26.0 - Implementation Report

Date: 2026-09-06

## Scope

v0.26.0 implements the server-side foundation for the planned Android technician application. It deliberately does **not** ship an Android APK/AAB yet. The release adds a restricted mobile API, device-bound mobile sessions, immutable work-order completion snapshots, customer signature evidence, server-generated signed PDFs and backup/restore support for the evidence chain.

## Architecture

The existing FastAPI backend remains the sole authority for authentication, authorization and work-order business rules. The future Android client will be a second client of the same backend and will never connect directly to PostgreSQL.

### Mobile authentication

- `MobileDevice` identifies a user/device installation.
- `MobileSession` stores only HMAC hashes of refresh secrets; raw refresh tokens are returned only to the client.
- Access JWTs are short-lived and use token type `mobile_access`.
- Refresh tokens rotate on every successful refresh.
- Reuse of the immediately previous refresh token is treated as replay and revokes the whole mobile session.
- Device revocation invalidates every active session for that device.
- Existing password-change and MFA rules are enforced for mobile login.
- Mobile access is restricted to Technician and Admin roles; technicians also require the existing service-module access.

### Mobile work-order API

Implemented under `/api/mobile`:

- `POST /auth/login`
- `POST /auth/mfa/verify`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /me`
- `GET /devices`
- `DELETE /devices/{device_id}`
- `GET /work-orders/today`
- `GET /work-orders/{id}`
- `POST /work-orders/{id}/start`
- `POST /work-orders/{id}/meter-readings`
- `GET /materials`
- `POST /work-orders/{id}/complete`
- `GET /work-orders/{id}/completion`
- `POST /work-orders/{id}/signature`
- `GET /work-orders/{id}/signed-pdf`

A Technician can operate only on work orders assigned to that technician. Admin access is explicit and remains subject to active user/session checks.

## Immutable completion and signature evidence

`WorkOrderCompletionSnapshot` stores a canonical server-side JSON representation of the exact completed work-order content plus SHA-256 and monotonically increasing revision.

The signature endpoint accepts only the newest unsigned snapshot and refuses signing when `source_work_order_version` no longer matches the current work-order version. This prevents silently applying an old customer signature to changed content.

`WorkOrderSignature` records:

- snapshot/work-order identity;
- signer name and optional role;
- acceptance text and acceptance-text version;
- sanitized signature PNG storage key, SHA-256 and size;
- server-generated signed PDF storage key, SHA-256 and size;
- signing timestamp;
- technician, device and client IP evidence;
- finalized work-order version.

If the underlying work order is later edited, the historical snapshot/PDF remains intact and the API reports the prior signature as no longer current.

## Signature upload hardening

- PNG only.
- Configurable maximum size, default 1024 KiB.
- PNG magic/content validation.
- Pillow image verification and server-side sanitized re-encode.
- Dimension/pixel controls.
- Blank/near-empty signature rejection.
- Existing malware scanner integration is applied.
- Generated storage keys are server controlled and path-contained.
- Evidence files are written atomically and made read-only where the filesystem permits it.

## Signed PDF

The backend uses `reportlab==4.4.9` and pins `Pillow==12.3.0` for signature image validation/re-encoding. The production image installs DejaVu fonts for Unicode/Hungarian text rendering. The PDF includes the frozen work-order content, customer/supplier context, technician/work data, meter/material details, acceptance text, signature, signer identity, time, snapshot revision and snapshot SHA-256. The finished PDF receives its own SHA-256.

## Database migration

New Alembic revision:

`0030_mobile_signatures` -> down revision `0029_cloud_security`

Tables:

- `mobile_devices`
- `mobile_sessions`
- `work_order_completion_snapshots`
- `work_order_signatures`

The work-order evidence relationship intentionally does not cascade-delete signed history.

## Backup and restore

Logical backup format is now version 14.

Persisted:

- mobile devices referenced by evidence;
- completion snapshots;
- signatures;
- signature PNG files;
- signed PDF files.

Not persisted/restored:

- mobile sessions and refresh-token state.

A restore therefore cannot resurrect an old authenticated mobile session. Signature evidence is validated against database references during v14 backup/restore.

## Verification completed in this environment

- targeted mobile tests: 5/5 PASS;
- complete backend API suite: 105/105 PASS using test-only compatibility shims outside the release tree for unavailable `python-jose`/`passlib` packages;
- backup-agent/release tests: 47/47 PASS;
- clean Alembic upgrade through `0030_mobile_signatures`: PASS;
- one Alembic head: `0030_mobile_signatures (head)`.

Final release verification:

- targeted mobile security/workflow tests: 5/5 PASS;
- production mobile configuration validation test: PASS;
- complete backend API suite: 105/105 PASS using release-external auth compatibility shims;
- backup-agent/release suite: 47/47 PASS;
- frontend Node regression suites: 31/31 PASS;
- shell syntax, Compose YAML parse and Python compile: PASS;
- clean Alembic migration and single-head verification: PASS (`0030_mobile_signatures`);
- Docker Engine is unavailable in this execution environment; live Compose/VPS acceptance remains required;
- Vite production build is not claimable here because `frontend/node_modules`/`vite` are unavailable.

## Environment limitation

The execution environment does not provide Docker Engine, therefore a real production `docker compose build/up` and PostgreSQL/ClamAV/Caddy container acceptance cannot be claimed here. The shipped v0.25 production preflight/acceptance tooling remains the required live VPS gate.

## Next phase

v0.27.0 should implement the Android/Capacitor technician client against this API: login/device registration, today's jobs, work-order editing, camera attachments, completion review, customer signature pad and signed-PDF display. Full offline synchronization should remain a later phase.
