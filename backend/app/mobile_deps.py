from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload, selectinload

from .access_control import PERMISSION_SERVICE_ACCESS
from .config import get_settings
from .database import get_db
from .models import MobileDevice, MobileSession, ROLE_ADMIN, ROLE_TECHNICIAN, User, UserPermission
from .security import decode_mobile_token_claims
from .services.auth_security import mfa_required_for_user


@dataclass(frozen=True)
class MobilePrincipal:
    user: User
    session: MobileSession
    device: MobileDevice


def get_mobile_principal(request: Request, db: Session = Depends(get_db)) -> MobilePrincipal:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mobil Bearer token szükséges")
    token = authorization[7:].strip()
    claims = decode_mobile_token_claims(token)
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Érvénytelen vagy lejárt mobil access token")

    session = (
        db.query(MobileSession)
        .options(joinedload(MobileSession.device))
        .filter(MobileSession.session_id == str(claims["sid"]))
        .one_or_none()
    )
    now = datetime.utcnow()
    if session is None or session.revoked_at is not None or session.absolute_expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A mobil munkamenet lejárt vagy visszavonásra került")
    if session.device is None or session.device.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A mobil eszköz visszavonásra került")

    user = (
        db.query(User)
        .options(
            joinedload(User.role),
            selectinload(User.permission_links).joinedload(UserPermission.permission),
        )
        .filter(User.id == session.user_id, User.email == str(claims["sub"]))
        .one_or_none()
    )
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inaktív vagy nem létező felhasználó")
    if user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A mobil használat előtt a webes felületen jelszót kell változtatni")
    if mfa_required_for_user(user, get_settings()) and session.mfa_verified_at is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA ellenőrzés szükséges")
    if user.role.name not in {ROLE_ADMIN, ROLE_TECHNICIAN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A mobil technikusi klienshez technikusi vagy admin szerepkör szükséges")
    if user.role.name != ROLE_ADMIN and PERMISSION_SERVICE_ACCESS not in user.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A Szerviz modul jogosultsága szükséges")

    # Security/audit freshness only; do not extend the absolute refresh lifetime.
    if (now - session.last_seen_at).total_seconds() >= 60:
        session.last_seen_at = now
        session.device.last_seen_at = now
        db.commit()
    request.state.mobile_session_id = session.session_id
    request.state.mobile_device_id = session.device_id
    return MobilePrincipal(user=user, session=session, device=session.device)
