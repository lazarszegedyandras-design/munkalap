"""Safety interlock for destructive regression helpers; never production data."""
from __future__ import annotations
import os
import re
from urllib.parse import urlsplit


def validate_test_target(url: str) -> str:
    run_id = os.environ.get("RELEASE_TEST_RUN_ID", "")
    if not re.fullmatch(r"munkalap-test-[0-9a-f]{12}", run_id):
        raise RuntimeError("This regression helper requires the isolated release-test launcher")
    parsed = urlsplit(url.replace("postgresql+psycopg2://", "postgresql://", 1))
    if parsed.scheme != "postgresql" or parsed.hostname != "test-db" or parsed.port != 5432 or parsed.path != "/munkalap_test":
        raise RuntimeError("Refusing a non-test database target")
    if parsed.query or parsed.fragment:
        raise RuntimeError("Connection overrides are forbidden for destructive tests")
    return run_id


def require_isolated_database(url: str) -> None:
    run_id = validate_test_target(url)
    admin_url = os.environ.get("TEST_DATABASE_ADMIN_URL", "")
    validate_test_target(admin_url)
    import psycopg2
    with psycopg2.connect(admin_url.replace("postgresql+psycopg2://", "postgresql://", 1)) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), run_id FROM release_test_guard.marker")
            if cur.fetchall() != [("munkalap_test", run_id)]:
                raise RuntimeError("Test database run marker does not match")
