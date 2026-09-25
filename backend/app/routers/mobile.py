from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from ..access_control import PERMISSION_SERVICE_ACCESS
from ..config import get_settings
from ..database import get_db
from ..mobile_deps import MobilePrincipal, get_mobile_principal
from ..models import (
    Asset,
    Material,
    MobileDevice,
    MobileSession,
    ROLE_ADMIN,
    ROLE_TECHNICIAN,
    User,
    WorkOrder,
    WorkOrderCompletionSnapshot,
    WorkOrderSignature,
    WorkOrderPhoto,
    WORK_ORDER_PHOTO_CATEGORIES,
)
from ..request_context import get_audit_request_context
from ..schemas import (
    MobileAuthRead,
    MobileCompletionSnapshotRead,
    MobileDeviceRead,
    MobileLoginRequest,
    MobileMeterReadingCreate,
    MobileMfaVerifyRequest,
    MobilePushTokenUpdate,
    MobileRefreshRequest,
    MobileSignatureRead,
    MobileWorkOrderComplete,
    MobileWorkOrderStart,
    MobileWorkOrderPhotoRead,
)
from ..security import create_mfa_challenge_token, decode_mfa_challenge, verify_password_with_dummy
from ..services.audit import AUDIT_RESULT_FAILURE, AUDIT_SEVERITY_WARNING, add_audit_log
from ..services.auth_security import (
    clear_login_user_bucket,
    mfa_required_for_user,
    record_login_failure,
    require_not_rate_limited,
    verify_mfa_code,
)
from ..services.push_notifications import clear_push_token, register_push_token
from ..services.mobile_auth import (
    create_mobile_session,
    register_or_reactivate_device,
    revoke_mobile_device,
    revoke_mobile_session,
    rotate_mobile_refresh_token,
)
from ..services.work_order_completion import create_completion_snapshot
from ..services.work_order_concurrency import CONFLICT_MESSAGE, commit_with_optimistic_lock, require_current_version
from ..services.work_order_photo_storage import photo_path, remove_work_order_photo, sanitize_and_store_work_order_photo
from ..services.work_order_signature_storage import (
    build_signed_work_order_pdf,
    remove_evidence_file,
    sanitize_and_store_signature_png,
    signature_path,
    store_signed_pdf,
)
from .printer_tracking import _create_meter_reading
from .work_orders import (
    base_query,
    set_materials,
    update_assets_after_maintenance_close,
    validate_time_ranges,
    work_order_to_dict,
)

router = APIRouter(prefix="/mobile", tags=["mobile"])


def _mobile_role_allowed(user: User) -> bool:
    if not user.role:
        return False
    if user.role.name == ROLE_ADMIN:
        return True
    return user.role.name == ROLE_TECHNICIAN and PERMISSION_SERVICE_ACCESS in user.permissions


def _auth_read(pair) -> MobileAuthRead:
    return MobileAuthRead(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.access_expires_in,
        refresh_expires_at=pair.refresh_expires_at,
        device_id=pair.device_id,
    )


def _load_challenge_user(db: Session, challenge_token: str) -> User:
    claims = decode_mfa_challenge(challenge_token, expected_purpose="mobile_login")
    if not claims:
        raise HTTPException(status_code=401, detail="A mobil MFA munkamenet lejárt vagy érvénytelen")
    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.email == str(claims["sub"]))
        .with_for_update()
        .one_or_none()
    )
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="A mobil MFA munkamenet lejárt vagy érvénytelen")
    return user


