from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from ..models import WorkOrder
from .notifications import create_notification


def capture_work_order_notification_state(order: WorkOrder) -> dict:
    return {
        "assigned_ids": {value for value in (order.technician_id, order.secondary_technician_id) if value is not None},
        "planned_date": order.planned_date,
        "planned_start_at": order.planned_start_at,
        "planned_end_at": order.planned_end_at,
    }


def _schedule_text(order: WorkOrder) -> str:
    if order.planned_start_at:
        return order.planned_start_at.strftime("%Y.%m.%d. %H:%M")
    if order.planned_date:
        return order.planned_date.strftime("%Y.%m.%d.")
    return "nincs időpont megadva"


def notify_work_order_changes(db: Session, order: WorkOrder, before: dict | None = None) -> None:
    current_ids = {value for value in (order.technician_id, order.secondary_technician_id) if value is not None}
    before_ids = set(before.get("assigned_ids", set())) if before else set()
    new_ids = current_ids - before_ids
    revision = int(order.version or 1) + (1 if before is not None else 0)

    for user_id in sorted(new_ids):
        create_notification(
            db,
            user_id=user_id,
            module="service",
            notification_type="work_order_assigned",
            title="Új munkalapot kaptál",
            message=f"{order.number} – {_schedule_text(order)}",
            link=f"/service/work-orders/{order.id}",
            source_type="work_order",
            source_id=order.id,
            dedupe_key=f"service:work-order:{order.id}:assigned:{user_id}:v{revision}",
        )

    if not before:
        return
    schedule_changed = any(
        before.get(key) != getattr(order, key)
        for key in ("planned_date", "planned_start_at", "planned_end_at")
    )
    if not schedule_changed:
        return
    for user_id in sorted(current_ids - new_ids):
        create_notification(
            db,
            user_id=user_id,
            module="service",
            notification_type="work_order_schedule_changed",
            title="Módosult a munkalap időpontja",
            message=f"{order.number} – új időpont: {_schedule_text(order)}",
            link=f"/service/work-orders/{order.id}",
            source_type="work_order",
            source_id=order.id,
            dedupe_key=f"service:work-order:{order.id}:schedule:{user_id}:v{revision}",
        )
