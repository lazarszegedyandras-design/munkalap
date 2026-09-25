from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import RequireCrmAccess, RequireHrSummaryView, RequireServiceAccess
from ..models import CrmActivity, CrmContract, CrmOpportunity, EmployeeProfile, LeaveRequest, User, WorkOrder
from ..services.hr_leave import count_workdays, leave_balance

router = APIRouter(prefix="/reports", tags=["reports"])


def _safe_csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv(filename: str, headers: list[str], rows: list[list]) -> StreamingResponse:
    buffer = StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow([_safe_csv_cell(value) for value in headers])
    writer.writerows([[_safe_csv_cell(value) for value in row] for row in rows])
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = date.today()
    start = date_from or today.replace(day=1)
    end = date_to or today
    if end < start:
        start, end = end, start
    return start, end


def _service_data(db: Session, date_from: date, date_to: date) -> dict:
    rows = db.query(WorkOrder).options(joinedload(WorkOrder.technician), joinedload(WorkOrder.secondary_technician)).filter(
        WorkOrder.planned_date >= date_from,
        WorkOrder.planned_date <= date_to,
        WorkOrder.status != "törölve / sztornózva",
    ).all()
    by_status: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    by_technician: dict[str, dict] = {}
    total_labor = Decimal("0")
    closed = urgent = 0
    for row in rows:
        by_status[row.status] += 1
        by_type[row.work_type or "Nincs megadva"] += 1
        if row.status == "lezárva":
            closed += 1
        if row.priority == "sürgős":
            urgent += 1
        if row.labor_hours is not None:
            total_labor += Decimal(str(row.labor_hours))
        technicians = [u for u in (row.technician, row.secondary_technician) if u]
        if not technicians:
            technicians = [None]
        for tech in technicians:
            name = tech.full_name if tech else "Nincs kijelölve"
            item = by_technician.setdefault(name, {"technician_name": name, "work_order_count": 0, "closed_count": 0, "labor_hours": Decimal("0")})
            item["work_order_count"] += 1
            if row.status == "lezárva": item["closed_count"] += 1
            if row.labor_hours is not None: item["labor_hours"] += Decimal(str(row.labor_hours))
    return {
        "date_from": date_from,
        "date_to": date_to,
        "work_order_count": len(rows),
        "closed_count": closed,
        "urgent_count": urgent,
        "labor_hours": total_labor,
        "by_status": dict(sorted(by_status.items())),
        "by_work_type": dict(sorted(by_type.items())),
        "by_technician": sorted(by_technician.values(), key=lambda x: (-x["work_order_count"], x["technician_name"])),
    }


@router.get("/service")
def service_report(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _=Depends(RequireServiceAccess),
):
    start, end = _period(date_from, date_to)
    return _service_data(db, start, end)


@router.get("/service.csv")
def service_report_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _=Depends(RequireServiceAccess),
):
    start, end = _period(date_from, date_to)
    data = _service_data(db, start, end)
    rows = [[r["technician_name"], r["work_order_count"], r["closed_count"], r["labor_hours"]] for r in data["by_technician"]]
    return _csv(f"szerviz-riport-{start}-{end}.csv", ["Technikus", "Munkalap", "Lezárt", "Munkaóra"], rows)


