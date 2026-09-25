from __future__ import annotations
from datetime import datetime
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from ..models import CrmContractArchive

SEQUENCE = "crm_contract_archive_number_seq"

def next_contract_archive_number(db: Session) -> str:
    if db.get_bind().dialect.name == "postgresql":
        serial = int(db.execute(text(f"SELECT nextval('{SEQUENCE}')")).scalar_one())
    else:
        serial = int(db.query(func.max(CrmContractArchive.id)).scalar() or 0) + 1
    return f"SZ-A-{datetime.utcnow().year}-{serial:06d}"
