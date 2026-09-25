# SECURITY MOBILE CHECKLIST v0.26.0

This is the security gate for clients using the v0.26 mobile API and for the future Android application.

## P0 - before any Android production use

- [ ] Public VPS v0.25 production checklist and acceptance are fully PASS.
- [ ] HTTPS is mandatory; Android cleartext HTTP is disabled.
- [ ] `SECRET_KEY`, MFA keys and database secrets are production-strength and stored outside source control.
- [ ] `MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES` is 1-30; recommended 15.
- [ ] `MOBILE_REFRESH_TOKEN_EXPIRE_DAYS` is 1-90; recommended 30.
- [ ] Admin MFA remains mandatory in production.
- [ ] Lost/stolen-device revocation is tested from Admin.
- [ ] Refresh rotation and replay revocation are acceptance-tested against the real PostgreSQL deployment.
- [ ] Mobile API authorization is verified with at least two technicians to prove cross-technician work-order access is denied.
- [ ] Signature upload malware scanning is enabled and fail-closed.
- [ ] Signature size limit is <=4096 KiB; recommended 1024 KiB.
- [ ] Signature files and generated PDFs are under backed-up runtime storage, not a public webroot.
- [ ] Backup/restore acceptance verifies both PNG and PDF evidence.
- [ ] Offsite backup immutability/versioning is active.
- [ ] Server clock/NTP and `BUSINESS_TIMEZONE=Europe/Budapest` are correct.
- [ ] Acceptance text and version have been legally/business reviewed before live signature collection.

## Evidence integrity

- [ ] Completion creates a server-side snapshot and SHA-256.
- [ ] Signing an outdated work-order version returns conflict and cannot reuse the old signature.
- [ ] A signed work-order edit never overwrites the previous snapshot, signature or signed PDF.
- [ ] Signed PDF SHA-256 matches the stored file.
- [ ] Deleting users/work orders with signature evidence is blocked or preserves the evidence chain according to DB constraints/business policy.

## Android client requirements for v0.27

- [ ] Refresh token is kept only in OS-protected secure storage/Android Keystore-backed storage.
- [ ] Tokens, passwords, signature pixels and personal data are not written to Logcat/crash logs.
- [ ] Release build is non-debuggable.
- [ ] Network Security Config rejects cleartext traffic.
- [ ] App backup/data-extraction rules are reviewed to prevent token leakage.
- [ ] Screens containing sensitive work-order data have an explicit screenshot policy.
- [ ] The app supports server-side device revoke and handles 401/re-auth cleanly.
- [ ] No database credential, server secret or privileged API key is bundled in APK/AAB.

## Legal/operational note

The on-screen handwritten signature implemented here is audit evidence tied to a specific immutable work-order snapshot. Do not label it as a qualified electronic signature (QES). If a future use case legally requires QES/advanced trust-service semantics, integrate an appropriate eIDAS trust service separately.
