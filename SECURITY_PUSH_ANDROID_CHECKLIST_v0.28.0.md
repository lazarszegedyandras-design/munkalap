# SECURITY / ANDROID RELEASE CHECKLIST v0.28.0

- [ ] Firebase project dedicated/approved for Munkalap.
- [ ] Android package is `hu.munkalap.technician`.
- [ ] `google-services.json` is stored outside Git and copied only at build time.
- [ ] Firebase service-account JSON is stored on the VPS as `secrets/firebase_service_account.json`, mode 600.
- [ ] Service account has only the permissions necessary to send FCM messages.
- [ ] `FCM_PROJECT_ID` matches the service-account `project_id`.
- [ ] Production preflight passes.
- [ ] FCM registration succeeds on a real Android device.
- [ ] New assignment push opens the correct work order.
- [ ] Schedule-change push opens the correct work order.
- [ ] Logout clears server push registration.
- [ ] Revoked/lost device no longer receives push.
- [ ] Backup contains no FCM registration token and no pending push outbox.
- [ ] Upload keystore is outside the repository and has an encrypted offsite backup.
- [ ] Signing environment file is mode 600 and not copied into release artifacts.
- [ ] Release APK signature verified with Android build tools.
- [ ] Release AAB built and accepted by Play Console / internal app distribution as applicable.
- [ ] SHA-256 of shipped APK/AAB recorded in release notes.

## Automatizált release ellenőrzés

A kódoldali kapuk v0.28.0 csomagolás előtt teljesültek: 113/113 backend regresszió, 49/49 backup/release teszt, 31/31 web frontend teszt, 7/7 mobil teszt, tiszta `0032_push_notifications` Alembic head, valamint shell/YAML/Python/JSX szintaktikai ellenőrzés. A fenti checkboxok közül a valódi Firebase-eszközön, VPS-en és Play/build környezetben végrehajtandó pontok szándékosan maradnak nyitva.
