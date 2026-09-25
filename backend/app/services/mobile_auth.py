from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from ..config import Settings
from ..models import MobileDevice, MobileSession, User
from ..request_context import get_audit_request_context
from ..security import create_mobile_access_token


def _now() -> datetime:
    return datetime.utcnow()


def _refresh_hash(secret: str, settings: Settings) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        f"mobile-refresh:{secret}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _parse_refresh_token(token: str) -> tuple[str, str]:
    try:
        session_id, secret = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Érvénytelen mobil refresh token") from exc
    if len(session_id) != 32 or len(secret) < 32:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Érvénytelen mobil refresh token")
    return session_id, secret


@dataclass(frozen=True)
class MobileTokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_at: datetime
    session_id: str
    device_id: int


def _access_token(user: User, session: MobileSession, settings: Settings) -> str:
    return create_mobile_access_token(
        user.email,
        session.session_id,
        timedelta(minutes=settings.mobile_access_token_expire_minutes),
    )


def _new_refresh_secret() -> str:
    return secrets.token_urlsafe(48)


def register_or_reactivate_device(
    db: Session,
    user: User,
    *,
    device_uuid: str,
    device_name: str,
    platform: str,
    app_version: str | None,
) -> MobileDevice:
    now = _now()
    device = (
        db.query(MobileDevice)
        .filter(MobileDevice.user_id == user.id, MobileDevice.device_uuid == device_uuid)
        .with_for_update()
        .one_or_none()
    )
    if device is None:
        device = MobileDevice(
            user_id=user.id,
            device_uuid=device_uuid,
            device_name=device_name,
            platform=platform,
            app_version=app_version,
            created_at=now,
            updated_at=now,
            last_seen_at=now,
        )
        db.add(device)
        db.flush()
    else:
        device.device_name = device_name
        device.platform = platform
        device.app_version = app_version
        device.last_seen_at = now
        device.updated_at = now
        # A felhasználó saját hitelesítő adataival végzett új bejelentkezés
        # újraregisztrálja a korábban visszavont eszközt.
        device.revoked_at = None
        db.flush()
    return device


def create_mobile_session(
    db: Session,
    user: User,
    device: MobileDevice,
    settings: Settings,
    *,
    mfa_verified: bool,
) -> MobileTokenPair:
    now = _now()
    context = get_audit_request_context()
    session_id = uuid4().hex
    refresh_secret = _new_refresh_secret()
    session = MobileSession(
        session_id=session_id,
        user_id=user.id,
        device_id=device.id,
        refresh_token_hash=_refresh_hash(refresh_secret, settings),
        created_at=now,
        last_seen_at=now,
        absolute_expires_at=now + timedelta(days=settings.mobile_refresh_token_expire_days),
        mfa_verified_at=now if mfa_verified else None,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    db.add(session)
    device.last_seen_at = now
    db.flush()
    return MobileTokenPair(
        access_token=_access_token(user, session, settings),
        refresh_token=f"{session_id}.{refresh_secret}",
        access_expires_in=settings.mobile_access_token_expire_minutes * 60,
        refresh_expires_at=session.absolute_expires_at,
        session_id=session_id,
        device_id=device.id,
    )


def rotate_mobile_refresh_token(db: Session, raw_token: str, settings: Settings) -> tuple[User, MobileSession, MobileTokenPair]:
    session_id, presented_secret = _parse_refresh_token(raw_token)
    session = (
        db.query(MobileSession)
        .options(joinedload(MobileSession.user).joinedload(User.role), joinedload(MobileSession.device))
        .filter(MobileSession.session_id == session_id)
        .with_for_update()
        .one_or_none()
    )
    now = _now()
    if session is None or session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A mobil munkamenet lejárt vagy visszavonásra került")
    if session.absolute_expires_at <= now:
        session.revoked_at = now
        db.flush()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A mobil munkamenet lejárt")
    if session.device is None or session.device.revoked_at is not None:
        session.revoked_at = now
        db.flush()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A mobil eszköz visszavonásra került")
    user = session.user
    if user is None or not user.is_active:
        session.revoked_at = now
        db.flush()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inaktív vagy nem létező felhasználó")

    candidate = _refresh_hash(presented_secret, settings)
    if session.previous_refresh_token_hash and hmac.compare_digest(candidate, session.previous_refresh_token_hash):
        # Bizonyítottan egy már felhasznált refresh token jelent meg újra.
        # Ez tokenlopás/replay jele, ezért az egész mobil sessiont lezárjuk.
        session.revoked_at = now
        db.flush()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Újrafelhasznált mobil refresh token; a munkamenet visszavonásra került")
    if not hmac.compare_digest(candidate, session.refresh_token_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Érvénytelen mobil refresh token")

    new_secret = _new_refresh_secret()
    session.previous_refresh_token_hash = session.refresh_token_hash
    session.refresh_token_hash = _refresh_hash(new_secret, settings)
    session.refresh_generation += 1
    session.last_seen_at = now
    session.device.last_seen_at = now
    session.device.updated_at = now
    db.flush()
    pair = MobileTokenPair(
        access_token=_access_token(user, session, settings),
        refresh_token=f"{session.session_id}.{new_secret}",
        access_expires_in=settings.mobile_access_token_expire_minutes * 60,
        refresh_expires_at=session.absolute_expires_at,
        session_id=session.session_id,
        device_id=session.device_id,
    )
    return user, session, pair


def revoke_mobile_session(db: Session, session_id: str) -> bool:
    session = db.query(MobileSession).filter(MobileSession.session_id == session_id).with_for_update().one_or_none()
    if session is None or session.revoked_at is not None:
        return False
    session.revoked_at = _now()
    db.flush()
    return True


def revoke_mobile_device(db: Session, user_id: int, device_id: int) -> bool:
    device = (
        db.query(MobileDevice)
        .filter(MobileDevice.id == device_id, MobileDevice.user_id == user_id)
        .with_for_update()
        .one_or_none()
    )
    if device is None:
        return False
    now = _now()
    device.revoked_at = now
    for session in db.query(MobileSession).filter(MobileSession.device_id == device.id, MobileSession.revoked_at.is_(None)).all():
        session.revoked_at = now
    db.flush()
    return True
