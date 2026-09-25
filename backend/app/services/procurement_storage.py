from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from ..config import Settings
from .malware_scan import scan_path
from .upload_validation import validate_safe_zip

CHUNK_SIZE = 1024 * 1024

EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

DECLARED_MIME_ALIASES = {
    ".pdf": {"application/pdf", "application/octet-stream", ""},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
        "",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
        "",
    },
    ".csv": {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel", "application/octet-stream", ""},
    ".jpg": {"image/jpeg", "application/octet-stream", ""},
    ".jpeg": {"image/jpeg", "application/octet-stream", ""},
    ".png": {"image/png", "application/octet-stream", ""},
}


@dataclass(frozen=True)
class StoredProcurementFile:
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str
    original_filename: str


def procurement_root(settings: Settings) -> Path:
    return Path(settings.runtime_dir) / "procurement_attachments"


def procurement_path(settings: Settings, storage_key: str) -> Path:
    root = procurement_root(settings).resolve()
    path = (root / storage_key).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Érvénytelen beszerzési csatolmány útvonal")
    return path


def _safe_original_filename(filename: str | None) -> str:
    name = Path(filename or "csatolmany").name.strip()
    if not name:
        name = "csatolmany"
    return name[:500]


def _validate_file(path: Path, original_filename: str, declared_type: str | None, header: bytes) -> tuple[str, str]:
    extension = Path(original_filename).suffix.lower()
    mime_type = EXTENSION_TO_MIME.get(extension)
    if not mime_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Engedélyezett formátumok: PDF, DOCX, XLSX, CSV, JPG, PNG",
        )

    declared = (declared_type or "").split(";", 1)[0].strip().lower()
    if declared not in DECLARED_MIME_ALIASES[extension]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="A fájl kiterjesztése és a böngésző által jelzett típusa eltér",
        )

    if extension == ".pdf" and not header.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="A fájl tartalma nem érvényes PDF")
    if extension in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=415, detail="A fájl tartalma nem érvényes JPEG")
    if extension == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=415, detail="A fájl tartalma nem érvényes PNG")
    if extension in {".docx", ".xlsx"}:
        try:
            with zipfile.ZipFile(path) as archive:
                validate_safe_zip(archive)
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=415, detail="A fájl nem érvényes Office Open XML dokumentum") from exc
        if "[Content_Types].xml" not in names:
            raise HTTPException(status_code=415, detail="A fájl nem érvényes Office Open XML dokumentum")
        required_prefix = "word/" if extension == ".docx" else "xl/"
        if not any(name.startswith(required_prefix) for name in names):
            raise HTTPException(status_code=415, detail="A fájl tartalma nem egyezik a kiterjesztéssel")
    if extension == ".csv":
        sample = path.read_bytes()[:8192]
        if b"\x00" in sample:
            raise HTTPException(status_code=415, detail="A CSV fájl bináris tartalmat tartalmaz")

    canonical_extension = ".jpg" if extension == ".jpeg" else extension
    return mime_type, canonical_extension


async def store_procurement_upload(upload: UploadFile, settings: Settings) -> StoredProcurementFile:
    original_filename = _safe_original_filename(upload.filename)
    root = procurement_root(settings)
    temp_dir = root / ".tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="upload-", dir=temp_dir)
    temp_path = Path(temp_name)
    size = 0
    digest = hashlib.sha256()
    header = b""
    max_size = settings.procurement_max_size_mb * 1024 * 1024
    try:
        with os.fdopen(fd, "wb") as handle:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                if len(header) < 16:
                    header += chunk[: 16 - len(header)]
                size += len(chunk)
                if size > max_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"A fájl legfeljebb {settings.procurement_max_size_mb} MB lehet",
                    )
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())

        if size == 0:
            raise HTTPException(status_code=400, detail="A feltöltött fájl üres")

        mime_type, extension = _validate_file(temp_path, original_filename, upload.content_type, header)
        scan_path(temp_path, settings)
        now = datetime.utcnow()
        storage_key = f"{now.year:04d}/{now.month:02d}/{uuid.uuid4().hex}{extension}"
        target = procurement_path(settings, storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_name, target)
        return StoredProcurementFile(
            storage_key=storage_key,
            mime_type=mime_type,
            size_bytes=size,
            sha256=digest.hexdigest(),
            original_filename=original_filename,
        )
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    finally:
        await upload.close()


def delete_procurement_file(settings: Settings, storage_key: str) -> None:
    try:
        procurement_path(settings, storage_key).unlink(missing_ok=True)
    except OSError:
        pass
