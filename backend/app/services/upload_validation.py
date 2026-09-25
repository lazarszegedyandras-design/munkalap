from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from ..config import Settings
from .malware_scan import scan_bytes

EXCEL_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
    "application/octet-stream",
    "",
}


def validate_safe_zip(archive: zipfile.ZipFile, *, max_files: int = 5000, max_uncompressed_bytes: int = 200 * 1024 * 1024) -> None:
    infos = archive.infolist()
    if len(infos) > max_files:
        raise HTTPException(status_code=415, detail="A tömörített dokumentum túl sok belső fájlt tartalmaz")
    total = sum(max(0, info.file_size) for info in infos)
    if total > max_uncompressed_bytes:
        raise HTTPException(status_code=415, detail="A tömörített dokumentum kibontott mérete túl nagy")
    for info in infos:
        normalized = Path(info.filename)
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        is_symlink = (unix_mode & 0o170000) == 0o120000
        if (
            normalized.is_absolute()
            or ".." in normalized.parts
            or "\\" in info.filename
            or ":" in info.filename
            or is_symlink
        ):
            raise HTTPException(status_code=415, detail="A tömörített dokumentum érvénytelen belső fájlnevet tartalmaz")
        if info.compress_size > 0 and info.file_size > 10 * 1024 * 1024 and info.file_size / info.compress_size > 200:
            raise HTTPException(status_code=415, detail="A tömörített dokumentum gyanús tömörítési arányt tartalmaz")


def validate_xlsx_bytes(payload: bytes, filename: str | None, declared_type: str | None) -> None:
    name = Path(filename or "import.xlsx").name
    if Path(name).suffix.lower() != ".xlsx":
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Csak XLSX fájl tölthető fel")
    declared = (declared_type or "").split(";", 1)[0].strip().lower()
    if declared not in EXCEL_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="A fájl MIME típusa nem XLSX")
    if not payload.startswith(b"PK"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="A fájl tartalma nem érvényes XLSX")
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            validate_safe_zip(archive)
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or not any(name.startswith("xl/") for name in names):
                raise HTTPException(status_code=415, detail="A fájl tartalma nem érvényes XLSX")
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=415, detail="A fájl tartalma nem érvényes XLSX") from exc


async def read_excel_upload(upload: UploadFile, settings: Settings) -> bytes:
    max_bytes = settings.import_max_size_mb * 1024 * 1024
    payload = await upload.read(max_bytes + 1)
    await upload.close()
    if len(payload) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Az importfájl legfeljebb {settings.import_max_size_mb} MB lehet")
    if not payload:
        raise HTTPException(status_code=400, detail="A feltöltött importfájl üres")
    validate_xlsx_bytes(payload, upload.filename, upload.content_type)
    scan_bytes(payload, settings)
    return payload