def _hr_data(db: Session, year: int) -> dict:
    profiles = db.query(EmployeeProfile).options(joinedload(EmployeeProfile.user)).filter(EmployeeProfile.active.is_(True)).order_by(EmployeeProfile.organizational_unit, EmployeeProfile.user_id).all()
    units: dict[str, dict] = {}
    totals = {"employee_count": 0, "total_days": Decimal("0"), "approved_days": Decimal("0"), "pending_days": Decimal("0"), "remaining_days": Decimal("0"), "sick_leave_used_days": Decimal("0")}
    for profile in profiles:
        balance = leave_balance(db, profile, year)
        unit_name = profile.organizational_unit or "Nincs megadva"
        unit = units.setdefault(unit_name, {"organizational_unit": unit_name, "employee_count": 0, "total_days": Decimal("0"), "approved_days": Decimal("0"), "pending_days": Decimal("0"), "remaining_days": Decimal("0"), "sick_leave_used_days": Decimal("0")})
        for target in (unit, totals):
            target["employee_count"] += 1
            for key in ("total_days", "approved_days", "pending_days", "remaining_days", "sick_leave_used_days"):
                target[key] += balance[key]
    monthly = {month: {"month": month, "approved_days": Decimal("0"), "pending_days": Decimal("0")} for month in range(1, 13)}
    requests = db.query(LeaveRequest).filter(
        LeaveRequest.start_date >= date(year, 1, 1),
        LeaveRequest.start_date <= date(year, 12, 31),
        LeaveRequest.status.in_(["approved", "pending"]),
        LeaveRequest.leave_type == "annual_leave",
    ).all()
    for req in requests:
        key = "approved_days" if req.status == "approved" else "pending_days"
        month = req.start_date.month
        while month <= req.end_date.month:
            segment_start = max(req.start_date, date(year, month, 1))
            next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
            segment_end = min(req.end_date, next_month - timedelta(days=1))
            monthly[month][key] += count_workdays(db, segment_start, segment_end)
            month += 1
    return {"year": year, **totals, "by_organizational_unit": sorted(units.values(), key=lambda x: x["organizational_unit"]), "monthly": list(monthly.values())}


@router.get("/hr")
def hr_report(
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    _=Depends(RequireHrSummaryView),
):
    return _hr_data(db, year or date.today().year)


@router.get("/hr.csv")
def hr_report_csv(
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    _=Depends(RequireHrSummaryView),
):
    resolved_year = year or date.today().year
    data = _hr_data(db, resolved_year)
    rows = [[r["organizational_unit"], r["employee_count"], r["total_days"], r["approved_days"], r["pending_days"], r["remaining_days"], r["sick_leave_used_days"]] for r in data["by_organizational_unit"]]
    return _csv(f"hr-riport-{resolved_year}.csv", ["Szervezeti egység", "Munkavállalók", "Éves keret", "Jóváhagyott", "Függőben", "Maradék", "Betegszabadság kiadott"], rows)


def _crm_data(db: Session, date_from: date, date_to: date) -> dict:
    start_dt = datetime.combine(date_from, datetime.min.time())
    end_dt = datetime.combine(date_to + timedelta(days=1), datetime.min.time())
    opportunities = db.query(CrmOpportunity).options(joinedload(CrmOpportunity.owner)).filter(
        CrmOpportunity.created_at >= start_dt,
        CrmOpportunity.created_at < end_dt,
    ).all()
    stages: dict[str, dict] = {}
    won = lost = 0
    open_value = Decimal("0")
    weighted = Decimal("0")
    for row in opportunities:
        item = stages.setdefault(row.stage, {"stage": row.stage, "count": 0, "value": Decimal("0")})
        item["count"] += 1
        value = Decimal(str(row.estimated_value or 0))
        item["value"] += value
        if row.stage == "nyert": won += 1
        elif row.stage == "elvesztett": lost += 1
        else:
            open_value += value
            probability = Decimal(str(row.probability if row.probability is not None else 0)) / Decimal("100")
            weighted += value * probability
    activity_rows = db.query(CrmActivity.activity_type, func.count(CrmActivity.id)).filter(
        CrmActivity.created_at >= start_dt, CrmActivity.created_at < end_dt
    ).group_by(CrmActivity.activity_type).all()
    expiring = db.query(CrmContract).options(joinedload(CrmContract.customer)).filter(
        CrmContract.status == "aktív",
        CrmContract.end_date.is_not(None),
        CrmContract.end_date >= date_from,
        CrmContract.end_date <= date_to,
    ).order_by(CrmContract.end_date).all()
    return {
        "date_from": date_from,
        "date_to": date_to,
        "opportunity_count": len(opportunities),
        "won_count": won,
        "lost_count": lost,
        "open_pipeline_value": open_value,
        "weighted_pipeline_value": weighted.quantize(Decimal("0.01")),
        "by_stage": sorted(stages.values(), key=lambda x: x["stage"]),
        "activities_by_type": {kind: count for kind, count in activity_rows},
        "expiring_contracts": [{"id": c.id, "contract_number": c.contract_number, "customer_name": c.customer.name if c.customer else "", "end_date": c.end_date, "contract_type": c.contract_type} for c in expiring],
    }


