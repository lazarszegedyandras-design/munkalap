# IMPLEMENTATION REPORT v0.28.0

## Scope

v0.28.0 adds Firebase Cloud Messaging push delivery and a reproducible Android signing/build pipeline on top of the v0.27 technician app.

## Backend

- `0032_push_notifications` migration.
- Per-device FCM registration state on `mobile_devices`.
- Transactional `push_delivery_outbox` with deduplication, retry state, locking and provider message IDs.
- Dedicated `push-worker` process; business API transactions never call FCM directly.
- FCM HTTP v1 sender using OAuth2 service-account credentials and `google-auth`.
- Invalid/unregistered FCM tokens are disabled automatically.
- Mobile endpoints to register/remove the current device token.
- New work-order assignment and planned-time changes create immediate technician notifications. v0.28 intentionally does not expose HR/CRM/procurement notification text on the Android lock screen.
- Push outbox is ephemeral and excluded from logical restore.
- FCM tokens are redacted from backups and disabled after restore.

## Android client

- Capacitor Push Notifications plugin.
- Android notification permission request and `work_orders` channel.
- Automatic FCM token registration after authenticated session restore/login.
- Foreground notification banner.
- Notification tap deep-links directly to the referenced work order.
- Logout removes server push registration and unregisters the local FCM token best-effort.

## Android native build/signing

- Firebase `google-services.json` is external to source control.
- Debug APK build script.
- Release APK and Play AAB build scripts.
- Upload keystore generator with 4096-bit RSA key and long validity.
- Signing passwords and keystore path are supplied only through environment variables.
- Release artifacts are copied to `mobile/native-dist/` with SHA-256 sums.

## Production configuration

Public production requires:

- `PUSH_NOTIFICATIONS_ENABLED=true`
- valid `FCM_PROJECT_ID`
- `secrets/firebase_service_account.json`
- Firebase Android `google-services.json` on the Android build machine

The VPS preflight validates the service-account JSON and ensures its `project_id` matches the configured Firebase project.

## Security properties

- Firebase private key is not included in the application ZIP or Android APK.
- FCM device tokens are not restored from backups.
- One registration token cannot remain assigned to two users/devices in the database.
- Push delivery failures do not roll back business transactions.
- Duplicate notification enqueueing is blocked per device/dedupe key. FCM delivery remains an at-least-once external transport, so a provider/network ambiguity can still produce a duplicate display.
- Short-lived Google OAuth tokens are generated from the service-account credential for FCM HTTP v1.

## Remaining environment-dependent acceptance

A signed APK/AAB requires a machine with Node/npm, JDK, Android SDK/Gradle dependencies, a real Firebase project, `google-services.json`, and the upload keystore. A live FCM delivery test also requires the production Firebase credentials and a physical/emulated Android device with Google Play services.

## Verification

Release-side verification completed in the available build environment:

- Backend API/application regression: **113/113 PASS**, executed in two batches. The host does not have the pinned `python-jose`/`passlib` packages, so authentication primitives were supplied by release-external test shims only; no shim is included in the release and production dependencies were not replaced.
- v0.28 push-specific coverage includes token registration/removal, assignment/schedule outbox creation, backup redaction, worker claim/success, invalid-token unregister behavior, production FCM configuration guard and the FCM HTTP v1 request/error mapping.
- Backup-agent/release regression: **49/49 PASS**.
- Existing web frontend regression: **31/31 PASS**.
- Mobile source tests: **7/7 PASS**.
- TypeScript parser validation: web frontend **50 files / 0 syntax errors**, mobile **18 files / 0 syntax errors**.
- Python compile, shell syntax and Compose YAML parse: **PASS**.
- Clean Alembic migration from `0001_initial` to **`0032_push_notifications (head)`**: **PASS**, single head.
- Android upload-keystore generator: **PASS** with a test-only external keystore; generated PKCS12/signing environment permissions were both `0600`.

## Build-environment limitation

A native APK/AAB was **not** produced in this execution environment. Java 21 and `keytool` are available, but no Android SDK is installed/configured. In addition, the environment cannot currently resolve `registry.npmjs.org` (`EAI_AGAIN`), so the Capacitor/push plugin dependencies cannot be installed. No real Firebase `google-services.json` or service-account credential is available here, and these secrets/config files are intentionally not fabricated or embedded into the release.

The included build scripts therefore remain the production path for generating the debug APK, signed release APK and Play AAB on the actual Android build machine after the Firebase files and Android SDK are supplied.
