# v0.30.0 migrate transaction hotfix 4

## Hiba

A valós Docker/PostgreSQL futásban az Alembic látszólag sikeresen végrehajtotta a
`0027` → `0032` migrációkat, de az utána induló seed ezt kapta:

```text
psycopg2.errors.UndefinedColumn: column users.mfa_enabled does not exist
```

Ez azt jelentette, hogy a migrációs DDL a log ellenére nem maradt commitolva.

## Gyökérok

A `backend/migrations/env.py` korábbi sorrendje:

```python
connection.execute(text("SET ROLE workapp_owner"))
context.configure(...)
with context.begin_transaction():
    context.run_migrations()
```

SQLAlchemy 2.x alatt a `connection.execute()` automatikusan tranzakciót nyit
(autobegin). Emiatt az Alembic már egy kívülről megnyitott tranzakcióban futott,
amelyet nem ő birtokolt/commitolt. A connection lezárásakor a tranzakció rollbackelt.
Az Alembic log mégis kiírta a revisionök futását, ezért a hiba megtévesztő volt.

## Javítás

A `SET ROLE workapp_owner` most az Alembic által megnyitott tranzakción **belül** fut:

```python
context.configure(connection=connection, target_metadata=target_metadata)
with context.begin_transaction():
    connection.execute(text("SET ROLE workapp_owner"))
    context.run_migrations()
```

Így ugyanaz a tranzakció tartalmazza a role-váltást, a DDL-t és az
`alembic_version` frissítését, és a context manager siker esetén commitolja őket.

## Security állapot

A javítás nem lazít a hardeningen:

- `workapp_migrate` marad non-superuser;
- `SET ROLE workapp_owner` megmarad;
- backend runtime továbbra is `workapp_app`;
- `cap_drop: ALL` és `no-new-privileges` változatlan;
- Docker volume vagy üzleti adat nem kerül törlésre.

## Regressziós teszt

Új `backend/tests/test_alembic_transaction_scope.py` ellenőrzi, hogy a
`SET ROLE` nem kerülhet vissza az Alembic transaction elé.
