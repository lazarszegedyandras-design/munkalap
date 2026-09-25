from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from ..access_control import PERMISSION_HR_LEAVE_APPROVE
from ..database import get_db
from ..deps import RequireHrAdmin, RequireHrLeaveApprove, RequireHrLeaveRequest, RequireHrLeaveSelf, RequireHrSummaryView
from ..models import EmployeeProfile, HrLeaveImportPerson, LeaveEntitlement, LeaveRequest, ROLE_ADMIN, User, UserPermission, WorkCalendarDay
from ..schemas import (
    EmployeeProfileRead,
    EmployeeProfileUpsert,
    HrAdminEmployeeRow,
    HrLeaveImportLink,
    HrLeaveImportRow,
    HrMeRead,
    HrSummaryRow,
    HrUserSummary,
    LeaveCancel,
    LeaveCancellationCreate,
    LeaveDecision,
    LeaveEntitlementRead,
    LeaveEntitlementUpsert,
    LeaveRequestCreate,
    LeaveRequestRead,
    WorkCalendarDayRead,
    WorkCalendarDayUpsert,
)
from ..services.audit import add_audit_log, snapshot_entity
from ..services.hr_import import apply_import_person, auto_apply_rlb_2026_imports, ensure_rlb_2026_staging, serialize_import_person, source_available as hr_source_available
from ..services.hr_leave import (
    count_workdays,
    ensure_no_overlap,
    get_employee_profile,
    get_entitlement,
    leave_balance,
    serialize_entitlement,
    serialize_leave_request,
    serialize_profile,
    validate_request_dates,
)

router = APIRouter(prefix="/hr", tags=["hr"])


def _request_query(db: Session):
    return db.query(LeaveRequest).options(
        joinedload(LeaveRequest.employee).joinedload(EmployeeProfile.user),
        joinedload(LeaveRequest.approver),
        joinedload(LeaveRequest.cancellation_approver),
    )


def _active_user(db: Session, user_id: int, field_name: str) -> User:
    user = (
        db.query(User)
        .options(joinedload(User.role), selectinload(User.permission_links).joinedload(UserPermission.permission))
        .filter(User.id == user_id, User.is_active.is_(True))
        .first()
    )
    if not user:
        raise HTTPException(status_code=400, detail=f"A megadott {field_name} felhasználó nem létezik vagy inaktív")
    return user


def _validate_approver(user: User, employee_user_id: int) -> None:
    if user.id == employee_user_id:
        raise HTTPException(status_code=400, detail="A munkavállaló nem lehet a saját szabadság-jóváhagyója")
    if user.role.name != ROLE_ADMIN and PERMISSION_HR_LEAVE_APPROVE not in user.permissions:
        raise HTTPException(status_code=400, detail="A szabadság-jóváhagyó felhasználónak HR jóváhagyási jogosultsággal kell rendelkeznie")


def _entitlement_for_response(entitlement: LeaveEntitlement | None):
    return serialize_entitlement(entitlement) if entitlement else None


def _leave_audit_snapshot(row: LeaveRequest) -> dict:
    """Audit state without exposing exact leave dates or free-text HR comments."""
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "approver_user_id": row.approver_user_id,
        "requested_days": str(row.requested_days),
        "status": row.status,
        "leave_type": getattr(row, "leave_type", "annual_leave"),
        "source": getattr(row, "source", "workflow"),
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
        "cancellation_status": row.cancellation_status,
        "cancellation_approver_user_id": row.cancellation_approver_user_id,
        "cancellation_requested_at": row.cancellation_requested_at.isoformat() if row.cancellation_requested_at else None,
        "cancellation_decided_at": row.cancellation_decided_at.isoformat() if row.cancellation_decided_at else None,
        "version": row.version,
    }


