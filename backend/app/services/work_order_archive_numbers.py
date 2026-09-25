from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..models import WorkOrderArchive

WORK_ORDER_ARCHIVE_NUMBER_SEQUENCE = "work_order_archive_number_seq"


def next_work_order_archive_number(db: Session) -> str:
    if db.get_bind().dialect.name == "postgresql":
        serial = int(db.execute(text(f"SELECT nextval('{WORK_ORDER_ARCHIVE_NUMBER_SEQUENCE}')")).scalar_one())
    else:
        serial = int(db.query(func.max(WorkOrderArchive.id)).scalar() or 0) + 1
    return f"AR-{datetime.utcnow().year}-{serial:06d}"
