from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import get_current_user
from ..models import Asset, AssetComponent, EmployeeProfile, LeaveRequest, ROLE_TECHNICIAN, Role, User, WorkOrder
from ..services.asset_display import asset_display_name
from ..services.printer_tracking import asset_printer_overview
from ..services.maintenance_schedule import maintenance_snapshot

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    today = date.today()
    open_statuses = ["új", "ütemezve", "folyamatban", "várakozik", "kész"]
    maintenance_assets = db.query(Asset).filter(Asset.status != "selejtezett").all()
    maintenance_states = [maintenance_snapshot(asset, today)["maintenance_state"] for asset in maintenance_assets]
    return {
        "open_work_orders": db.query(func.count(WorkOrder.id)).filter(WorkOrder.status.in_(open_statuses)).scalar(),
        "urgent_work_orders": db.query(func.count(WorkOrder.id)).filter(WorkOrder.priority == "sürgős", WorkOrder.status.in_(open_statuses)).scalar(),
        "due_today_work_orders": db.query(func.count(WorkOrder.id)).filter(WorkOrder.planned_date == today, WorkOrder.status.in_(open_statuses)).scalar(),
        "due_maintenance_assets": sum(state == "overdue" for state in maintenance_states),
        "due_soon_maintenance_assets": sum(state == "due_30_days" for state in maintenance_states),
        "missing_maintenance_assets": sum(state == "missing_last" for state in maintenance_states),
        "faulty_assets": db.query(func.count(Asset.id)).filter(Asset.status.in_(["hibás", "javítás alatt"])).scalar(),
    }


