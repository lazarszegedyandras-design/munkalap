# SECURITY PRODUCTION CHECKLIST v0.25.0

This checklist is the release gate for the first public VPS deployment of Munkalap v0.25.0.
The application must not be treated as public production until every P0 item is completed and the acceptance scripts pass on the actual VPS.

## 1. VPS and account baseline - P0

- [ ] Supported Ubuntu LTS host is fully patched.
- [ ] Docker Engine and the Docker Compose plugin are installed from a trusted package source.
- [ ] Daily unattended OS security updates are enabled.
- [ ] A non-root administrator account with SSH public-key authentication exists.
- [ ] A second administrator session can log in with the SSH key before password/root SSH is disabled.
- [ ] VPS provider firewall allows only TCP 80/443 publicly and restricts SSH to the administrator CIDR or VPN.
- [ ] `deploy/vps/configure-ufw.sh` has completed with the intended `ADMIN_SSH_CIDR`.
- [ ] `deploy/vps/harden-ssh.sh` has been run only after key-login verification.

## 2. DNS and TLS - P0

- [ ] `APP_DOMAIN` is a dedicated production hostname.
- [ ] DNS A record points to the VPS public IPv4.
- [ ] If an AAAA record exists, IPv6 is intentionally configured and firewalled; otherwise remove the AAAA record.
- [ ] TCP 80 and 443 reach the VPS from the public Internet.
- [ ] Caddy obtains a valid public certificate for `APP_DOMAIN`.
- [ ] HTTPS redirects and HSTS are visible from an external client.
- [ ] Certificate expiry monitoring is configured.

## 3. Production secrets - P0

Run `deploy/vps/bootstrap-production-config.sh` and then verify:

- [ ] `.env.production` mode is 600 or 400.
- [ ] `secrets/` mode is 700.
- [ ] Every file in `secrets/` is mode 600 or 400.
- [ ] PostgreSQL password is unique and not reused elsewhere.
- [ ] A PostgreSQL admin, `workapp_migrate` and `workapp_app` credential is present, unique and not reused elsewhere.
- [ ] `SECRET_KEY`, `MFA_ENCRYPTION_KEY`, `BACKUP_AGENT_TOKEN` and `BACKUP_RUNNER_TOKEN` are independent random secrets.
- [ ] Restic repository password is stored outside the Git repository.
- [ ] S3/object-storage access key is dedicated to this backup repository.
- [ ] Bootstrap Admin password is changed after first successful login.
- [ ] Admin MFA enrollment and recovery-code storage are completed before general access is enabled.
- [ ] `secrets/`, `.env`, and `.env.production` are absent from any release archive, Git commit and Docker build context.

## 4. Container exposure and network isolation - P0

After deploy, verify on the VPS:

- [ ] Only Caddy publishes TCP 80/443 to the public host.
- [ ] Frontend port 3000 is not publicly listening.
- [ ] FastAPI port 8000 is not publicly listening.
- [ ] PostgreSQL port 5432 is not publicly listening.
- [ ] Backup-agent port 8090 is not published.
- [ ] Backup-runner port 8091 is not published.
- [ ] ClamAV port 3310 is not published.
- [ ] `data_net`, `security_net`, `backup_api_net` and `privileged_net` remain Docker-internal networks.
- [ ] Only `backup-runner` mounts `/var/run/docker.sock`.
- [ ] Backend is absent from `privileged_net` and does not receive `BACKUP_RUNNER_TOKEN`.
- [ ] Frontend/backend containers use read-only filesystems where defined.
- [ ] `no-new-privileges` remains enabled.
- [ ] Production does not introduce `privileged: true` containers.

### Known privileged exception

The dedicated `backup-runner` mounts `/var/run/docker.sock` because destructive restore orchestration must stop/start allowlisted services and control the database container. This remains a high-impact trust boundary. The runner has no published port, is reachable only from the backup-agent on the internal `privileged_net`, uses an independent bearer token and exposes typed allowlisted operations instead of generic commands or caller-selected container resources. Do not connect the backend or a public network to `privileged_net`.

## 5. Application production security - P0

- [ ] `ENVIRONMENT=production`.
- [ ] `PUBLIC_BASE_URL=https://APP_DOMAIN`.
- [ ] `CORS_ORIGINS=https://APP_DOMAIN` only.
- [ ] `SESSION_COOKIE_SECURE=true`.
- [ ] `ADMIN_MFA_REQUIRED=true`.
- [ ] `SENSITIVE_MFA_MAX_AGE_SECONDS` is between 60 and 900 seconds.
- [ ] `DOCS_ENABLED=false`.
- [ ] `MALWARE_SCAN_ENABLED=true`.
- [ ] `MALWARE_SCAN_FAIL_CLOSED=true`.
- [ ] `TRUSTED_PROXY_CIDRS` contains only the fixed frontend proxy address used in the production Compose network.
- [ ] `/api/health/ready` returns `{"status":"ready"}` over public HTTPS.
- [ ] Security headers pass `deploy/vps/acceptance-production.sh`.

