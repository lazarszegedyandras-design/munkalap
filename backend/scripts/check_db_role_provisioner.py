#!/usr/bin/env python3
"""PostgreSQL 16 regression check for idempotent object ownership transfer."""

from __future__ import annotations

from uuid import uuid4
from scripts.isolated_test_guard import require_isolated_database

import psycopg2
from psycopg2 import sql

from scripts.provision_db_roles import OWNER_ROLE, main as provision_roles, secret


def fixture_names() -> tuple[str, str]:
    suffix = uuid4().hex[:12]
    return f"security_role_fixture_{suffix}", f"security_standalone_seq_{suffix}"


def create_fixture(admin_url: str, table_name: str, standalone_name: str) -> tuple[list[tuple], str, str]:
    with psycopg2.connect(admin_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "CREATE TABLE {} ("
                    "serial_id SERIAL, "
                    "identity_id BIGINT GENERATED ALWAYS AS IDENTITY, "
                    "business_value TEXT NOT NULL)"
                ).format(sql.Identifier("public", table_name))
            )
            cursor.execute(
                sql.SQL("CREATE SEQUENCE {}").format(sql.Identifier("public", standalone_name))
            )
            cursor.execute(
                sql.SQL("INSERT INTO {} (business_value) VALUES (%s), (%s)").format(
                    sql.Identifier("public", table_name)
                ),
                ("existing-business-row-a", "existing-business-row-b"),
            )
            cursor.execute(
                "SELECT pg_get_serial_sequence(%s, 'serial_id'), pg_get_serial_sequence(%s, 'identity_id')",
                (f"public.{table_name}", f"public.{table_name}"),
            )
            serial_sequence, identity_sequence = cursor.fetchone()
            cursor.execute(
                sql.SQL("SELECT serial_id, identity_id, business_value FROM {} ORDER BY serial_id").format(
                    sql.Identifier("public", table_name)
                )
            )
            rows = cursor.fetchall()
        connection.commit()
    return rows, serial_sequence, identity_sequence


def relation_owner(cursor, qualified_name: str) -> str:
    cursor.execute("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = %s::regclass", (qualified_name,))
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Regression object is missing: {qualified_name}")
    return row[0]


def verify_fixture(
    admin_url: str,
    table_name: str,
    standalone_name: str,
    serial_sequence: str,
    identity_sequence: str,
    expected_rows: list[tuple],
) -> None:
    with psycopg2.connect(admin_url) as connection:
        with connection.cursor() as cursor:
            for qualified_name in (
                f"public.{table_name}",
                serial_sequence,
                identity_sequence,
                f"public.{standalone_name}",
            ):
                owner = relation_owner(cursor, qualified_name)
                if owner != OWNER_ROLE:
                    raise RuntimeError(f"Unexpected owner for {qualified_name}: {owner}")
            cursor.execute(
                sql.SQL("SELECT serial_id, identity_id, business_value FROM {} ORDER BY serial_id").format(
                    sql.Identifier("public", table_name)
                )
            )
            if cursor.fetchall() != expected_rows:
                raise RuntimeError("Provisioner changed existing fixture business data")


def cleanup(admin_url: str, table_name: str, standalone_name: str) -> None:
    with psycopg2.connect(admin_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier("public", table_name)))
            cursor.execute(sql.SQL("DROP SEQUENCE IF EXISTS {}").format(sql.Identifier("public", standalone_name)))
        connection.commit()


def main() -> None:
    admin_url = secret("DB_ADMIN_URL")
    require_isolated_database(admin_url)
    table_name, standalone_name = fixture_names()
    try:
        rows, serial_sequence, identity_sequence = create_fixture(admin_url, table_name, standalone_name)
        provision_roles()
        verify_fixture(admin_url, table_name, standalone_name, serial_sequence, identity_sequence, rows)
        provision_roles()
        verify_fixture(admin_url, table_name, standalone_name, serial_sequence, identity_sequence, rows)
    finally:
        cleanup(admin_url, table_name, standalone_name)
    print("Database role provisioner PostgreSQL 16 regression PASS")


if __name__ == "__main__":
    main()