@router.get("/maintenance-planning")
def maintenance_planning(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    today = date.today()
    assets = (
        db.query(Asset)
        .options(joinedload(Asset.customer), joinedload(Asset.current_location))
        .filter(Asset.status != "selejtezett")
        .order_by(Asset.id)
        .all()
    )
    items = []
    for asset in assets:
        snapshot = maintenance_snapshot(asset, today)
        if snapshot["maintenance_state"] not in {"overdue", "due_30_days", "missing_last"}:
            continue
        items.append({
            "asset_id": asset.id,
            "asset_name": asset_display_name(asset),
            "company_code": asset.company_code,
            "customer_name": asset.customer.name if asset.customer else None,
            "location_name": asset.current_location.name if asset.current_location else None,
            "last_maintenance_date": asset.last_maintenance_date,
            **snapshot,
        })
    priority = {"overdue": 0, "due_30_days": 1, "missing_last": 2}
    items.sort(
        key=lambda item: (
            priority.get(item["maintenance_state"], 99),
            item["effective_next_maintenance_date"] or date.max,
            item["asset_name"].casefold(),
        )
    )
    return {
        "overdue_count": sum(item["maintenance_state"] == "overdue" for item in items),
        "due_30_days_count": sum(item["maintenance_state"] == "due_30_days" for item in items),
        "missing_last_count": sum(item["maintenance_state"] == "missing_last" for item in items),
        "items": items,
    }


def _event_interval(order: WorkOrder) -> tuple[datetime, datetime, str] | None:
    """Return the interval displayed in the weekly calendar.

    Closed work orders prefer actual timestamps. Open work orders prefer planned
    timestamps. Historical records without exact times fall back to a one-hour
    block on the planned date so they remain visible and can be corrected.
    """
    is_closed = order.status == "lezárva" or order.closed_at is not None

    if is_closed and order.started_at and order.completed_at:
        start, end, source = order.started_at, order.completed_at, "actual"
    elif is_closed and order.planned_start_at and order.completed_at and order.completed_at > order.planned_start_at:
        start, end, source = order.planned_start_at, order.completed_at, "mixed"
    elif is_closed and order.completed_at and order.labor_hours is not None and float(order.labor_hours) > 0:
        end = order.completed_at
        start = end - timedelta(hours=float(order.labor_hours))
        source = "labor_derived"
    elif order.planned_start_at:
        start = order.planned_start_at
        end = order.planned_end_at or (start + timedelta(hours=1))
        source = "planned"
    elif order.started_at:
        start = order.started_at
        end = order.completed_at or (start + timedelta(hours=1))
        source = "actual" if is_closed else "in_progress"
    elif order.planned_date:
        start = datetime.combine(order.planned_date, time(hour=9))
        end = start + timedelta(hours=1)
        source = "date_fallback"
    else:
        return None

    if end <= start:
        end = start + timedelta(hours=1)
    return start, end, source


@router.get("/calendar")
def weekly_calendar(
    week_start: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    requested = week_start or date.today()
    monday = requested - timedelta(days=requested.weekday())
    next_monday = monday + timedelta(days=7)
    week_start_dt = datetime.combine(monday, time.min)
    week_end_dt = datetime.combine(next_monday, time.min)

    overlap_filter = or_(
        WorkOrder.planned_date.between(monday, next_monday - timedelta(days=1)),
        and_(
            WorkOrder.planned_start_at.isnot(None),
            WorkOrder.planned_start_at < week_end_dt,
            or_(WorkOrder.planned_end_at.is_(None), WorkOrder.planned_end_at > week_start_dt),
        ),
        and_(
            WorkOrder.started_at.isnot(None),
            WorkOrder.started_at < week_end_dt,
            or_(WorkOrder.completed_at.is_(None), WorkOrder.completed_at > week_start_dt),
        ),
    )

    orders = (
        db.query(WorkOrder)
        .options(
            joinedload(WorkOrder.customer),
            joinedload(WorkOrder.location),
            joinedload(WorkOrder.technician),
            joinedload(WorkOrder.secondary_technician),
        )
        .filter(WorkOrder.status != "törölve / sztornózva", overlap_filter)
        .order_by(WorkOrder.planned_date, WorkOrder.planned_start_at, WorkOrder.started_at, WorkOrder.id)
        .all()
    )

    events: list[dict] = []
    for order in orders:
        interval = _event_interval(order)
        if not interval:
            continue
        start, end, source = interval
        if start >= week_end_dt or end <= week_start_dt:
            continue
        events.append(
            {
                "id": order.id,
                "number": order.number,
                "status": order.status,
                "priority": order.priority,
                "is_closed": order.status == "lezárva" or order.closed_at is not None,
                "technician_id": order.technician_id or order.secondary_technician_id,
                "technician_ids": [technician_id for technician_id in (order.technician_id, order.secondary_technician_id) if technician_id is not None],
                "technician_name": ", ".join(
                    name
                    for name in (
                        order.technician.full_name if order.technician else None,
                        order.secondary_technician.full_name if order.secondary_technician else None,
                    )
                    if name
                ) or "Nincs kijelölve",
                "customer_name": order.customer.name if order.customer else "-",
                "location_name": order.location.name if order.location else None,
                "description": order.description,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration_source": source,
                "planned_start_at": order.planned_start_at.isoformat() if order.planned_start_at else None,
                "planned_end_at": order.planned_end_at.isoformat() if order.planned_end_at else None,
                "started_at": order.started_at.isoformat() if order.started_at else None,
                "completed_at": order.completed_at.isoformat() if order.completed_at else None,
            }
        )

    technicians = (
        db.query(User)
        .join(Role)
        .filter(Role.name == ROLE_TECHNICIAN, User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )

    leave_rows = (
        db.query(LeaveRequest)
        .join(EmployeeProfile, LeaveRequest.employee_id == EmployeeProfile.id)
        .join(User, EmployeeProfile.user_id == User.id)
        .join(Role, User.role_id == Role.id)
        .options(joinedload(LeaveRequest.employee).joinedload(EmployeeProfile.user))
        .filter(
            LeaveRequest.status == "approved",
            LeaveRequest.start_date < next_monday,
            LeaveRequest.end_date >= monday,
            EmployeeProfile.active.is_(True),
            User.is_active.is_(True),
            Role.name == ROLE_TECHNICIAN,
        )
        .order_by(LeaveRequest.start_date, User.full_name, LeaveRequest.id)
        .all()
    )

    return {
        "week_start": monday.isoformat(),
        "week_end": (next_monday - timedelta(days=1)).isoformat(),
        "days": [(monday + timedelta(days=offset)).isoformat() for offset in range(7)],
        "technicians": [{"id": user.id, "name": user.full_name} for user in technicians],
        "events": events,
        "leave_events": [
            {
                "id": row.id,
                "technician_id": row.employee.user_id,
                "technician_name": row.employee.user.full_name,
                "leave_type": row.leave_type,
                "start_date": row.start_date,
                "end_date": row.end_date,
            }
            for row in leave_rows
        ],
    }


@router.get("/printer-maintenance")
def printer_maintenance(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    assets = (
        db.query(Asset)
        .options(joinedload(Asset.customer), joinedload(Asset.current_location))
        .join(AssetComponent, AssetComponent.asset_id == Asset.id)
        .filter(Asset.status != "selejtezett", AssetComponent.is_active.is_(True))
        .distinct()
        .order_by(Asset.id)
        .all()
    )
    due_items = []
    stale_assets = []
    for asset in assets:
        overview = asset_printer_overview(db, asset)
        if overview["meter_is_stale"]:
            stale_assets.append({
                "asset_id": asset.id,
                "asset_name": asset_display_name(asset),
                "customer_name": asset.customer.name if asset.customer else None,
                "location_name": asset.current_location.name if asset.current_location else None,
                "latest_meter_value": overview["latest_meter"]["value"] if overview["latest_meter"] else None,
                "latest_meter_at": overview["latest_meter"]["recorded_at"] if overview["latest_meter"] else None,
                "meter_age_days": overview["meter_age_days"],
            })
        for component in overview["components"]:
            if not component["is_active"] or component["forecast_status"] not in {"overdue", "due_30_days"}:
                continue
            due_items.append({
                "asset_id": asset.id,
                "asset_name": asset_display_name(asset),
                "customer_name": asset.customer.name if asset.customer else None,
                "location_name": asset.current_location.name if asset.current_location else None,
                "component_id": component["id"],
                "component_name": component["name"],
                "part_number": component["part_number"],
                "remaining_pages": component["remaining_pages"],
                "forecast_at": component["forecast_at"],
                "status": component["forecast_status"],
                "status_label": component["forecast_status_label"],
            })
    due_items.sort(key=lambda item: (0 if item["status"] == "overdue" else 1, item["forecast_at"] or datetime.max))
    stale_assets.sort(key=lambda item: (item["latest_meter_at"] is not None, item["latest_meter_at"] or datetime.min))
    return {
        "overdue_count": sum(1 for item in due_items if item["status"] == "overdue"),
        "due_30_days_count": sum(1 for item in due_items if item["status"] == "due_30_days"),
        "stale_meter_assets_count": len(stale_assets),
        "due_items": due_items,
        "stale_assets": stale_assets,
    }
