from __future__ import annotations

import hashlib
import io
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import Settings
from .malware_scan import scan_bytes

JPEG_SIGNATURE = b"\xff\xd8\xff"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class StoredWorkOrderPhoto:
    storage_key: str
    sha256: str
    size_bytes: int
    mime_type: str
    width: int
    height: int


def photo_root(settings: Settings) -> Path:
    configured = settings.mobile_photo_dir.strip()
    return Path(configured) if configured else Path(settings.runtime_dir) / "work_order_photos"


def photo_path(settings: Settings, storage_key: str) -> Path:
    root = photo_root(settings).resolve()
    path = (root / storage_key).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Érvénytelen munkalap-fénykép tárhelyútvonal")
    return path


def _safe_original_filename(value: str | None) -> str | None:
    if not value:
        return None
    name = Path(value).name.replace("\x00", "").strip()
    return name[:255] or None


async def sanitize_and_store_work_order_photo(upload: UploadFile, settings: Settings) -> tuple[StoredWorkOrderPhoto, str | None]:
    max_bytes = settings.mobile_photo_max_size_mb * 1024 * 1024
    raw = await upload.read(max_bytes + 1)
    original = _safe_original_filename(upload.filename)
    await upload.close()
    if not raw:
        raise HTTPException(status_code=400, detail="A fénykép üres")
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail=f"A fénykép legfeljebb {settings.mobile_photo_max_size_mb} MB lehet")
    if not (raw.startswith(JPEG_SIGNATURE) or raw.startswith(PNG_SIGNATURE)):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Csak JPEG vagy PNG fénykép tölthető fel")
    scan_bytes(raw, settings)

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            width, height = probe.size
            if width < 64 or height < 64 or width * height > settings.mobile_photo_max_pixels:
                raise HTTPException(status_code=400, detail="A fénykép felbontása érvénytelen vagy túl nagy")
            probe.verify()
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            max_dim = settings.mobile_photo_max_dimension
            if max(image.size) > max_dim:
                image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            # A szerver újrakódolja a képet: EXIF/GPS és egyéb metaadat nem marad meg.
            image.save(output, format="JPEG", quality=85, optimize=True, progressive=True)
            sanitized = output.getvalue()
            width, height = image.size
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="A feltöltött fénykép sérült vagy érvénytelen") from exc

    scan_bytes(sanitized, settings)
    now = datetime.utcnow()
    storage_key = f"{now.year:04d}/{now.month:02d}/{uuid.uuid4().hex}.jpg"
    target = photo_path(settings, storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="photo-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(sanitized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        try:
            os.chmod(target, 0o440)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return StoredWorkOrderPhoto(
        storage_key=storage_key,
        sha256=hashlib.sha256(sanitized).hexdigest(),
        size_bytes=len(sanitized),
        mime_type="image/jpeg",
        width=width,
        height=height,
    ), original


def remove_work_order_photo(settings: Settings, storage_key: str) -> None:
    try:
        path = photo_path(settings, storage_key)
        if path.is_file():
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            path.unlink()
    except (OSError, ValueError):
        pass
