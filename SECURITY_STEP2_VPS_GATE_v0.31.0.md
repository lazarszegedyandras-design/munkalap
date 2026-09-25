# Security Step 2 – VPS production gate (v0.31.0)

## Cél

A Step 1 izolált release acceptance után ez a kapu a **valódi Ubuntu VPS és a tényleges production deployment** biztonsági állapotát ellenőrzi. A Step 2 nem helyettesíti az Android fizikai eszközös E2E/signing acceptance-et és nem ad önmagában teljes `production_go` státuszt.

## Beépített kapuk

1. **Production preflight**
   - kizárólag Docker secret fájlokban engedi a jelszavakat/tokent/kulcsokat;
   - pontos reverse-proxy host CIDR-t és korlátozott login rate-limit tartományokat követel;
   - ellenőrzi a Compose trust boundary-ket, a published portokat, capability-ket, bounded logolást és a tested-image lockot;
   - Caddy konfigurációt tényleges Caddy konténerrel validál.
2. **Host hardening gate**
   - aktív UFW, default inbound DENY, csak admin CIDR-ről engedett SSH, publikus 80/443; az extra SSH/OpenSSH application-profile allow szabály blokkol;
   - effektív `sshd -T`: jelszavas és keyboard-interactive login tiltva, root login tiltva, kulcsos auth engedélyezve, `MaxAuthTries <= 3`;
   - Docker 2375/2376 nincs publikálva, socket nem world-writable, seccomp aktív;
   - belső app/DB/backup/ClamAV portok nincsenek hoston publikálva;
   - NTP szinkron és unattended security update gate.
3. **Aktuális security scan**
   - Trivy v0.74.0 scanner image immutable GHCR manifest digesttel rögzítve;
   - a vulnerability DB minden production gate elején kötelezően frissül; frissítési hiba esetén FAIL, nincs csendes stale-cache fallback;
   - source vulnerability, secret és misconfiguration scan;
   - az összes Step 1-ben tesztelt saját image, valamint Caddy/ClamAV és opcionálisan Uptime Kuma image vulnerability scan;
   - minden CRITICAL CVE blokkol akkor is, ha még nincs upstream fix; HIGH CVE ismert javítással blokkol; minden secret finding blokkol; HIGH/CRITICAL misconfiguration blokkol;
   - vendor által még nem javított HIGH CVE külön kockázati tételként megmarad az evidence-ben, de nem blokkol automatikusan;
   - secret scanner nyers JSON-ja csak ideiglenes könyvtárban él, az evidence nem másolja ki a matched secret értéket;
   - a Trivy konténer **nem kap Docker socketet**: az image-ek host oldali `docker image save` tarból kerülnek scanre.
4. **Live HTTPS acceptance**
   - tested image ID-k futnak;
   - HTTP→HTTPS redirect, TLS cert >14 nap, TLS 1.2/1.3 Caddy policy;
   - HSTS, CSP, nosniff, frame, referrer és permissions headerek;
   - `Server` header elrejtve; docs/OpenAPI nem publikus; TRACE tiltva;
   - Caddy felülírja a kliens által küldött forwarding headereket; a publikus login 429 smoke változó hamis `X-Forwarded-For` mellett is bizonyítja, hogy a limiter nem kerülhető meg header-spoofinggal;
   - a futó Caddy/ClamAV/(opcionális) Uptime Kuma image ID-nek egyeznie kell az aktuálisan pullolt és scanelt runtime image ID-vel;
   - backend production config gate, audit hash-chain ellenőrzés, Firebase credential smoke, offsite config gate.
5. **Backup/restore acceptance**
   - új MASTER + offsite backup;
   - `restic check`;
   - offsite snapshot staged restore production felülírása nélkül;
   - minden visszaállított `checksums.sha256` manifest tényleges SHA-256 ellenőrzése;
   - külön explicit engedéllyel fizikai backup/restore drill.

## Release sorrend

A v0.31.0 forrás megváltozott, ezért a korábbi v0.30.1 image lock **nem érvényes**. Először új Step 1 full PASS kell, majd a pontos image-eket kell promotálni. A VPS deploy a Trivy gate-et még az `up` előtt lefuttatja.

A teljes Step 2 gate már futó production deploymenten:

```bash
sudo env RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE=YES \
  ./deploy/vps/step2-production-security-gate.sh
```

Evidence: `security-results/<UTC>-step2-v0.31.0/`. Meglévő evidence könyvtárat a gate nem ír felül.

Sikeres végállapot:

```text
status: PASS_STEP2_VPS_SECURITY_GATE
vps_security_go: true
production_go: false
```

A `production_go` szándékosan marad false, amíg az Android fizikai-eszköz E2E/release signing és a külön signed-document integrity/concurrency gate nincs lezárva.

## Fail-closed szabály

- bármely CRITICAL CVE, javítható HIGH CVE, secret vagy HIGH/CRITICAL misconfiguration blocker: deployment/gate FAIL.
- host hardening eltérés: FAIL.
- offsite vagy restore integritási eltérés: FAIL.
- fizikai restore drill explicit jóváhagyása nélkül: BLOCKED, nem PASS.
- scanner vagy dependency adatbázis nem elérhető: FAIL, nem "skip".
