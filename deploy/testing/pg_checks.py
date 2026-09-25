"""Real PostgreSQL lifecycle checks; intended ONLY for the generated test stack.

This file is copied into a test layer on the release image, not the web image.
Migrations/seeding are run in a separate container from that exact release image.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import time
import urllib.request

import psycopg2
from alembic.config import Config
from alembic.script import ScriptDirectory
from scripts.isolated_test_guard import require_isolated_database, validate_test_target


def connect_admin():
    url = os.environ["TEST_DATABASE_ADMIN_URL"]
    validate_test_target(url)
    return psycopg2.connect(url.replace("postgresql+psycopg2://", "postgresql://", 1))


def marker():
    run_id = validate_test_target(os.environ["TEST_DATABASE_ADMIN_URL"])
    with connect_admin() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS release_test_guard")
            cur.execute("CREATE TABLE IF NOT EXISTS release_test_guard.marker (run_id text PRIMARY KEY, state jsonb NOT NULL DEFAULT '{}'::jsonb)")
            cur.execute("SELECT run_id FROM release_test_guard.marker")
            rows = cur.fetchall()
            if rows and rows != [(run_id,)]:
                raise RuntimeError("Refusing to reuse a different test database")
            if not rows:
                cur.execute("INSERT INTO release_test_guard.marker(run_id) VALUES (%s)", (run_id,))
    print("Isolated PostgreSQL test marker ready")


def guard():
    require_isolated_database(os.environ["DATABASE_URL"])


def remember(key, value):
    with connect_admin() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE release_test_guard.marker SET state=jsonb_set(state, %s, %s::jsonb)", ([key], json.dumps(value, default=str)))


def recall(key):
    with connect_admin() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state -> %s FROM release_test_guard.marker", (key,))
            return cur.fetchone()[0]


def legacy_fixture():
    guard()
    with connect_admin() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM public.alembic_version")
            if cur.fetchall() != [("0026_location_active_status",)]:
                raise RuntimeError("Legacy fixture requires revision 0026")
            cur.execute("INSERT INTO public.roles(name) VALUES ('ReleaseLegacyFixture') RETURNING id")
            role_id = cur.fetchone()[0]
            cur.execute("INSERT INTO public.users(email,full_name,password_hash,role_id) VALUES (%s,%s,%s,%s) RETURNING id", ("legacy-fixture@example.com", "Release fixture - not real data", "not-a-login-hash", role_id))
            user_id = cur.fetchone()[0]
            cur.execute("INSERT INTO public.customers(name) VALUES ('Release customer fixture') RETURNING id")
            customer_id = cur.fetchone()[0]
    remember("legacy", {"role": role_id, "user": user_id, "customer": customer_id})
    print("Synthetic legacy records committed at revision 0026")


def assert_head():
    guard()
    heads = ScriptDirectory.from_config(Config("/app/alembic.ini")).get_heads()
    if len(heads) != 1:
        raise RuntimeError("Expected exactly one Alembic head")
    with connect_admin() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM public.alembic_version")
            if cur.fetchall() != [(heads[0],)]:
                raise RuntimeError("Committed database revision is not at the source head")
            cur.execute("SHOW server_version_num")
            if not 160000 <= int(cur.fetchone()[0]) < 170000:
                raise RuntimeError("This baseline requires PostgreSQL 16")
            cur.execute("SELECT mfa_enabled FROM public.users LIMIT 1")
            for table in ("auth_sessions", "mobile_sessions", "work_order_signatures"):
                cur.execute("SELECT to_regclass(%s)", ("public." + table,))
                if cur.fetchone()[0] is None:
                    raise RuntimeError("Missing migrated table: " + table)
    print("Committed Alembic head and security schema verified: " + heads[0])


def verify_legacy():
    guard()
    expected = recall("legacy")
    with connect_admin() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT email, full_name, password_hash, role_id FROM public.users WHERE id=%s", (expected["user"],))
            if cur.fetchone() != ("legacy-fixture@example.com", "Release fixture - not real data", "not-a-login-hash", expected["role"]):
                raise RuntimeError("Legacy user data changed")
            cur.execute("SELECT name FROM public.customers WHERE id=%s", (expected["customer"],))
            if cur.fetchone() != ("Release customer fixture",):
                raise RuntimeError("Legacy customer data changed")
    print("Legacy synthetic business records preserved")


def state():
    with connect_admin() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,email,full_name,password_hash,role_id FROM public.users ORDER BY id")
            users = cur.fetchall()
            cur.execute("SELECT id,name FROM public.roles ORDER BY id")
            roles = cur.fetchall()
            cur.execute("SELECT id,name FROM public.customers ORDER BY id")
            customers = cur.fetchall()
    return json.loads(json.dumps({"users": users, "roles": roles, "customers": customers}, default=str))


def snapshot():
    guard(); remember("idempotency", state())
    print("Idempotency fixture snapshot recorded (no values printed)")


def compare_snapshot():
    guard()
    if state() != recall("idempotency"):
        raise RuntimeError("Second provision/migration/seed changed fixture state")
    print("Second provision/migration/seed preserved fixture state")


def identities():
    guard()
    if os.getuid() != 10001 or os.getgid() != 10001:
        raise RuntimeError("Test process is not the release non-root identity")
    expected = "workapp_app"
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT session_user,current_user")
            if cur.fetchone() != (expected, expected):
                raise RuntimeError("Unexpected runtime DB identity")
    print("Runtime UID/GID and database identity verified")


def privileges():
    guard()
    from scripts.check_db_privileges import main
    main()


def role_regression():
    guard()
    from scripts.check_db_role_provisioner import main
    main()


def smoke():
    guard()
    # Internal HTTP only: no host publication, no TLS/public-production claim.
    deadline = time.monotonic() + 90
    while True:
        try:
            with urllib.request.urlopen("http://backend:8000/api/health/ready", timeout=3) as r:
                if json.load(r).get("status") != "ready":
                    raise RuntimeError("Backend not ready")
            with urllib.request.urlopen("http://frontend:3000/", timeout=3) as r:
                if r.status != 200 or b"<html" not in r.read().lower():
                    raise RuntimeError("Frontend HTML unavailable")
            with urllib.request.urlopen("http://frontend:3000/api/version", timeout=3) as r:
                if json.load(r).get("version") != Path("/app/VERSION").read_text().strip():
                    raise RuntimeError("Frontend proxy points at a different release")
            print("Internal backend readiness, frontend HTML and version proxy PASS")
            return
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)


COMMANDS = {fn.__name__.replace("_", "-"): fn for fn in
            (marker, legacy_fixture, assert_head, verify_legacy, snapshot, compare_snapshot, identities, privileges, role_regression, smoke)}
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=COMMANDS)
    COMMANDS[parser.parse_args().action]()
