# PostgreSQL 16 provisioner sequence ownership fix – v0.30.0

## Fixed behavior

- `TABLE`, `PARTITIONED TABLE`, `MATERIALIZED VIEW` and regular view ownership is transferred before sequence processing.
- SERIAL column-owned sequences are recognized through `pg_depend.deptype = 'a'`.
- IDENTITY column-owned sequences are recognized through `pg_depend.deptype = 'i'`.
- Column-owned sequences never receive a separate `ALTER SEQUENCE ... OWNER` command.
- Only standalone public sequences are explicitly transferred.
- Every dynamic schema/object/role identifier continues to use `psycopg2.sql.Identifier`.

## Regression coverage

`backend/tests/test_provision_db_roles.py` checks catalog filtering, both dependency types, operation order and quoted standalone sequence ownership SQL.

`backend/scripts/check_db_role_provisioner.py` performs the live PostgreSQL regression:

1. creates uniquely named SERIAL, IDENTITY and standalone-sequence fixtures;
2. inserts existing fixture business rows;
3. runs the complete provisioner;
4. verifies the table and all three sequences are owned by `workapp_owner`;
5. verifies the rows are byte-for-byte unchanged;
6. runs the complete provisioner a second time and repeats the checks;
7. removes all fixtures in a `finally` cleanup.

## Windows / Docker Desktop verification

From the application directory:

```powershell
docker compose build --no-cache db-role-provisioner
docker compose run --rm db-role-provisioner python scripts/check_db_role_provisioner.py
```

Expected final line:

```text
Database role provisioner PostgreSQL 16 regression PASS
```

Do not use `docker compose down -v`; the existing PostgreSQL volume must be retained.