@router.get("/me", response_model=HrMeRead)
def hr_me(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveSelf),
):
    profile = get_employee_profile(db, current_user.id)
    requests = (
        _request_query(db)
        .filter(
            LeaveRequest.employee_id == profile.id,
            LeaveRequest.start_date >= date(year, 1, 1),
            LeaveRequest.start_date <= date(year, 12, 31),
        )
        .order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc())
        .all()
    )
    return {
        "profile": serialize_profile(profile),
        "balance": leave_balance(db, profile, year),
        "leave_requests": [serialize_leave_request(row) for row in requests],
    }


@router.get("/me/leave-requests", response_model=list[LeaveRequestRead])
def my_leave_requests(
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveSelf),
):
    profile = get_employee_profile(db, current_user.id)
    query = _request_query(db).filter(LeaveRequest.employee_id == profile.id)
    if year is not None:
        query = query.filter(
            LeaveRequest.start_date >= date(year, 1, 1),
            LeaveRequest.start_date <= date(year, 12, 31),
        )
    return [serialize_leave_request(row) for row in query.order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc()).all()]


@router.post("/me/leave-requests", response_model=LeaveRequestRead, status_code=status.HTTP_201_CREATED)
def create_leave_request(
    payload: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveRequest),
):
    profile = get_employee_profile(db, current_user.id)
    validate_request_dates(profile, payload.start_date, payload.end_date)
    if not profile.leave_approver_user_id:
        raise HTTPException(status_code=409, detail="Nincs szabadság-jóváhagyó beállítva a HR profilhoz")
    approver = _active_user(db, profile.leave_approver_user_id, "jóváhagyó")
    _validate_approver(approver, current_user.id)
    ensure_no_overlap(db, profile.id, payload.start_date, payload.end_date)

    requested_days = count_workdays(db, payload.start_date, payload.end_date)
    if requested_days <= 0:
        raise HTTPException(status_code=400, detail="A megadott időszak nem tartalmaz elszámolható munkanapot")

    balance = leave_balance(db, profile, payload.start_date.year)
    if requested_days > balance["available_to_request_days"]:
        raise HTTPException(
            status_code=409,
            detail=f"Nincs elegendő elérhető szabadságkeret. Igény: {requested_days} nap, igényelhető: {balance['available_to_request_days']} nap",
        )

    row = LeaveRequest(
        employee_id=profile.id,
        approver_user_id=approver.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        requested_days=requested_days,
        status="pending",
        leave_type="annual_leave",
        source="workflow",
        employee_comment=(payload.employee_comment or "").strip() or None,
        submitted_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    row = _request_query(db).filter(LeaveRequest.id == row.id).one()
    add_audit_log(
        db,
        current_user,
        "LEAVE_REQUEST_SUBMITTED",
        "leave_request",
        row.id,
        f"Szabadságigény beküldve ({requested_days} nap)",
        entity_display_id=f"SZAB-{row.id}",
        before=None,
        after=_leave_audit_snapshot(row),
    )
    db.commit()
    return serialize_leave_request(row)


@router.post("/me/leave-requests/{request_id}/request-cancellation", response_model=LeaveRequestRead)
def request_own_leave_cancellation(
    request_id: int,
    payload: LeaveCancellationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveSelf),
):
    profile = get_employee_profile(db, current_user.id)
    row = _request_query(db).filter(LeaveRequest.id == request_id, LeaveRequest.employee_id == profile.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Szabadságigény nem található")
    if row.version != payload.version:
        raise HTTPException(status_code=409, detail="A szabadságigény időközben módosult; frissítsd az oldalt")
    if row.status != "approved":
        raise HTTPException(status_code=409, detail="Csak jóváhagyott szabadság visszavonása kérelmezhető")
    if row.cancellation_status == "pending":
        raise HTTPException(status_code=409, detail="A szabadság visszavonása már jóváhagyásra vár")
    if not profile.leave_approver_user_id:
        raise HTTPException(status_code=409, detail="Nincs szabadság-jóváhagyó beállítva a HR profilhoz")
    approver = _active_user(db, profile.leave_approver_user_id, "jóváhagyó")
    _validate_approver(approver, current_user.id)

    before = _leave_audit_snapshot(row)
    row.cancellation_status = "pending"
    row.cancellation_approver_user_id = approver.id
    row.cancellation_approver = approver
    row.cancellation_comment = (payload.comment or "").strip() or None
    row.cancellation_approver_comment = None
    row.cancellation_requested_at = datetime.utcnow()
    row.cancellation_decided_at = None
    row.version += 1
    add_audit_log(
        db,
        current_user,
        "LEAVE_CANCELLATION_REQUESTED",
        "leave_request",
        row.id,
        "Jóváhagyott szabadság visszavonása kérelmezve",
        entity_display_id=f"SZAB-{row.id}",
        before=before,
        after=_leave_audit_snapshot(row),
    )
    db.commit()
    return serialize_leave_request(row)


@router.post("/me/leave-requests/{request_id}/cancel", response_model=LeaveRequestRead)
def cancel_own_leave_request(
    request_id: int,
    payload: LeaveCancel,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveSelf),
):
    profile = get_employee_profile(db, current_user.id)
    row = _request_query(db).filter(LeaveRequest.id == request_id, LeaveRequest.employee_id == profile.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Szabadságigény nem található")
    if row.version != payload.version:
        raise HTTPException(status_code=409, detail="A szabadságigény időközben módosult; frissítsd az oldalt")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Csak jóváhagyásra váró szabadságigény vonható vissza")
    before = _leave_audit_snapshot(row)
    row.status = "cancelled"
    row.cancelled_at = datetime.utcnow()
    row.version += 1
    add_audit_log(
        db,
        current_user,
        "LEAVE_REQUEST_CANCELLED",
        "leave_request",
        row.id,
        "Saját szabadságigény visszavonva",
        entity_display_id=f"SZAB-{row.id}",
        before=before,
        after=_leave_audit_snapshot(row),
    )
    db.commit()
    return serialize_leave_request(row)


@router.get("/approvals", response_model=list[LeaveRequestRead])
def assigned_approvals(
    request_status: str | None = Query(default="pending", alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveApprove),
):
    query = _request_query(db)
    if request_status == "pending":
        query = query.filter(or_(
            and_(LeaveRequest.approver_user_id == current_user.id, LeaveRequest.status == "pending"),
            and_(LeaveRequest.cancellation_approver_user_id == current_user.id, LeaveRequest.cancellation_status == "pending"),
        ))
    else:
        query = query.filter(LeaveRequest.approver_user_id == current_user.id)
        if request_status:
            if request_status not in {"approved", "rejected", "cancelled"}:
                raise HTTPException(status_code=400, detail="Érvénytelen szabadságigény-státusz")
            query = query.filter(LeaveRequest.status == request_status)
    return [serialize_leave_request(row) for row in query.order_by(LeaveRequest.updated_at.desc(), LeaveRequest.id.desc()).all()]


def _decide_leave_request(db: Session, current_user: User, request_id: int, payload: LeaveDecision, decision: str):
    row = _request_query(db).filter(
        LeaveRequest.id == request_id,
        LeaveRequest.approver_user_id == current_user.id,
    ).first()
    if not row:
        # Szándékosan nem áruljuk el, hogy más jóváhagyóhoz tartozik-e ilyen rekord.
        raise HTTPException(status_code=404, detail="Jóváhagyandó szabadságigény nem található")
    if row.version != payload.version:
        raise HTTPException(status_code=409, detail="A szabadságigény időközben módosult; frissítsd az oldalt")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="A szabadságigény már nem vár jóváhagyásra")

    if decision == "approved":
        balance = leave_balance(db, row.employee, row.start_date.year)
        if row.requested_days > balance["total_days"] - balance["approved_days"]:
            raise HTTPException(status_code=409, detail="A szabadságkeret időközben csökkent; az igény jelenleg nem hagyható jóvá")

    before = _leave_audit_snapshot(row)
    row.status = decision
    row.approver_comment = (payload.comment or "").strip() or None
    row.decided_at = datetime.utcnow()
    row.version += 1
    action = "LEAVE_REQUEST_APPROVED" if decision == "approved" else "LEAVE_REQUEST_REJECTED"
    description = "Szabadságigény jóváhagyva" if decision == "approved" else "Szabadságigény elutasítva"
    add_audit_log(
        db,
        current_user,
        action,
        "leave_request",
        row.id,
        description,
        entity_display_id=f"SZAB-{row.id}",
        before=before,
        after=_leave_audit_snapshot(row),
    )
    db.commit()
    return serialize_leave_request(row)


