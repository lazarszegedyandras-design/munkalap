from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..access_control import PERMISSION_CATALOG, PERMISSION_HR_LEAVE_APPROVE, PERMISSION_SERVICE_ACCESS
from ..database import get_db
from ..deps import RequireAdmin, RequireRecentMfa, RequireServiceAccess, get_current_user
from ..models import EmployeeProfile, LeaveRequest, MobileDevice, ProcurementAttachment, ProcurementRequest, PushDeliveryOutbox, ROLE_ADMIN, Role, User
from ..schemas import PermissionAssignmentUpdate, PermissionRead, RoleRead, UserCreate, UserRead, UserUpdate
from ..security import get_password_hash
from ..services.audit import add_audit_log, snapshot_entity
from ..services.auth_security import revoke_user_sessions
from ..services.mobile_auth import revoke_mobile_device
from ..services.permissions import ensure_permission_catalog, set_user_permissions
from ..services.push_notifications import enqueue_test_push_for_device

router = APIRouter(prefix="/users", tags=["users"])


def _pending_leave_approvals(db: Session, user_id: int) -> int:
    return db.query(LeaveRequest).filter(
        or_(
            (LeaveRequest.approver_user_id == user_id) & (LeaveRequest.status == "pending"),
            (LeaveRequest.cancellation_approver_user_id == user_id) & (LeaveRequest.cancellation_status == "pending"),
        ),
    ).count()


def _effective_can_approve_leave(db: Session, user: User, *, role_id: int | None = None, permission_codes: list[str] | None = None) -> bool:
    role = db.get(Role, role_id) if role_id is not None else user.role
    codes = set(permission_codes if permission_codes is not None else user.permissions)
    return bool(role and (role.name == ROLE_ADMIN or PERMISSION_HR_LEAVE_APPROVE in codes))


def _guard_pending_hr_approvals(db: Session, user: User, *, will_be_active: bool, can_approve_leave: bool) -> None:
    if _pending_leave_approvals(db, user.id) and (not will_be_active or not can_approve_leave):
        raise HTTPException(
            status_code=409,
            detail="A felhasználóhoz jóváhagyásra váró szabadságigény vagy visszavonási kérelem tartozik. A jóváhagyói hozzáférés vagy az aktív státusz csak ezek lezárása után vonható vissza.",
        )


def _user_audit_snapshot(user: User) -> dict:
    data = snapshot_entity(user) or {}
    data["permission_codes"] = list(user.permissions)
    data["role_name"] = user.role.name if user.role else None
    return data


@router.get("/roles", response_model=list[RoleRead])
def list_roles(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Role).order_by(Role.name).all()


@router.get("/permissions", response_model=list[PermissionRead])
def list_permissions(_: User = Depends(RequireAdmin)):
    return list(PERMISSION_CATALOG)


