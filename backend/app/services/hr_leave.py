from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from ..models import EmployeeProfile, LeaveEntitlement, LeaveRequest, User, WorkCalendarDay

ZERO = Decimal("0.00")


def decimal_days(value) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(Decimal("0.01"))


def get_employee_profile(db: Session, user_id: int, *, required: bool = True) -> EmployeeProfile | None:
    profile = (
        db.query(EmployeeProfile)
        .options(joinedload(EmployeeProfile.user), joinedload(EmployeeProfile.manager), joinedload(EmployeeProfile.leave_approver))
        .filter(EmployeeProfile.user_id == user_id)
        .first()
    )
    if required and (profile is None or not profile.active):
        raise HTTPException(status_code=409, detail="A felhasználóhoz nincs aktív HR munkavállalói profil beállítva")
    return profile


def get_entitlement(db: Session, employee_id: int, year: int) -> LeaveEntitlement | None:
    return db.query(LeaveEntitlement).filter(
        LeaveEntitlement.employee_id == employee_id,
        LeaveEntitlement.year == year,
    ).first()


def count_workdays(db: Session, start_date: date, end_date: date) -> Decimal:
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="A zárónap nem lehet korábbi a kezdőnapnál")
    overrides = {
        row.calendar_date: row.is_working_day
        for row in db.query(WorkCalendarDay).filter(
            WorkCalendarDay.calendar_date >= start_date,
            WorkCalendarDay.calendar_date <= end_date,
        ).all()
    }
    current = start_date
    days = 0
    while current <= end_date:
        is_working = overrides.get(current, current.weekday() < 5)
        if is_working:
            days += 1
        current += timedelta(days=1)
    return Decimal(days).quantize(Decimal("0.01"))


def leave_balance(db: Session, profile: EmployeeProfile, year: int) -> dict:
    entitlement = get_entitlement(db, profile.id, year)
    base = decimal_days(entitlement.base_days if entitlement else 0)
    carried = decimal_days(entitlement.carried_days if entitlement else 0)
    adjustment = decimal_days(entitlement.adjustment_days if entitlement else 0)
    child = decimal_days(entitlement.child_days if entitlement else 0)
    sick_entitlement = decimal_days(entitlement.sick_leave_days if entitlement else 0)
    total = base + child + carried + adjustment

    rows = db.query(LeaveRequest).filter(
        LeaveRequest.employee_id == profile.id,
        LeaveRequest.start_date >= date(year, 1, 1),
        LeaveRequest.start_date <= date(year, 12, 31),
        LeaveRequest.status.in_(["pending", "approved"]),
    ).all()
    annual_rows = [row for row in rows if getattr(row, "leave_type", "annual_leave") == "annual_leave"]
    sick_rows = [row for row in rows if getattr(row, "leave_type", "annual_leave") == "sick_leave"]
    approved = sum((decimal_days(row.requested_days) for row in annual_rows if row.status == "approved"), ZERO)
    pending = sum((decimal_days(row.requested_days) for row in annual_rows if row.status == "pending"), ZERO)
    sick_used = sum((decimal_days(row.requested_days) for row in sick_rows if row.status == "approved"), ZERO)
    remaining = total - approved
    available = total - approved - pending
    return {
        "year": year,
        "base_days": base,
        "carried_days": carried,
        "adjustment_days": adjustment,
        "child_days": child,
        "total_days": total,
        "approved_days": approved,
        "pending_days": pending,
        "remaining_days": remaining,
        "available_to_request_days": available,
        "sick_leave_entitlement_days": sick_entitlement,
        "sick_leave_used_days": sick_used,
        "sick_leave_remaining_days": sick_entitlement - sick_used,
    }


