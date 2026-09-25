from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from ..models import Asset, AssetComponent, AssetComponentReplacement, AssetMeterReading

METER_STALE_DAYS = 30
FORECAST_WINDOW_DAYS = 180
AVERAGE_MONTH_DAYS = 30


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def latest_meter_reading(db: Session, asset_id: int) -> AssetMeterReading | None:
    return (
        db.query(AssetMeterReading)
        .filter(AssetMeterReading.asset_id == asset_id)
        .order_by(AssetMeterReading.recorded_at.desc(), AssetMeterReading.id.desc())
        .first()
    )


def calculate_monthly_usage(readings: list[AssetMeterReading]) -> tuple[float | None, int]:
    if len(readings) < 2:
        return None, len(readings)
    ordered = sorted(readings, key=lambda row: (row.recorded_at, row.id))
    latest = ordered[-1]
    cutoff = latest.recorded_at - timedelta(days=FORECAST_WINDOW_DAYS)
    recent = [row for row in ordered if row.recorded_at >= cutoff]
    if len(recent) < 2:
        recent = ordered
    first, last = recent[0], recent[-1]
    elapsed_days = (_naive(last.recorded_at) - _naive(first.recorded_at)).total_seconds() / 86400
    difference = last.value - first.value
    if elapsed_days <= 0 or difference <= 0:
        return None, len(recent)
    return difference / elapsed_days * AVERAGE_MONTH_DAYS, len(recent)


def component_forecast(component: AssetComponent, latest: AssetMeterReading | None, monthly_usage: float | None) -> dict:
    used_pages = None
    remaining_pages = None
    usage_percent = None
    forecast_at = None
    status = "insufficient_data"
    status_label = "Nincs elegendő adat"

    if latest and component.last_replacement_meter is not None:
        used_pages = latest.value - component.last_replacement_meter
        if component.expected_life_pages and component.expected_life_pages > 0 and used_pages >= 0:
            remaining_pages = component.expected_life_pages - used_pages
            usage_percent = max(0.0, min(100.0, used_pages / component.expected_life_pages * 100))
            if remaining_pages <= 0:
                status = "overdue"
                status_label = "Csere esedékes"
                forecast_at = latest.recorded_at
            elif monthly_usage and monthly_usage > 0:
                months_remaining = remaining_pages / monthly_usage
                days_remaining = max(1, math.ceil(months_remaining * AVERAGE_MONTH_DAYS))
                forecast_at = latest.recorded_at + timedelta(days=days_remaining)
                if days_remaining <= 30:
                    status = "due_30_days"
                    status_label = "30 napon belül várható"
                else:
                    status = "forecast_available"
                    status_label = "Előrejelzés elérhető"
            else:
                status_label = "Nincs elég számlálóadat"

    return {
        "id": component.id,
        "asset_id": component.asset_id,
        "name": component.name,
        "part_number": component.part_number,
        "expected_life_pages": component.expected_life_pages,
        "last_replacement_at": component.last_replacement_at,
        "last_replacement_meter": component.last_replacement_meter,
        "is_active": component.is_active,
        "note": component.note,
        "used_pages": used_pages,
        "remaining_pages": remaining_pages,
        "usage_percent": round(usage_percent, 1) if usage_percent is not None else None,
        "forecast_at": forecast_at,
        "forecast_status": status,
        "forecast_status_label": status_label,
    }


def reading_to_dict(row: AssetMeterReading) -> dict:
    return {
        "id": row.id,
        "asset_id": row.asset_id,
        "value": row.value,
        "black_white_value": row.black_white_value,
        "color_value": row.color_value,
        "scan_value": row.scan_value,
        "recorded_at": row.recorded_at,
        "work_order_id": row.work_order_id,
        "work_order_number": row.work_order.number if row.work_order else None,
        "recorded_by_user_id": row.recorded_by_user_id,
        "recorded_by_name": row.recorded_by.full_name if row.recorded_by else None,
        "note": row.note,
        "created_at": row.created_at,
    }


def replacement_to_dict(row: AssetComponentReplacement) -> dict:
    return {
        "id": row.id,
        "asset_id": row.asset_id,
        "asset_component_id": row.asset_component_id,
        "component_name": row.component.name if row.component else None,
        "material_id": row.material_id,
        "material_name": row.material.name if row.material else None,
        "material_sku": row.material.sku if row.material else None,
        "work_order_id": row.work_order_id,
        "work_order_number": row.work_order.number if row.work_order else None,
        "technician_id": row.technician_id,
        "technician_name": row.technician.full_name if row.technician else None,
        "replaced_at": row.replaced_at,
        "meter_value": row.meter_value,
        "note": row.note,
        "created_at": row.created_at,
    }


def asset_printer_overview(db: Session, asset: Asset) -> dict:
    readings = (
        db.query(AssetMeterReading)
        .options(joinedload(AssetMeterReading.work_order), joinedload(AssetMeterReading.recorded_by))
        .filter(AssetMeterReading.asset_id == asset.id)
        .order_by(AssetMeterReading.recorded_at.desc(), AssetMeterReading.id.desc())
        .all()
    )
    latest = readings[0] if readings else None
    monthly_usage, usage_sample_count = calculate_monthly_usage(readings)
    components = (
        db.query(AssetComponent)
        .filter(AssetComponent.asset_id == asset.id)
        .order_by(AssetComponent.is_active.desc(), AssetComponent.name)
        .all()
    )
    replacements = (
        db.query(AssetComponentReplacement)
        .options(
            joinedload(AssetComponentReplacement.component),
            joinedload(AssetComponentReplacement.material),
            joinedload(AssetComponentReplacement.work_order),
            joinedload(AssetComponentReplacement.technician),
        )
        .filter(AssetComponentReplacement.asset_id == asset.id)
        .order_by(AssetComponentReplacement.replaced_at.desc(), AssetComponentReplacement.id.desc())
        .all()
    )
    now = datetime.utcnow()
    meter_age_days = None
    if latest:
        meter_age_days = max(0, (_naive(now) - _naive(latest.recorded_at)).days)
    forecasts = [component_forecast(component, latest, monthly_usage) for component in components]
    return {
        "asset": {
            "id": asset.id,
            "display_name": getattr(asset, "display_name", None) or asset.type or asset.model or asset.serial_number or f"Eszköz #{asset.id}",
            "serial_number": asset.serial_number,
            "manufacturer": asset.manufacturer,
            "model": asset.model,
            "customer_name": asset.customer.name if asset.customer else None,
            "location_name": asset.current_location.name if asset.current_location else None,
        },
        "latest_meter": reading_to_dict(latest) if latest else None,
        "meter_age_days": meter_age_days,
        "meter_is_stale": meter_age_days is None or meter_age_days > METER_STALE_DAYS,
        "average_monthly_usage": round(monthly_usage, 2) if monthly_usage is not None else None,
        "usage_sample_count": usage_sample_count,
        "readings": [reading_to_dict(row) for row in readings],
        "components": forecasts,
        "replacements": [replacement_to_dict(row) for row in replacements],
    }
