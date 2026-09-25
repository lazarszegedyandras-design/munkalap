from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import User, WorkOrder, WorkOrderCompletionSnapshot
from .asset_display import asset_display_name, visible_internal_id
from .company_profiles import resolve_work_order_company_profile


def _json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def canonical_snapshot_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def snapshot_sha256(payload: dict) -> str:
    return hashlib.sha256(canonical_snapshot_bytes(payload)).hexdigest()


def build_completion_snapshot_payload(order: WorkOrder, settings: Settings) -> dict:
    supplier = resolve_work_order_company_profile(order, settings)
    contact = order.contact
    if contact is None and order.customer and order.customer.contacts:
        contact = next((row for row in order.customer.contacts if row.is_primary), order.customer.contacts[0])

    assets = []
    for link in order.asset_links:
        asset = link.asset
        latest = max(asset.meter_readings, key=lambda row: (row.recorded_at, row.id), default=None)
        assets.append({
            "id": asset.id,
            "internal_id": visible_internal_id(asset.internal_id),
            "display_name": asset_display_name(asset),
            "manufacturer": asset.manufacturer,
            "model": asset.model,
            "serial_number": asset.serial_number,
            "type": asset.type,
            "latest_meter": None if latest is None else {
                "value": latest.value,
                "black_white_value": latest.black_white_value,
                "color_value": latest.color_value,
                "scan_value": latest.scan_value,
                "recorded_at": latest.recorded_at.isoformat(),
            },
        })

    photos = [
        {
            "id": photo.id,
            "category": photo.category,
            "note": photo.note,
            "sha256": photo.sha256,
            "size_bytes": photo.size_bytes,
            "mime_type": photo.mime_type,
            "width": photo.width,
            "height": photo.height,
            "created_at": photo.created_at.isoformat(),
        }
        for photo in order.photos
    ]

    materials = []
    for line in order.material_lines:
        materials.append({
            "material_id": line.material_id,
            "sku": line.material.sku,
            "name": line.material.name,
            "unit": line.material.unit,
            "quantity": _json_value(line.quantity),
            "unit_price": _json_value(line.unit_price),
            "note": line.note,
        })

    return {
        "schema_version": 1,
        "work_order": {
            "id": order.id,
            "number": order.number,
            "version": order.version,
            "status": order.status,
            "priority": order.priority,
            "work_type": order.work_type,
            "contract_type": order.contract_type,
            "description": order.description,
            "work_done": order.work_done,
            "final_status": order.final_status,
            "labor_hours": _json_value(order.labor_hours),
            "internal_note": order.internal_note,
            "customer_note": order.customer_note,
            "planned_date": _json_value(order.planned_date),
            "planned_start_at": _json_value(order.planned_start_at),
            "planned_end_at": _json_value(order.planned_end_at),
            "started_at": _json_value(order.started_at),
            "completed_at": _json_value(order.completed_at),
        },
        "customer": None if order.customer is None else {
            "id": order.customer.id,
            "name": order.customer.name,
            "address": order.customer.address,
            "phone": order.customer.phone,
            "email": order.customer.email,
            "company_code": order.customer.company_code,
        },
        "location": None if order.location is None else {
            "id": order.location.id,
            "name": order.location.name,
            "address": order.location.address,
        },
        "contact": None if contact is None else {
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "email": contact.email,
        },
        "contract": None if order.contract is None else {
            "id": order.contract.id,
            "number": order.contract.contract_number,
            "type": order.contract.contract_type,
            "status": order.contract.status,
        },
        "technicians": [
            {"id": user.id, "name": user.full_name}
            for user in (order.technician, order.secondary_technician)
            if user is not None
        ],
        "supplier": supplier.to_dict() if supplier else None,
        "assets": assets,
        "materials": materials,
        "photos": photos,
    }


def create_completion_snapshot(db: Session, order: WorkOrder, user: User, settings: Settings) -> WorkOrderCompletionSnapshot:
    current_revision = (
        db.query(func.max(WorkOrderCompletionSnapshot.revision))
        .filter(WorkOrderCompletionSnapshot.work_order_id == order.id)
        .scalar()
        or 0
    )
    payload = build_completion_snapshot_payload(order, settings)
    digest = snapshot_sha256(payload)
    row = WorkOrderCompletionSnapshot(
        work_order_id=order.id,
        revision=int(current_revision) + 1,
        source_work_order_version=order.version,
        snapshot_json=payload,
        snapshot_sha256=digest,
        created_by_user_id=user.id,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row
