from __future__ import annotations

from datetime import date, datetime, time
from math import ceil

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from ..access_control import PERMISSION_PROCUREMENT_APPROVE
from ..config import get_settings
from ..database import get_db
from ..deps import RequireProcurementApprove, get_current_user
from ..models import ProcurementAttachment, ProcurementRequest, ROLE_ADMIN, User
from ..schemas import (
    ProcurementAttachmentRead,
    ProcurementDecision,
    ProcurementRequestCreate,
    ProcurementRequestPage,
    ProcurementRequestRead,
    ProcurementRequestUpdate,
    ProcurementWithdraw,
)
from ..services.audit import add_audit_log, snapshot_entity
from ..services.notifications import create_notification
from ..services.procurement_numbers import next_procurement_request_number
from ..services.procurement_storage import delete_procurement_file, procurement_path, store_procurement_upload

router = APIRouter(prefix="/procurement", tags=["procurement"])

VALID_STATUSES = {"pending", "approved", "rejected", "withdrawn"}


def _can_approve(user: User) -> bool:
    return user.role.name == ROLE_ADMIN or PERMISSION_PROCUREMENT_APPROVE in user.permissions


def _request_query(db: Session):
    return db.query(ProcurementRequest).options(
        joinedload(ProcurementRequest.requester),
        joinedload(ProcurementRequest.approver),
        selectinload(ProcurementRequest.attachments),
    )


def _request_snapshot(row: ProcurementRequest) -> dict:
    data = snapshot_entity(row) or {}
    data["requester_name"] = row.requester.full_name if row.requester else None
    data["approver_name"] = row.approver.full_name if row.approver else None
    return data


def _validate_status_filter(value: str | None) -> str | None:
    if not value:
        return None
    if value not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Érvénytelen beszerzési státusz")
    return value