@router.post("/approvals/{request_id}/approve", response_model=LeaveRequestRead)
def approve_leave_request(
    request_id: int,
    payload: LeaveDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveApprove),
):
    return _decide_leave_request(db, current_user, request_id, payload, "approved")


@router.post("/approvals/{request_id}/reject", response_model=LeaveRequestRead)
def reject_leave_request(
    request_id: int,
    payload: LeaveDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveApprove),
):
    return _decide_leave_request(db, current_user, request_id, payload, "rejected")


def _decide_leave_cancellation(db: Session, current_user: User, request_id: int, payload: LeaveDecision, decision: str):
    row = _request_query(db).filter(
        LeaveRequest.id == request_id,
        LeaveRequest.cancellation_approver_user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Jóváhagyandó szabadság-visszavonás nem található")
    if row.version != payload.version:
        raise HTTPException(status_code=409, detail="A szabadságigény időközben módosult; frissítsd az oldalt")
    if row.status != "approved" or row.cancellation_status != "pending":
        raise HTTPException(status_code=409, detail="A szabadság visszavonása már nem vár jóváhagyásra")

    before = _leave_audit_snapshot(row)
    now = datetime.utcnow()
    row.cancellation_status = decision
    row.cancellation_approver_comment = (payload.comment or "").strip() or None
    row.cancellation_decided_at = now
    if decision == "approved":
        row.status = "cancelled"
        row.cancelled_at = now
        action = "LEAVE_CANCELLATION_APPROVED"
        description = "Szabadság-visszavonás jóváhagyva"
    else:
        action = "LEAVE_CANCELLATION_REJECTED"
        description = "Szabadság-visszavonás elutasítva"
    row.version += 1
    add_audit_log(
        db,
        current_user,
        action,
        "leave_request",
        row.id,
        description,
        entity_display_id=f"SZAB-{row.id}",
        before=before,
        after=_leave_audit_snapshot(row),
    )
    db.commit()
    return serialize_leave_request(row)


@router.post("/approvals/{request_id}/cancellation/approve", response_model=LeaveRequestRead)
def approve_leave_cancellation(
    request_id: int,
    payload: LeaveDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveApprove),
):
    return _decide_leave_cancellation(db, current_user, request_id, payload, "approved")