@router.get("/technicians", response_model=list[UserRead])
def list_technicians(db: Session = Depends(get_db), _: User = Depends(RequireServiceAccess)):
    return db.query(User).join(Role).filter(Role.name == "Technikus / szerelő", User.is_active.is_(True)).order_by(User.full_name).all()


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), _: User = Depends(RequireAdmin)):
    return db.query(User).order_by(User.full_name).all()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin), _: User = Depends(RequireRecentMfa)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Ezzel az email címmel már van felhasználó")
    if not db.get(Role, payload.role_id):
        raise HTTPException(status_code=400, detail="Érvénytelen szerepkör")

    ensure_permission_catalog(db)
    permission_codes = payload.permission_codes if payload.permission_codes is not None else [PERMISSION_SERVICE_ACCESS]
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        is_active=payload.is_active,
        role_id=payload.role_id,
        password_hash=get_password_hash(payload.password),
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    try:
        assigned = set_user_permissions(db, user, permission_codes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        current_user,
        "létrehozás",
        "user",
        user.id,
        f"Felhasználó létrehozva: {user.email}; jogosultságok: {', '.join(assigned) or 'nincs'}",
        entity_display_id=user.email,
        before=None,
        after=_user_audit_snapshot(user),
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin), _: User = Depends(RequireRecentMfa)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Felhasználó nem található")
    before_snapshot = _user_audit_snapshot(user)
    data = payload.model_dump(exclude_unset=True)
    permission_codes = data.pop("permission_codes", None) if "permission_codes" in data else None
    permissions_were_supplied = "permission_codes" in payload.model_fields_set
    if "email" in data and data["email"] != user.email and db.query(User).filter(User.email == data["email"]).first():
        raise HTTPException(status_code=400, detail="Ezzel az email címmel már van felhasználó")
    if "role_id" in data and not db.get(Role, data["role_id"]):
        raise HTTPException(status_code=400, detail="Érvénytelen szerepkör")
    effective_codes = permission_codes if permissions_were_supplied else list(user.permissions)
    _guard_pending_hr_approvals(
        db,
        user,
        will_be_active=data.get("is_active", user.is_active),
        can_approve_leave=_effective_can_approve_leave(db, user, role_id=data.get("role_id"), permission_codes=effective_codes),
    )
    security_sensitive_change = False
    if password := data.pop("password", None):
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="A saját jelszót a Jelszó módosítása oldalon, a jelenlegi jelszó megadásával lehet megváltoztatni")
        user.password_hash = get_password_hash(password)
        user.must_change_password = True
        security_sensitive_change = True
    for field, value in data.items():
        if field in {"email", "is_active", "role_id"} and getattr(user, field) != value:
            security_sensitive_change = True
        setattr(user, field, value)
    if security_sensitive_change:
        revoke_user_sessions(db, user.id)

    permission_note = ""
    if permissions_were_supplied:
        ensure_permission_catalog(db)
        try:
            assigned = set_user_permissions(db, user, permission_codes or [])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        permission_note = f"; jogosultságok: {', '.join(assigned) or 'nincs'}"

    db.flush()
    add_audit_log(
        db, current_user, "módosítás", "user", user.id,
        f"Felhasználó módosítva: {user.email}{permission_note}",
        entity_display_id=user.email, before=before_snapshot, after=_user_audit_snapshot(user),
    )
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/permissions", response_model=UserRead)
def update_user_permissions(
    user_id: int,
    payload: PermissionAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
    _: User = Depends(RequireRecentMfa),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Felhasználó nem található")
    before_snapshot = _user_audit_snapshot(user)
    ensure_permission_catalog(db)
    _guard_pending_hr_approvals(
        db, user, will_be_active=user.is_active,
        can_approve_leave=_effective_can_approve_leave(db, user, permission_codes=payload.permission_codes),
    )
    try:
        assigned = set_user_permissions(db, user, payload.permission_codes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.flush()
    add_audit_log(
        db,
        current_user,
        "jogosultság-módosítás",
        "user",
        user.id,
        f"Felhasználói jogosultságok módosítva: {user.email}; új jogosultságok: {', '.join(assigned) or 'nincs'}",
        entity_display_id=user.email,
        before=before_snapshot,
        after=_user_audit_snapshot(user),
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}/mobile-devices")
def list_user_mobile_devices(user_id: int, db: Session = Depends(get_db), _: User = Depends(RequireAdmin)):
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="Felhasználó nem található")
    rows = db.query(MobileDevice).filter(MobileDevice.user_id == user_id).order_by(MobileDevice.last_seen_at.desc()).all()
    result = []
    for row in rows:
        latest = (
            db.query(PushDeliveryOutbox)
            .filter(PushDeliveryOutbox.device_id == row.id)
            .order_by(PushDeliveryOutbox.created_at.desc(), PushDeliveryOutbox.id.desc())
            .first()
        )
        result.append({
            "id": row.id,
            "device_uuid": row.device_uuid,
            "device_name": row.device_name,
            "platform": row.platform,
            "app_version": row.app_version,
            "last_seen_at": row.last_seen_at,
            "revoked_at": row.revoked_at,
            "push_enabled": bool(row.push_enabled),
            "push_token_updated_at": row.push_token_updated_at,
            "last_push": None if latest is None else {
                "id": latest.id,
                "status": latest.status,
                "attempt_count": latest.attempt_count,
                "created_at": latest.created_at,
                "last_attempt_at": latest.last_attempt_at,
                "sent_at": latest.sent_at,
                "last_error": latest.last_error,
                "provider_message_id": latest.provider_message_id,
            },
        })
    return result


@router.post("/{user_id}/mobile-devices/{device_id}/test-push", status_code=status.HTTP_202_ACCEPTED)
def admin_test_push_user_mobile_device(
    user_id: int,
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Felhasználó nem található")
    device = db.query(MobileDevice).filter(MobileDevice.id == device_id, MobileDevice.user_id == user_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Mobil eszköz nem található")
    try:
        delivery = enqueue_test_push_for_device(db, device, actor_user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    add_audit_log(
        db,
        current_user,
        "MOBILE_PUSH_TEST_QUEUED",
        "user",
        user_id,
        f"Teszt push sorba állítva: device_id={device_id}; delivery_id={delivery.id}",
        entity_display_id=target.email,
        after={"device_id": device_id, "delivery_id": delivery.id, "status": delivery.status},
    )
    db.commit()
    db.refresh(delivery)
    return {"delivery_id": delivery.id, "status": delivery.status}


@router.delete("/{user_id}/mobile-devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_revoke_user_mobile_device(user_id: int, device_id: int, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Felhasználó nem található")
    if not revoke_mobile_device(db, user_id, device_id):
        raise HTTPException(status_code=404, detail="Mobil eszköz nem található")
    add_audit_log(db, current_user, "MOBILE_DEVICE_REVOKED_BY_ADMIN", "user", user_id, f"Mobil eszköz adminisztrátor által visszavonva: device_id={device_id}", entity_display_id=target.email)
    db.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Saját admin felhasználó nem törölhető")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Felhasználó nem található")
    has_hr_profile = db.query(EmployeeProfile.id).filter(EmployeeProfile.user_id == user.id).first() is not None
    has_hr_approval_history = db.query(LeaveRequest.id).filter(or_(
        LeaveRequest.approver_user_id == user.id,
        LeaveRequest.cancellation_approver_user_id == user.id,
    )).first() is not None
    if has_hr_profile or has_hr_approval_history:
        raise HTTPException(status_code=409, detail="HR adatokkal rendelkező felhasználó nem törölhető; állítsd inaktívra, hogy a HR előzmények megmaradjanak")
    has_procurement_history = db.query(ProcurementRequest.id).filter(or_(
        ProcurementRequest.requester_user_id == user.id,
        ProcurementRequest.approved_by_user_id == user.id,
    )).first() is not None or db.query(ProcurementAttachment.id).filter(
        ProcurementAttachment.uploaded_by_user_id == user.id
    ).first() is not None
    if has_procurement_history:
        raise HTTPException(status_code=409, detail="Beszerzési előzménnyel rendelkező felhasználó nem törölhető; állítsd inaktívra, hogy az üzleti előzmények megmaradjanak")
    before_snapshot = _user_audit_snapshot(user)
    add_audit_log(
        db, current_user, "törlés", "user", user.id, f"Felhasználó törölve: {user.email}",
        entity_display_id=user.email, before=before_snapshot, after=None,
    )
    db.delete(user)
    db.commit()
    return None
