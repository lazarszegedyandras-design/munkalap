from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..models import WorkOrder

WORK_ORDER_NUMBER_SEQUENCE = "work_order_number_seq"


def next_work_order_number(db: Session) -> str:
    """Return a concurrency-safe work order number.

    PostgreSQL uses a real database sequence, so parallel requests cannot receive
    the same serial number. SQLite is used only by the test suite and falls back
    to the next numeric id.
    """
    if db.get_bind().dialect.name == "postgresql":
        serial = int(db.execute(text(f"SELECT nextval('{WORK_ORDER_NUMBER_SEQUENCE}')")).scalar_one())
    else:
        serial = int(db.query(func.max(WorkOrder.id)).scalar() or 0) + 1
    return f"ML-{datetime.utcnow().year}-{serial:06d}"
