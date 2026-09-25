from __future__ import annotations
import hashlib, os, tempfile, uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException, UploadFile, status
from ..config import Settings
from .malware_scan import scan_path

CHUNK_SIZE = 1024 * 1024

@dataclass(frozen=True)
class StoredContractArchive:
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str
    original_filename: str

@dataclass(frozen=True)
class StagedContractArchiveDeletion:
    original_path: Path
    staged_path: Path

def contract_archive_root(settings: Settings) -> Path:
    return Path(settings.runtime_dir) / "contract_archives"

def contract_archive_path(settings: Settings, storage_key: str) -> Path:
    root = contract_archive_root(settings).resolve()
    path = (root / storage_key).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Érvénytelen szerződés-archív fájlútvonal")
    return path

def _safe_name(filename: str | None) -> str:
    name = Path(filename or "szerzodes.pdf").name.strip() or "szerzodes.pdf"
    return name[:500]

async def store_contract_pdf(upload: UploadFile, settings: Settings) -> StoredContractArchive:
    original = _safe_name(upload.filename)
    if Path(original).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Szerződéshez csak PDF fájl tölthető fel")
    root = contract_archive_root(settings); tmp = root / ".tmp"; tmp.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="upload-", dir=tmp)
    digest = hashlib.sha256(); size = 0; header = b""; limit = settings.archive_max_size_mb * 1024 * 1024
    try:
        with os.fdopen(fd, "wb") as handle:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk: break
                if len(header) < 8: header += chunk[:8-len(header)]
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"A fájl legfeljebb {settings.archive_max_size_mb} MB lehet")
                digest.update(chunk); handle.write(chunk)
            handle.flush(); os.fsync(handle.fileno())
        if size == 0: raise HTTPException(status_code=400, detail="A feltöltött fájl üres")
        if not header.startswith(b"%PDF-"):
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="A feltöltött fájl tartalma nem PDF")
        if upload.content_type and upload.content_type not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="A böngésző által jelzett fájltípus nem PDF")
        scan_path(Path(temp_name), settings)
        now = datetime.utcnow(); key = f"{now.year:04d}/{now.month:02d}/{uuid.uuid4().hex}.pdf"
        target = contract_archive_path(settings, key); target.parent.mkdir(parents=True, exist_ok=True); os.replace(temp_name, target)
        return StoredContractArchive(key, "application/pdf", size, digest.hexdigest(), original)
    except Exception:
        try: os.unlink(temp_name)
        except OSError: pass
        raise
    finally:
        await upload.close()

def stage_contract_archive_deletion(settings: Settings, storage_key: str) -> StagedContractArchiveDeletion | None:
    original = contract_archive_path(settings, storage_key)
    if not original.is_file(): return None
    trash = contract_archive_root(settings) / ".trash"; trash.mkdir(parents=True, exist_ok=True)
    staged = trash / f"{uuid.uuid4().hex}-{original.name}"; os.replace(original, staged)
    return StagedContractArchiveDeletion(original, staged)

def rollback_contract_archive_deletion(staged):
    if staged is None or not staged.staged_path.exists(): return
    staged.original_path.parent.mkdir(parents=True, exist_ok=True); os.replace(staged.staged_path, staged.original_path)

def finalize_contract_archive_deletion(staged):
    if staged is not None: staged.staged_path.unlink(missing_ok=True)

def delete_contract_archive_file(settings: Settings, storage_key: str):
    try: contract_archive_path(settings, storage_key).unlink(missing_ok=True)
    except OSError: pass
