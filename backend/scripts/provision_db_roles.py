#!/usr/bin/env python3
"""Idempotently provision least-privilege PostgreSQL roles for production.

This script is intentionally a one-shot deployment task. It requires the
bootstrap database credential and must never run in the long-lived backend.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from psycopg2 import sql


OWNER_ROLE = "workapp_owner"
MIGRATE_ROLE = "workapp_migrate"
APP_ROLE = "workapp_app"


def secret(name: str) -> str:
    direct = os.getenv(name, "").strip()
    if direct:
        return direct
    path = os.getenv(f"{name}_FILE", "").strip()
    if not path:
        raise RuntimeError(f"Missing required setting: {name} or {name}_FILE")
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"Secret file for {name} is empty")
    return value


def ensure_role(cursor, name: str, *, login: bool, password: str | None = None) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} {}").format(
                sql.Identifier(name),
                sql.SQL("LOGIN" if login else "NOLOGIN"),
            )
        )
    cursor.execute(
        sql.SQL("ALTER ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION").format(
            sql.Identifier(name),
            sql.SQL("LOGIN" if login else "NOLOGIN"),
        )
    )
    if login:
        cursor.execute(sql.SQL("ALTER ROLE {} PASSWORD %s").format(sql.Identifier(name)), (password,))


def transfer_public_objects(cursor) -> None:
    # Transfer table-like relations first. PostgreSQL recursively changes the
    # owner of SERIAL/IDENTITY sequences owned by their table columns, so those
    # sequences must not receive a separate ALTER SEQUENCE command.
    cursor.execute(
        """
        SELECT c.relkind, c.relname
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind IN ('r', 'p', 'v', 'm')
           AND pg_get_userbyid(c.relowner) <> %s
         ORDER BY CASE c.relkind
                    WHEN 'r' THEN 1
                    WHEN 'p' THEN 1
                    WHEN 'm' THEN 2
                    WHEN 'v' THEN 3
                    ELSE 4
                  END,
                  c.relname
        """,
        (OWNER_ROLE,),
    )
    commands = {
        "r": "ALTER TABLE {} OWNER TO {}",
        "p": "ALTER TABLE {} OWNER TO {}",
        "v": "ALTER VIEW {} OWNER TO {}",
        "m": "ALTER MATERIALIZED VIEW {} OWNER TO {}",
    }
    for kind, name in cursor.fetchall():
        cursor.execute(
            sql.SQL(commands[kind]).format(
                sql.Identifier("public", name),
                sql.Identifier(OWNER_ROLE),
            )
        )

    # Only standalone sequences are transferred explicitly. pg_depend records
    # SERIAL ownership as DEPENDENCY_AUTO ('a') and IDENTITY ownership as
    # DEPENDENCY_INTERNAL ('i'); names are deliberately not used as evidence.
    cursor.execute(
        """
        SELECT c.relname
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind = 'S'
           AND pg_get_userbyid(c.relowner) <> %s
           AND NOT EXISTS (
               SELECT 1
                 FROM pg_depend d
                WHERE d.classid = 'pg_class'::regclass
                  AND d.objid = c.oid
                  AND d.refclassid = 'pg_class'::regclass
                  AND d.refobjsubid > 0
                  AND d.deptype IN ('a', 'i')
           )
         ORDER BY c.relname
        """,
        (OWNER_ROLE,),
    )
    for (name,) in cursor.fetchall():
        cursor.execute(
            sql.SQL("ALTER SEQUENCE {} OWNER TO {}").format(
                sql.Identifier("public", name),
                sql.Identifier(OWNER_ROLE),
            )
        )

    cursor.execute(
        """
        SELECT p.proname, pg_get_function_identity_arguments(p.oid)
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND pg_get_userbyid(p.proowner) <> %s
        """,
        (OWNER_ROLE,),
    )
    for name, identity_arguments in cursor.fetchall():
        cursor.execute(
            sql.SQL("ALTER FUNCTION {}({}) OWNER TO {}").format(
                sql.Identifier("public", name),
                sql.SQL(identity_arguments),
                sql.Identifier(OWNER_ROLE),
            )
        )

    # Keep the bootstrap account as database owner for disaster recovery, but
    # move the application schema and all current/future app objects to NOLOGIN.
    cursor.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(OWNER_ROLE)))
    cursor.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    cursor.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(sql.Identifier(APP_ROLE)))
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))

    database_name = os.getenv("POSTGRES_DB", "workapp")
    cursor.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database_name), sql.Identifier(APP_ROLE)
        )
    )
    cursor.execute(
        sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(
            sql.Identifier(APP_ROLE)
        )
    )
    cursor.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(APP_ROLE))
    )
    cursor.execute(
        sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(
            sql.Identifier(OWNER_ROLE), sql.Identifier(APP_ROLE)
        )
    )
    cursor.execute(
        sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(
            sql.Identifier(OWNER_ROLE), sql.Identifier(APP_ROLE)
        )
    )


def main() -> None:
    admin_url = secret("DB_ADMIN_URL")
    app_password = secret("DATABASE_APP_PASSWORD")
    migrate_password = secret("DATABASE_MIGRATE_PASSWORD")
    with psycopg2.connect(admin_url) as connection:
        connection.autocommit = False
        with connection.cursor() as cursor:
            ensure_role(cursor, OWNER_ROLE, login=False)
            ensure_role(cursor, MIGRATE_ROLE, login=True, password=migrate_password)
            ensure_role(cursor, APP_ROLE, login=True, password=app_password)
            cursor.execute(
                sql.SQL("GRANT {} TO {}").format(sql.Identifier(OWNER_ROLE), sql.Identifier(MIGRATE_ROLE))
            )
            # Converge an already-existing runtime role as well: a stale owner
            # membership would otherwise survive an idempotent upgrade.
            cursor.execute(
                sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(OWNER_ROLE), sql.Identifier(APP_ROLE))
            )
            transfer_public_objects(cursor)
        connection.commit()
    print("Database roles and runtime grants provisioned")


if __name__ == "__main__":
    main()