## 6. Offsite backup - P0

Public production requires an offsite copy in addition to the local pgBackRest/runtime repository.

- [ ] Dedicated S3-compatible bucket/repository exists outside the VPS.
- [ ] `RESTIC_REPOSITORY` points to the real repository.
- [ ] Restic password and object-storage credentials are populated in secret files.
- [ ] `deploy/vps/init-offsite-backup.sh` succeeds.
- [ ] `deploy/vps/run-backup-acceptance.sh` creates a successful local master backup and a successful offsite Restic snapshot.
- [ ] `deploy/vps/offsite-check.sh` succeeds.
- [ ] `deploy/vps/offsite-restore-stage.sh latest` can stage a snapshot without overwriting production.
- [ ] The staged restore has been inspected before any destructive recovery procedure is approved.
- [ ] Backup failure is operationally monitored.

### Ransomware / deletion protection

Restic encrypts backup contents, but encryption is not the same as immutability. If an attacker obtains credentials with delete rights, remote snapshots can potentially be removed. Enable the object-storage provider's strongest available versioning/Object Lock/retention or append-only protection, and use credentials scoped as narrowly as the provider allows. Keep any break-glass delete credential outside the VPS where possible.

Default retention in this release:

- daily: 14
- weekly: 8
- monthly: 12

Retention must be reviewed against business and legal requirements before go-live.

## 7. Monitoring and alerting - P0

- [ ] At least one uptime monitor runs outside the VPS.
- [ ] External monitor checks `https://APP_DOMAIN/health`.
- [ ] External monitor checks `https://APP_DOMAIN/api/health/ready`.
- [ ] Alerts reach at least one responsible person by a channel independent of the VPS.
- [ ] TLS certificate expiry is monitored.
- [ ] VPS disk capacity is monitored.
- [ ] Container restart/unhealthy state is monitored.
- [ ] HTTP 5xx growth is reviewed/alerted.
- [ ] Backup/offsite failure is reviewed/alerted.
- [ ] Optional local Uptime Kuma is bound to `127.0.0.1` only and accessed through SSH/VPN.

## 8. Deployment gates - P0

Run in this order from the application root on the real VPS:

```sh
sudo deploy/vps/prepare-ubuntu-vps.sh
./deploy/vps/bootstrap-production-config.sh APP_DOMAIN TLS_EMAIL BOOTSTRAP_ADMIN_EMAIL
# Fill RESTIC_REPOSITORY and object-storage credentials.
sudo ADMIN_SSH_CIDR=ADMIN.PUBLIC.IP/32 deploy/vps/configure-ufw.sh
deploy/vps/preflight-production.sh
deploy/vps/deploy-production.sh
RUN_DESTRUCTIVE_RESTORE_ACCEPTANCE=YES deploy/vps/security-hardening-acceptance.sh
deploy/vps/run-backup-acceptance.sh
deploy/vps/offsite-check.sh
deploy/vps/offsite-restore-stage.sh latest
```

Then, after verifying a second key-based SSH session:

```sh
sudo CONFIRM_SSH_HARDENING=YES deploy/vps/harden-ssh.sh
```

Go-live requires all of the following:

- [ ] `preflight-production.sh` PASS.
- [ ] `deploy-production.sh` PASS.
- [ ] `security-hardening-acceptance.sh` PASS, including DB least-privilege and physical restore evidence.
- [ ] `acceptance-production.sh` PASS.
- [ ] `run-backup-acceptance.sh` PASS including offsite status.
- [ ] `offsite-check.sh` PASS.
- [ ] Staged offsite restore completed successfully.
- [ ] First Admin login and MFA enrollment completed.
- [ ] External monitoring is actively alerting.
- [ ] DNS and provider firewall are documented.

## 9. Post-go-live checks - P1

- [ ] Review Caddy/backend security logs after the first day.
- [ ] Confirm no unexpected host ports are listening with `ss -lntup`.
- [ ] Confirm no container has been manually started with an ad-hoc public port.
- [ ] Confirm offsite snapshot creation after the first scheduled backup.
- [ ] Schedule a recurring restore drill.
- [ ] Schedule OS/container/dependency vulnerability review.
- [ ] Document a break-glass VPS recovery procedure and responsible contacts.

## Release limitation

This repository contains the production deployment controls and acceptance tooling, but it cannot itself perform provider-side DNS, provider firewall, S3 Object Lock/versioning or external-monitor account configuration. Those are explicit live-environment gates above.
