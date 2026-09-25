#!/usr/bin/env python3
"""Runtime database privilege acceptance checks; leaves no business data."""

from __future__ import annotations

from uuid import uuid4

import psycopg2

from app.config import get_settings
from scripts.isolated_test_guard import require_isolated_database


EXPECTED = {
    "workapp_owner": (False, False, False, False),
    "workapp_migrate": (False, False, False, False),
    "workapp_app": (False, False, False, False),
}


def must_fail(cursor, statement: str) -> None:
    cursor.execute("SAVEPOINT security_privilege_check")
    try:
        cursor.execute(statement)
    except psycopg2.Error as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT security_privilege_check")
        cursor.execute("RELEASE SAVEPOINT security_privilege_check")
        if exc.pgcode != "42501":
            raise RuntimeError("DDL failed for a reason other than insufficient privilege") from exc
        return
    cursor.execute("ROLLBACK TO SAVEPOINT security_privilege_check")
    cursor.execute("RELEASE SAVEPOINT security_privilege_check")
    raise RuntimeError(f"Runtime role unexpectedly executed forbidden DDL: {statement.split()[0:3]}")


def main() -> None:
    url = get_settings().database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    require_isolated_database(url)
    with psycopg2.connect(url) as connection:
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            current_user = cursor.fetchone()[0]
            if current_user != "workapp_app":
                raise RuntimeError(f"Runtime DB user must be workapp_app, found {current_user!r}")

            cursor.execute(
                """
                SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication
                  FROM pg_roles
                 WHERE rolname IN ('workapp_owner', 'workapp_migrate', 'workapp_app')
                """
            )
            roles = {row[0]: tuple(row[1:]) for row in cursor.fetchall()}
            if roles != EXPECTED:
                raise RuntimeError(f"Unexpected database role attributes: {roles!r}")

            cursor.execute("SELECT pg_has_role('workapp_app', 'workapp_owner', 'MEMBER')")
            if cursor.fetchone()[0]:
                raise RuntimeError("workapp_app must not be a member of workapp_owner")
            cursor.execute("SELECT pg_has_role('workapp_migrate', 'workapp_owner', 'MEMBER')")
            if not cursor.fetchone()[0]:
                raise RuntimeError("workapp_migrate must be a member of workapp_owner")

            cursor.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            if cursor.fetchone()[0]:
                raise RuntimeError("workapp_app must not have CREATE on schema public")

            must_fail(cursor, "CREATE TABLE security_should_fail(id int)")
            must_fail(cursor, "ALTER TABLE users ADD COLUMN security_should_fail int")
            must_fail(cursor, "DROP TABLE users")
            must_fail(cursor, "CREATE ROLE security_should_fail")

            cursor.execute("SELECT count(*) FROM users")
            cursor.fetchone()
            marker = f"security-check-{uuid4().hex}"
            cursor.execute("INSERT INTO roles(name) VALUES (%s) RETURNING id", (marker,))
            role_id = cursor.fetchone()[0]
            cursor.execute("UPDATE roles SET name = %s WHERE id = %s", (marker + "-updated", role_id))
            if cursor.rowcount != 1:
                raise RuntimeError("Runtime UPDATE privilege check failed")
            cursor.execute("DELETE FROM roles WHERE id = %s", (role_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("Runtime DELETE privilege check failed")
        connection.rollback()
    print("Database least-privilege acceptance PASS")


if __name__ == "__main__":
    main()