@router.post("/approvals/{request_id}/cancellation/reject", response_model=LeaveRequestRead)
def reject_leave_cancellation(
    request_id: int,
    payload: LeaveDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrLeaveApprove),
):
    return _decide_leave_cancellation(db, current_user, request_id, payload, "rejected")


@router.get("/summary", response_model=list[HrSummaryRow])
def hr_summary(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    db: Session = Depends(get_db),
    _: User = Depends(RequireHrSummaryView),
):
    profiles = (
        db.query(EmployeeProfile)
        .options(joinedload(EmployeeProfile.user))
        .filter(EmployeeProfile.active.is_(True))
        .order_by(User.full_name)
        .join(EmployeeProfile.user)
        .all()
    )
    result = []
    for profile in profiles:
        balance = leave_balance(db, profile, year)
        result.append({
            "employee_id": profile.id,
            "user_id": profile.user_id,
            "employee_number": profile.employee_number,
            "full_name": profile.user.full_name,
            "company_code": profile.company_code,
            "organizational_unit": profile.organizational_unit,
            "job_title": profile.job_title,
            "year": year,
            "total_days": balance["total_days"],
            "approved_days": balance["approved_days"],
            "pending_days": balance["pending_days"],
            "remaining_days": balance["remaining_days"],
            "sick_leave_used_days": balance["sick_leave_used_days"],
            "sick_leave_remaining_days": balance["sick_leave_remaining_days"],
        })
    return result


