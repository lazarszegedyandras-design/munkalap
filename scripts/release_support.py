"""Standard-library helpers for isolated release tests (no production config)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from urllib.parse import urlsplit

PROJECT_RE = re.compile(r"^munkalap-test-[0-9a-f]{12}$")
BACKEND_SERVICES = ("backend", "migrate", "db-role-provisioner", "runtime-permissions", "push-worker")
MANIFEST_NAME = "release-source-manifest.json"


def clean_environment(source=None):
    """Keep Docker client connectivity, not application/Compose/Python settings."""
    source = os.environ if source is None else source
    allowed = {
        "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMFILES",
        "TEMP", "TMP", "TMPDIR", "APPDATA", "LOCALAPPDATA", "LANG", "LC_ALL",
        "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_CERT_PATH",
        "DOCKER_TLS_VERIFY", "DOCKER_API_VERSION", "SSH_AUTH_SOCK",
    }
    env = {key: value for key, value in source.items() if key.upper() in allowed}
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", COMPOSE_ANSI="never")
    return env


def safe_source_path(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe manifest path")
    denied = {"secrets", "node_modules", "__pycache__", ".pytest_cache", ".git", "runtime", "backups", "munkalap-backups", "pre-restore-backups", "imports", "keystore", "security-results"}
    if any(p.lower() in denied for p in path.parts):
        raise ValueError("Private/runtime path in source manifest: " + name)
    base = path.name.lower()
    if base.startswith(".env") and not base.endswith(".example"):
        raise ValueError("Environment file in source manifest: " + name)
    if base in {".release.env", "android-release.env", "google-services.json"}:
        raise ValueError("Local configuration in source manifest")
    if path.as_posix().lower() in {
        "backend/app/data/company_profiles.json",
        "backend/app/data/customer_assets_20260616.json",
        "backend/app/data/hr_leave_2026_rlb.json",
        "backend/migrations/versions/0024_contract_details_archives_hr_calendar.py",
    }:
        raise ValueError("Private application data in source manifest: " + name)
    if path.suffix.lower() in {".pem", ".key", ".p12", ".jks", ".keystore", ".dump", ".sqlite", ".db"}:
        raise ValueError("Private/database file in source manifest")
    return path


def load_manifest(root):
    root = Path(root).resolve()
    raw = (root / MANIFEST_NAME).read_bytes()
    data = json.loads(raw)
    if data.get("format") != 1 or not data.get("files"):
        raise ValueError("Missing/unsupported release source manifest")
    for name, expected in data["files"].items():
        parts = safe_source_path(name).parts
        path = root
        for part in parts:
            path = path / part
            if path.is_symlink():
                raise ValueError("Symlink is not allowed in source snapshot: " + name)
        if not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Missing file or invalid manifest digest: " + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Source differs from reviewed release: " + name)
    version = (root / "VERSION").read_text().strip()
    if data.get("version") != version:
        raise ValueError("Manifest/VERSION mismatch")
    return data, hashlib.sha256(raw).hexdigest()


def copy_snapshot(root, dest, data):
    """Only hash-verified release files enter the Docker build context."""
    root, dest = Path(root), Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    for name, expected in data["files"].items():
        relative = safe_source_path(name)
        source = root / relative
        # Recheck during copy: do not use a file changed after manifest validation.
        if source.is_symlink():
            raise ValueError("Source changed to a symlink: " + name)
        payload = source.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("Source changed during snapshot: " + name)
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    shutil.copyfile(root / MANIFEST_NAME, dest / MANIFEST_NAME)


def image_tags(project, version):
    if not PROJECT_RE.fullmatch(project):
        raise ValueError("Unsafe test project name")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?", version):
        raise ValueError("Invalid release version")
    return {kind: f"{project}-{kind}:{version}" for kind in
            ("backend", "db", "frontend", "backup-agent", "backup-runner", "python-tests", "node-tests")}


def build_model(snapshot, tags, source_digest):
    context = str(Path(snapshot).resolve())
    labels = {"hu.lunait.release.source-sha256": source_digest,
              "hu.lunait.release.version": tags["backend"].rsplit(":", 1)[1]}
    recipes = {
        "backend": ("backend/Dockerfile", context),
        "db": ("database/Dockerfile", context),
        "frontend": ("Dockerfile", context + "/frontend"),
        "backup-agent": ("backup_agent/Dockerfile", context),
        "backup-runner": ("backup_runner/Dockerfile", context),
        "python-tests": ("deploy/testing/Dockerfile", context),
        "node-tests": ("deploy/testing/Node.Dockerfile", context),
    }
    model = {"services": {}}
    for name, (recipe, ctx) in recipes.items():
        build = {"context": ctx, "dockerfile": recipe, "labels": labels}
        if name == "python-tests":
            build["args"] = {"RELEASE_BACKEND_IMAGE": tags["backend"]}
        if name == "frontend":
            build["args"] = {"VITE_API_URL": "/api"}
        model["services"][name] = {"image": tags[name], "pull_policy": "never", "build": build}
    return model


def runtime_model(project, images, credentials):
    """Standalone Compose model; NEVER merge an application/production file."""
    if not PROJECT_RE.fullmatch(project):
        raise ValueError("Unsafe test project name")
    c = credentials
    db = "munkalap_test"
    url = lambda user, password: f"postgresql+psycopg2://{user}:{password}@test-db:5432/{db}"
    env = {
        "ENVIRONMENT": "development", "DATABASE_URL": "sqlite://",
        "RUNTIME_DIR": "/app/runtime", "ARCHIVE_DIR": "/app/runtime/archives",
        "SECRET_KEY": c["key"], "MFA_ENCRYPTION_KEY": c["mfa"],
        "BACKUP_AGENT_TOKEN": c["key"], "BACKUP_RUNNER_TOKEN": c["key"],
        "BACKUP_REPOSITORY_DIR": "/tmp/test-repo", "BACKUP_CONTROL_DIR": "/tmp/test-control",
        "BACKUP_PROJECT_DIR": "/suite", "PUSH_NOTIFICATIONS_ENABLED": "false",
        "MALWARE_SCAN_ENABLED": "false", "ADMIN_MFA_REQUIRED": "false",
        "SESSION_COOKIE_SECURE": "false", "BACKEND_WORKERS": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "RELEASE_TEST_RUN_ID": project, "PYTHONPATH": "/app:/suite:/suite/backup_agent:/suite/backup_runner",
    }
    admin = url("test_bootstrap", c["admin"])
    app = url("workapp_app", c["app"])
    migrate = url("workapp_migrate", c["migrate"])
    pg_env = {**env, "DATABASE_URL": app, "TEST_DATABASE_ADMIN_URL": admin,
              "DB_ADMIN_URL": admin.replace("postgresql+psycopg2://", "postgresql://"),
              "POSTGRES_DB": db, "DATABASE_APP_PASSWORD": c["app"],
              "DATABASE_MIGRATE_PASSWORD": c["migrate"]}

    def python_service(image, entrypoint, environment=None, network=True):
        value = {"image": image, "pull_policy": "never", "user": "10001:10001", "restart": "no",
                 "entrypoint": entrypoint, "command": [], "working_dir": "/app",
                 "environment": environment if environment is not None else dict(env),
                 "read_only": True, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
                 "tmpfs": ["/tmp:size=256m,mode=1777", "/app/runtime:size=128m,uid=10001,gid=10001,mode=0700"],
                 "labels": {"hu.lunait.release.test-run": project}}
        value.update({"networks": ["test_net"]} if network else {"network_mode": "none"})
        return value

    services = {
        "test-db": {
            "image": images["db"], "pull_policy": "never", "restart": "no",
            "environment": {"POSTGRES_DB": db, "POSTGRES_USER": "test_bootstrap", "POSTGRES_PASSWORD": c["admin"]},
            "command": ["postgres", "-c", "archive_mode=off", "-c", "max_connections=50"],
            "read_only": True,
            "tmpfs": ["/var/lib/postgresql/data:size=768m,mode=0700", "/var/run/postgresql:size=16m,mode=1777", "/tmp:size=32m,mode=1777"],
            "healthcheck": {"test": ["CMD", "pg_isready", "-h", "127.0.0.1", "-U", "test_bootstrap", "-d", db], "interval": "2s", "timeout": "3s", "retries": 40},
            "security_opt": ["no-new-privileges:true"], "networks": ["test_net"],
            "labels": {"hu.lunait.release.test-run": project}},
        "python-tests": python_service(images["python-tests"], ["python", "-m", "pytest"], network=False),
        "pg-checks": python_service(images["python-tests"], ["python", "/suite/deploy/testing/pg_checks.py"], pg_env),
        "db-role-provisioner": python_service(images["backend"], ["python", "/app/scripts/provision_db_roles.py"], pg_env),
        "migrate": python_service(images["backend"], ["/bin/sh", "/app/migrate-entrypoint.sh"], {
            **env, "DATABASE_URL": migrate, "MIGRATION_SET_ROLE": "workapp_owner", "ENVIRONMENT": "production",
            "BOOTSTRAP_ADMIN_EMAIL": "release-admin@example.com", "BOOTSTRAP_ADMIN_PASSWORD": c["bootstrap"]}),
        "legacy-migrate": python_service(images["backend"], ["alembic"], {**env, "DATABASE_URL": admin}),
        "backend": python_service(images["backend"], ["/bin/sh", "/app/entrypoint.sh"], {**env, "DATABASE_URL": app}),
        "node-tests": {
            "image": images["node-tests"], "pull_policy": "never", "user": "node", "restart": "no",
            "entrypoint": ["node", "--test"], "command": [], "working_dir": "/suite",
            "network_mode": "none", "read_only": True, "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"], "tmpfs": ["/tmp:size=32m,mode=1777"],
            "labels": {"hu.lunait.release.test-run": project}},
        "frontend": {
            "image": images["frontend"], "pull_policy": "never", "restart": "no", "read_only": True,
            "tmpfs": ["/tmp:size=32m,mode=1777", "/var/cache/nginx:size=64m,mode=1777", "/var/run:size=8m,mode=1777"],
            "security_opt": ["no-new-privileges:true"], "networks": ["test_net"],
            "labels": {"hu.lunait.release.test-run": project}},
    }
    return {"services": services, "networks": {"test_net": {"internal": True}}}


def validate_runtime_model(model, project, expected_images):
    """Fail closed if isolation changes before any container is started."""
    if not PROJECT_RE.fullmatch(project):
        raise ValueError("Unsafe test project")
    for key in ("volumes", "secrets", "configs", "include"):
        if model.get(key):
            raise ValueError("Forbidden test model section: " + key)
    net = model.get("networks", {}).get("test_net", {})
    if net.get("internal") is not True or net.get("external"):
        raise ValueError("Test network must be internal and project-scoped")
    if net.get("name") not in (None, project + "_test_net"):
        raise ValueError("Unscoped test network")
    expected_services = {"test-db", "python-tests", "pg-checks", "db-role-provisioner", "migrate", "legacy-migrate", "backend", "node-tests", "frontend"}
    if set(model.get("services", {})) != expected_services:
        raise ValueError("Unexpected services in test project")
    for name, service in model["services"].items():
        if service.get("image") not in set(expected_images.values()):
            raise ValueError("Unexpected image: " + name)
        for key in ("volumes", "volumes_from", "secrets", "configs", "env_file", "ports", "devices", "privileged", "cap_add", "pid", "ipc", "build", "extends", "external_links", "extra_hosts"):
            if service.get(key):
                raise ValueError(f"Forbidden {key} on test service {name}")
        if name in {"backend", "migrate", "legacy-migrate", "db-role-provisioner", "python-tests", "pg-checks"}:
            if service.get("user") != "10001:10001" or "ALL" not in service.get("cap_drop", []):
                raise ValueError("Non-root/capability boundary changed")
        # Compose supplies default container names on config rendering; only this project is allowed.
        if service.get("container_name") not in (None, f"{project}-{name}-1"):
            raise ValueError("Unscoped container name")
        if service.get("network_mode") not in (None, "none"):
            raise ValueError("Host/container networking not allowed")
        if set(service.get("networks", {})) - {"test_net"}:
            raise ValueError("Unexpected network")
        for key, value in service.get("environment", {}).items():
            if key.endswith("_FILE") and value:
                raise ValueError("File secrets/configuration not allowed")
            if key.endswith("DATABASE_URL") or key in {"DB_ADMIN_URL", "TEST_DATABASE_ADMIN_URL"}:
                if value == "sqlite://":
                    continue
                parsed = urlsplit(value.replace("postgresql+psycopg2://", "postgresql://"))
                if parsed.hostname != "test-db" or parsed.port != 5432 or parsed.path != "/munkalap_test":
                    raise ValueError("Non-test database connection")
        if service.get("labels", {}).get("hu.lunait.release.test-run") != project:
            raise ValueError("Missing run ownership label")
    image = model["services"]["backend"]["image"]
    for name in ("migrate", "db-role-provisioner", "legacy-migrate"):
        if model["services"][name]["image"] != image:
            raise ValueError("Mixed backend image IDs")


def redact(text, values):
    for value in sorted(set(values), key=len, reverse=True):
        if value:
            text = text.replace(value, "<test-secret-redacted>")
    return text
