from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import RequireAdmin
from ..models import AuditLog, User
from ..services.audit import verify_audit_chain

router = APIRouter(prefix="/audit-logs", tags=["audit_logs"])


def _serialize(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "actor_user_id": row.actor_user_id,
        "actor_name": row.actor_name,
        "actor_email": row.actor_email,
        "actor_role": row.actor_role,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "entity_display_id": row.entity_display_id,
        "description": row.description,
        "before_data": row.before_data,
        "after_data": row.after_data,
        "changes": row.changes,
        "request_id": row.request_id,
        "correlation_id": row.correlation_id,
        "session_id": row.session_id,
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "result": row.result,
        "severity": row.severity,
        "previous_hash": row.previous_hash,
        "entry_hash": row.entry_hash,
        "created_at": row.created_at,
    }


@router.get("")
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=100),
    entity_type: str | None = Query(default=None, max_length=100),
    result: str | None = Query(default=None, max_length=32),
    severity: str | None = Query(default=None, max_length=32),
    actor: str | None = Query(default=None, max_length=255),
    request_id: str | None = Query(default=None, max_length=100),
    correlation_id: str | None = Query(default=None, max_length=100),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(RequireAdmin),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if result:
        query = query.filter(AuditLog.result == result)
    if severity:
        query = query.filter(AuditLog.severity == severity)
    if actor:
        like = f"%{actor.strip()}%"
        query = query.filter(or_(AuditLog.actor_name.ilike(like), AuditLog.actor_email.ilike(like)))
    if request_id:
        query = query.filter(AuditLog.request_id == request_id)
    if correlation_id:
        query = query.filter(AuditLog.correlation_id == correlation_id)
    if created_from:
        query = query.filter(AuditLog.created_at >= created_from)
    if created_to:
        query = query.filter(AuditLog.created_at <= created_to)

    total = query.count()
    rows = query.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    return {
        "items": [_serialize(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/integrity")
def audit_integrity(db: Session = Depends(get_db), _: User = Depends(RequireAdmin)):
    return verify_audit_chain(db)
