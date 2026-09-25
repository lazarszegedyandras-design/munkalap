# Security / Release Checklist - v0.29.0

## P0 - kotelezo production gate

- [ ] Production API kizartolag HTTPS es `/api/mobile` vegpontot hasznal.
- [ ] `google-services.json` package neve `hu.munkalap.technician`.
- [ ] Firebase project id egyezik a jovahagyott production projekttel.
- [ ] Firebase service-account JSON csak VPS secret taroloban van.
- [ ] `google-services.json` nincs Gitben, Docker contextben vagy release ZIP-ben.
- [ ] Release keystore es signing jelszavak nincsenek repositoryban/release ZIP-ben.
- [ ] Release signing cert SHA-256 fingerprint rogzitett es preflighttal ellenorzott.
- [ ] APK alairas ervenyes es v2 vagy ujabb scheme-et hasznal.
- [ ] AAB JAR alairas ervenyes; ahol lehet, bundletool validate is PASS.
- [ ] `SHA256SUMS.txt` es `release-manifest.json` letrejott.
- [ ] `release-manifest.json` nem tartalmaz secretet vagy FCM tokent.
- [ ] Legalabb egy valodi Android eszkozon install/launch smoke PASS.
- [ ] Push registration Admin UI-ban aktiv, FCM token nem lathato.
- [ ] Admin/VPS teszt push FCM provider statusza `sent`.
- [ ] A telefonon a teszt push tenylegesen megjelenik.
- [ ] Work-order assignment push megjelenik es a deep link a helyes munkalapot nyitja.
- [ ] Schedule-change push megjelenik es a deep link a helyes munkalapot nyitja.
- [ ] Mobil eszkoz visszavonasa utan access/refresh/push hozzaferes megszunik.
- [ ] Production backup/restore acceptance PASS.
- [ ] Offsite backup check PASS es provider oldali torlesvedelem beallitva.

## P1 - erosen ajanlott

- [ ] Google Play Internal Testing csatornan az AAB telepitheto.
- [ ] Play App Signing / upload key ownership dokumentalt.
- [ ] Signing keystore legalabb ket, kulon fizikai/logikai helyen titkositva mentve.
- [ ] Kulso uptime monitor aktiv.
- [ ] Push worker failed/failed_permanent metric monitorozva.
- [ ] Admin mobil-eszkoz lista es revoke folyamat uzemeltetesi dokumentacio resze.
- [ ] Android alkalmazas privacy/notification szovege jovahagyva.

## Bizonyitasi kovetelmenyek

Mentsd el a release-hez:

- `VERSION`;
- release ZIP SHA-256;
- APK/AAB SHA-256;
- signing cert SHA-256 fingerprint;
- `release-manifest.json`;
- production acceptance output;
- backup/restore acceptance output;
- FCM provider smoke output;
- telefonos deep-link smoke rovid jegyzokonyve.

FCM `sent` nem azonos a telefonon torteno tenyleges megjelenessel; a manualis eszkozellenorzes kulon P0 kapu.
