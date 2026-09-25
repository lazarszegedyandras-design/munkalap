# Public VPS deployment – v0.31.0

## Kötelező előfeltételek

1. Ubuntu VPS, Docker Engine + Docker Compose plugin.
2. A/AAAA DNS rekord a VPS-re.
3. Provider firewall: publikus TCP 80/443; SSH csak admin CIDR/VPN irányból.
4. `.env.production` és `secrets/` a `.env.production.example` alapján, 600/400 jogosultságokkal.
5. S3-kompatibilis offsite Restic repository.
6. Firebase service-account secret a push workerhez.
7. Külső uptime monitor a VPS-en kívül.
8. Step 1 `--suite all` PASS és az abból promotált `release-images.lock.json`.

## Első VPS hardening

```bash
sudo ./deploy/vps/prepare-ubuntu-vps.sh
./deploy/vps/bootstrap-production-config.sh app.example.hu admin@example.hu
```

A `.env.production` fájlban állítsd be legalább az `APP_DOMAIN`, `TLS_EMAIL`, `RESTIC_REPOSITORY`, `FCM_PROJECT_ID`, `ADMIN_SSH_CIDR` értékeket. Titkot ne írj bele; a secret fájlokat használd.

SSH kulcsos bejelentkezést egy második sessionben ellenőrizve:

```bash
sudo CONFIRM_SSH_HARDENING=YES ./deploy/vps/harden-ssh.sh
sudo ./deploy/vps/configure-ufw.sh
```

## Deploy

```bash
./deploy/vps/preflight-production.sh
./deploy/vps/deploy-production.sh
```

A deploy **még az `up` előtt** futtatja az aktuális Trivy security gate-et, és a scanner vulnerability DB-jét kötelezően frissíti. Minden CRITICAL CVE (fix elérhetőségétől függetlenül), javítható HIGH CVE, secret finding vagy HIGH/CRITICAL misconfiguration esetén a deployment leáll. Javítás nélküli HIGH CVE evidence-ként megmarad és külön kockázati felülvizsgálatot igényel.

A saját alkalmazás image-ek nem rebuildelődnek a VPS deploy során: a Step 1-ben tesztelt, promotált image ID-ket a `release-images.lock.json` köti a release source manifesthez.

## Teljes Step 2 VPS security gate

A deployment után:

```bash
sudo env RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE=YES \
  ./deploy/vps/step2-production-security-gate.sh
```

A gate sorrendje:

1. production preflight;
2. host UFW/SSH/Docker/seccomp/NTP/update ellenőrzés;
3. current source + image Trivy scan;
4. live HTTPS/TLS/header/rate-limit/audit acceptance;
5. MASTER + offsite backup acceptance;
6. Restic repository check;
7. staged offsite restore + SHA-256 artifact validation;
8. explicit fizikai backup/restore drill.

Evidence könyvtár: `security-results/<UTC>-step2-v0.31.0/`.

A Step 2 PASS csak `vps_security_go=true`. A teljes `production_go` továbbra is tiltva marad, amíg az Android fizikai készülék E2E/release-signing és signed-document integrity/concurrency kapuk nem PASS állapotúak.

## Targetált ellenőrzések

```bash
./deploy/vps/check-backend-migrate-identities.sh
./deploy/vps/check-db-role-provisioner.sh
./deploy/vps/security-scan.sh
./deploy/vps/acceptance-production.sh
./deploy/vps/run-backup-acceptance.sh
./deploy/vps/offsite-check.sh
./deploy/vps/offsite-restore-stage.sh latest
```

## FCM valódi eszköz smoke

```bash
./deploy/vps/push-smoke-test.sh <mobile_device_id>
```

Vagy `.env.production`:

```text
PUSH_SMOKE_DEVICE_ID=<mobile_device_id>
PUSH_SMOKE_WAIT_SECONDS=45
```

A szerveroldali PASS azt bizonyítja, hogy az FCM elfogadta a küldést. A készülék notification megjelenítését és deep linkjét az Android device E2E gate zárja le.

## Kapcsolódó dokumentumok

- `SECURITY_STEP2_VPS_GATE_v0.31.0.md`
- `IMPLEMENTATION_REPORT_v0.31.0.md`
- `STEP1_TEST_BASELINE_v0.30.1.md`
- `ANDROID_E2E_RELEASE_RUNBOOK_v0.29.0.md`
- `mobile/ANDROID_BUILD_SIGNING.md`
