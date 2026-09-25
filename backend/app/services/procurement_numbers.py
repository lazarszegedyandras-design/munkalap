from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import ProcurementRequestSequence


def next_procurement_request_number(db: Session, *, now: datetime | None = None) -> str:
    """Allocate a collision-safe yearly BESZ sequence number inside the caller transaction."""
    year = (now or datetime.utcnow()).year

    # PostgreSQL deployments use a transaction-scoped advisory lock so that
    # the first sequence row for a year is also safe under concurrent inserts.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": 230000 + year})

    query = db.query(ProcurementRequestSequence).filter(ProcurementRequestSequence.year == year)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    sequence = query.one_or_none()
    if sequence is None:
        sequence = ProcurementRequestSequence(year=year, next_value=1)
        db.add(sequence)
        db.flush()

    value = sequence.next_value
    sequence.next_value = value + 1
    db.flush()
    return f"BESZ-{year:04d}-{value:04d}"
