from __future__ import annotations

import hmac
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_SERVICES = frozenset({"db", "backend", "frontend", "backup-agent", "push-worker", "migrate"})
LIFECYCLE_SERVICES = frozenset({"db", "backend", "frontend"})
IMAGE_EXPORT_SERVICES = frozenset({"db", "backend", "frontend", "backup-agent", "push-worker"})
BACKUP_LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{8,100}$")
LSN_RE = re.compile(r"^[0-9A-F]+/[0-9A-F]+$")
REPOSITORY_ROOT = Path(os.getenv("BACKUP_REPOSITORY_DIR", "/repo"))
STANZA = os.getenv("PGBACKREST_STANZA", "workapp")


def _read_secret(name: str, file_name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    path = os.getenv(file_name, "").strip()
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


RUNNER_TOKEN = _read_secret("BACKUP_RUNNER_TOKEN", "BACKUP_RUNNER_TOKEN_FILE")
app = FastAPI(title="Munkalap privileged backup runner", docs_url=None, redoc_url=None, openapi_url=None)


def require_token(x_backup_runner_token: str | None = Header(default=None)) -> None:
    if not RUNNER_TOKEN or not x_backup_runner_token or not hmac.compare_digest(x_backup_runner_token, RUNNER_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Runner authentication failed")


def run(command: list[str], *, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-2000:]
        raise HTTPException(status_code=502, detail=f"Allowlisted Docker operation failed ({result.returncode}): {detail}")
    return result


def project_name() -> str:
    hostname = os.getenv("HOSTNAME", "")
    result = run(["docker", "inspect", hostname, "--format", '{{ index .Config.Labels "com.docker.compose.project" }}'])
    value = result.stdout.strip()
    if not value:
        raise HTTPException(status_code=503, detail="Compose project label is unavailable")
    return value


def validate_service(service: str, allowed: frozenset[str] = ALLOWED_SERVICES) -> str:
    if service not in allowed:
        raise HTTPException(status_code=422, detail="Service is not allowlisted for this operation")
    return service


def container_id(service: str, *, include_stopped: bool = True) -> str:
    validate_service(service)
    command = ["docker", "ps"]
    if include_stopped:
        command.append("-a")
    command += [
        "--filter", f"label=com.docker.compose.project={project_name()}",
        "--filter", f"label=com.docker.compose.service={service}",
        "--format", "{{.ID}}",
    ]
    ids = [line.strip() for line in run(command).stdout.splitlines() if line.strip()]
    if len(ids) != 1:
        raise HTTPException(status_code=503, detail=f"Expected exactly one container for service {service}")
    return ids[0]


def service_metadata(service: str) -> dict:
    cid = container_id(service)
    result = run(["docker", "inspect", cid, "--format", "{{.Config.Image}}|{{.Image}}|{{.State.Running}}"])
    reference, image_id, running = (result.stdout.strip().split("|", 2) + ["", "", "false"])[:3]
    return {"service": service, "image_reference": reference, "image_id": image_id, "running": running.lower() == "true"}


def volume_name(service: str, destination: str) -> str:
    payload = json.loads(run(["docker", "inspect", container_id(service)]).stdout)
    for mount in (payload[0].get("Mounts", []) if payload else []):
        if mount.get("Destination") == destination and mount.get("Type") == "volume" and mount.get("Name"):
            return str(mount["Name"])
    raise HTTPException(status_code=503, detail=f"Required named volume is unavailable for {service}")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LifecycleRequest(StrictModel):
    timeout_seconds: int = Field(default=60, ge=1, le=120)


class PgBackRestAction(StrictModel):
    action: Literal["stanza-create", "check"]


class PgBackRestBackup(StrictModel):
    backup_type: Literal["full", "incr"]


class PgBackRestLabel(StrictModel):
    label: str = Field(min_length=8, max_length=100)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        if not BACKUP_LABEL_RE.fullmatch(value):
            raise ValueError("Invalid pgBackRest label")
        return value


class RestoreRequest(PgBackRestLabel):
    stop_lsn: str = Field(min_length=3, max_length=32)

    @field_validator("stop_lsn")
    @classmethod
    def validate_lsn(cls, value: str) -> str:
        normalized = value.upper()
        if not LSN_RE.fullmatch(normalized):
            raise ValueError("Invalid PostgreSQL LSN")
        return normalized


class ImageExportRequest(StrictModel):
    services: list[Literal["db", "backend", "frontend", "backup-agent", "push-worker"]] = Field(min_length=1, max_length=5)
    destination: str = Field(min_length=1, max_length=240)


@app.get("/health")
def health(_: None = Depends(require_token)):
    return {"status": "ok"}


@app.get("/project")
def project(_: None = Depends(require_token)):
    return {"project_name": project_name()}


@app.get("/services/{service}")
def get_service(service: str, _: None = Depends(require_token)):
    return service_metadata(validate_service(service))


@app.post("/services/{service}/stop")
def stop_service(service: str, payload: LifecycleRequest, _: None = Depends(require_token)):
    validate_service(service, LIFECYCLE_SERVICES)
    meta = service_metadata(service)
    if meta["running"]:
        run(["docker", "stop", "--time", str(payload.timeout_seconds), container_id(service)])
    return {"service": service, "running": False}


@app.post("/services/{service}/start")
def start_service(service: str, _: None = Depends(require_token)):
    validate_service(service, LIFECYCLE_SERVICES)
    meta = service_metadata(service)
    if not meta["running"]:
        run(["docker", "start", container_id(service)])
    return {"service": service, "running": True}


@app.post("/pgbackrest/action")
def pgbackrest_action(payload: PgBackRestAction, _: None = Depends(require_token)):
    result = run(["docker", "exec", "-u", "postgres", container_id("db"), "pgbackrest", f"--stanza={STANZA}", payload.action])
    return {"ok": True, "output": result.stdout[-4000:]}


@app.get("/pgbackrest/info")
def pgbackrest_info(_: None = Depends(require_token)):
    result = run(["docker", "exec", "-u", "postgres", container_id("db"), "pgbackrest", f"--stanza={STANZA}", "--output=json", "info"])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Invalid pgBackRest info output") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=502, detail="Invalid pgBackRest info output")
    return {"stanzas": payload}


@app.post("/pgbackrest/backup")
def pgbackrest_backup(payload: PgBackRestBackup, _: None = Depends(require_token)):
    run(["docker", "exec", "-u", "postgres", container_id("db"), "pgbackrest", f"--stanza={STANZA}", f"--type={payload.backup_type}", "backup"], timeout=86400)
    return {"ok": True}


@app.post("/pgbackrest/verify")
def pgbackrest_verify(payload: PgBackRestLabel, _: None = Depends(require_token)):
    run(["docker", "exec", "-u", "postgres", container_id("db"), "pgbackrest", f"--stanza={STANZA}", f"--set={payload.label}", "--output=text", "verify"], timeout=86400)
    return {"ok": True}


@app.get("/database/state")
def database_state(_: None = Depends(require_token)):
    if not service_metadata("db")["running"]:
        return {"running": False, "ready": False, "state": None}
    command = (
        'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null '
        '&& psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc '
        '"SELECT CASE WHEN pg_is_in_recovery() THEN \'recovery\' ELSE \'primary\' END"'
    )
    result = run(["docker", "exec", container_id("db"), "sh", "-lc", command], check=False)
    state_value = (result.stdout or "").strip().splitlines()
    state_name = state_value[-1].strip() if state_value else None
    return {"running": True, "ready": result.returncode == 0 and state_name == "primary", "state": state_name}


@app.get("/alembic/status")
def alembic_status(_: None = Depends(require_token)):
    if not service_metadata("backend")["running"]:
        return {"running": False, "current": None, "heads": []}
    cid = container_id("backend")
    current = run(["docker", "exec", cid, "alembic", "current"], check=False)
    heads = run(["docker", "exec", cid, "alembic", "heads"], check=False)
    if current.returncode != 0 or heads.returncode != 0:
        return {"running": True, "current": None, "heads": [], "ready": False}
    current_lines = [line.strip() for line in current.stdout.splitlines() if line.strip()]
    head_lines = [line.strip() for line in heads.stdout.splitlines() if line.strip()]
    return {
        "running": True,
        "ready": bool(current_lines) and len(head_lines) == 1,
        "current": current_lines[-1].split()[0] if current_lines else None,
        "heads": [line.split()[0] for line in head_lines],
    }


@app.get("/docker/versions")
def docker_versions(_: None = Depends(require_token)):
    version = run(["docker", "version"], check=False)
    compose = run(["docker", "compose", "version"], check=False)
    return {"docker": (version.stdout or version.stderr), "compose": (compose.stdout or compose.stderr)}


@app.post("/images/export")
def export_images(payload: ImageExportRequest, _: None = Depends(require_token)):
    destination = (REPOSITORY_ROOT / payload.destination).resolve()
    root = REPOSITORY_ROOT.resolve()
    if destination == root or root not in destination.parents or destination.suffix != ".tar":
        raise HTTPException(status_code=422, detail="Invalid repository destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    references: list[str] = []
    for service in payload.services:
        validate_service(service, IMAGE_EXPORT_SERVICES)
        reference = service_metadata(service)["image_reference"]
        if reference and reference not in references:
            references.append(reference)
    if not references:
        raise HTTPException(status_code=422, detail="No allowlisted images to export")
    run(["docker", "image", "save", "-o", str(destination), *references], timeout=86400)
    return {"ok": True, "destination": payload.destination}


@app.post("/database/restore")
def restore_database(payload: RestoreRequest, _: None = Depends(require_token)):
    db_volume = volume_name("db", "/var/lib/postgresql/data")
    repo_volume = volume_name("db", "/var/lib/pgbackrest")
    image_reference = service_metadata("db")["image_reference"]
    if not image_reference:
        raise HTTPException(status_code=503, detail="Database image reference is unavailable")
    run([
        "docker", "run", "--rm", "--user", "postgres", "--entrypoint", "pgbackrest",
        "-v", f"{db_volume}:/var/lib/postgresql/data",
        "-v", f"{repo_volume}:/var/lib/pgbackrest",
        image_reference,
        f"--stanza={STANZA}", f"--set={payload.label}", "--delta", "--type=lsn", f"--target={payload.stop_lsn}",
        "--target-timeline=current", "--target-action=promote", "restore",
    ], timeout=86400)
    return {"ok": True}
