# Migrate/backend non-root startup fix – v0.30.0

## Root cause

The migrate service started as root while its Compose security policy dropped every Linux capability. Its entrypoint then invoked `gosu app`, but without `CAP_SETUID`/`CAP_SETGID` the UID/GID transition was rejected before database readiness or Alembic could run.

The backend used the same runtime privilege-drop pattern with capabilities added back. That model was removed as well so the two services cannot diverge or fail at the same boundary.

## Fixed runtime model

- Image user: `10001:10001` (`app`).
- Backend Compose user: `10001:10001`.
- Migrate Compose user: `10001:10001`.
- `cap_drop: ALL`: retained.
- `no-new-privileges`: retained.
- Added capabilities: none.
- Runtime UID/GID switch, `gosu`, `su-exec`, `setpriv`, `chown`, `chmod`: none.
- Source and runtime-directory ownership is prepared during image build.
- The migrate entrypoint verifies the migration secret is readable, waits for PostgreSQL, runs Alembic, runs the idempotent seed and exits 0 only after success.

## Windows / Docker Desktop verification

From the application directory after replacing the source files:

```powershell
docker compose build --no-cache backend db-role-provisioner migrate push-worker
docker compose run --rm migrate
docker compose run --rm --no-deps migrate id
docker compose run --rm --no-deps backend id
docker compose run --rm --no-deps migrate alembic heads
docker compose up -d
docker compose ps -a
```

Expected identity for both inspected services:

```text
uid=10001(app) gid=10001(app)
```

The migrate container must finish with exit code `0`, and `alembic heads` must print exactly one `(head)` revision. Do not run `docker compose down -v`; the existing PostgreSQL volume must be retained.
