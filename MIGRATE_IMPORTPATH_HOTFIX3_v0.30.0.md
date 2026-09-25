# v0.30.0 migrate import-path hotfix 3

## Hiba

A migrate konténer már helyesen `uid=10001(app)` / `gid=10001(app)` identitással indult, de a következő ponton leállt:

```text
python scripts/wait_for_db.py
ModuleNotFoundError: No module named 'app'
```

A közvetlen scriptfuttatásnál a Python a `/app/scripts` könyvtárat tette a modulkeresési út elejére; az alkalmazáscsomag viszont `/app/app` alatt található.

## Javítás

- `backend/scripts/__init__.py` létrehozva.
- Backend és migrate entrypoint: `python -m scripts.wait_for_db`.
- Backend image: explicit `PYTHONPATH=/app` biztonsági/üzemeltetési tartalék a deployment helper scriptekhez.
- Startup fingerprint: `v0.30.0-hotfix3`.
- Release configuration tesztek frissítve az új modulindítás ellenőrzésére.

A javítás nem ad vissza root jogosultságot, `SETUID`/`SETGID` capabilityt, és nem változtat adatbázis-volume-ot.

## Elvárt migrate log

```text
migrate-entrypoint v0.30.0-hotfix3 uid=10001 gid=10001
Database is ready
```

Ezután az Alembic/DB jogosultsági réteg fut; ha ott további hiba van, az külön migrációs vagy PostgreSQL privilege probléma.
