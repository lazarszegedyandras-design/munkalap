# v0.30.0 localhost port hotfix6

## Hiba

A local hotfix launcher csak a `compose.yaml` fájlt töltötte be. A base compose a frontend 3000-es portját csak `expose` direktívával tette elérhetővé a Docker belső hálózatán, ezért a Windows host `http://localhost:3000` címe nem volt elérhető.

A repository már tartalmazta a helyes `docker-compose.dev.yml` fejlesztői override-ot, benne a loopback-only port mappinggel:

```yaml
frontend:
  ports:
    - "127.0.0.1:${APP_PORT:-3000}:3000"
```

## Javítás

A `start-v0.30.0-hotfix.ps1` minden Compose műveletnél explicit a következő két fájlt használja:

```text
compose.yaml
docker-compose.dev.yml
```

Ez lokálisan publikálja:

- frontend: `127.0.0.1:3000`
- backend: `127.0.0.1:8000`
- PostgreSQL: `127.0.0.1:5432`

A bind minden esetben loopback-only, tehát nem `0.0.0.0` címre történik. A production compose nem módosult, a publikus VPS továbbra is Caddy/80/443 modellen működik.

## Gyors javítás már futó környezethez

Új build nélkül a frontend újralétrehozható:

```powershell
docker compose -p munkalap -f compose.yaml -f docker-compose.dev.yml up -d --no-deps --force-recreate frontend
```

Ellenőrzés:

```powershell
docker compose -p munkalap -f compose.yaml -f docker-compose.dev.yml port frontend 3000
```

Elvárt:

```text
127.0.0.1:3000
```

Ezután: `http://localhost:3000`.