@router.get("/summary/calendar")
def hr_summary_calendar(
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(RequireHrSummaryView),
):
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="A záró dátum nem lehet korábbi a kezdő dátumnál")
    if (date_to - date_from).days > 370:
        raise HTTPException(status_code=400, detail="Legfeljebb 371 nap kérhető le egyszerre")
    rows = (
        _request_query(db)
        .filter(
            LeaveRequest.status.in_(["approved", "pending"]),
            LeaveRequest.start_date <= date_to,
            LeaveRequest.end_date >= date_from,
        )
        .order_by(LeaveRequest.start_date, LeaveRequest.employee_id, LeaveRequest.id)
        .all()
    )
    return {
        "date_from": date_from,
        "date_to": date_to,
        "events": [
            {
                "id": row.id,
                "employee_id": row.employee_id,
                "user_id": row.employee.user_id,
                "full_name": row.employee.user.full_name,
                "company_code": row.employee.company_code,
                "leave_type": row.leave_type,
                "status": row.status,
                "start_date": row.start_date,
                "end_date": row.end_date,
                "days": float(row.requested_days),
                "source": row.source,
            }
            for row in rows
        ],
    }


@router.get("/admin/employees", response_model=list[HrAdminEmployeeRow])
def admin_employee_rows(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    db: Session = Depends(get_db),
    _: User = Depends(RequireHrAdmin),
):
    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name).all()
    profiles = {
        profile.user_id: profile
        for profile in db.query(EmployeeProfile).options(
            joinedload(EmployeeProfile.user), joinedload(EmployeeProfile.manager), joinedload(EmployeeProfile.leave_approver)
        ).all()
    }
    entitlements = {
        item.employee_id: item
        for item in db.query(LeaveEntitlement).filter(LeaveEntitlement.year == year).all()
    }
    rows = []
    for user in users:
        profile = profiles.get(user.id)
        rows.append({
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "can_approve_leave": user.role.name == ROLE_ADMIN or PERMISSION_HR_LEAVE_APPROVE in user.permissions,
            },
            "profile": serialize_profile(profile) if profile else None,
            "entitlement": _entitlement_for_response(entitlements.get(profile.id) if profile else None),
        })
    return rows


