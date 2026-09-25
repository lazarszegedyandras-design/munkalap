from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from math import ceil
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..models import Asset, AssetComponent, AssetMeterReading
from .printer_tracking import METER_STALE_DAYS, calculate_monthly_usage, component_forecast
from .maintenance_schedule import maintenance_snapshot


FORECAST_PRIORITY = {
    "overdue": 0,
    "due_30_days": 1,
    "forecast_available": 2,
    "insufficient_data": 3,
}


ASSET_SORT_FIELDS = {
    "status",
    "company_code",
    "display_name",
    "customer_name",
    "location_name",
    "serial_number",
    "latest_meter_value",
    "next_event",
    "last_maintenance_date",
    "maintenance_cycle_months",
    "effective_next_maintenance_date",
    "maintenance_days_since_last",
    "updated_at",
}


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def _forecast_sort_key(item: dict) -> tuple[int, datetime]:
    forecast_at = item.get("forecast_at")
    if forecast_at is None:
        forecast_at = datetime.max
    return FORECAST_PRIORITY.get(item.get("forecast_status"), 99), _naive(forecast_at)


def build_asset_list_summaries(db: Session, assets: list[Asset]) -> dict[int, dict]:
    """Build list-view status summaries with batched tracking queries."""
    asset_ids = [asset.id for asset in assets]
    if not asset_ids:
        return {}

    readings_by_asset: dict[int, list[AssetMeterReading]] = defaultdict(list)
    for reading in (
        db.query(AssetMeterReading)
        .filter(AssetMeterReading.asset_id.in_(asset_ids))
        .order_by(AssetMeterReading.asset_id, AssetMeterReading.recorded_at.desc(), AssetMeterReading.id.desc())
        .all()
    ):
        readings_by_asset[reading.asset_id].append(reading)

    components_by_asset: dict[int, list[AssetComponent]] = defaultdict(list)
    for component in (
        db.query(AssetComponent)
        .filter(AssetComponent.asset_id.in_(asset_ids), AssetComponent.is_active.is_(True))
        .order_by(AssetComponent.asset_id, AssetComponent.name)
        .all()
    ):
        components_by_asset[component.asset_id].append(component)

    now = datetime.utcnow()
    today = now.date()
    result: dict[int, dict] = {}

    for asset in assets:
        readings = readings_by_asset.get(asset.id, [])
        latest = readings[0] if readings else None
        monthly_usage, _ = calculate_monthly_usage(readings)
        meter_age_days = None
        if latest:
            meter_age_days = max(0, (_naive(now) - _naive(latest.recorded_at)).days)
        meter_state = "missing" if latest is None else "stale" if meter_age_days > METER_STALE_DAYS else "fresh"
        meter_state_label = {
            "missing": "Nincs számlálóadat",
            "stale": "Elavult számlálóadat",
            "fresh": "Aktuális számlálóadat",
        }[meter_state]

        forecasts = [component_forecast(component, latest, monthly_usage) for component in components_by_asset.get(asset.id, [])]
        forecasts.sort(key=_forecast_sort_key)
        next_forecast = forecasts[0] if forecasts else None
        due_count = sum(item["forecast_status"] in {"overdue", "due_30_days"} for item in forecasts)
        if next_forecast:
            forecast_state = next_forecast["forecast_status"]
            forecast_state_label = next_forecast["forecast_status_label"]
        else:
            forecast_state = "none"
            forecast_state_label = "Nincs követett alkatrész"

        maintenance = maintenance_snapshot(asset, today)
        result[asset.id] = {
            "latest_meter_value": latest.value if latest else None,
            "latest_meter_at": latest.recorded_at if latest else None,
            "meter_age_days": meter_age_days,
            "meter_state": meter_state,
            "meter_state_label": meter_state_label,
            "average_monthly_usage": round(monthly_usage, 2) if monthly_usage is not None else None,
            "next_component_name": next_forecast["name"] if next_forecast else None,
            "next_component_forecast_at": next_forecast["forecast_at"] if next_forecast else None,
            "component_forecast_status": forecast_state,
            "component_forecast_status_label": forecast_state_label,
            "component_due_count": due_count,
            **maintenance,
        }

    return result


def filter_asset_list_rows(
    rows: list[dict],
    *,
    maintenance_state: str | None = None,
    meter_state: str | None = None,
    forecast_state: str | None = None,
) -> list[dict]:
    filtered = rows
    if maintenance_state:
        if maintenance_state == "due":
            allowed = {"overdue", "due_30_days"}
        elif maintenance_state == "needs_planning":
            allowed = {"overdue", "due_30_days", "missing_last"}
        else:
            allowed = {maintenance_state}
        filtered = [row for row in filtered if row.get("maintenance_state") in allowed]
    if meter_state:
        allowed = {"missing", "stale"} if meter_state == "needs_update" else {meter_state}
        filtered = [row for row in filtered if row.get("meter_state") in allowed]
    if forecast_state:
        allowed = {"overdue", "due_30_days"} if forecast_state == "due" else {forecast_state}
        filtered = [row for row in filtered if row.get("component_forecast_status") in allowed]
    return filtered


def _next_event_value(row: dict) -> datetime | None:
    candidates: list[datetime] = []
    maintenance_date = row.get("effective_next_maintenance_date") or row.get("next_maintenance_date")
    if maintenance_date:
        if isinstance(maintenance_date, datetime):
            candidates.append(_naive(maintenance_date))
        else:
            candidates.append(datetime.combine(maintenance_date, datetime.min.time()))
    component_date = row.get("next_component_forecast_at")
    if component_date:
        candidates.append(_naive(component_date))
    return min(candidates) if candidates else None


def _sort_value(row: dict, sort: str) -> Any:
    if sort == "next_event":
        return _next_event_value(row)
    value = row.get(sort)
    if isinstance(value, str):
        return value.casefold()
    if isinstance(value, datetime):
        return _naive(value)
    return value


def sort_asset_list_rows(rows: list[dict], sort: str, order: str) -> list[dict]:
    selected_sort = sort if sort in ASSET_SORT_FIELDS else "company_code"
    reverse = order == "desc"
    populated = [row for row in rows if _sort_value(row, selected_sort) is not None]
    missing = [row for row in rows if _sort_value(row, selected_sort) is None]
    populated.sort(
        key=lambda row: (_sort_value(row, selected_sort), row.get("id", 0)),
        reverse=reverse,
    )
    return populated + missing


def asset_list_summary(rows: list[dict]) -> dict[str, int]:
    return {
        "total": len(rows),
        "active": sum(row.get("status") == "aktív" for row in rows),
        "problem": sum(row.get("status") in {"hibás", "javítás alatt"} for row in rows),
        "maintenance": sum(row.get("maintenance_state") in {"overdue", "due_30_days"} for row in rows),
        "maintenance_missing": sum(row.get("maintenance_state") == "missing_last" for row in rows),
        "component_due": sum(row.get("component_forecast_status") in {"overdue", "due_30_days"} for row in rows),
        "stale_meters": sum(row.get("meter_state") in {"missing", "stale"} for row in rows),
    }


def paginate_asset_list_rows(rows: list[dict], page: int, page_size: int) -> tuple[list[dict], int, int, int]:
    total = len(rows)
    pages = max(1, ceil(total / page_size))
    normalized_page = min(max(1, page), pages)
    start = (normalized_page - 1) * page_size
    return rows[start : start + page_size], normalized_page, total, pages
