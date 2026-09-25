from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Notification, User
from ..services.notifications import refresh_user_notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _serialize(row: Notification) -> dict:
    return {
        "id": row.id,
        "module": row.module,
        "notification_type": row.notification_type,
        "title": row.title,
        "message": row.message,
        "link": row.link,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "is_read": row.is_read,
        "read_at": row.read_at,
        "created_at": row.created_at,
    }


@router.get("")
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    refresh_user_notifications(db, current_user)
    db.commit()
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    rows = query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()
    return [_serialize(row) for row in rows]


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    refresh_user_notifications(db, current_user)
    db.commit()
    count = db.query(Notification).filter(Notification.user_id == current_user.id, Notification.is_read.is_(False)).count()
    return {"unread_count": count}


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == current_user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Értesítés nem található")
    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.utcnow()
        db.commit()
    return _serialize(row)


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    rows = db.query(Notification).filter(Notification.user_id == current_user.id, Notification.is_read.is_(False)).all()
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.commit()
    return {"updated": len(rows)}
