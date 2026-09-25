from __future__ import annotations

import json
import unicodedata
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..models import (
    EmployeeProfile,
    HrLeaveImportAbsence,
    HrLeaveImportPerson,
    LeaveEntitlement,
    LeaveRequest,
    User,
)

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "hr_leave_2026_rlb.json"
IMPORT_SOURCE = "rlb_pdf_2026"


def source_file() -> Path:
    runtime_file = Path(get_settings().runtime_dir) / DATA_FILE.name
    return runtime_file if runtime_file.is_file() else DATA_FILE


def source_available() -> bool:
    return source_file().is_file()


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _norm(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join("".join(ch for ch in normalized if not unicodedata.combining(ch)).lower().split())


def _source_reference(employee_number: str, leave_type: str, start_date: date, end_date: date) -> str:
    return f"rlb:2026:{employee_number}:{leave_type}:{start_date.isoformat()}:{end_date.isoformat()}"


def ensure_rlb_2026_staging(db: Session) -> list[HrLeaveImportPerson]:
    """Load the supplied 2026 RLB records into idempotent staging tables."""
    path = source_file()
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    year = int(payload["year"])
    source_record_date = date.fromisoformat(payload["source_record_date"])
    for person_data in payload["people"]:
        source_key = f"rlb:{year}:{person_data['employee_number']}"
        person = db.query(HrLeaveImportPerson).filter(HrLeaveImportPerson.source_key == source_key).first()
        if not person:
            person = HrLeaveImportPerson(source_key=source_key, year=year, employee_number=person_data["employee_number"], full_name=person_data["full_name"], source_file=person_data["source_file"])
            db.add(person)
            db.flush()
        person.full_name = person_data["full_name"]
        person.email_hint = (person_data.get("email_hint") or None)
        person.employee_number = person_data["employee_number"]
        person.employment_start_date = date.fromisoformat(person_data["employment_start_date"]) if person_data.get("employment_start_date") else None
        person.job_title = person_data.get("job_title") or None
        person.base_days = _decimal(person_data.get("base_days"))
        person.child_days = _decimal(person_data.get("child_days"))
        person.sick_leave_days = _decimal(person_data.get("sick_leave_days"))
        person.source_file = person_data["source_file"]
        person.source_record_date = source_record_date

        known_refs = {row.source_reference for row in person.absences}
        for leave_type, start, end, days in person_data.get("absences", []):
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            ref = _source_reference(person.employee_number, leave_type, start_date, end_date)
            if ref in known_refs:
                continue
            db.add(HrLeaveImportAbsence(
                import_person_id=person.id,
                leave_type=leave_type,
                start_date=start_date,
                end_date=end_date,
                days=_decimal(days),
                source_reference=ref,
            ))
    db.flush()
    db.expire_all()
    return db.query(HrLeaveImportPerson).options(joinedload(HrLeaveImportPerson.absences), joinedload(HrLeaveImportPerson.linked_user)).filter(HrLeaveImportPerson.year == year).order_by(HrLeaveImportPerson.full_name).all()


def _candidate_users(db: Session, person: HrLeaveImportPerson) -> list[User]:
    candidates: list[User] = []
    if person.email_hint:
        user = db.query(User).filter(func.lower(User.email) == person.email_hint.lower()).first()
        if user:
            candidates.append(user)
    exact_name = db.query(User).filter(func.lower(User.full_name) == person.full_name.lower()).all()
    for user in exact_name:
        if user not in candidates:
            candidates.append(user)
    if not candidates:
        target = _norm(person.full_name)
        for user in db.query(User).all():
            if _norm(user.full_name) == target:
                candidates.append(user)
    return candidates


def _existing_year_requests(db: Session, profile_id: int, year: int) -> list[LeaveRequest]:
    return db.query(LeaveRequest).filter(
        LeaveRequest.employee_id == profile_id,
        LeaveRequest.start_date >= date(year, 1, 1),
        LeaveRequest.start_date <= date(year, 12, 31),
    ).all()


def apply_import_person(db: Session, person: HrLeaveImportPerson, user: User, *, allow_merge: bool = False) -> bool:
    """Apply one staged source record to a user without silently overwriting conflicting HR history."""
    profile = db.query(EmployeeProfile).filter(EmployeeProfile.user_id == user.id).first()
    if profile and profile.employee_number and profile.employee_number != person.employee_number:
        person.linked_user_id = user.id
        person.status = "conflict"
        person.status_message = f"A felhasználó HR törzsszáma eltér: {profile.employee_number} != {person.employee_number}."
        return False

    duplicate_profile = db.query(EmployeeProfile).filter(
        EmployeeProfile.employee_number == person.employee_number,
        EmployeeProfile.user_id != user.id,
    ).first()
    if duplicate_profile:
        person.linked_user_id = user.id
        person.status = "conflict"
        person.status_message = "A forrás törzsszáma már másik HR profilhoz tartozik."
        return False

    if not profile:
        profile = EmployeeProfile(user_id=user.id, active=True)
        db.add(profile)
        db.flush()
    profile.employee_number = person.employee_number
    profile.employment_start_date = person.employment_start_date
    profile.job_title = person.job_title
    if not profile.company_code:
        profile.company_code = "DRH"

    entitlement = db.query(LeaveEntitlement).filter(
        LeaveEntitlement.employee_id == profile.id,
        LeaveEntitlement.year == person.year,
    ).first()
    source_total = _decimal(person.base_days) + _decimal(person.child_days)
    if entitlement:
        current_total = _decimal(entitlement.base_days) + _decimal(getattr(entitlement, "child_days", 0)) + _decimal(entitlement.carried_days) + _decimal(entitlement.adjustment_days)
        source_shape = (
            _decimal(person.base_days), _decimal(person.child_days), _decimal(person.sick_leave_days), Decimal("0.00"), Decimal("0.00")
        )
        current_shape = (
            _decimal(entitlement.base_days), _decimal(getattr(entitlement, "child_days", 0)), _decimal(getattr(entitlement, "sick_leave_days", 0)), _decimal(entitlement.carried_days), _decimal(entitlement.adjustment_days)
        )
        if current_shape != source_shape and not allow_merge:
            person.linked_user_id = user.id
            person.status = "conflict"
            person.status_message = f"Már van eltérő {person.year}. évi szabadságkeret ({current_total} nap); automatikus felülírás nem történt."
            return False
    else:
        entitlement = LeaveEntitlement(employee_id=profile.id, year=person.year)
        db.add(entitlement)

    existing_requests = _existing_year_requests(db, profile.id, person.year)
    non_imported = [row for row in existing_requests if row.source != IMPORT_SOURCE]
    if non_imported and not allow_merge:
        # If all manually existing rows are exact counterparts of the source rows, it is safe to keep them and apply only metadata.
        source_keys = {(a.leave_type, a.start_date, a.end_date, _decimal(a.days)) for a in person.absences}
        existing_keys = {(getattr(r, "leave_type", "annual_leave"), r.start_date, r.end_date, _decimal(r.requested_days)) for r in non_imported if r.status == "approved"}
        if not existing_keys.issubset(source_keys):
            person.linked_user_id = user.id
            person.status = "conflict"
            person.status_message = f"Már vannak {person.year}. évi HR távolléti adatok; automatikus összefésülés nem történt."
            return False

    entitlement.base_days = _decimal(person.base_days)
    entitlement.child_days = _decimal(person.child_days)
    entitlement.sick_leave_days = _decimal(person.sick_leave_days)
    entitlement.carried_days = Decimal("0.00")
    entitlement.adjustment_days = Decimal("0.00")
    entitlement.note = f"RLB szabadságnyilvántartás import, forrásnap: {person.source_record_date.isoformat() if person.source_record_date else person.year}."

    existing_exact = {
        (getattr(row, "leave_type", "annual_leave"), row.start_date, row.end_date, _decimal(row.requested_days))
        for row in existing_requests if row.status == "approved"
    }
    recorded_at = datetime.combine(person.source_record_date or date(person.year, 12, 31), time.min)
    for absence in person.absences:
        if db.query(LeaveRequest.id).filter(LeaveRequest.source_reference == absence.source_reference).first():
            continue
        key = (absence.leave_type, absence.start_date, absence.end_date, _decimal(absence.days))
        if key in existing_exact:
            continue
        db.add(LeaveRequest(
            employee_id=profile.id,
            approver_user_id=None,
            start_date=absence.start_date,
            end_date=absence.end_date,
            requested_days=_decimal(absence.days),
            status="approved",
            leave_type=absence.leave_type,
            source=IMPORT_SOURCE,
            source_reference=absence.source_reference,
            source_record_date=person.source_record_date,
            employee_comment=None,
            approver_comment=None,
            submitted_at=recorded_at,
            decided_at=None,
            version=1,
        ))

    person.linked_user_id = user.id
    person.status = "applied"
    person.status_message = f"Import alkalmazva: {user.full_name}."
    person.applied_at = datetime.utcnow()
    db.flush()
    return True


def auto_apply_rlb_2026_imports(db: Session) -> dict[str, int]:
    people = ensure_rlb_2026_staging(db)
    stats = {"applied": 0, "pending": 0, "conflict": 0, "ambiguous": 0}
    for person in people:
        if person.status == "applied":
            stats["applied"] += 1
            continue
        candidates = _candidate_users(db, person)
        if len(candidates) == 1:
            applied = apply_import_person(db, person, candidates[0])
            stats["applied" if applied else "conflict"] += 1
        elif len(candidates) > 1:
            person.status = "ambiguous"
            person.status_message = "Több lehetséges felhasználó található; kézi párosítás szükséges."
            stats["ambiguous"] += 1
        else:
            person.status = "pending"
            person.status_message = "Nincs automatikusan párosítható felhasználó; HR admin párosítás szükséges."
            stats["pending"] += 1
    db.commit()
    return stats


def serialize_import_person(person: HrLeaveImportPerson) -> dict:
    return {
        "id": person.id,
        "year": person.year,
        "full_name": person.full_name,
        "email_hint": person.email_hint,
        "employee_number": person.employee_number,
        "employment_start_date": person.employment_start_date,
        "job_title": person.job_title,
        "base_days": _decimal(person.base_days),
        "child_days": _decimal(person.child_days),
        "sick_leave_days": _decimal(person.sick_leave_days),
        "source_file": person.source_file,
        "source_record_date": person.source_record_date,
        "linked_user_id": person.linked_user_id,
        "linked_user_name": person.linked_user.full_name if person.linked_user else None,
        "status": person.status,
        "status_message": person.status_message,
        "absence_count": len(person.absences),
        "annual_used_days": sum((_decimal(row.days) for row in person.absences if row.leave_type == "annual_leave"), Decimal("0.00")),
        "sick_used_days": sum((_decimal(row.days) for row in person.absences if row.leave_type == "sick_leave"), Decimal("0.00")),
    }
