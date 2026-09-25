from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import User, WorkOrder, WorkOrderEditSession

HEARTBEAT_INTERVAL_SECONDS = 5
SESSION_TIMEOUT_SECONDS = 25


def _utcnow() -> datetime:
    return datetime.utcnow()


def cleanup_stale_edit_sessions(db: Session, now: datetime | None = None) -> int:
    now = now or _utcnow()
    cutoff = now - timedelta(seconds=SESSION_TIMEOUT_SECONDS)
    deleted = (
        db.query(WorkOrderEditSession)
        .filter(WorkOrderEditSession.last_seen_at < cutoff)
        .delete(synchronize_session=False)
    )
    if deleted:
        db.flush()
    return deleted


def _active_editors(db: Session, work_order_id: int, exclude_user_id: int | None = None) -> list[dict]:
    cutoff = _utcnow() - timedelta(seconds=SESSION_TIMEOUT_SECONDS)
    query = (
        db.query(WorkOrderEditSession, User)
        .join(User, User.id == WorkOrderEditSession.user_id)
        .filter(
            WorkOrderEditSession.work_order_id == work_order_id,
            WorkOrderEditSession.last_seen_at >= cutoff,
            User.is_active.is_(True),
        )
        .order_by(WorkOrderEditSession.last_seen_at.desc())
    )
    if exclude_user_id is not None:
        query = query.filter(WorkOrderEditSession.user_id != exclude_user_id)

    # Egy felhasználó több böngészőlappal is jelen lehet. A felületen egyszer jelenjen meg.
    editors: dict[int, dict] = {}
    for session, user in query.all():
        if user.id in editors:
            continue
        editors[user.id] = {
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "started_at": session.started_at,
            "last_seen_at": session.last_seen_at,
        }
    return list(editors.values())


def _presence_payload(db: Session, work_order_id: int, current_user_id: int, session_token: str | None) -> dict:
    editors = _active_editors(db, work_order_id, exclude_user_id=current_user_id)
    return {
        "work_order_id": work_order_id,
        "session_token": session_token,
        "active_editors": editors,
        "has_other_editors": bool(editors),
        "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        "session_timeout_seconds": SESSION_TIMEOUT_SECONDS,
    }


def start_edit_session(db: Session, work_order_id: int, current_user: User) -> dict:
    if not db.get(WorkOrder, work_order_id):
        raise ValueError("Munkalap nem található")

    now = _utcnow()
    cleanup_stale_edit_sessions(db, now)
    session = WorkOrderEditSession(
        work_order_id=work_order_id,
        user_id=current_user.id,
        session_token=uuid4().hex,
        started_at=now,
        last_seen_at=now,
    )
    db.add(session)
    db.commit()
    return _presence_payload(db, work_order_id, current_user.id, session.session_token)


def heartbeat_edit_session(
    db: Session,
    work_order_id: int,
    current_user: User,
    session_token: str,
) -> dict:
    if not db.get(WorkOrder, work_order_id):
        raise ValueError("Munkalap nem található")

    now = _utcnow()
    cleanup_stale_edit_sessions(db, now)
    session = (
        db.query(WorkOrderEditSession)
        .filter(
            WorkOrderEditSession.work_order_id == work_order_id,
            WorkOrderEditSession.user_id == current_user.id,
            WorkOrderEditSession.session_token == session_token,
        )
        .first()
    )
    # Ha a böngésző rövid időre alvó állapotba került és a session lejárt,
    # ugyanazzal a kliens tokennel újra létrehozzuk a jelenlétet.
    if session is None:
        session = WorkOrderEditSession(
            work_order_id=work_order_id,
            user_id=current_user.id,
            session_token=session_token,
            started_at=now,
            last_seen_at=now,
        )
        db.add(session)
    else:
        session.last_seen_at = now
    db.commit()
    return _presence_payload(db, work_order_id, current_user.id, session_token)


def stop_edit_session(db: Session, work_order_id: int, current_user: User, session_token: str) -> None:
    (
        db.query(WorkOrderEditSession)
        .filter(
            WorkOrderEditSession.work_order_id == work_order_id,
            WorkOrderEditSession.user_id == current_user.id,
            WorkOrderEditSession.session_token == session_token,
        )
        .delete(synchronize_session=False)
    )
    db.commit()


def get_edit_presence(db: Session, work_order_id: int, current_user: User) -> dict:
    if not db.get(WorkOrder, work_order_id):
        raise ValueError("Munkalap nem található")
    cleanup_stale_edit_sessions(db)
    db.commit()
    return _presence_payload(db, work_order_id, current_user.id, None)