@router.put("/admin/employees/{user_id}/profile", response_model=EmployeeProfileRead)
def upsert_employee_profile(
    user_id: int,
    payload: EmployeeProfileUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrAdmin),
):
    employee_user = _active_user(db, user_id, "munkavállaló")
    if payload.employment_start_date and payload.employment_end_date and payload.employment_end_date < payload.employment_start_date:
        raise HTTPException(status_code=400, detail="A munkaviszony vége nem lehet korábbi a kezdeténél")
    manager = _active_user(db, payload.manager_user_id, "vezető") if payload.manager_user_id else None
    approver = _active_user(db, payload.leave_approver_user_id, "jóváhagyó") if payload.leave_approver_user_id else None
    if manager and manager.id == employee_user.id:
        raise HTTPException(status_code=400, detail="A munkavállaló nem lehet a saját vezetője")
    if approver:
        _validate_approver(approver, employee_user.id)

    data = payload.model_dump()
    for field in ("employee_number", "company_code", "organizational_unit", "job_title"):
        value = data.get(field)
        data[field] = value.strip() or None if isinstance(value, str) else value
    if data.get("employee_number"):
        duplicate = db.query(EmployeeProfile).filter(
            EmployeeProfile.employee_number == data["employee_number"],
            EmployeeProfile.user_id != user_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Ez a törzsszám már más munkavállalóhoz tartozik")

    profile = db.query(EmployeeProfile).filter(EmployeeProfile.user_id == user_id).first()
    before = snapshot_entity(profile) if profile else None
    if not profile:
        profile = EmployeeProfile(user_id=user_id)
        db.add(profile)
        db.flush()
    for field, value in data.items():
        setattr(profile, field, value)
    db.flush()
    profile = (
        db.query(EmployeeProfile)
        .options(joinedload(EmployeeProfile.user), joinedload(EmployeeProfile.manager), joinedload(EmployeeProfile.leave_approver))
        .filter(EmployeeProfile.id == profile.id)
        .one()
    )
    add_audit_log(
        db,
        current_user,
        "HR_EMPLOYEE_PROFILE_UPSERT",
        "employee_profile",
        profile.id,
        f"HR munkavállalói profil mentve: {employee_user.full_name}",
        entity_display_id=employee_user.email,
        before=before,
        after=snapshot_entity(profile),
    )
    db.commit()
    return serialize_profile(profile)


@router.put("/admin/employees/{user_id}/entitlement", response_model=LeaveEntitlementRead)
def upsert_leave_entitlement(
    user_id: int,
    payload: LeaveEntitlementUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrAdmin),
):
    profile = get_employee_profile(db, user_id)
    if payload.base_days + payload.child_days + payload.carried_days + payload.adjustment_days < 0:
        raise HTTPException(status_code=400, detail="Az éves teljes szabadságkeret nem lehet negatív")
    entitlement = get_entitlement(db, profile.id, payload.year)
    before = snapshot_entity(entitlement) if entitlement else None
    if not entitlement:
        entitlement = LeaveEntitlement(employee_id=profile.id, year=payload.year)
        db.add(entitlement)
    entitlement.base_days = payload.base_days
    entitlement.carried_days = payload.carried_days
    entitlement.adjustment_days = payload.adjustment_days
    entitlement.child_days = payload.child_days
    entitlement.sick_leave_days = payload.sick_leave_days
    entitlement.note = (payload.note or "").strip() or None
    db.flush()
    add_audit_log(
        db,
        current_user,
        "LEAVE_ENTITLEMENT_UPSERT",
        "leave_entitlement",
        entitlement.id,
        f"Éves szabadságkeret mentve: {profile.user.full_name}, {payload.year}",
        entity_display_id=f"{profile.user.email}/{payload.year}",
        before=before,
        after=snapshot_entity(entitlement),
    )
    db.commit()
    return serialize_entitlement(entitlement)


@router.get("/admin/imported-leave", response_model=list[HrLeaveImportRow])
def imported_leave_rows(
    year: int = Query(default=2026, ge=2000, le=2100),
    db: Session = Depends(get_db),
    _: User = Depends(RequireHrAdmin),
):
    ensure_rlb_2026_staging(db)
    db.commit()
    rows = (
        db.query(HrLeaveImportPerson)
        .options(joinedload(HrLeaveImportPerson.linked_user), joinedload(HrLeaveImportPerson.absences))
        .filter(HrLeaveImportPerson.year == year)
        .order_by(HrLeaveImportPerson.full_name)
        .all()
    )
    return [serialize_import_person(row) for row in rows]


@router.post("/admin/imported-leave/auto-link")
def auto_link_imported_leave(
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrAdmin),
):
    if not hr_source_available():
        raise HTTPException(status_code=409, detail="A HR import forrásfájl nincs telepítve.")
    stats = auto_apply_rlb_2026_imports(db)
    add_audit_log(
        db, current_user, "HR_RLB_IMPORT_AUTO_LINK", "hr_leave_import", None,
        f"RLB 2026 szabadságadatok automatikus párosítása: {stats}",
        after=stats,
    )
    db.commit()
    return stats


