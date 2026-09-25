from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from fastapi.responses import FileResponse
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from ..config import get_settings
from ..database import get_db
from ..deps import RequireAdmin, RequireOfficeOrAdmin, get_current_user
from ..models import Asset, User, WorkOrder, WorkOrderArchive, WorkOrderArchiveAsset, WorkOrderAsset
from ..services.asset_display import asset_display_name, visible_internal_id
from ..services.audit import add_asset_history, add_audit_log
from ..services.work_order_archive_numbers import next_work_order_archive_number
from ..services.work_order_archive_storage import (
    archive_path,
    delete_archive_file,
    finalize_archive_file_deletion,
    rollback_archive_file_deletion,
    stage_archive_file_deletion,
    store_archive_upload,
)

router = APIRouter(tags=["work_order_archives"])


class ArchiveDeleteConfirmation(BaseModel):
    confirmation: str


def archive_query(db: Session):
    return db.query(WorkOrderArchive).options(
        joinedload(WorkOrderArchive.work_order),
        joinedload(WorkOrderArchive.uploaded_by),
        selectinload(WorkOrderArchive.asset_links).joinedload(WorkOrderArchiveAsset.asset),
    )


def archive_to_dict(archive: WorkOrderArchive) -> dict:
    return {
        "id": archive.id,
        "archive_number": archive.archive_number,
        "work_order_id": archive.work_order_id,
        "work_order_number": archive.work_order.number if archive.work_order else None,
        "source_number": archive.source_number,
        "work_date": archive.work_date,
        "note": archive.note,
        "original_filename": archive.original_filename,
        "mime_type": archive.mime_type,
        "size_bytes": archive.size_bytes,
        "sha256": archive.sha256,
        "uploaded_by_user_id": archive.uploaded_by_user_id,
        "uploaded_by_name": archive.uploaded_by.full_name if archive.uploaded_by else None,
        "created_at": archive.created_at,
        "assets": [
            {
                "id": link.asset.id,
                "internal_id": visible_internal_id(link.asset.internal_id),
                "display_name": asset_display_name(link.asset),
                "serial_number": link.asset.serial_number,
                "company_code": link.asset.company_code,
            }
            for link in archive.asset_links
        ],
        "asset_ids": [link.asset_id for link in archive.asset_links],
    }


def _clean_optional(value: str | None, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_length] if max_length else cleaned


async def _create_archive(
    *,
    db: Session,
    current_user: User,
    upload: UploadFile,
    assets: list[Asset],
    work_order: WorkOrder | None,
    source_number: str | None,
    work_date: date | None,
    note: str | None,
) -> dict:
    settings = get_settings()
    stored = await store_archive_upload(upload, settings)
    archive = WorkOrderArchive(
        archive_number=next_work_order_archive_number(db),
        work_order_id=work_order.id if work_order else None,
        source_number=_clean_optional(source_number, 100),
        work_date=work_date,
        note=_clean_optional(note),
        original_filename=stored.original_filename,
        storage_key=stored.storage_key,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        uploaded_by_user_id=current_user.id,
    )
    try:
        db.add(archive)
        db.flush()
        for asset in assets:
            archive.asset_links.append(WorkOrderArchiveAsset(asset_id=asset.id))
            add_asset_history(
                db,
                asset.id,
                current_user,
                "archív munkalap feltöltve",
                f"{archive.archive_number} – {stored.original_filename}",
                work_order.id if work_order else None,
            )
        add_audit_log(
            db,
            current_user,
            "feltöltés",
            "work_order_archive",
            archive.id,
            f"{archive.archive_number} archív munkalap feltöltve ({stored.original_filename})",
        )
        if work_order:
            add_audit_log(
                db,
                current_user,
                "archiválás",
                "work_order",
                work_order.id,
                f"Archív fájl csatolva: {archive.archive_number} ({stored.original_filename})",
            )
        db.commit()
    except Exception:
        db.rollback()
        delete_archive_file(settings, stored.storage_key)
        raise
    created = archive_query(db).filter(WorkOrderArchive.id == archive.id).first()
    return archive_to_dict(created)


