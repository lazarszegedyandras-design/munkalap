from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from ..config import Settings
from .malware_scan import scan_path

CHUNK_SIZE = 1024 * 1024
ALLOWED_FILE_TYPES = {
    "application/pdf": (".pdf", (b"%PDF-",)),
    "image/jpeg": (".jpg", (b"\xff\xd8\xff",)),
    "image/png": (".png", (b"\x89PNG\r\n\x1a\n",)),
}
EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


@dataclass(frozen=True)
class StoredArchiveFile:
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str
    original_filename: str


def archive_root(settings: Settings) -> Path:
    configured = settings.archive_dir.strip()
    return Path(configured) if configured else Path(settings.runtime_dir) / "work_order_archives"


def archive_path(settings: Settings, storage_key: str) -> Path:
    root = archive_root(settings).resolve()
    path = (root / storage_key).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Érvénytelen archív fájlútvonal")
    return path


def _safe_original_filename(filename: str | None) -> str:
    name = Path(filename or "munkalap").name.strip()
    if not name:
        name = "munkalap"
    return name[:500]


def _determine_type(filename: str, declared_type: str | None, header: bytes) -> tuple[str, str]:
    extension = Path(filename).suffix.lower()
    mime_type = EXTENSION_TO_MIME.get(extension)
    if not mime_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Csak PDF, JPG vagy PNG kiterjesztésű fájl archiválható",
        )
    canonical_extension, signatures = ALLOWED_FILE_TYPES[mime_type]
    if not any(header.startswith(signature) for signature in signatures):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="A fájl tartalma nem egyezik a megadott fájltípussal",
        )
    if declared_type in ALLOWED_FILE_TYPES and declared_type != mime_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="A fájl kiterjesztése és böngésző által jelzett típusa eltér",
        )
    return mime_type, canonical_extension


async def store_archive_upload(upload: UploadFile, settings: Settings) -> StoredArchiveFile:
    original_filename = _safe_original_filename(upload.filename)
    root = archive_root(settings)
    temp_dir = root / ".tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="upload-", dir=temp_dir)
    size = 0
    digest = hashlib.sha256()
    header = b""
    max_size = settings.archive_max_size_mb * 1024 * 1024
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
                        detail=f"A fájl legfeljebb {settings.archive_max_size_mb} MB lehet",
                    )
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if size == 0:
            raise HTTPException(status_code=400, detail="A feltöltött fájl üres")
        mime_type, extension = _determine_type(original_filename, upload.content_type, header)
        scan_path(Path(temp_name), settings)
        now = datetime.utcnow()
        storage_key = f"{now.year:04d}/{now.month:02d}/{uuid.uuid4().hex}{extension}"
        target = archive_path(settings, storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_name, target)
        return StoredArchiveFile(
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


@dataclass(frozen=True)
class StagedArchiveDeletion:
    original_path: Path
    staged_path: Path


def stage_archive_file_deletion(settings: Settings, storage_key: str) -> StagedArchiveDeletion | None:
    original = archive_path(settings, storage_key)
    if not original.is_file():
        return None
    trash_dir = archive_root(settings) / ".trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    staged = trash_dir / f"{uuid.uuid4().hex}-{original.name}"
    os.replace(original, staged)
    return StagedArchiveDeletion(original_path=original, staged_path=staged)


def rollback_archive_file_deletion(staged: StagedArchiveDeletion | None) -> None:
    if staged is None or not staged.staged_path.exists():
        return
    staged.original_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged.staged_path, staged.original_path)


def finalize_archive_file_deletion(staged: StagedArchiveDeletion | None) -> None:
    if staged is None:
        return
    staged.staged_path.unlink(missing_ok=True)


def delete_archive_file(settings: Settings, storage_key: str) -> None:
    try:
        archive_path(settings, storage_key).unlink(missing_ok=True)
    except OSError:
        pass