@router.post("/auth/login", response_model=MobileAuthRead)
def mobile_login(payload: MobileLoginRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    context = get_audit_request_context()
    email = str(payload.email).strip().lower()
    require_not_rate_limited(db, email, context.ip_address, settings)
    user = db.query(User).options(joinedload(User.role)).filter(User.email == email).one_or_none()
    verified_hash = verify_password_with_dummy(payload.password, user.password_hash if user else None)
    valid = bool(user and user.is_active and verified_hash)
    if not valid:
        record_login_failure(db, email, context.ip_address, settings)
        add_audit_log(db, user, "MOBILE_LOGIN_FAILED", "security", email, "Sikertelen mobil bejelentkezés", result=AUDIT_RESULT_FAILURE, severity=AUDIT_SEVERITY_WARNING)
        db.commit()
        raise HTTPException(status_code=401, detail="Hibás email vagy jelszó")
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="A mobil használat előtt a webes felületen jelszót kell változtatni")
    if not _mobile_role_allowed(user):
        raise HTTPException(status_code=403, detail="A mobil technikusi klienshez technikusi jogosultság szükséges")

    clear_login_user_bucket(db, email)
    if mfa_required_for_user(user, settings):
        if not user.mfa_enabled:
            add_audit_log(db, user, "MOBILE_MFA_SETUP_REQUIRED", "security", user.id, "A mobil belépés előtt webes MFA-regisztráció szükséges")
            db.commit()
            return MobileAuthRead(mfa_setup_required=True)
        challenge = create_mfa_challenge_token(user.email, "mobile_login")
        add_audit_log(db, user, "MOBILE_MFA_CHALLENGE_CREATED", "security", user.id, "Mobil MFA ellenőrzés szükséges")
        db.commit()
        return MobileAuthRead(mfa_required=True, challenge_token=challenge)

    device = register_or_reactivate_device(
        db, user,
        device_uuid=payload.device_uuid,
        device_name=payload.device_name,
        platform=payload.platform,
        app_version=payload.app_version,
    )
    pair = create_mobile_session(db, user, device, settings, mfa_verified=False)
    add_audit_log(db, user, "MOBILE_LOGIN_SUCCESS", "security", user.id, f"Sikeres mobil bejelentkezés: {device.device_name}", session_id=pair.session_id)
    db.commit()
    return _auth_read(pair)