@router.get("/crm")
def crm_report(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _=Depends(RequireCrmAccess),
):
    start, end = _period(date_from, date_to)
    return _crm_data(db, start, end)


@router.get("/crm.csv")
def crm_report_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _=Depends(RequireCrmAccess),
):
    start, end = _period(date_from, date_to)
    data = _crm_data(db, start, end)
    rows = [[r["stage"], r["count"], r["value"]] for r in data["by_stage"]]
    return _csv(f"crm-pipeline-riport-{start}-{end}.csv", ["Szakasz", "Lehetőségek", "Érték"], rows)

@router.get("/crm-opportunities.csv")
def crm_opportunities_csv(
    customer_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(RequireCrmAccess),
):
    query = db.query(CrmOpportunity).options(joinedload(CrmOpportunity.customer), joinedload(CrmOpportunity.owner)).order_by(CrmOpportunity.updated_at.desc())
    if customer_id:
        query = query.filter(CrmOpportunity.customer_id == customer_id)
    rows = query.all()
    return _csv(
        "crm-lehetosegek.csv",
        ["Ügyfél", "Lehetőség", "Szakasz", "Érték", "Deviza", "Valószínűség %", "Várható zárás", "Felelős", "Forrás", "Következő lépés"],
        [[r.customer.name if r.customer else "", r.title, r.stage, r.estimated_value or "", r.currency, r.probability if r.probability is not None else "", r.expected_close_date or "", r.owner.full_name if r.owner else "", r.source or "", r.next_step or ""] for r in rows],
    )


@router.get("/crm-activities.csv")
def crm_activities_csv(
    customer_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(RequireCrmAccess),
):
    query = db.query(CrmActivity).options(joinedload(CrmActivity.customer), joinedload(CrmActivity.owner)).order_by(CrmActivity.created_at.desc())
    if customer_id:
        query = query.filter(CrmActivity.customer_id == customer_id)
    rows = query.all()
    return _csv(
        "crm-aktivitasok.csv",
        ["Ügyfél", "Típus", "Tárgy", "Felelős", "Határidő", "Teljesítve", "Leírás"],
        [[r.customer.name if r.customer else "", r.activity_type, r.subject, r.owner.full_name if r.owner else "", r.due_at or "", r.completed_at or "", r.description or ""] for r in rows],
    )


@router.get("/crm-contracts.csv")
def crm_contracts_csv(
    customer_id: int | None = None,
    status: str | None = None,
    company_code: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(RequireCrmAccess),
):
    query = db.query(CrmContract).options(joinedload(CrmContract.customer)).order_by(CrmContract.end_date, CrmContract.contract_number)
    if customer_id:
        query = query.filter(CrmContract.customer_id == customer_id)
    if status:
        query = query.filter(CrmContract.status == status)
    if company_code:
        query = query.filter(CrmContract.company_code == company_code)
    rows = query.all()
    return _csv(
        "crm-szerzodesek.csv",
        ["Vállalkozó", "Szerződésszám", "Ügyfél", "Szerződő név", "Szerződő székhely", "Típus", "Tárgy", "Státusz", "Kezdet", "Lejárat", "Futamidő", "Számlázási gyakoriság", "Fizetési feltétel", "Számlázási név", "TIG / munkalap", "e-számla cím", "Díjmódosítás", "Elszámolási modell", "SLA", "Megjegyzés"],
        [[r.company_code, r.contract_number, r.customer.name if r.customer else "", r.contracting_party_name or "", r.contracting_party_address or "", r.contract_type, r.subject or "", r.status, r.start_date or "", r.end_date or "", r.term_text or "", r.billing_frequency or "", r.payment_terms or "", r.billing_name or "", r.service_confirmation or "", r.e_invoice_email or "", r.price_adjustment_terms or "", r.billing_model or "", r.sla or "", r.note or ""] for r in rows],
    )
