from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any


STANDARD_CYCLE_LABELS = {
    1: "1 hónap",
    2: "2 hónap",
    3: "3 hónap",
    4: "4 hónap",
    6: "6 hónap",
    12: "1 év",
}


def add_calendar_months(value: date, months: int) -> date:
    """Add calendar months while keeping the day where possible.

    Example: 31 January + 1 month = 28/29 February. Contract maintenance
    cycles are calendar periods, therefore a simple 30-day multiplication
    would create accumulating drift.
    """
    if months < 0:
        raise ValueError("A hónapok száma nem lehet negatív")
    total_month = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total_month, 12)
    month = month_index + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def maintenance_cycle_label(months: int | None, note: str | None = None) -> str | None:
    cleaned_note = (note or "").strip()
    if months:
        return STANDARD_CYCLE_LABELS.get(months, f"{months} hónap")
    return cleaned_note or None


def calculated_next_maintenance_date(asset: Any) -> date | None:
    months = getattr(asset, "maintenance_cycle_months", None)
    last_date = getattr(asset, "last_maintenance_date", None)
    if months and last_date:
        return add_calendar_months(last_date, months)
    return None


def effective_next_maintenance_date(asset: Any) -> tuple[date | None, str | None]:
    calculated = calculated_next_maintenance_date(asset)
    if calculated:
        return calculated, "contract_cycle"
    manual = getattr(asset, "next_maintenance_date", None)
    if manual:
        return manual, "manual"
    return None, None


def maintenance_snapshot(asset: Any, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    calculated = calculated_next_maintenance_date(asset)
    effective, source = effective_next_maintenance_date(asset)
    last_date = getattr(asset, "last_maintenance_date", None)
    months = getattr(asset, "maintenance_cycle_months", None)
    note = getattr(asset, "maintenance_cycle_note", None)

    days_since_last = (today - last_date).days if last_date else None
    days_until_due = (effective - today).days if effective else None

    if months and not last_date:
        state = "missing_last"
        label = "Nincs utolsó karbantartás"
    elif effective is None:
        state = "none"
        label = "Nincs ütemezve"
    elif days_until_due < 0:
        state = "overdue"
        label = "Lejárt"
    elif days_until_due <= 30:
        state = "due_30_days"
        label = "30 napon belül"
    else:
        state = "future"
        label = "Később esedékes"

    return {
        "maintenance_cycle_months": months,
        "maintenance_cycle_note": note,
        "maintenance_cycle_label": maintenance_cycle_label(months, note),
        "calculated_next_maintenance_date": calculated,
        "effective_next_maintenance_date": effective,
        "maintenance_due_source": source,
        "maintenance_days_since_last": days_since_last,
        "maintenance_days_until_due": days_until_due,
        "maintenance_state": state,
        "maintenance_state_label": label,
    }
