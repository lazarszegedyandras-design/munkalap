from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import hmac
from calendar import monthrange
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from runner_client import get as runner_get, post as runner_post

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

APP_VERSION = os.environ.get("APP_VERSION", "0.31.0")

def _secret_env(name: str, file_name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    path = os.environ.get(file_name, "").strip()
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""

AGENT_TOKEN = _secret_env("BACKUP_AGENT_TOKEN", "BACKUP_AGENT_TOKEN_FILE")
CONTROL_DIR = Path(os.environ.get("BACKUP_CONTROL_DIR", "/control"))
REPOSITORY_ROOT = Path(os.environ.get("BACKUP_REPOSITORY_DIR", "/repo"))
RUNTIME_ROOT = Path(os.environ.get("BACKUP_RUNTIME_DIR", "/runtime"))
RUNTIME_OWNER_UID = int(os.environ.get("BACKUP_RUNTIME_UID", "10001"))
RUNTIME_OWNER_GID = int(os.environ.get("BACKUP_RUNTIME_GID", "10001"))
PROJECT_ROOT = Path(os.environ.get("BACKUP_PROJECT_DIR", "/project"))
TIMEZONE = os.environ.get("BACKUP_TIMEZONE", "Europe/Budapest")
STANZA = os.environ.get("PGBACKREST_STANZA", "workapp")
BACKEND_INTERNAL_URL = os.environ.get("BACKEND_INTERNAL_URL", "http://backend:8000").rstrip("/")
DB_PATH = CONTROL_DIR / "backup-control.sqlite"
APP_BACKUPS = REPOSITORY_ROOT / "app_backups"
OFFSITE_ENABLED = os.environ.get("OFFSITE_BACKUP_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
RESTIC_REPOSITORY = os.environ.get("RESTIC_REPOSITORY", "").strip()
RESTIC_PASSWORD_VALUE = _secret_env("RESTIC_PASSWORD", "RESTIC_PASSWORD_FILE")
AWS_ACCESS_KEY_ID_VALUE = _secret_env("AWS_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID_FILE")
AWS_SECRET_ACCESS_KEY_VALUE = _secret_env("AWS_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY_FILE")
AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "eu-central-1").strip() or "eu-central-1"
RESTIC_KEEP_DAILY = max(1, int(os.environ.get("RESTIC_KEEP_DAILY", "14")))
RESTIC_KEEP_WEEKLY = max(1, int(os.environ.get("RESTIC_KEEP_WEEKLY", "8")))
RESTIC_KEEP_MONTHLY = max(1, int(os.environ.get("RESTIC_KEEP_MONTHLY", "12")))
LOCK = threading.RLock()
RUN_LOCK = threading.Lock()
PGBACKREST_READY = threading.Event()
PGBACKREST_STATE_LOCK = threading.Lock()
PGBACKREST_LAST_ERROR: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    threading.Thread(target=bootstrap_pgbackrest, daemon=True, name="pgbackrest-bootstrap").start()
    threading.Thread(target=scheduler_loop, daemon=True, name="backup-scheduler").start()
    yield


app = FastAPI(
    title="Munkalap backup agent",
    version=APP_VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


class ScheduleUpdate(BaseModel):
    enabled: bool = False
    daily_time: str = Field(default="23:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = TIMEZONE

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("Érvénytelen időzóna") from exc
        return value


class ManualBackupRequest(BaseModel):
    requested_by_user_id: int | None = None
    requested_by_name: str | None = Field(default=None, max_length=255)
    requested_by_email: str | None = Field(default=None, max_length=255)


class RestoreRequest(ManualBackupRequest):
    confirmation: str = Field(min_length=1, max_length=100)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        if value != "VISSZAALLIT":
            raise ValueError("A visszaállításhoz pontosan ezt kell megadni: VISSZAALLIT")
        return value


class RecoveryClearRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=100)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        if value != "HELYREALLITAS_KESZ":
            raise ValueError("A zárolás feloldásához pontosan ezt kell megadni: HELYREALLITAS_KESZ")
        return value


def require_token(x_backup_agent_token: str | None = Header(default=None)) -> None:
    if not AGENT_TOKEN or not x_backup_agent_token or not hmac.compare_digest(x_backup_agent_token, AGENT_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Backup-agent hitelesítés sikertelen")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def connect() -> sqlite3.Connection:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    REPOSITORY_ROOT.mkdir(parents=True, exist_ok=True)
    APP_BACKUPS.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                requested_kind TEXT NOT NULL,
                effective_kind TEXT,
                trigger TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                local_date TEXT,
                base_master_id TEXT,
                pgbackrest_label TEXT,
                deployment_fingerprint TEXT,
                backup_dir TEXT,
                size_bytes INTEGER,
                app_size_bytes INTEGER,
                db_repo_delta_bytes INTEGER,
                db_repo_set_bytes INTEGER,
                requested_by_user_id INTEGER,
                requested_by_name TEXT,
                requested_by_email TEXT,
                message TEXT,
                error TEXT,
                offsite_status TEXT,
                offsite_snapshot_id TEXT,
                offsite_finished_at TEXT,
                offsite_error TEXT
            );
            CREATE TABLE IF NOT EXISTS restore_jobs (
                id TEXT PRIMARY KEY,
                backup_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                pre_restore_backup_id TEXT,
                post_restore_backup_id TEXT,
                rollback_restore_backup_id TEXT,
                requested_by_user_id INTEGER,
                requested_by_name TEXT,
                requested_by_email TEXT,
                message TEXT,
                error TEXT,
                rollback_status TEXT,
                rollback_error TEXT
            );
            """
        )
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        for column, sql_type in {
            "app_size_bytes": "INTEGER",
            "db_repo_delta_bytes": "INTEGER",
            "db_repo_set_bytes": "INTEGER",
            "offsite_status": "TEXT",
            "offsite_snapshot_id": "TEXT",
            "offsite_finished_at": "TEXT",
            "offsite_error": "TEXT",
        }.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {sql_type}")
        restore_columns = {row["name"] for row in conn.execute("PRAGMA table_info(restore_jobs)").fetchall()}
        if "rollback_restore_backup_id" not in restore_columns:
            conn.execute("ALTER TABLE restore_jobs ADD COLUMN rollback_restore_backup_id TEXT")
        defaults = {
            "schedule.enabled": "false",
            "schedule.daily_time": "23:30",
            "schedule.timezone": TIMEZONE,
            "schedule.last_run_date": "",
            "schedule.last_attempt_date": "",
            "schedule.last_covered_date": "",
            "restore.recovery_required": "false",
        }
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        conn.execute(
            """
            UPDATE jobs
            SET status='failed', finished_at=?, error=?
            WHERE status IN ('queued', 'running')
            """,
            (now_iso(), "A backup-agent újraindult a feladat befejezése előtt"),
        )
        interrupted = conn.execute(
            "SELECT id FROM restore_jobs WHERE status IN ('queued', 'running') LIMIT 1"
        ).fetchone()
        if interrupted:
            conn.execute(
                """
                UPDATE restore_jobs
                SET status='interrupted', finished_at=?, error=?
                WHERE status IN ('queued', 'running')
                """,
                (now_iso(), "A backup-agent újraindult a visszaállítás befejezése előtt; host-szintű ellenőrzés szükséges"),
            )
            conn.execute(
                "INSERT INTO settings(key, value) VALUES ('restore.recovery_required', 'true') "
                "ON CONFLICT(key) DO UPDATE SET value='true'"
            )
        conn.commit()


def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default


def set_settings(values: dict[str, str]) -> None:
    with connect() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
        conn.commit()


def schedule_payload() -> dict[str, Any]:
    return {
        "enabled": get_setting("schedule.enabled", "false") == "true",
        "daily_time": get_setting("schedule.daily_time", "23:30"),
        "timezone": get_setting("schedule.timezone", TIMEZONE),
        "last_run_date": get_setting("schedule.last_run_date", "") or None,
        "last_attempt_date": get_setting("schedule.last_attempt_date", "") or None,
        "last_covered_date": get_setting("schedule.last_covered_date", "") or None,
    }

def offsite_configuration_errors() -> list[str]:
    if not OFFSITE_ENABLED:
        return []
    errors: list[str] = []
    if not RESTIC_REPOSITORY:
        errors.append("RESTIC_REPOSITORY is required")
    if not RESTIC_PASSWORD_VALUE:
        errors.append("RESTIC_PASSWORD or RESTIC_PASSWORD_FILE is required")
    if RESTIC_REPOSITORY.startswith("s3:"):
        if not AWS_ACCESS_KEY_ID_VALUE:
            errors.append("AWS_ACCESS_KEY_ID or AWS_ACCESS_KEY_ID_FILE is required for S3")
        if not AWS_SECRET_ACCESS_KEY_VALUE:
            errors.append("AWS_SECRET_ACCESS_KEY or AWS_SECRET_ACCESS_KEY_FILE is required for S3")
    return errors


def restic_environment() -> dict[str, str]:
    env = dict(os.environ)
    env["RESTIC_REPOSITORY"] = RESTIC_REPOSITORY
    env["RESTIC_PASSWORD"] = RESTIC_PASSWORD_VALUE
    env.pop("RESTIC_PASSWORD_FILE", None)
    if AWS_ACCESS_KEY_ID_VALUE:
        env["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY_ID_VALUE
    if AWS_SECRET_ACCESS_KEY_VALUE:
        env["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_ACCESS_KEY_VALUE
    if AWS_DEFAULT_REGION:
        env["AWS_DEFAULT_REGION"] = AWS_DEFAULT_REGION
    return env


def snapshot_control_database() -> Path:
    target_dir = REPOSITORY_ROOT / "control_state"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "backup-control.sqlite"
    temp = target.with_suffix(".sqlite.tmp")
    temp.unlink(missing_ok=True)
    with sqlite3.connect(DB_PATH) as source, sqlite3.connect(temp) as destination:
        source.backup(destination)
    temp.replace(target)
    target.chmod(0o600)
    return target


def run_offsite_backup(backup_id: str) -> dict[str, Any]:
    errors = offsite_configuration_errors()
    if errors:
        raise RuntimeError("Offsite backup configuration error: " + "; ".join(errors))
    snapshot_control_database()
    env = restic_environment()
    result = run(
        [
            "restic", "backup", "/repo",
            "--tag", "munkalap",
            "--tag", f"backup-id:{backup_id}",
            "--json",
        ],
        env=env,
        timeout=21600,
    )
    snapshot_id = None
    for line in reversed(result.stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("message_type") == "summary":
            snapshot_id = payload.get("snapshot_id")
            break
    run(
        [
            "restic", "forget",
            "--keep-daily", str(RESTIC_KEEP_DAILY),
            "--keep-weekly", str(RESTIC_KEEP_WEEKLY),
            "--keep-monthly", str(RESTIC_KEEP_MONTHLY),
            "--tag", "munkalap",
            "--prune",
        ],
        env=env,
        timeout=21600,
    )
    finished_at = now_iso()
    set_settings({
        "offsite.last_success_at": finished_at,
        "offsite.last_snapshot_id": str(snapshot_id or ""),
        "offsite.last_error": "",
    })
    return {"snapshot_id": snapshot_id, "finished_at": finished_at}


def record_offsite_result(backup_id: str, *, status_value: str, snapshot_id: str | None = None, error: str | None = None) -> None:
    finished_at = now_iso()
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET offsite_status=?, offsite_snapshot_id=?, offsite_finished_at=?, offsite_error=? WHERE id=?",
            (status_value, snapshot_id, finished_at, error[:4000] if error else None, backup_id),
        )
        conn.commit()
    if error:
        set_settings({"offsite.last_error": error[:4000]})


def offsite_status_payload() -> dict[str, Any]:
    return {
        "enabled": OFFSITE_ENABLED,
        "configured": OFFSITE_ENABLED and not offsite_configuration_errors(),
        "repository_type": "s3" if RESTIC_REPOSITORY.startswith("s3:") else ("other" if RESTIC_REPOSITORY else None),
        "last_success_at": get_setting("offsite.last_success_at", "") or None,
        "last_snapshot_id": get_setting("offsite.last_snapshot_id", "") or None,
        "last_error": get_setting("offsite.last_error", "") or None,
        "retention": {
            "daily": RESTIC_KEEP_DAILY,
            "weekly": RESTIC_KEEP_WEEKLY,
            "monthly": RESTIC_KEEP_MONTHLY,
        },
    }


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        capture_output=capture,
        check=False,
        env=env,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Parancs sikertelen ({result.returncode}): {' '.join(command)}\n{detail}")
    return result


def service_image(service: str) -> tuple[str, str]:
    result = runner_get(f"/services/{service}")
    return str(result.get("image_reference") or ""), str(result.get("image_id") or "")


def service_is_running(service: str) -> bool:
    return bool(runner_get(f"/services/{service}").get("running"))


def quiesce_application() -> dict[str, bool]:
    states = {service: service_is_running(service) for service in ("backend", "frontend")}
    try:
        for service in ("frontend", "backend"):
            if states.get(service):
                runner_post(f"/services/{service}/stop", {"timeout_seconds": 30})
    except Exception:
        resume_application(states)
        raise
    return states


def resume_application(states: dict[str, bool]) -> None:
    for service in ("backend", "frontend"):
        if states.get(service) and not service_is_running(service):
            runner_post(f"/services/{service}/start")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deployment_fingerprint() -> tuple[str, dict[str, Any]]:
    digest = hashlib.sha256()
    details: dict[str, Any] = {"files": {}, "images": {}}
    for name in ("VERSION", "docker-compose.yml", ".env"):
        path = PROJECT_ROOT / name
        if path.exists() and path.is_file():
            file_hash = sha256_file(path)
            details["files"][name] = file_hash
            digest.update(name.encode())
            digest.update(file_hash.encode())
    for service in ("db", "backend", "frontend", "backup-agent"):
        try:
            reference, image_id = service_image(service)
        except Exception:
            continue
        details["images"][service] = {"reference": reference, "image_id": image_id}
        digest.update(service.encode())
        digest.update(image_id.encode())
    return digest.hexdigest(), details


def runtime_manifest() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not RUNTIME_ROOT.exists():
        return result
    for path in sorted(RUNTIME_ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(RUNTIME_ROOT)
        if relative_path.parts and (relative_path.parts[0].startswith(".restore-stage-") or relative_path.parts[0].startswith(".restore-old-")):
            continue
        relative = relative_path.as_posix()
        stat = path.stat()
        result[relative] = {
            "sha256": sha256_file(path),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return result


def latest_successful_job() -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE status='success' ORDER BY finished_at DESC, rowid DESC LIMIT 1"
        ).fetchone()


def latest_master_job() -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE status='success' AND effective_kind='master' ORDER BY finished_at DESC, rowid DESC LIMIT 1"
        ).fetchone()


def load_runtime_manifest(job: sqlite3.Row | None) -> dict[str, Any]:
    if not job or not job["backup_dir"]:
        return {}
    path = REPOSITORY_ROOT / str(job["backup_dir"]) / "runtime-manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def job_artifacts_present(job: sqlite3.Row | None) -> bool:
    if not job or not job["backup_dir"]:
        return False
    target = REPOSITORY_ROOT / str(job["backup_dir"])
    return all((target / name).is_file() for name in ("manifest.json", "checksums.sha256", "runtime-manifest.json"))


def ensure_pgbackrest() -> None:
    global PGBACKREST_LAST_ERROR
    try:
        runner_post("/pgbackrest/action", {"action": "stanza-create"})
        runner_post("/pgbackrest/action", {"action": "check"})
    except Exception as exc:
        with PGBACKREST_STATE_LOCK:
            PGBACKREST_LAST_ERROR = f"{type(exc).__name__}: {exc}"[:1000]
        PGBACKREST_READY.clear()
        raise
    else:
        with PGBACKREST_STATE_LOCK:
            PGBACKREST_LAST_ERROR = None
        PGBACKREST_READY.set()


def bootstrap_pgbackrest() -> None:
    for attempt in range(1, 31):
        try:
            ensure_pgbackrest()
            return
        except Exception:
            if attempt < 30:
                time.sleep(10)


def pgbackrest_info() -> list[dict[str, Any]]:
    payload = runner_get("/pgbackrest/info").get("stanzas")
    if not isinstance(payload, list):
        raise RuntimeError("A pgBackRest info kimenete érvénytelen")
    return payload


def latest_pgbackrest_backup() -> dict[str, Any] | None:
    payload = pgbackrest_info()
    backups = payload[0].get("backup", []) if payload else []
    return backups[-1] if backups else None


def pgbackrest_backup_details(label: str) -> dict[str, Any]:
    for stanza in pgbackrest_info():
        for backup in stanza.get("backup", []):
            if str(backup.get("label")) == label:
                return backup
    raise RuntimeError(f"A pgBackRest backup set nem található: {label}")


def pgbackrest_backup_stop_lsn(label: str) -> str:
    details = pgbackrest_backup_details(label)
    stop_lsn = (details.get("lsn") or {}).get("stop")
    if not stop_lsn:
        raise RuntimeError(f"A pgBackRest backup stop LSN nem olvasható: {label}")
    return str(stop_lsn)


def pgbackrest_verify_set(label: str) -> None:
    if not label:
        raise RuntimeError("A pgBackRest verify backup labelje hiányzik")
    runner_post("/pgbackrest/verify", {"label": label}, timeout=86400)


def pgbackrest_backup(kind: str) -> dict[str, Any]:
    backup_type = "full" if kind == "master" else "incr"
    runner_post("/pgbackrest/backup", {"backup_type": backup_type}, timeout=86400)
    backup = latest_pgbackrest_backup()
    if not backup or not backup.get("label"):
        raise RuntimeError("A pgBackRest mentés elkészült, de a backup label nem olvasható vissza")
    return backup


def copy_project_files(target: Path) -> None:
    for name in ("VERSION", "CHANGELOG.md", "docker-compose.yml", ".env"):
        source = PROJECT_ROOT / name
        if source.exists() and source.is_file():
            shutil.copy2(source, target / name)


def write_system_metadata(target: Path) -> None:
    versions = runner_get("/docker/versions")
    (target / "docker-version.txt").write_text(str(versions.get("docker") or ""), encoding="utf-8")
    (target / "docker-compose-version.txt").write_text(str(versions.get("compose") or ""), encoding="utf-8")


def write_runtime_snapshot(target: Path, kind: str, previous_manifest: dict[str, Any], current_manifest: dict[str, Any]) -> dict[str, Any]:
    changed = sorted(
        path for path, metadata in current_manifest.items()
        if path not in previous_manifest or previous_manifest[path].get("sha256") != metadata.get("sha256")
    )
    deleted = sorted(path for path in previous_manifest if path not in current_manifest)
    if kind == "master":
        changed = sorted(current_manifest)
        deleted = []
    tar_path = target / ("app-runtime-full.tar.gz" if kind == "master" else "app-runtime-incremental.tar.gz")
    with tarfile.open(tar_path, "w:gz") as archive:
        for relative in changed:
            source = RUNTIME_ROOT / relative
            if source.exists() and source.is_file():
                archive.add(source, arcname=relative, recursive=False)
    (target / "runtime-manifest.json").write_text(json.dumps(current_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    delta = {"changed": changed, "deleted": deleted}
    (target / "runtime-delta.json").write_text(json.dumps(delta, ensure_ascii=False, indent=2), encoding="utf-8")
    return delta


def save_images(target: Path, deployment: dict[str, Any]) -> None:
    services = [service for service in deployment.get("images", {}) if service in {"db", "backend", "frontend", "backup-agent", "push-worker"}]
    if services:
        destination = (target / "docker-images.tar").relative_to(REPOSITORY_ROOT).as_posix()
        runner_post("/images/export", {"services": services, "destination": destination}, timeout=86400)


def write_checksums(target: Path) -> None:
    lines = []
    for path in sorted(target.rglob("*")):
        if not path.is_file() or path.name == "checksums.sha256":
            continue
        relative = path.relative_to(target).as_posix()
        lines.append(f"{sha256_file(path)} *{relative}")
    (target / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def folder_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def new_job_id(kind: str) -> str:
    prefix = "MST" if kind == "master" else "INC"
    timezone_name = schedule_payload()["timezone"]
    return f"{prefix}-{datetime.now(ZoneInfo(timezone_name)).strftime('%Y%m%d-%H%M%S-%f')}"


class BackupBusyError(RuntimeError):
    pass


def active_job_exists() -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM jobs WHERE status IN ('queued', 'running') LIMIT 1").fetchone() is not None


def active_restore_exists() -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM restore_jobs WHERE status IN ('queued', 'running') LIMIT 1").fetchone() is not None


def restore_recovery_required() -> bool:
    return get_setting("restore.recovery_required", "false") == "true"


def runtime_recovery_artifacts() -> list[str]:
    if not RUNTIME_ROOT.exists():
        return []
    return sorted(
        child.name
        for child in RUNTIME_ROOT.iterdir()
        if child.name.startswith(".restore-stage-") or child.name.startswith(".restore-old-")
    )


def insert_backup_job(
    requested_kind: str,
    trigger: str,
    actor: ManualBackupRequest | None = None,
    *,
    allow_during_restore: bool = False,
) -> str:
    with LOCK:
        if not allow_during_restore and (active_job_exists() or active_restore_exists() or restore_recovery_required()):
            raise BackupBusyError("Másik mentési vagy visszaállítási feladat már fut, illetve helyreállítás szükséges")
        job_id = new_job_id(requested_kind)
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(id, requested_kind, trigger, status, created_at, requested_by_user_id, requested_by_name, requested_by_email)
                VALUES (?, ?, ?, 'queued', ?, ?, ?, ?)
                """,
                (
                    job_id, requested_kind, trigger, now_iso(),
                    actor.requested_by_user_id if actor else None,
                    actor.requested_by_name if actor else None,
                    actor.requested_by_email if actor else None,
                ),
            )
            conn.commit()
    return job_id


def create_job(requested_kind: str, trigger: str, actor: ManualBackupRequest | None = None) -> str:
    job_id = insert_backup_job(requested_kind, trigger, actor)
    thread = threading.Thread(target=perform_job, args=(job_id,), daemon=True, name=f"backup-{job_id}")
    thread.start()
    return job_id


def _append_resume_warning(job_id: str, warning: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT status, message, error FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return
        if row["status"] == "success":
            conn.execute(
                "UPDATE jobs SET message=? WHERE id=?",
                (((row["message"] or "") + "; FIGYELEM: " + warning).strip("; ")[:4000], job_id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET error=? WHERE id=?",
                (((row["error"] or "") + "; " + warning).strip("; ")[:4000], job_id),
            )
        conn.commit()


def _perform_backup_job(job_id: str, *, leave_quiesced_on_success: bool = False) -> dict[str, Any]:
    application_states: dict[str, bool] = {}
    final_job_id = job_id
    success = False
    try:
        with connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise RuntimeError(f"A backup feladat nem található: {job_id}")
            conn.execute("UPDATE jobs SET status='running', started_at=? WHERE id=?", (now_iso(), job_id))
            conn.commit()

        requested_kind = str(row["requested_kind"])
        fingerprint, deployment = deployment_fingerprint()
        latest_master = latest_master_job()
        previous = latest_successful_job()
        effective_kind = requested_kind
        promotion_reason = None
        ensure_pgbackrest()
        if requested_kind == "incremental":
            if latest_master is None:
                effective_kind = "master"
                promotion_reason = "Nincs használható korábbi MASTER mentés"
            elif latest_master["deployment_fingerprint"] != fingerprint:
                effective_kind = "master"
                promotion_reason = "Az alkalmazás deploymentje megváltozott"
            elif not job_artifacts_present(latest_master) or not job_artifacts_present(previous):
                effective_kind = "master"
                promotion_reason = "A korábbi runtime mentési lánc hiányos"
            else:
                pg_labels = {
                    str(backup.get("label"))
                    for stanza in pgbackrest_info()
                    for backup in stanza.get("backup", [])
                    if backup.get("label")
                }
                if not latest_master["pgbackrest_label"] or str(latest_master["pgbackrest_label"]) not in pg_labels:
                    effective_kind = "master"
                    promotion_reason = "A korábbi MASTER pgBackRest mentése nem található"

        backup_id = job_id
        if effective_kind == "master" and not job_id.startswith("MST-"):
            backup_id = "MST-" + job_id.removeprefix("INC-")
        final_job_id = backup_id
        relative_dir = Path("app_backups") / backup_id
        target = REPOSITORY_ROOT / relative_dir
        target.mkdir(parents=True, exist_ok=False)
        target.chmod(0o700)

        application_states = quiesce_application()
        pg_backup = pgbackrest_backup(effective_kind)
        pg_label = str(pg_backup["label"])
        pg_info = pg_backup.get("info") or {}
        pg_repository = pg_info.get("repository") or {}
        db_repo_delta_bytes = int(pg_repository.get("delta") or 0)
        db_repo_set_bytes = int(pg_repository.get("size") or 0)

        previous_manifest = {} if effective_kind == "master" else load_runtime_manifest(previous)
        current_manifest = runtime_manifest()
        delta = write_runtime_snapshot(target, effective_kind, previous_manifest, current_manifest)
        copy_project_files(target)
        write_system_metadata(target)
        if effective_kind == "master":
            save_images(target, deployment)

        metadata = {
            "format": "munkalap-integrated-backup",
            "format_version": 1,
            "application_version": APP_VERSION,
            "backup_id": backup_id,
            "requested_kind": requested_kind,
            "effective_kind": effective_kind,
            "trigger": row["trigger"],
            "created_at": now_iso(),
            "pgbackrest_stanza": STANZA,
            "pgbackrest_label": pg_label,
            "base_master_id": backup_id if effective_kind == "master" else (latest_master["id"] if latest_master else None),
            "deployment_fingerprint": fingerprint,
            "deployment": deployment,
            "runtime_delta": delta,
            "promotion_reason": promotion_reason,
        }
        (target / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        write_checksums(target)
        app_size = folder_size(target)
        size = app_size + db_repo_delta_bytes
        local_today = datetime.now(ZoneInfo(schedule_payload()["timezone"])).date().isoformat()
        message = "Mentés sikeresen elkészült"
        if promotion_reason:
            message += f"; MASTER-re emelve: {promotion_reason}"
        with connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET id=?, effective_kind=?, status='success', finished_at=?, local_date=?, base_master_id=?,
                    pgbackrest_label=?, deployment_fingerprint=?, backup_dir=?, size_bytes=?, message=?,
                    app_size_bytes=?, db_repo_delta_bytes=?, db_repo_set_bytes=?
                WHERE id=?
                """,
                (
                    backup_id, effective_kind, now_iso(), local_today,
                    metadata["base_master_id"], pg_label, fingerprint, relative_dir.as_posix(), size, message,
                    app_size, db_repo_delta_bytes, db_repo_set_bytes, job_id,
                ),
            )
            conn.commit()
        schedule_updates = {"schedule.last_covered_date": local_today}
        if row["trigger"] == "scheduled":
            schedule_updates["schedule.last_run_date"] = local_today
        try:
            set_settings(schedule_updates)
        except Exception as exc:
            warning = f"Az ütemezési állapot frissítése sikertelen: {type(exc).__name__}: {exc}"
            with connect() as conn:
                saved = conn.execute("SELECT message FROM jobs WHERE id=?", (backup_id,)).fetchone()
                if saved:
                    updated_message = ((saved["message"] or "") + "; FIGYELEM: " + warning).strip("; ")[:4000]
                    conn.execute("UPDATE jobs SET message=? WHERE id=?", (updated_message, backup_id))
                    conn.commit()
            traceback.print_exc()
        success = True
        stop_lsn = str((pg_backup.get("lsn") or {}).get("stop") or "")
        return {
            "job_id": backup_id,
            "application_states": application_states,
            "pgbackrest_label": pg_label,
            "pgbackrest_stop_lsn": stop_lsn,
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        with connect() as conn:
            candidate_id = final_job_id
            exists = conn.execute("SELECT 1 FROM jobs WHERE id=?", (candidate_id,)).fetchone()
            if not exists:
                candidate_id = job_id
            conn.execute("UPDATE jobs SET status='failed', finished_at=?, error=? WHERE id=?", (now_iso(), error[:4000], candidate_id))
            conn.commit()
        raise
    finally:
        if application_states and (not success or not leave_quiesced_on_success):
            try:
                resume_application(application_states)
            except Exception:
                traceback.print_exc()
                row_id = final_job_id
                with connect() as conn:
                    if not conn.execute("SELECT 1 FROM jobs WHERE id=?", (row_id,)).fetchone():
                        row_id = job_id
                _append_resume_warning(row_id, "Az alkalmazási szolgáltatások automatikus újraindítása sikertelen")


def perform_job(job_id: str) -> None:
    if not RUN_LOCK.acquire(blocking=False):
        with connect() as conn:
            conn.execute("UPDATE jobs SET status='failed', finished_at=?, error=? WHERE id=?", (now_iso(), "Másik mentési vagy visszaállítási feladat már fut", job_id))
            conn.commit()
        return
    try:
        result = _perform_backup_job(job_id)
        final_backup_id = str(result.get("job_id") or job_id)
        if OFFSITE_ENABLED:
            try:
                offsite = run_offsite_backup(final_backup_id)
                record_offsite_result(
                    final_backup_id,
                    status_value="success",
                    snapshot_id=str(offsite.get("snapshot_id") or "") or None,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                record_offsite_result(final_backup_id, status_value="failed", error=error)
                traceback.print_exc()
    except Exception:
        traceback.print_exc()
    finally:
        RUN_LOCK.release()


def list_jobs(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    return [dict(row) for row in rows]


def backup_chain(row: sqlite3.Row) -> list[sqlite3.Row]:
    if row["effective_kind"] == "master":
        return [row]
    base_master_id = row["base_master_id"]
    if not base_master_id:
        raise HTTPException(status_code=409, detail="Az inkrementális mentéshez nincs alap MASTER rendelve")
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status='success'
              AND finished_at <= ?
              AND (id = ? OR (base_master_id = ? AND effective_kind='incremental'))
            ORDER BY finished_at ASC, rowid ASC
            """,
            (row["finished_at"], base_master_id, base_master_id),
        ).fetchall()
    if not rows or rows[0]["id"] != base_master_id or rows[-1]["id"] != row["id"]:
        raise HTTPException(status_code=409, detail="A runtime inkrementális mentési lánc hiányos")
    return rows


def validate_app_artifacts(row: sqlite3.Row) -> int:
    if not row["backup_dir"]:
        raise HTTPException(status_code=409, detail=f"Hiányzik a backup könyvtár: {row['id']}")
    target = REPOSITORY_ROOT / str(row["backup_dir"])
    checksum_path = target / "checksums.sha256"
    if not checksum_path.exists():
        raise HTTPException(status_code=409, detail=f"Hiányzik a checksum fájl: {row['id']}")
    checked = 0
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            expected, relative = line.split(" *", 1)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=f"Érvénytelen checksum sor ({row['id']})") from exc
        if len(expected) != 64 or any(char not in "0123456789abcdefABCDEF" for char in expected):
            raise HTTPException(status_code=409, detail=f"Érvénytelen checksum érték ({row['id']}): {relative}")
        path = (target / relative).resolve()
        if target.resolve() not in path.parents and path != target.resolve():
            raise HTTPException(status_code=409, detail="Érvénytelen mentési fájlútvonal")
        if not path.exists() or sha256_file(path) != expected:
            raise HTTPException(status_code=409, detail=f"Sérült mentési elem ({row['id']}): {relative}")
        checked += 1
    return checked


def validate_backup(job_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row or row["status"] != "success" or not row["backup_dir"]:
        raise HTTPException(status_code=404, detail="A mentési pont nem található vagy nem sikeres")
    chain = backup_chain(row)
    checked = sum(validate_app_artifacts(item) for item in chain)
    ensure_pgbackrest()
    labels = {
        str(backup.get("label"))
        for stanza in pgbackrest_info()
        for backup in stanza.get("backup", [])
        if backup.get("label")
    }
    missing_labels = [item["id"] for item in chain if not item["pgbackrest_label"] or str(item["pgbackrest_label"]) not in labels]
    if missing_labels:
        raise HTTPException(
            status_code=409,
            detail="A mentési láncból hiányzik pgBackRest adatbázismentés: " + ", ".join(missing_labels),
        )
    target_label = str(row["pgbackrest_label"] or "")
    try:
        pgbackrest_verify_set(target_label)
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail=f"A pgBackRest repository fizikai ellenőrzése sikertelen ({job_id}): {type(exc).__name__}: {exc}",
        ) from exc
    return {
        "backup_id": job_id,
        "valid": True,
        "checked_files": checked,
        "chain_points": len(chain),
        "pgbackrest_verified": True,
        "pgbackrest_label": target_label,
        "validated_at": now_iso(),
    }



def stop_service(service: str, timeout_seconds: int = 60) -> None:
    if service_is_running(service):
        runner_post(f"/services/{service}/stop", {"timeout_seconds": timeout_seconds})


def start_service(service: str) -> None:
    if not service_is_running(service):
        runner_post(f"/services/{service}/start")


def wait_for_database(attempts: int = 60, delay_seconds: float = 2.0) -> None:
    last_detail = ""
    for _ in range(attempts):
        state = runner_get("/database/state")
        if state.get("ready") and state.get("state") == "primary":
            return
        last_detail = str(state.get("state") or "not ready")[-1000:]
        time.sleep(delay_seconds)
    suffix = f": {last_detail}" if last_detail else ""
    raise RuntimeError("A PostgreSQL nem vált elérhető, primary állapotú adatbázissá a visszaállítás után" + suffix)


def backend_health_ready() -> bool:
    request = urllib.request.Request(BACKEND_INTERNAL_URL + "/api/health", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("status") == "ok"


def wait_for_backend(attempts: int = 90, delay_seconds: float = 2.0) -> dict[str, str]:
    last_detail = ""
    for _ in range(attempts):
        if service_is_running("backend"):
            alembic = runner_get("/alembic/status")
            heads = list(alembic.get("heads") or [])
            current_revision = alembic.get("current")
            if len(heads) != 1:
                last_detail = f"Restore utáni Alembic head hiba: {len(heads)} head található"
            elif not current_revision:
                last_detail = "Az Alembic current kimenete üres"
            elif heads[0] != current_revision:
                raise RuntimeError(f"Restore utáni migrációs eltérés: current={current_revision}, head={heads[0]}")
            elif backend_health_ready():
                return {"current": str(current_revision), "head": str(heads[0])}
            else:
                last_detail = "Az Alembic rendben van, de a backend /api/health végpont még nem elérhető"
        time.sleep(delay_seconds)
    raise RuntimeError("A backend nem vált üzemképessé a visszaállítás után" + (f": {last_detail}" if last_detail else ""))


def _safe_extract_tar(tar_path: Path, target: Path) -> None:
    target_resolved = target.resolve()
    with tarfile.open(tar_path, "r:gz") as archive:
        for member in archive.getmembers():
            if member.islnk() or member.issym() or member.isdev():
                raise RuntimeError(f"Nem támogatott elem a runtime archívumban: {member.name}")
            resolved = (target / member.name).resolve()
            if resolved != target_resolved and target_resolved not in resolved.parents:
                raise RuntimeError(f"Érvénytelen útvonal a runtime archívumban: {member.name}")
        archive.extractall(target, filter="data")


def normalize_runtime_permissions(root: Path = RUNTIME_ROOT) -> None:
    """Keep restored runtime content writable by the non-root FastAPI uid/gid.

    Never follows symlinks while changing ownership/permissions.
    """
    if not root.exists():
        return

    def normalize_one(path: Path) -> None:
        if path.is_symlink():
            os.lchown(path, RUNTIME_OWNER_UID, RUNTIME_OWNER_GID)
            return
        os.chown(path, RUNTIME_OWNER_UID, RUNTIME_OWNER_GID)
        mode = stat.S_IMODE(path.stat().st_mode)
        owner_bits = stat.S_IRUSR | stat.S_IWUSR
        if path.is_dir():
            owner_bits |= stat.S_IXUSR
        os.chmod(path, mode | owner_bits)

    normalize_one(root)
    for current_root, dir_names, file_names in os.walk(root, followlinks=False):
        base = Path(current_root)
        for name in dir_names:
            normalize_one(base / name)
        for name in file_names:
            normalize_one(base / name)


def runtime_content_signature(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        result[relative] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    return result


def build_runtime_restore_stage(chain: list[sqlite3.Row], restore_id: str) -> Path:
    stage = RUNTIME_ROOT / f".restore-stage-{restore_id}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, mode=0o700)
    for index, row in enumerate(chain):
        target = REPOSITORY_ROOT / str(row["backup_dir"])
        kind = str(row["effective_kind"])
        tar_name = "app-runtime-full.tar.gz" if kind == "master" else "app-runtime-incremental.tar.gz"
        tar_path = target / tar_name
        if not tar_path.is_file():
            raise RuntimeError(f"Hiányzik a runtime archívum: {row['id']}")
        if index == 0 and kind != "master":
            raise RuntimeError("A runtime restore lánc nem MASTER mentéssel kezdődik")
        if kind == "incremental":
            delta_path = target / "runtime-delta.json"
            delta = json.loads(delta_path.read_text(encoding="utf-8"))
            for relative in delta.get("deleted", []):
                candidate = (stage / str(relative)).resolve()
                if stage.resolve() not in candidate.parents:
                    raise RuntimeError("Érvénytelen törlési útvonal a runtime delta manifestben")
                if candidate.is_dir():
                    shutil.rmtree(candidate)
                elif candidate.exists():
                    candidate.unlink()
        _safe_extract_tar(tar_path, stage)

    target_dir = REPOSITORY_ROOT / str(chain[-1]["backup_dir"])
    expected_raw = json.loads((target_dir / "runtime-manifest.json").read_text(encoding="utf-8"))
    expected = {
        str(name): {"sha256": str(meta.get("sha256")), "size": int(meta.get("size") or 0)}
        for name, meta in expected_raw.items()
    }
    actual = runtime_content_signature(stage)
    if expected != actual:
        missing = sorted(set(expected) - set(actual))[:10]
        extra = sorted(set(actual) - set(expected))[:10]
        changed = sorted(
            name for name in set(expected) & set(actual) if expected[name] != actual[name]
        )[:10]
        raise RuntimeError(
            "A rekonstruált runtime nem egyezik a mentési pont manifestjével "
            f"(hiányzó={missing}, extra={extra}, eltérő={changed})"
        )
    return stage


def install_runtime_stage(stage: Path, restore_id: str) -> Path:
    old = RUNTIME_ROOT / f".restore-old-{restore_id}"
    if old.exists():
        shutil.rmtree(old)
    old.mkdir(parents=True, mode=0o700)
    for child in list(RUNTIME_ROOT.iterdir()):
        if child == stage or child == old:
            continue
        shutil.move(str(child), str(old / child.name))
    for child in list(stage.iterdir()):
        shutil.move(str(child), str(RUNTIME_ROOT / child.name))
    stage.rmdir()
    normalize_runtime_permissions(RUNTIME_ROOT)
    return old


def rollback_runtime_swap(old: Path | None) -> None:
    if not old or not old.exists():
        return
    for child in list(RUNTIME_ROOT.iterdir()):
        if child == old:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)
    for child in list(old.iterdir()):
        shutil.move(str(child), str(RUNTIME_ROOT / child.name))
    old.rmdir()
    normalize_runtime_permissions(RUNTIME_ROOT)


def cleanup_runtime_old(old: Path | None) -> None:
    if old and old.exists():
        shutil.rmtree(old)


def restore_database_to_label(label: str, stop_lsn: str) -> None:
    if not stop_lsn:
        raise RuntimeError("A kiválasztott backup stop LSN értéke hiányzik")
    runner_post("/database/restore", {"label": label, "stop_lsn": stop_lsn}, timeout=86400)


def notify_backend_restore_event(restore_row: dict[str, Any], *, outcome: str, checks: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps({
        "restore_id": restore_row.get("id"),
        "backup_id": restore_row.get("backup_id"),
        "pre_restore_backup_id": restore_row.get("pre_restore_backup_id"),
        "post_restore_backup_id": restore_row.get("post_restore_backup_id"),
        "rollback_restore_backup_id": restore_row.get("rollback_restore_backup_id"),
        "requested_by_user_id": restore_row.get("requested_by_user_id"),
        "requested_by_name": restore_row.get("requested_by_name"),
        "requested_by_email": restore_row.get("requested_by_email"),
        "outcome": outcome,
        "checks": checks or {},
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        BACKEND_INTERNAL_URL + "/api/backups/internal/restore-event",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Backup-Agent-Token": AGENT_TOKEN},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            response_body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            response_body = ""
        http_detail = f"HTTP {exc.code} {exc.reason}"
        if response_body:
            http_detail += f": {response_body[:2000]}"
        raise RuntimeError(f"A restore audit/post-check backend hívás sikertelen: {http_detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"A restore audit/post-check backend hívás sikertelen: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("A restore audit/post-check backend válasza érvénytelen")
    return payload


def new_restore_id() -> str:
    timezone_name = schedule_payload()["timezone"]
    return f"RST-{datetime.now(ZoneInfo(timezone_name)).strftime('%Y%m%d-%H%M%S-%f')}"


def list_restore_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM restore_jobs ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (max(1, min(limit, 200)),),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_restore_job() -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM restore_jobs ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()


def create_restore_job(backup_id: str, payload: RestoreRequest) -> str:
    current_fingerprint, _ = deployment_fingerprint()
    with LOCK:
        if RUN_LOCK.locked() or active_job_exists() or active_restore_exists() or restore_recovery_required():
            raise BackupBusyError("Másik mentési/visszaállítási feladat fut, vagy megszakadt restore helyreállítása szükséges")
        with connect() as conn:
            target = conn.execute("SELECT * FROM jobs WHERE id=? AND status='success'", (backup_id,)).fetchone()
            if not target:
                raise HTTPException(status_code=404, detail="A kiválasztott sikeres mentési pont nem található")
            if not target["deployment_fingerprint"] or str(target["deployment_fingerprint"]) != current_fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A kiválasztott mentés más deploymenthez tartozik. Webes restore csak azonos deploymenten belül "
                        "engedélyezett; verzió/image/config visszaállításhoz használd a host restore scriptet."
                    ),
                )
            restore_id = new_restore_id()
            conn.execute(
                """
                INSERT INTO restore_jobs(
                    id, backup_id, status, created_at,
                    requested_by_user_id, requested_by_name, requested_by_email
                ) VALUES (?, ?, 'queued', ?, ?, ?, ?)
                """,
                (
                    restore_id, backup_id, now_iso(), payload.requested_by_user_id,
                    payload.requested_by_name, payload.requested_by_email,
                ),
            )
            conn.commit()
    threading.Thread(target=perform_restore, args=(restore_id,), daemon=True, name=f"restore-{restore_id}").start()
    return restore_id


def _restore_row(restore_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM restore_jobs WHERE id=?", (restore_id,)).fetchone()
    if not row:
        raise RuntimeError(f"A restore feladat nem található: {restore_id}")
    return dict(row)


def _set_restore_fields(restore_id: str, **values: Any) -> None:
    if not values:
        return
    columns = ", ".join(f"{key}=?" for key in values)
    with connect() as conn:
        conn.execute(
            f"UPDATE restore_jobs SET {columns} WHERE id=?",
            (*values.values(), restore_id),
        )
        conn.commit()


def _stop_application_and_db() -> None:
    for service in ("frontend", "backend", "db"):
        try:
            stop_service(service)
        except Exception:
            traceback.print_exc()


def perform_restore(restore_id: str) -> None:
    if not RUN_LOCK.acquire(blocking=False):
        _set_restore_fields(
            restore_id, status="failed", finished_at=now_iso(),
            error="Másik mentési vagy visszaállítási feladat már fut",
        )
        return

    original_app_states: dict[str, bool] = {}
    runtime_old: Path | None = None
    pre_backup_id: str | None = None
    pre_pg_label: str | None = None
    pre_stop_lsn: str | None = None
    target_stop_lsn: str | None = None
    post_backup_id: str | None = None
    rollback_backup_id: str | None = None
    destructive_started = False
    stage_path = RUNTIME_ROOT / f".restore-stage-{restore_id}"
    try:
        _set_restore_fields(restore_id, status="running", started_at=now_iso())
        restore = _restore_row(restore_id)
        backup_id = str(restore["backup_id"])
        validation = validate_backup(backup_id)
        with connect() as conn:
            target = conn.execute("SELECT * FROM jobs WHERE id=?", (backup_id,)).fetchone()
        if not target:
            raise RuntimeError("A kiválasztott mentési pont eltűnt a restore indítása után")

        current_fingerprint, _ = deployment_fingerprint()
        if not target["deployment_fingerprint"] or str(target["deployment_fingerprint"]) != current_fingerprint:
            raise RuntimeError(
                "A kiválasztott mentés más deploymenthez tartozik. Webes restore csak azonos deploymenten belül engedélyezett; "
                "verzió-visszaállításhoz használd a host restore scriptet."
            )

        target_stop_lsn = pgbackrest_backup_stop_lsn(str(target["pgbackrest_label"]))

        actor = ManualBackupRequest(
            requested_by_user_id=restore.get("requested_by_user_id"),
            requested_by_name=restore.get("requested_by_name"),
            requested_by_email=restore.get("requested_by_email"),
        )
        pre_job_id = insert_backup_job("master", "pre_restore", actor, allow_during_restore=True)
        pre_result = _perform_backup_job(pre_job_id, leave_quiesced_on_success=True)
        pre_backup_id = str(pre_result["job_id"])
        pre_pg_label = str(pre_result["pgbackrest_label"])
        pre_stop_lsn = str(pre_result.get("pgbackrest_stop_lsn") or "")
        original_app_states = dict(pre_result["application_states"])
        if not pre_stop_lsn:
            raise RuntimeError("A pre-restore MASTER backup-stop LSN értéke hiányzik")
        _set_restore_fields(restore_id, pre_restore_backup_id=pre_backup_id)

        chain = backup_chain(target)
        stage = build_runtime_restore_stage(chain, restore_id)
        destructive_started = True
        stop_service("db")
        runtime_old = install_runtime_stage(stage, restore_id)
        restore_database_to_label(str(target["pgbackrest_label"]), target_stop_lsn)
        start_service("db")
        wait_for_database()

        # A restore új PostgreSQL timeline-t hozhat létre. Mielőtt az alkalmazás
        # újra írhatna, teljes MASTER készül a visszaállított állapotról, és ez
        # lesz a következő inkrementális lánc új alapja.
        post_job_id = insert_backup_job("master", "post_restore", actor, allow_during_restore=True)
        post_result = _perform_backup_job(post_job_id, leave_quiesced_on_success=True)
        post_backup_id = str(post_result["job_id"])
        _set_restore_fields(restore_id, post_restore_backup_id=post_backup_id)

        checks: dict[str, Any] = {"backup_validation": validation}
        if original_app_states.get("backend"):
            start_service("backend")
            checks["alembic"] = wait_for_backend()
            event_result = notify_backend_restore_event(
                {**_restore_row(restore_id), "post_restore_backup_id": post_backup_id},
                outcome="success",
                checks=checks,
            )
            checks["audit"] = event_result.get("audit_chain")
            if not (event_result.get("audit_chain") or {}).get("valid", False):
                raise RuntimeError("A restore utáni audit hash-chain ellenőrzés sikertelen")
        if original_app_states.get("frontend"):
            start_service("frontend")

        cleanup_runtime_old(runtime_old)
        runtime_old = None
        set_settings({"restore.recovery_required": "false"})
        _set_restore_fields(
            restore_id,
            status="success",
            finished_at=now_iso(),
            message=(
                f"Visszaállítás sikeres: {backup_id}; pre-restore MASTER={pre_backup_id}; "
                f"új láncalap MASTER={post_backup_id}"
            ),
            rollback_status=None,
            rollback_error=None,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:4000]
        traceback.print_exc()
        rollback_status = "not_required"
        rollback_error = None
        if destructive_started and pre_backup_id and pre_pg_label and pre_stop_lsn:
            rollback_status = "running"
            try:
                _stop_application_and_db()
                rollback_runtime_swap(runtime_old)
                runtime_old = None
                restore_database_to_label(pre_pg_label, pre_stop_lsn)
                start_service("db")
                wait_for_database()

                # A rollback restore is uj PostgreSQL timeline-t hozhat letre.
                # Uj MASTER nelkul a korabbi post-restore MASTER maradna a
                # latest_master, ami hibas inkrementalis lancot inditana.
                rollback_job_id = insert_backup_job("master", "rollback_restore", actor, allow_during_restore=True)
                rollback_result = _perform_backup_job(rollback_job_id, leave_quiesced_on_success=True)
                rollback_backup_id = str(rollback_result["job_id"])
                _set_restore_fields(restore_id, rollback_restore_backup_id=rollback_backup_id)

                if original_app_states.get("backend"):
                    start_service("backend")
                    checks = {"alembic": wait_for_backend()}
                    try:
                        notify_backend_restore_event(
                            {**_restore_row(restore_id), "rollback_restore_backup_id": rollback_backup_id},
                            outcome="failed_rolled_back",
                            checks={"restore_error": error, **checks},
                        )
                    except Exception:
                        traceback.print_exc()
                if original_app_states.get("frontend"):
                    start_service("frontend")
                rollback_status = "success"
                set_settings({"restore.recovery_required": "false"})
            except Exception as rollback_exc:
                traceback.print_exc()
                rollback_status = "failed"
                rollback_error = f"{type(rollback_exc).__name__}: {rollback_exc}"[:4000]
                set_settings({"restore.recovery_required": "true"})
        elif original_app_states:
            try:
                if stage_path.exists():
                    shutil.rmtree(stage_path)
                resume_application(original_app_states)
                set_settings({"restore.recovery_required": "false"})
            except Exception as resume_exc:
                traceback.print_exc()
                rollback_status = "failed"
                rollback_error = f"A restore előtti alkalmazásállapot visszaindítása sikertelen: {type(resume_exc).__name__}: {resume_exc}"[:4000]
                set_settings({"restore.recovery_required": "true"})
        _set_restore_fields(
            restore_id,
            status="failed" if rollback_status != "failed" else "critical",
            finished_at=now_iso(),
            error=error,
            rollback_status=rollback_status,
            rollback_error=rollback_error,
        )
    finally:
        RUN_LOCK.release()


def scheduled_kind_for_date(day: date) -> str:
    return "master" if day.day == monthrange(day.year, day.month)[1] else "incremental"


def scheduler_loop() -> None:
    while True:
        try:
            schedule = schedule_payload()
            if (
                schedule["enabled"]
                and PGBACKREST_READY.is_set()
                and not RUN_LOCK.locked()
                and not active_job_exists()
                and not active_restore_exists()
                and not restore_recovery_required()
            ):
                tz = ZoneInfo(schedule["timezone"])
                now = datetime.now(tz)
                today = now.date()
                due_h, due_m = [int(part) for part in schedule["daily_time"].split(":", 1)]
                today_text = today.isoformat()
                if (
                    (now.hour, now.minute) >= (due_h, due_m)
                    and schedule.get("last_attempt_date") != today_text
                    and schedule.get("last_covered_date") != today_text
                ):
                    set_settings({"schedule.last_attempt_date": today_text})
                    create_job(scheduled_kind_for_date(today), "scheduled")
            time.sleep(30)
        except Exception:
            traceback.print_exc()
            time.sleep(30)


@app.get("/health")
def health(_: None = Depends(require_token)):
    return {"status": "ok", "version": APP_VERSION, "timezone": TIMEZONE}


@app.get("/status")
def status_info(_: None = Depends(require_token)):
    latest = latest_successful_job()
    master = latest_master_job()
    usage = shutil.disk_usage(REPOSITORY_ROOT)
    restore = latest_restore_job()
    try:
        current_fingerprint, _ = deployment_fingerprint()
    except Exception:
        current_fingerprint = None
    return {
        "agent_version": APP_VERSION,
        "deployment_fingerprint": current_fingerprint,
        "schedule": schedule_payload(),
        "job_running": RUN_LOCK.locked(),
        "restore_running": active_restore_exists(),
        "restore_recovery_required": restore_recovery_required(),
        "latest_restore": dict(restore) if restore else None,
        "latest_backup": dict(latest) if latest else None,
        "latest_master": dict(master) if master else None,
        "repository": {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        },
        "pgbackrest_stanza": STANZA,
        "pgbackrest_ready": PGBACKREST_READY.is_set(),
        "pgbackrest_error": PGBACKREST_LAST_ERROR,
        "offsite": offsite_status_payload(),
    }


@app.get("/offsite/status")
def offsite_status(_: None = Depends(require_token)):
    return offsite_status_payload()


@app.get("/schedule")
def get_schedule(_: None = Depends(require_token)):
    return schedule_payload()


@app.put("/schedule")
def update_schedule(payload: ScheduleUpdate, _: None = Depends(require_token)):
    set_settings({
        "schedule.enabled": "true" if payload.enabled else "false",
        "schedule.daily_time": payload.daily_time,
        "schedule.timezone": payload.timezone,
    })
    return schedule_payload()


@app.get("/backups")
def backups(limit: int = 100, _: None = Depends(require_token)):
    return list_jobs(limit)


@app.get("/backups/{backup_id}")
def backup_status(backup_id: str, _: None = Depends(require_token)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (backup_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="A backup feladat nem található")
    return dict(row)


@app.post("/backups/master", status_code=status.HTTP_202_ACCEPTED)
def create_master(payload: ManualBackupRequest, _: None = Depends(require_token)):
    if RUN_LOCK.locked() or active_job_exists() or active_restore_exists() or restore_recovery_required():
        raise HTTPException(status_code=409, detail="Másik mentési/visszaállítási feladat fut, vagy helyreállítás szükséges")
    try:
        job_id = create_job("master", "manual", payload)
    except BackupBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job_id": job_id, "status": "queued"}


@app.post("/backups/{backup_id}/validate")
def validate(backup_id: str, _: None = Depends(require_token)):
    return validate_backup(backup_id)


@app.get("/restores")
def restores(limit: int = 50, _: None = Depends(require_token)):
    return list_restore_jobs(limit)


@app.get("/restores/{restore_id}")
def restore_status(restore_id: str, _: None = Depends(require_token)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM restore_jobs WHERE id=?", (restore_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="A restore feladat nem található")
    return dict(row)


@app.post("/backups/{backup_id}/restore", status_code=status.HTTP_202_ACCEPTED)
def restore_backup(backup_id: str, payload: RestoreRequest, _: None = Depends(require_token)):
    try:
        restore_id = create_restore_job(backup_id, payload)
    except BackupBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"restore_id": restore_id, "backup_id": backup_id, "status": "queued"}


@app.post("/recovery/clear")
def clear_recovery_lock(payload: RecoveryClearRequest, _: None = Depends(require_token)):
    if RUN_LOCK.locked() or active_job_exists() or active_restore_exists():
        raise HTTPException(status_code=409, detail="Aktív mentési vagy restore feladat mellett a zárolás nem oldható fel")
    artifacts = runtime_recovery_artifacts()
    if artifacts:
        raise HTTPException(
            status_code=409,
            detail=(
                "A runtime-ban befejezetlen restore staging/rollback könyvtár található: "
                + ", ".join(artifacts[:10])
                + ". Előbb host-szinten ellenőrizd/helyreállítsd az app_runtime tartalmát."
            ),
        )
    wait_for_database(attempts=5, delay_seconds=1)
    wait_for_backend(attempts=5, delay_seconds=1)
    ensure_pgbackrest()
    set_settings({"restore.recovery_required": "false"})
    return {"recovery_required": False, "cleared_at": now_iso(), "runtime_recovery_artifacts": []}