def _apply_filters(query, *, request_status: str | None, search: str | None, date_from: date | None, date_to: date | None):
    if request_status:
        query = query.filter(ProcurementRequest.status == request_status)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.join(ProcurementRequest.requester).filter(or_(
            ProcurementRequest.request_number.ilike(pattern),
            ProcurementRequest.subject.ilike(pattern),
            ProcurementRequest.purpose.ilike(pattern),
            User.full_name.ilike(pattern),
        ))
    if date_from:
        query = query.filter(ProcurementRequest.submitted_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(ProcurementRequest.submitted_at <= datetime.combine(date_to, time.max))
    return query


def _notify_approvers(db: Session, row: ProcurementRequest) -> None:
    users = db.query(User).options(joinedload(User.role), selectinload(User.permission_links)).filter(User.is_active.is_(True)).all()
    for user in users:
        if user.id == row.requester_user_id or not _can_approve(user):
            continue
        create_notification(
            db,
            user_id=user.id,
            module="procurement",
            notification_type="procurement_approval_pending",
            title="Új beszerzési igény",
            message=f"{row.requester.full_name}: {row.subject} – {row.total_amount} {row.currency}",
            link=f"/procurement/requests/{row.id}",
            source_type="procurement_request",
            source_id=row.id,
            dedupe_key=f"procurement:request:{row.id}:pending",
        )


def _notify_requester_decision(db: Session, row: ProcurementRequest) -> None:
    label = "jóváhagyva" if row.status == "approved" else "elutasítva"
    create_notification(
        db,
        user_id=row.requester_user_id,
        module="procurement",
        notification_type=f"procurement_{row.status}",
        title=f"Beszerzési igény {label}",
        message=f"{row.request_number} – {row.subject}",
        link=f"/procurement/requests/{row.id}",
        source_type="procurement_request",
        source_id=row.id,
        dedupe_key=f"procurement:request:{row.id}:{row.status}:{row.version}",
    )


def _load_visible_request(db: Session, request_id: int, current_user: User) -> ProcurementRequest:
    row = _request_query(db).filter(ProcurementRequest.id == request_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Beszerzési igény nem található")
    if row.requester_user_id != current_user.id and not _can_approve(current_user):
        raise HTTPException(status_code=403, detail="Nincs jogosultság a beszerzési igény megtekintéséhez")
    return row


@router.post("/requests", response_model=ProcurementRequestRead, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: ProcurementRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    row = ProcurementRequest(
        request_number=next_procurement_request_number(db, now=now),
        requester_user_id=current_user.id,
        requester=current_user,
        subject=payload.subject,
        purpose=payload.purpose,
        description=payload.description,
        total_amount=payload.total_amount,
        currency=payload.currency,
        status="pending",
        submitted_at=now,
    )
    db.add(row)
    db.flush()
    row = _request_query(db).filter(ProcurementRequest.id == row.id).one()
    add_audit_log(
        db,
        current_user,
        "PROCUREMENT_REQUEST_CREATED",
        "procurement_request",
        row.id,
        f"Beszerzési igény létrehozva: {row.request_number}",
        entity_display_id=row.request_number,
        before=None,
        after=_request_snapshot(row),
    )
    _notify_approvers(db, row)
    db.commit()
    return row


@router.get("/requests", response_model=ProcurementRequestPage)
def list_own_requests(
    request_status: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=255),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request_status = _validate_status_filter(request_status)
    query = _request_query(db).filter(ProcurementRequest.requester_user_id == current_user.id)
    query = _apply_filters(query, request_status=request_status, search=search, date_from=date_from, date_to=date_to)
    total = query.order_by(None).count()
    items = query.order_by(ProcurementRequest.submitted_at.desc(), ProcurementRequest.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "page": page, "page_size": page_size, "total": total, "pages": max(1, ceil(total / page_size))}


@router.get("/requests/{request_id}", response_model=ProcurementRequestRead)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _load_visible_request(db, request_id, current_user)


@router.patch("/requests/{request_id}", response_model=ProcurementRequestRead)
def update_request(
    request_id: int,
    payload: ProcurementRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _request_query(db).filter(
        ProcurementRequest.id == request_id,
        ProcurementRequest.requester_user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Saját beszerzési igény nem található")
    if row.version != payload.version:
        raise HTTPException(status_code=409, detail="A beszerzési igény időközben módosult; frissítsd az oldalt")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Csak jóváhagyásra váró beszerzési igény módosítható")

    before = _request_snapshot(row)
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    for field, value in data.items():
        setattr(row, field, value)
    row.version += 1
    db.flush()
    add_audit_log(
        db, current_user, "PROCUREMENT_REQUEST_UPDATED", "procurement_request", row.id,
        f"Beszerzési igény módosítva: {row.request_number}", entity_display_id=row.request_number,
        before=before, after=_request_snapshot(row),
    )
    db.commit()
    return row


@router.post("/requests/{request_id}/withdraw", response_model=ProcurementRequestRead)
def withdraw_request(
    request_id: int,
    payload: ProcurementWithdraw,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _request_query(db).filter(
        ProcurementRequest.id == request_id,
        ProcurementRequest.requester_user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Saját beszerzési igény nem található")
    if row.version != payload.version:
        raise HTTPException(status_code=409, detail="A beszerzési igény időközben módosult; frissítsd az oldalt")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Csak jóváhagyásra váró beszerzési igény vonható vissza")

    before = _request_snapshot(row)
    row.status = "withdrawn"
    row.withdrawn_at = datetime.utcnow()
    row.version += 1
    add_audit_log(
        db, current_user, "PROCUREMENT_REQUEST_WITHDRAWN", "procurement_request", row.id,
        f"Beszerzési igény visszavonva: {row.request_number}", entity_display_id=row.request_number,
        before=before, after=_request_snapshot(row),
    )
    db.commit()
    return row


@router.post("/requests/{request_id}/attachments", response_model=list[ProcurementAttachmentRead], status_code=status.HTTP_201_CREATED)
async def upload_attachments(
    request_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _request_query(db).filter(
        ProcurementRequest.id == request_id,
        ProcurementRequest.requester_user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Saját beszerzési igény nem található")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Csak jóváhagyásra váró igényhez tölthető fel csatolmány")
    if not files:
        raise HTTPException(status_code=400, detail="Nincs feltöltendő fájl")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Egyszerre legfeljebb 20 fájl tölthető fel")

    settings = get_settings()
    created: list[ProcurementAttachment] = []
    stored_keys: list[str] = []
    try:
        for upload in files:
            stored = await store_procurement_upload(upload, settings)
            stored_keys.append(stored.storage_key)
            attachment = ProcurementAttachment(
                procurement_request_id=row.id,
                original_filename=stored.original_filename,
                storage_key=stored.storage_key,
                mime_type=stored.mime_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
                uploaded_by_user_id=current_user.id,
            )
            db.add(attachment)
            db.flush()
            created.append(attachment)
            add_audit_log(
                db, current_user, "PROCUREMENT_ATTACHMENT_UPLOADED", "procurement_attachment", attachment.id,
                f"Beszerzési csatolmány feltöltve: {stored.original_filename}",
                entity_display_id=stored.original_filename,
                before=None,
                after=snapshot_entity(attachment),
            )
        row.version += 1
        db.commit()
        return created
    except Exception:
        db.rollback()
        for storage_key in stored_keys:
            delete_procurement_file(settings, storage_key)
        raise


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = db.query(ProcurementAttachment).options(joinedload(ProcurementAttachment.request)).filter(ProcurementAttachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Csatolmány nem található")
    if attachment.request.requester_user_id != current_user.id and not _can_approve(current_user):
        raise HTTPException(status_code=403, detail="Nincs jogosultság a csatolmány letöltéséhez")

    settings = get_settings()
    path = procurement_path(settings, attachment.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="A csatolt fájl nem található a tárhelyen")
    add_audit_log(
        db, current_user, "PROCUREMENT_ATTACHMENT_DOWNLOADED", "procurement_attachment", attachment.id,
        f"Beszerzési csatolmány letöltve: {attachment.original_filename}", entity_display_id=attachment.original_filename,
        before=None, after=snapshot_entity(attachment),
    )
    db.commit()
    return FileResponse(path, media_type=attachment.mime_type, filename=attachment.original_filename, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/approvals", response_model=ProcurementRequestPage)
def list_approvals(
    request_status: str | None = Query(default="pending", alias="status"),
    search: str | None = Query(default=None, max_length=255),
    requester_user_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(RequireProcurementApprove),
):
    request_status = _validate_status_filter(request_status)
    query = _request_query(db)
    if requester_user_id:
        query = query.filter(ProcurementRequest.requester_user_id == requester_user_id)
    query = _apply_filters(query, request_status=request_status, search=search, date_from=date_from, date_to=date_to)
    total = query.order_by(None).count()
    pending_first = (ProcurementRequest.status != "pending").asc()
    items = query.order_by(pending_first, ProcurementRequest.submitted_at.desc(), ProcurementRequest.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "page": page, "page_size": page_size, "total": total, "pages": max(1, ceil(total / page_size))}


def _decide_request(db: Session, current_user: User, request_id: int, payload: ProcurementDecision, decision: str) -> ProcurementRequest:
    # A döntési tranzakció csak a beszerzési rekordot zárolja. Eager JOIN mellett
    # a PostgreSQL FOR UPDATE nullable kapcsolatoknál hibázhatna.
    query = db.query(ProcurementRequest).filter(ProcurementRequest.id == request_id)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Beszerzési igény nem található")
    if row.requester_user_id == current_user.id:
        raise HTTPException(status_code=403, detail="Saját beszerzési igény nem hagyható jóvá vagy utasítható el.")
    if row.version != payload.version:
        raise HTTPException(status_code=409, detail="A beszerzési igény időközben módosult; frissítsd az oldalt")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="A beszerzési igényt időközben már elbírálták.")
    comment = (payload.comment or "").strip() or None
    if decision == "rejected" and not comment:
        raise HTTPException(status_code=422, detail="Elutasításkor a jóváhagyói megjegyzés kötelező")

    before = _request_snapshot(row)
    row.status = decision
    row.approved_by_user_id = current_user.id
    row.approver = current_user
    row.approver_comment = comment
    row.decided_at = datetime.utcnow()
    row.version += 1
    db.flush()
    action = "PROCUREMENT_REQUEST_APPROVED" if decision == "approved" else "PROCUREMENT_REQUEST_REJECTED"
    description = "Beszerzési igény jóváhagyva" if decision == "approved" else "Beszerzési igény elutasítva"
    add_audit_log(
        db, current_user, action, "procurement_request", row.id,
        f"{description}: {row.request_number}", entity_display_id=row.request_number,
        before=before, after=_request_snapshot(row),
    )
    _notify_requester_decision(db, row)
    db.commit()
    return row


@router.post("/requests/{request_id}/approve", response_model=ProcurementRequestRead)
def approve_request(
    request_id: int,
    payload: ProcurementDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireProcurementApprove),
):
    return _decide_request(db, current_user, request_id, payload, "approved")


@router.post("/requests/{request_id}/reject", response_model=ProcurementRequestRead)
def reject_request(
    request_id: int,
    payload: ProcurementDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireProcurementApprove),
):
    return _decide_request(db, current_user, request_id, payload, "rejected")