@router.post("/admin/imported-leave/{import_id}/link", response_model=HrLeaveImportRow)
def link_imported_leave(
    import_id: int,
    payload: HrLeaveImportLink,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrAdmin),
):
    person = (
        db.query(HrLeaveImportPerson)
        .options(joinedload(HrLeaveImportPerson.linked_user), joinedload(HrLeaveImportPerson.absences))
        .filter(HrLeaveImportPerson.id == import_id)
        .first()
    )
    if not person:
        raise HTTPException(status_code=404, detail="Importált szabadságadat nem található")
    user = _active_user(db, payload.user_id, "munkavállaló")
    if person.status == "applied" and person.linked_user_id not in {None, user.id}:
        raise HTTPException(status_code=409, detail="Az import már másik felhasználóhoz lett alkalmazva")
    before = serialize_import_person(person)
    applied = apply_import_person(db, person, user, allow_merge=payload.allow_merge)
    db.flush()
    person = (
        db.query(HrLeaveImportPerson)
        .options(joinedload(HrLeaveImportPerson.linked_user), joinedload(HrLeaveImportPerson.absences))
        .filter(HrLeaveImportPerson.id == import_id)
        .one()
    )
    after = serialize_import_person(person)
    add_audit_log(
        db, current_user, "HR_RLB_IMPORT_LINK", "hr_leave_import", person.id,
        f"RLB szabadságadat párosítás: {person.full_name} -> {user.full_name}; alkalmazva={applied}",
        entity_display_id=person.employee_number, before=before, after=after,
        result="success" if applied else "failure", severity="info" if applied else "warning",
    )
    db.commit()
    return after


@router.get("/admin/calendar", response_model=list[WorkCalendarDayRead])
def list_work_calendar(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    db: Session = Depends(get_db),
    _: User = Depends(RequireHrAdmin),
):
    return db.query(WorkCalendarDay).filter(
        WorkCalendarDay.calendar_date >= date(year, 1, 1),
        WorkCalendarDay.calendar_date <= date(year, 12, 31),
    ).order_by(WorkCalendarDay.calendar_date).all()


@router.put("/admin/calendar", response_model=WorkCalendarDayRead)
def upsert_work_calendar_day(
    payload: WorkCalendarDayUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrAdmin),
):
    row = db.query(WorkCalendarDay).filter(WorkCalendarDay.calendar_date == payload.calendar_date).first()
    before = snapshot_entity(row) if row else None
    if not row:
        row = WorkCalendarDay(calendar_date=payload.calendar_date, is_working_day=payload.is_working_day)
        db.add(row)
    row.is_working_day = payload.is_working_day
    row.label = (payload.label or "").strip() or None
    db.flush()
    add_audit_log(
        db,
        current_user,
        "WORK_CALENDAR_DAY_UPSERT",
        "work_calendar_day",
        row.id,
        f"Munkanaptár-kivétel mentve: {payload.calendar_date.isoformat()}",
        entity_display_id=payload.calendar_date.isoformat(),
        before=before,
        after=snapshot_entity(row),
    )
    db.commit()
    db.refresh(row)
    return row


@router.delete("/admin/calendar/{calendar_date}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_calendar_day(
    calendar_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireHrAdmin),
):
    row = db.query(WorkCalendarDay).filter(WorkCalendarDay.calendar_date == calendar_date).first()
    if not row:
        raise HTTPException(status_code=404, detail="Munkanaptár-kivétel nem található")
    before = snapshot_entity(row)
    add_audit_log(
        db,
        current_user,
        "WORK_CALENDAR_DAY_DELETE",
        "work_calendar_day",
        row.id,
        f"Munkanaptár-kivétel törölve: {calendar_date.isoformat()}",
        entity_display_id=calendar_date.isoformat(),
        before=before,
        after=None,
    )
    db.delete(row)
    db.commit()
    return None