@router.post("/auth/mfa/verify", response_model=MobileAuthRead)
def mobile_mfa_verify(payload: MobileMfaVerifyRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    context = get_audit_request_context()
    user = _load_challenge_user(db, payload.challenge_token)
    require_not_rate_limited(db, user.email, context.ip_address, settings)
    method = verify_mfa_code(user, payload.code, settings)
    if not user.mfa_enabled or method is None:
        record_login_failure(db, user.email, context.ip_address, settings)
        add_audit_log(db, user, "MOBILE_MFA_FAILED", "security", user.id, "Sikertelen mobil MFA ellenőrzés", result=AUDIT_RESULT_FAILURE, severity=AUDIT_SEVERITY_WARNING)
        db.commit()
        raise HTTPException(status_code=401, detail="Hibás vagy már felhasznált MFA/recovery kód")
    if not _mobile_role_allowed(user):
        raise HTTPException(status_code=403, detail="A mobil technikusi klienshez technikusi jogosultság szükséges")
    clear_login_user_bucket(db, user.email)
    device = register_or_reactivate_device(
        db, user,
        device_uuid=payload.device_uuid,
        device_name=payload.device_name,
        platform=payload.platform,
        app_version=payload.app_version,
    )
    pair = create_mobile_session(db, user, device, settings, mfa_verified=True)
    add_audit_log(db, user, "MOBILE_MFA_SUCCESS", "security", user.id, f"Sikeres mobil MFA ellenőrzés ({method})", session_id=pair.session_id)
    db.commit()
    return _auth_read(pair)


@router.post("/auth/refresh", response_model=MobileAuthRead)
def mobile_refresh(payload: MobileRefreshRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    try:
        user, session, pair = rotate_mobile_refresh_token(db, payload.refresh_token, settings)
    except HTTPException:
        db.commit()
        raise
    if not _mobile_role_allowed(user):
        session.revoked_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=403, detail="A mobil jogosultság megszűnt")
    add_audit_log(db, user, "MOBILE_TOKEN_REFRESH", "security", user.id, "Mobil access token megújítva", session_id=session.session_id)
    db.commit()
    return _auth_read(pair)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def mobile_logout(principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    revoke_mobile_session(db, principal.session.session_id)
    add_audit_log(db, principal.user, "MOBILE_LOGOUT", "security", principal.user.id, "Mobil munkamenet kijelentkeztetve", session_id=principal.session.session_id)
    db.commit()


@router.get("/me")
def mobile_me(principal: MobilePrincipal = Depends(get_mobile_principal)):
    return {
        "id": principal.user.id,
        "email": principal.user.email,
        "full_name": principal.user.full_name,
        "role": principal.user.role.name,
        "device_id": principal.device.id,
        "device_name": principal.device.device_name,
    }


@router.get("/config")
def mobile_config(principal: MobilePrincipal = Depends(get_mobile_principal)):
    settings = get_settings()
    return {
        "acceptance_text": settings.work_order_acceptance_text,
        "acceptance_text_version": settings.work_order_acceptance_text_version,
        "photo_max_size_mb": settings.mobile_photo_max_size_mb,
        "photo_categories": WORK_ORDER_PHOTO_CATEGORIES,
        "business_timezone": settings.business_timezone,
    }


@router.get("/devices", response_model=list[MobileDeviceRead])
def mobile_devices(principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    return db.query(MobileDevice).filter(MobileDevice.user_id == principal.user.id).order_by(MobileDevice.last_seen_at.desc()).all()


@router.put("/devices/push-token", response_model=MobileDeviceRead)
def update_current_push_token(
    payload: MobilePushTokenUpdate,
    principal: MobilePrincipal = Depends(get_mobile_principal),
    db: Session = Depends(get_db),
):
    device = db.get(MobileDevice, principal.device.id)
    if device is None or device.revoked_at is not None:
        raise HTTPException(status_code=403, detail="A mobil eszköz nem aktív")
    register_push_token(db, device, payload.token, enabled=payload.enabled)
    add_audit_log(db, principal.user, "MOBILE_PUSH_REGISTERED", "mobile_device", device.id, f"Push értesítés regisztrálva: {device.device_name}")
    db.commit()
    db.refresh(device)
    return device


@router.delete("/devices/push-token", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_push_token(
    principal: MobilePrincipal = Depends(get_mobile_principal),
    db: Session = Depends(get_db),
):
    device = db.get(MobileDevice, principal.device.id)
    if device is not None:
        clear_push_token(db, device)
        add_audit_log(db, principal.user, "MOBILE_PUSH_REMOVED", "mobile_device", device.id, f"Push értesítés kikapcsolva: {device.device_name}")
        db.commit()
    return None


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def mobile_revoke_device(device_id: int, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    if not revoke_mobile_device(db, principal.user.id, device_id):
        raise HTTPException(status_code=404, detail="Mobil eszköz nem található")
    add_audit_log(db, principal.user, "MOBILE_DEVICE_REVOKED", "security", device_id, "Mobil eszköz visszavonva")
    db.commit()


def _order_for_mobile(db: Session, order_id: int, principal: MobilePrincipal) -> WorkOrder:
    order = base_query(db).filter(WorkOrder.id == order_id).one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    if principal.user.role.name != ROLE_ADMIN and principal.user.id not in {order.technician_id, order.secondary_technician_id}:
        raise HTTPException(status_code=403, detail="A munkalap nincs hozzád rendelve")
    return order


def _signature_read(row: WorkOrderSignature | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "snapshot_id": row.snapshot_id,
        "signer_name": row.signer_name,
        "signer_role": row.signer_role,
        "signed_at": row.signed_at,
        "signature_sha256": row.signature_sha256,
        "signed_pdf_sha256": row.signed_pdf_sha256,
        "signed_pdf_size_bytes": row.signed_pdf_size_bytes,
    }


def _photo_read(row: WorkOrderPhoto) -> dict:
    return {
        "id": row.id,
        "work_order_id": row.work_order_id,
        "category": row.category,
        "note": row.note,
        "original_filename": row.original_filename,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "mime_type": row.mime_type,
        "width": row.width,
        "height": row.height,
        "created_at": row.created_at,
    }


def _snapshot_read(row: WorkOrderCompletionSnapshot | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "work_order_id": row.work_order_id,
        "revision": row.revision,
        "source_work_order_version": row.source_work_order_version,
        "snapshot_sha256": row.snapshot_sha256,
        "snapshot": row.snapshot_json,
        "created_at": row.created_at,
        "signature": _signature_read(row.signature),
    }


@router.get("/work-orders/today")
def mobile_today(
    day: str | None = Query(default=None, max_length=10),
    principal: MobilePrincipal = Depends(get_mobile_principal),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    try:
        target_day = datetime.strptime(day, "%Y-%m-%d").date() if day else datetime.now(ZoneInfo(settings.business_timezone)).date()
    except (ValueError, Exception) as exc:
        if day:
            raise HTTPException(status_code=400, detail="A nap formátuma YYYY-MM-DD legyen") from exc
        raise HTTPException(status_code=500, detail="Érvénytelen üzleti időzóna-konfiguráció") from exc
    query = base_query(db).filter(WorkOrder.planned_date == target_day, WorkOrder.status != "törölve / sztornózva")
    if principal.user.role.name != ROLE_ADMIN:
        query = query.filter(or_(WorkOrder.technician_id == principal.user.id, WorkOrder.secondary_technician_id == principal.user.id))
    orders = query.order_by(WorkOrder.planned_start_at.asc().nullslast(), WorkOrder.id.asc()).all()
    return [work_order_to_dict(row) for row in orders]


@router.get("/work-orders/{order_id}")
def mobile_work_order(order_id: int, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    order = _order_for_mobile(db, order_id, principal)
    result = work_order_to_dict(order)
    latest = (
        db.query(WorkOrderCompletionSnapshot)
        .options(joinedload(WorkOrderCompletionSnapshot.signature))
        .filter(WorkOrderCompletionSnapshot.work_order_id == order.id)
        .order_by(WorkOrderCompletionSnapshot.revision.desc())
        .first()
    )
    result["completion_snapshot"] = _snapshot_read(latest)
    result["signature_current"] = bool(latest and latest.signature and latest.signature.finalized_work_order_version == order.version)
    result["photos"] = [_photo_read(row) for row in order.photos]
    return result


@router.post("/work-orders/{order_id}/start")
def mobile_start_work_order(order_id: int, payload: MobileWorkOrderStart, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    order = _order_for_mobile(db, order_id, principal)
    if order.status in {"lezárva", "törölve / sztornózva"}:
        raise HTTPException(status_code=409, detail="Lezárt vagy sztornózott munkalap nem indítható")
    if order.started_at is not None and order.status == "folyamatban":
        return work_order_to_dict(order)
    require_current_version(order, payload.version)
    order.started_at = payload.started_at or datetime.utcnow()
    order.status = "folyamatban"
    order.updated_at = datetime.utcnow()
    add_audit_log(db, principal.user, "MOBILE_WORK_ORDER_STARTED", "work_order", order.id, f"Munkavégzés elindítva mobilról: {order.number}")
    commit_with_optimistic_lock(db)
    order = _order_for_mobile(db, order_id, principal)
    return work_order_to_dict(order)


@router.post("/work-orders/{order_id}/meter-readings", status_code=status.HTTP_201_CREATED)
def mobile_meter_reading(order_id: int, payload: MobileMeterReadingCreate, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    order = _order_for_mobile(db, order_id, principal)
    if order.status in {"lezárva", "törölve / sztornózva"}:
        raise HTTPException(status_code=409, detail="Lezárt vagy sztornózott munkalaphoz nem rögzíthető új számláló")
    if payload.asset_id not in {link.asset_id for link in order.asset_links}:
        raise HTTPException(status_code=400, detail="Az eszköz nincs a munkalaphoz kapcsolva")
    asset = db.get(Asset, payload.asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Eszköz nem található")
    row = _create_meter_reading(
        db, asset, principal.user, payload.value, payload.recorded_at or datetime.utcnow(), order.id,
        payload.black_white_value, payload.color_value, payload.scan_value, payload.note,
    )
    add_audit_log(db, principal.user, "MOBILE_METER_RECORDED", "asset_meter_reading", row.id, f"Számláló mobilról rögzítve a(z) {order.number} munkalaphoz")
    db.commit()
    return {"id": row.id, "asset_id": row.asset_id, "value": row.value, "recorded_at": row.recorded_at}


@router.get("/materials")
def mobile_materials(q: str | None = Query(default=None, max_length=100), principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    query = db.query(Material)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(Material.sku.ilike(term), Material.name.ilike(term)))
    rows = query.order_by(Material.name.asc()).limit(100).all()
    return [{"id": row.id, "sku": row.sku, "name": row.name, "unit": row.unit, "unit_price": float(row.unit_price) if row.unit_price is not None else None} for row in rows]


@router.get("/work-orders/{order_id}/photos", response_model=list[MobileWorkOrderPhotoRead])
def mobile_list_photos(order_id: int, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    _order_for_mobile(db, order_id, principal)
    rows = db.query(WorkOrderPhoto).filter(WorkOrderPhoto.work_order_id == order_id).order_by(WorkOrderPhoto.created_at.asc(), WorkOrderPhoto.id.asc()).all()
    return [_photo_read(row) for row in rows]


@router.post("/work-orders/{order_id}/photos", response_model=MobileWorkOrderPhotoRead, status_code=status.HTTP_201_CREATED)
async def mobile_upload_photo(
    order_id: int,
    category: str = Form(...),
    note: str | None = Form(default=None, max_length=500),
    photo: UploadFile = File(...),
    principal: MobilePrincipal = Depends(get_mobile_principal),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    order = _order_for_mobile(db, order_id, principal)
    if order.status in {"kész", "lezárva", "törölve / sztornózva"}:
        raise HTTPException(status_code=409, detail="Aláírásra előkészített, lezárt vagy sztornózott munkalap fényképei nem módosíthatók")
    category = category.strip().lower()
    if category not in WORK_ORDER_PHOTO_CATEGORIES:
        raise HTTPException(status_code=400, detail="Érvénytelen fényképkategória")
    stored = None
    try:
        stored, original_filename = await sanitize_and_store_work_order_photo(photo, settings)
        row = WorkOrderPhoto(
            work_order_id=order.id,
            category=category,
            note=note.strip() if note and note.strip() else None,
            original_filename=original_filename,
            storage_key=stored.storage_key,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            mime_type=stored.mime_type,
            width=stored.width,
            height=stored.height,
            uploaded_by_user_id=principal.user.id,
            mobile_device_id=principal.device.id,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        add_audit_log(db, principal.user, "MOBILE_WORK_ORDER_PHOTO_UPLOADED", "work_order", order.id, f"Munkalap-fénykép feltöltve: {order.number} / {category}")
        db.commit()
        db.refresh(row)
        return _photo_read(row)
    except Exception:
        db.rollback()
        if stored is not None:
            remove_work_order_photo(settings, stored.storage_key)
        raise


@router.get("/work-orders/{order_id}/photos/{photo_id}/content")
def mobile_photo_content(order_id: int, photo_id: int, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    _order_for_mobile(db, order_id, principal)
    row = db.query(WorkOrderPhoto).filter(WorkOrderPhoto.id == photo_id, WorkOrderPhoto.work_order_id == order_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fénykép nem található")
    path = photo_path(get_settings(), row.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="A fényképfájl nem található")
    return FileResponse(path, media_type=row.mime_type, filename=f"{row.id}.jpg", headers={"Cache-Control": "private, max-age=300"})


@router.delete("/work-orders/{order_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def mobile_delete_photo(order_id: int, photo_id: int, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    settings = get_settings()
    order = _order_for_mobile(db, order_id, principal)
    if order.status in {"kész", "lezárva", "törölve / sztornózva"}:
        raise HTTPException(status_code=409, detail="Aláírásra előkészített, lezárt vagy sztornózott munkalap fényképei nem módosíthatók")
    row = db.query(WorkOrderPhoto).filter(WorkOrderPhoto.id == photo_id, WorkOrderPhoto.work_order_id == order_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fénykép nem található")
    storage_key = row.storage_key
    db.delete(row)
    add_audit_log(db, principal.user, "MOBILE_WORK_ORDER_PHOTO_DELETED", "work_order", order.id, f"Munkalap-fénykép törölve: {order.number}")
    db.commit()
    remove_work_order_photo(settings, storage_key)


@router.post("/work-orders/{order_id}/complete", response_model=MobileCompletionSnapshotRead)
def mobile_complete_work_order(order_id: int, payload: MobileWorkOrderComplete, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    settings = get_settings()
    order = _order_for_mobile(db, order_id, principal)
    if order.status in {"lezárva", "törölve / sztornózva"}:
        raise HTTPException(status_code=409, detail="Lezárt vagy sztornózott munkalap nem készíthető elő aláírásra")
    require_current_version(order, payload.version)
    order.work_done = payload.work_done
    order.final_status = payload.final_status
    order.labor_hours = payload.labor_hours
    order.started_at = payload.started_at or order.started_at or datetime.utcnow()
    order.completed_at = payload.completed_at or datetime.utcnow()
    order.internal_note = payload.internal_note
    order.customer_note = payload.customer_note
    validate_time_ranges(order.planned_start_at, order.planned_end_at, order.started_at, order.completed_at)
    if payload.materials is not None:
        set_materials(db, order, payload.materials)
    order.status = "kész"
    order.updated_at = datetime.utcnow()
    try:
        db.flush()  # increments the optimistic WorkOrder.version before hashing the snapshot
    except StaleDataError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=CONFLICT_MESSAGE) from exc
    snapshot = create_completion_snapshot(db, order, principal.user, settings)
    add_audit_log(db, principal.user, "MOBILE_COMPLETION_SNAPSHOT_CREATED", "work_order", order.id, f"Aláírásra váró munkalap-snapshot létrehozva: {order.number} / rev. {snapshot.revision}")
    db.commit()
    snapshot = db.query(WorkOrderCompletionSnapshot).options(joinedload(WorkOrderCompletionSnapshot.signature)).filter(WorkOrderCompletionSnapshot.id == snapshot.id).one()
    return _snapshot_read(snapshot)


@router.get("/work-orders/{order_id}/completion", response_model=MobileCompletionSnapshotRead)
def mobile_completion(order_id: int, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    _order_for_mobile(db, order_id, principal)
    row = (
        db.query(WorkOrderCompletionSnapshot)
        .options(joinedload(WorkOrderCompletionSnapshot.signature))
        .filter(WorkOrderCompletionSnapshot.work_order_id == order_id)
        .order_by(WorkOrderCompletionSnapshot.revision.desc())
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Még nincs aláírásra előkészített munkalap-snapshot")
    return _snapshot_read(row)


@router.post("/work-orders/{order_id}/signature", response_model=MobileSignatureRead)
async def mobile_sign_work_order(
    order_id: int,
    snapshot_id: int = Form(...),
    signer_name: str = Form(..., min_length=2, max_length=255),
    signer_role: str | None = Form(default=None, max_length=255),
    signature: UploadFile = File(...),
    principal: MobilePrincipal = Depends(get_mobile_principal),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    order = _order_for_mobile(db, order_id, principal)
    if order.status in {"lezárva", "törölve / sztornózva"}:
        raise HTTPException(status_code=409, detail="A munkalap már lezárt vagy sztornózott")
    snapshot = (
        db.query(WorkOrderCompletionSnapshot)
        .options(joinedload(WorkOrderCompletionSnapshot.signature))
        .filter(WorkOrderCompletionSnapshot.id == snapshot_id, WorkOrderCompletionSnapshot.work_order_id == order_id)
        .with_for_update()
        .one_or_none()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="A munkalap-snapshot nem található")
    latest = db.query(WorkOrderCompletionSnapshot).filter(WorkOrderCompletionSnapshot.work_order_id == order_id).order_by(WorkOrderCompletionSnapshot.revision.desc()).first()
    if latest is None or latest.id != snapshot.id:
        raise HTTPException(status_code=409, detail="Csak a munkalap legfrissebb revisionje írható alá")
    if snapshot.signature is not None:
        raise HTTPException(status_code=409, detail="Ez a munkalap-revision már alá lett írva")
    if snapshot.source_work_order_version != order.version:
        raise HTTPException(status_code=409, detail="A munkalap az aláírásra előkészítés óta megváltozott; készíts új snapshotot")

    max_bytes = settings.mobile_signature_max_size_kb * 1024
    raw = await signature.read(max_bytes + 1)
    await signature.close()
    stored_sig = None
    stored_pdf = None
    try:
        stored_sig = sanitize_and_store_signature_png(raw, settings)
        signature_png = signature_path(settings, stored_sig.storage_key).read_bytes()
        signed_at = datetime.utcnow()
        pdf_bytes = build_signed_work_order_pdf(
            snapshot=snapshot.snapshot_json,
            snapshot_revision=snapshot.revision,
            snapshot_sha256=snapshot.snapshot_sha256,
            signer_name=signer_name.strip(),
            signer_role=signer_role.strip() if signer_role else None,
            acceptance_text=settings.work_order_acceptance_text,
            signed_at=signed_at,
            technician_name=principal.user.full_name,
            signature_png=signature_png,
        )
        stored_pdf = store_signed_pdf(pdf_bytes, settings)

        was_closed = order.status == "lezárva"
        had_prior_signature = db.query(WorkOrderSignature.id).filter(WorkOrderSignature.work_order_id == order.id).first() is not None
        order.status = "lezárva"
        order.completed_at = order.completed_at or signed_at
        order.closed_at = signed_at
        order.updated_at = signed_at
        if not was_closed and not had_prior_signature:
            update_assets_after_maintenance_close(db, order, principal.user)
        try:
            db.flush()  # finalize WorkOrder.version so future edits invalidate current-signature status
        except StaleDataError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=CONFLICT_MESSAGE) from exc

        row = WorkOrderSignature(
            snapshot_id=snapshot.id,
            work_order_id=order.id,
            signer_name=signer_name.strip(),
            signer_role=signer_role.strip() if signer_role else None,
            acceptance_text=settings.work_order_acceptance_text,
            acceptance_text_version=settings.work_order_acceptance_text_version,
            signature_storage_key=stored_sig.storage_key,
            signature_sha256=stored_sig.sha256,
            signature_size_bytes=stored_sig.size_bytes,
            signed_pdf_storage_key=stored_pdf.storage_key,
            signed_pdf_sha256=stored_pdf.sha256,
            signed_pdf_size_bytes=stored_pdf.size_bytes,
            signed_at=signed_at,
            finalized_work_order_version=order.version,
            technician_user_id=principal.user.id,
            mobile_device_id=principal.device.id,
            ip_address=get_audit_request_context().ip_address,
        )
        db.add(row)
        db.flush()
        add_audit_log(db, principal.user, "MOBILE_WORK_ORDER_SIGNED", "work_order", order.id, f"Munkalap ügyfél által aláírva és lezárva: {order.number} / rev. {snapshot.revision}")
        db.commit()
        db.refresh(row)
        return _signature_read(row)
    except Exception:
        db.rollback()
        if stored_pdf is not None:
            remove_evidence_file(settings, stored_pdf.storage_key)
        if stored_sig is not None:
            remove_evidence_file(settings, stored_sig.storage_key)
        raise


@router.get("/work-orders/{order_id}/signed-pdf")
def mobile_signed_pdf(order_id: int, principal: MobilePrincipal = Depends(get_mobile_principal), db: Session = Depends(get_db)):
    order = _order_for_mobile(db, order_id, principal)
    row = db.query(WorkOrderSignature).filter(WorkOrderSignature.work_order_id == order.id).order_by(WorkOrderSignature.signed_at.desc()).first()
    if row is None:
        raise HTTPException(status_code=404, detail="A munkalaphoz még nincs aláírt PDF")
    path = signature_path(get_settings(), row.signed_pdf_storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Az aláírt PDF hiányzik a tárhelyről")
    safe_number = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in order.number)
    return FileResponse(path, media_type="application/pdf", filename=f"{safe_number}-signed-r{row.snapshot.revision}.pdf")
