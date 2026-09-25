# v0.30.0 migrate launch hotfix 2

## Verified source-state finding

The uploaded package already had a non-root migrate entrypoint and contained no runtime `gosu`, `su-exec` or `setpriv` invocation in the backend image, migrate entrypoint or base Compose service. Therefore the observed runtime message `failed switching to "app": operation not permitted` cannot be produced by the uploaded migrate script itself. The remaining credible deployment cause is stale/effective Compose or stale image metadata selected on the host during an in-place upgrade.

## Hotfix

- Added canonical `compose.yaml` so modern Docker Compose selects this release rather than an older `compose.yaml` left in the directory.
- Added an intentionally empty `compose.override.yaml` to neutralize an older same-name default override during extraction.
- Changed backend-image-based services to explicit Compose `entrypoint` values and empty `command` arrays. This removes any dependency on inherited/default image commands and prevents a stale command-only override from reintroducing `gosu`.
- Added startup fingerprints to backend and migrate logs.
- Added `start-v0.30.0-hotfix.ps1`, which explicitly uses `-f compose.yaml`, ignores `COMPOSE_FILE` for file selection, validates that the effective Compose config contains no privilege-switch helper, preserves named volumes, rebuilds, starts, and prints failure logs.

## Required Windows start command

Run from the extracted release directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-v0.30.0-hotfix.ps1
```

Do not run `docker compose down -v`.

## Expected migrate log prefix

```text
migrate-entrypoint v0.30.0-hotfix2 uid=10001 gid=10001
```

If that prefix does not appear, the host is still not executing this release's migrate entrypoint.