@router.post("/work-orders/{work_order_id}/archives", status_code=status.HTTP_201_CREATED)
async def upload_work_order_archive(
    work_order_id: int,
    archive_file: UploadFile = File(...),
    source_number: str | None = Form(default=None),
    work_date: date | None = Form(default=None),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    work_order = (
        db.query(WorkOrder)
        .options(selectinload(WorkOrder.asset_links).joinedload(WorkOrderAsset.asset))
        .filter(WorkOrder.id == work_order_id)
        .first()
    )
    if not work_order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    assets = [link.asset for link in work_order.asset_links if link.asset]
    effective_source_number = _clean_optional(source_number, 100) or work_order.number
    effective_work_date = work_date or (
        work_order.completed_at.date() if work_order.completed_at else work_order.planned_date
    )
    return await _create_archive(
        db=db,
        current_user=current_user,
        upload=archive_file,
        assets=assets,
        work_order=work_order,
        source_number=effective_source_number,
        work_date=effective_work_date,
        note=note,
    )


@router.post("/assets/{asset_id}/work-order-archives", status_code=status.HTTP_201_CREATED)
async def upload_asset_work_order_archive(
    asset_id: int,
    archive_file: UploadFile = File(...),
    source_number: str | None = Form(default=None),
    work_date: date | None = Form(default=None),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Eszköz nem található")
    return await _create_archive(
        db=db,
        current_user=current_user,
        upload=archive_file,
        assets=[asset],
        work_order=None,
        source_number=source_number,
        work_date=work_date,
        note=note,
    )


@router.post("/work-order-archives", status_code=status.HTTP_201_CREATED)
async def upload_global_work_order_archive(
    archive_file: UploadFile = File(...),
    asset_id: int = Form(...),
    work_order_id: int | None = Form(default=None),
    source_number: str | None = Form(default=None),
    work_date: date | None = Form(default=None),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Eszköz nem található")

    work_order = None
    assets = [asset]
    effective_source_number = _clean_optional(source_number, 100)
    effective_work_date = work_date
    if work_order_id is not None:
        work_order = (
            db.query(WorkOrder)
            .options(selectinload(WorkOrder.asset_links).joinedload(WorkOrderAsset.asset))
            .filter(WorkOrder.id == work_order_id)
            .first()
        )
        if not work_order:
            raise HTTPException(status_code=404, detail="Munkalap nem található")
        work_order_assets = [link.asset for link in work_order.asset_links if link.asset]
        if asset.id not in {row.id for row in work_order_assets}:
            raise HTTPException(status_code=400, detail="A kiválasztott munkalap nem kapcsolódik a kiválasztott eszközhöz")
        assets = work_order_assets
        effective_source_number = effective_source_number or work_order.number
        effective_work_date = effective_work_date or (
            work_order.completed_at.date() if work_order.completed_at else work_order.planned_date
        )

    return await _create_archive(
        db=db,
        current_user=current_user,
        upload=archive_file,
        assets=assets,
        work_order=work_order,
        source_number=effective_source_number,
        work_date=effective_work_date,
        note=note,
    )


@router.get("/work-orders/{work_order_id}/archives")
def list_work_order_archives(
    work_order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not db.get(WorkOrder, work_order_id):
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    rows = archive_query(db).filter(WorkOrderArchive.work_order_id == work_order_id).order_by(WorkOrderArchive.created_at.desc()).all()
    return [archive_to_dict(row) for row in rows]


@router.get("/assets/{asset_id}/work-order-archives")
def list_asset_work_order_archives(
    asset_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not db.get(Asset, asset_id):
        raise HTTPException(status_code=404, detail="Eszköz nem található")
    rows = (
        archive_query(db)
        .join(WorkOrderArchiveAsset, WorkOrderArchiveAsset.archive_id == WorkOrderArchive.id)
        .filter(WorkOrderArchiveAsset.asset_id == asset_id)
        .order_by(WorkOrderArchive.created_at.desc())
        .all()
    )
    return [archive_to_dict(row) for row in rows]


@router.get("/work-order-archives/paged")
def list_archives_paged(
    q: str | None = None,
    asset_id: int | None = None,
    work_order_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = (
        archive_query(db)
        .outerjoin(WorkOrder, WorkOrderArchive.work_order_id == WorkOrder.id)
        .outerjoin(WorkOrderArchiveAsset, WorkOrderArchiveAsset.archive_id == WorkOrderArchive.id)
        .outerjoin(Asset, WorkOrderArchiveAsset.asset_id == Asset.id)
    )
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                WorkOrderArchive.archive_number.ilike(like),
                WorkOrderArchive.source_number.ilike(like),
                WorkOrderArchive.original_filename.ilike(like),
                WorkOrderArchive.note.ilike(like),
                WorkOrder.number.ilike(like),
                Asset.internal_id.ilike(like),
                Asset.serial_number.ilike(like),
                Asset.company_code.ilike(like),
            )
        )
    if asset_id:
        query = query.filter(WorkOrderArchiveAsset.asset_id == asset_id)
    if work_order_id:
        query = query.filter(WorkOrderArchive.work_order_id == work_order_id)
    if date_from:
        query = query.filter(WorkOrderArchive.work_date >= date_from)
    if date_to:
        query = query.filter(WorkOrderArchive.work_date <= date_to)

    query = query.distinct()
    total = query.count()
    sort_columns = {
        "archive_number": WorkOrderArchive.archive_number,
        "source_number": WorkOrderArchive.source_number,
        "work_date": WorkOrderArchive.work_date,
        "original_filename": WorkOrderArchive.original_filename,
        "created_at": WorkOrderArchive.created_at,
    }
    sort_column = sort_columns.get(sort, WorkOrderArchive.created_at)
    order_by = asc(sort_column) if order == "asc" else desc(sort_column)
    rows = query.order_by(order_by, WorkOrderArchive.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    pages = max(1, (total + page_size - 1) // page_size)
    normalized_page = min(page, pages)
    if normalized_page != page:
        rows = query.order_by(order_by, WorkOrderArchive.id.desc()).offset((normalized_page - 1) * page_size).limit(page_size).all()
    return {
        "items": [archive_to_dict(row) for row in rows],
        "page": normalized_page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
        "sort": sort if sort in sort_columns else "created_at",
        "order": order,
    }


@router.get("/work-order-archives/{archive_id}")
def get_archive(
    archive_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    archive = archive_query(db).filter(WorkOrderArchive.id == archive_id).first()
    if not archive:
        raise HTTPException(status_code=404, detail="Archív munkalap nem található")
    return archive_to_dict(archive)


@router.get("/work-order-archives/{archive_id}/preview")
def preview_archive(
    archive_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    archive = archive_query(db).filter(WorkOrderArchive.id == archive_id).first()
    if not archive:
        raise HTTPException(status_code=404, detail="Archív munkalap nem található")
    path = archive_path(get_settings(), archive.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Az archív fájl hiányzik a tárhelyről")
    add_audit_log(
        db,
        current_user,
        "előnézet",
        "work_order_archive",
        archive.id,
        f"{archive.archive_number} előnézete megnyitva",
    )
    db.commit()
    return FileResponse(
        path=path,
        media_type=archive.mime_type,
        filename=archive.original_filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/work-order-archives/{archive_id}/download")
def download_archive(
    archive_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    archive = archive_query(db).filter(WorkOrderArchive.id == archive_id).first()
    if not archive:
        raise HTTPException(status_code=404, detail="Archív munkalap nem található")
    path = archive_path(get_settings(), archive.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Az archív fájl hiányzik a tárhelyről")
    add_audit_log(
        db,
        current_user,
        "letöltés",
        "work_order_archive",
        archive.id,
        f"{archive.archive_number} letöltve",
    )
    db.commit()
    return FileResponse(
        path=path,
        media_type=archive.mime_type,
        filename=archive.original_filename,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/work-order-archives/{archive_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_archive(
    archive_id: int,
    payload: ArchiveDeleteConfirmation,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    if payload.confirmation.strip() != "TÖRÖL":
        raise HTTPException(status_code=400, detail="A törléshez pontosan a TÖRÖL szót kell megadni")

    archive = archive_query(db).filter(WorkOrderArchive.id == archive_id).first()
    if not archive:
        raise HTTPException(status_code=404, detail="Archív munkalap nem található")

    settings = get_settings()
    staged_file = None
    try:
        staged_file = stage_archive_file_deletion(settings, archive.storage_key)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Az archív fájl nem helyezhető törlésre") from exc

    archive_number = archive.archive_number
    original_filename = archive.original_filename
    work_order_id = archive.work_order_id
    linked_assets = [link.asset for link in archive.asset_links if link.asset]

    try:
        for asset in linked_assets:
            add_asset_history(
                db,
                asset.id,
                current_user,
                "archív munkalap törölve",
                f"{archive_number} – {original_filename}",
                work_order_id,
            )
        add_audit_log(
            db,
            current_user,
            "törlés",
            "work_order_archive",
            archive.id,
            f"{archive_number} archív munkalap és fájl törölve ({original_filename})",
        )
        if work_order_id:
            add_audit_log(
                db,
                current_user,
                "archívum törlése",
                "work_order",
                work_order_id,
                f"Archív fájl törölve: {archive_number} ({original_filename})",
            )
        db.delete(archive)
        db.commit()
    except Exception:
        db.rollback()
        try:
            rollback_archive_file_deletion(staged_file)
        except OSError:
            pass
        raise

    try:
        finalize_archive_file_deletion(staged_file)
    except OSError:
        # Az adatbázisból már törölt rekordhoz tartozó, .trash alatti maradvány
        # biztonságosabb, mint a visszaállíthatatlan féltranzakció.
        pass
    return None