def serialize_profile(profile: EmployeeProfile) -> dict:
    def user_data(user: User | None):
        if not user:
            return None
        return {"id": user.id, "full_name": user.full_name, "email": user.email}

    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "employee_number": profile.employee_number,
        "company_code": profile.company_code,
        "organizational_unit": profile.organizational_unit,
        "job_title": profile.job_title,
        "manager_user_id": profile.manager_user_id,
        "leave_approver_user_id": profile.leave_approver_user_id,
        "employment_start_date": profile.employment_start_date,
        "employment_end_date": profile.employment_end_date,
        "active": profile.active,
        "user": user_data(profile.user),
        "manager": user_data(profile.manager),
        "leave_approver": user_data(profile.leave_approver),
    }


def serialize_entitlement(entitlement: LeaveEntitlement) -> dict:
    total = decimal_days(entitlement.base_days) + decimal_days(entitlement.child_days) + decimal_days(entitlement.carried_days) + decimal_days(entitlement.adjustment_days)
    return {
        "id": entitlement.id,
        "employee_id": entitlement.employee_id,
        "year": entitlement.year,
        "base_days": decimal_days(entitlement.base_days),
        "carried_days": decimal_days(entitlement.carried_days),
        "adjustment_days": decimal_days(entitlement.adjustment_days),
        "child_days": decimal_days(entitlement.child_days),
        "sick_leave_days": decimal_days(entitlement.sick_leave_days),
        "note": entitlement.note,
        "total_days": total,
    }


def serialize_leave_request(row: LeaveRequest) -> dict:
    approval_kind = None
    if row.status == "pending":
        approval_kind = "leave_request"
    elif getattr(row, "cancellation_status", None) == "pending":
        approval_kind = "cancellation"
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "employee_user_id": row.employee.user_id,
        "employee_name": row.employee.user.full_name,
        "approver_user_id": row.approver_user_id,
        "approver_name": row.approver.full_name if row.approver else None,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "requested_days": decimal_days(row.requested_days),
        "status": row.status,
        "leave_type": getattr(row, "leave_type", "annual_leave"),
        "source": getattr(row, "source", "workflow"),
        "source_record_date": getattr(row, "source_record_date", None),
        "employee_comment": row.employee_comment,
        "approver_comment": row.approver_comment,
        "submitted_at": row.submitted_at,
        "decided_at": row.decided_at,
        "cancelled_at": row.cancelled_at,
        "cancellation_status": getattr(row, "cancellation_status", None),
        "cancellation_approver_user_id": getattr(row, "cancellation_approver_user_id", None),
        "cancellation_approver_name": row.cancellation_approver.full_name if getattr(row, "cancellation_approver", None) else None,
        "cancellation_comment": getattr(row, "cancellation_comment", None),
        "cancellation_approver_comment": getattr(row, "cancellation_approver_comment", None),
        "cancellation_requested_at": getattr(row, "cancellation_requested_at", None),
        "cancellation_decided_at": getattr(row, "cancellation_decided_at", None),
        "approval_kind": approval_kind,
        "version": row.version,
    }


def validate_request_dates(profile: EmployeeProfile, start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="A zárónap nem lehet korábbi a kezdőnapnál")
    if start_date.year != end_date.year:
        raise HTTPException(status_code=400, detail="Egy szabadságigény nem nyúlhat át másik naptári évre")
    if profile.employment_start_date and start_date < profile.employment_start_date:
        raise HTTPException(status_code=400, detail="A szabadság kezdete nem lehet korábbi a munkaviszony kezdeténél")
    if profile.employment_end_date and end_date > profile.employment_end_date:
        raise HTTPException(status_code=400, detail="A szabadság vége nem lehet későbbi a munkaviszony végénél")


def ensure_no_overlap(db: Session, employee_id: int, start_date: date, end_date: date) -> None:
    overlap = db.query(LeaveRequest).filter(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status.in_(["pending", "approved"]),
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
    ).first()
    if overlap:
        raise HTTPException(status_code=409, detail="A megadott időszak átfed egy már függőben lévő vagy jóváhagyott szabadsággal")
