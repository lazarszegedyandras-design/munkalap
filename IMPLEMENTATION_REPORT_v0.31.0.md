# Implementation report – v0.31.0 Security Step 2

Dátum: 2026-09-12

## Alap

A v0.30.1 Step 1 teljes izolált acceptance-je 62/62 stage PASS eredménnyel lezárult. A v0.31.0 erre a baseline-ra épül, és a publikus VPS production security gate-et valósítja meg.

## Fő változások

- Új fail-closed Trivy scan pipeline source/image vulnerability, secret és misconfiguration ellenőrzéssel, kötelező friss vulnerability DB-vel és nem felülírható evidence könyvtárral.
- A Trivy v0.74.0 scanner GHCR manifest digesttel rögzített; a scan nem kap Docker socketet.
- Production host gate: UFW default-deny + restricted SSH (extra numeric/OpenSSH allow tiltással), SSH effective config, Docker daemon/socket, seccomp, NTP, unattended upgrades, host-port exposure.
- Production Compose preflight megerősítve: plaintext secret tiltás, exact proxy CIDR, auth rate-limit tartományok, edge-only port publishing, bounded container logging, secret/capability trust boundary-k.
- A backend többé sem development, sem production Compose alatt nem kap bootstrap-admin jelszó környezeti változót; a bootstrap secret kizárólag a one-shot migrate service-é.
- Frontend container `cap_drop: ALL`.
- Caddy edge: admin API off, TLS 1.2/1.3, TRACE/CONNECT tiltás, docs/OpenAPI blokkolás, teljes security header policy.
- Nginx: connection limit, explicit 429 status, web + mobile auth rate limiting.
- Caddy explicit forwarding-header felülírás: kliens `X-Forwarded-For` spoofing nem vihető tovább a belső limiter/audit felé.
- Live acceptance: exact tested application image IDs + aktuális scanelt runtime image ID-k, redirect/header/TLS/docs/TRACE/rate-limit/anti-spoof, audit chain.
- Offsite staged restore: alkalmazás backup checksum-manifestek teljes SHA-256 ellenőrzése.
- Új Step 2 orchestrator strukturált evidence/report kimenettel.
- Uptime Kuma 2.5.3 -> 2.5.4 frissítés a 2026-09-11-i security-fix release-re.

## Aktuális upstream ellenőrzés a fejlesztéskor

- Trivy: v0.74.0 (2026-08-14), scanner manifest digest rögzítve.
- Caddy: v2.11.4, a projektben már ez volt használatban.
- ClamAV: v1.5.4, a projektben már ez volt használatban.
- Uptime Kuma: v2.5.4 (2026-09-11), security fixeket is tartalmazó release.

## Helyben lefuttatott verifikáció

- `tests/release`: **55/55 PASS** (`python3 -m unittest discover -s tests/release -v`).
- `backup_agent/tests/test_release_configuration.py`: **38/38 PASS** (`python3 -m pytest backup_agent/tests/test_release_configuration.py -q`).
- `scripts/trivy_gate.py` célzott unit tesztek: a fenti release suite részeként PASS.
- Python compile: PASS a módosított Python security-gate modulokra.
- POSIX shell syntax (`sh -n`): **21/21 PASS** a `deploy/vps` shell scriptekre.
- Compose YAML parse: **3/3 PASS**; `docker-compose.yml` és `compose.yaml` byte-azonos.
- Nginx config syntax: **PASS** helyi `nginx -t` ellenőrzéssel (a backend host csak a syntax-próbához localhostra helyettesítve).
- Egyszerű high-signal source-secret mintaellenőrzés: **0 találat**; ez nem helyettesíti a cél-VPS-en futó Trivy secret scannert.

A teljes backend pytest helyben nem futtatható a projekt pinned `psycopg2`/konténer dependency-készlete nélkül; ezt nem jelöljük PASS-nak. A v0.31.0-hoz ezért kötelező új `test-release.ps1 -Suite all` futás a felhasználó Docker környezetében.

Az aktuális image CVE scan és a host/TLS/UFW/restore Step 2 acceptance csak a cél-VPS-en hiteles. A csomag ezeket automatizálja és blokkolóvá teszi, de helyi Docker/VPS hiányában nem állít róluk mért PASS eredményt.
