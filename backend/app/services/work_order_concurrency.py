from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from ..models import WorkOrder

CONFLICT_MESSAGE = (
    "A munkalapot egy másik felhasználó időközben módosította. "
    "A felülírás elkerülése érdekében a mentés megszakadt; töltsd újra a munkalapot, "
    "ellenőrizd a változásokat, majd mentsd újra."
)


def require_current_version(order: WorkOrder, expected_version: int) -> None:
    if expected_version != order.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CONFLICT_MESSAGE)


def commit_with_optimistic_lock(db: Session) -> None:
    try:
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CONFLICT_MESSAGE) from exc
