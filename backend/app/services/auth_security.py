from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote
from datetime import datetime, timedelta
from typing import Iterable
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import Settings
from ..access_control import PERMISSION_ADMIN_BACKUP_RESTORE
from ..models import AuthSession, ROLE_ADMIN, SecurityRateLimit, User
from ..request_context import get_audit_request_context
from ..security import create_access_token


def _now() -> datetime:
    return datetime.utcnow()


def _fernet(settings: Settings) -> Fernet:
    source = settings.mfa_encryption_key.strip() or settings.secret_key
    key = base64.urlsafe_b64encode(hashlib.sha256(source.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_mfa_secret(secret: str, settings: Settings) -> str:
    return _fernet(settings).encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_mfa_secret(ciphertext: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("Az MFA titok nem fejthető vissza a jelenlegi MFA_ENCRYPTION_KEY kulccsal") from exc


HIGH_RISK_PERMISSIONS = frozenset({PERMISSION_ADMIN_BACKUP_RESTORE})


def mfa_required_for_user(user: User, settings: Settings) -> bool:
    has_high_risk_permission = bool(HIGH_RISK_PERMISSIONS.intersection(user.permissions))
    return bool(
        user.mfa_enabled
        or has_high_risk_permission
        or (settings.admin_mfa_required and user.role and user.role.name == ROLE_ADMIN)
    )


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_at(secret: str, counter: int, digits: int = 6) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded.upper())
    digest = hmac.new(key, struct.pack("!Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack("!I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return f"{code:0{digits}d}"


def build_totp_uri(user: User, secret: str, settings: Settings) -> str:
    issuer = settings.app_name[:64]
    label = quote(f"{issuer}:{user.email}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}&algorithm=SHA1&digits=6&period=30"


def verify_totp(user: User, code: str, settings: Settings, *, consume: bool = True) -> bool:
    if not user.mfa_secret_encrypted:
        return False
    normalized = "".join(ch for ch in str(code) if ch.isdigit())
    if len(normalized) != 6:
        return False
    secret = decrypt_mfa_secret(user.mfa_secret_encrypted, settings)
    current_counter = int(datetime.utcnow().timestamp()) // 30
    for offset in (-1, 0, 1):
        counter = current_counter + offset
        expected = _totp_at(secret, counter)
        if hmac.compare_digest(expected, normalized):
            if user.mfa_last_counter is not None and counter <= user.mfa_last_counter:
                return False
            if consume:
                user.mfa_last_counter = counter
            return True
    return False


_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _recovery_hash(code: str, settings: Settings) -> str:
    normalized = code.replace("-", "").strip().upper()
    pepper = settings.mfa_encryption_key.strip() or settings.secret_key
    return hashlib.sha256(f"{pepper}:recovery:{normalized}".encode("utf-8")).hexdigest()


def generate_recovery_codes(settings: Settings, count: int = 10) -> tuple[list[str], list[str]]:
    plain: list[str] = []
    hashes: list[str] = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        formatted = f"{raw[:5]}-{raw[5:]}"
        plain.append(formatted)
        hashes.append(_recovery_hash(formatted, settings))
    return plain, hashes


def consume_recovery_code(user: User, code: str, settings: Settings) -> bool:
    candidate = _recovery_hash(code, settings)
    hashes = list(user.mfa_recovery_codes or [])
    if candidate not in hashes:
        return False
    hashes.remove(candidate)
    user.mfa_recovery_codes = hashes
    return True


def verify_mfa_code(user: User, code: str, settings: Settings) -> str | None:
    if verify_totp(user, code, settings, consume=True):
        return "totp"
    if consume_recovery_code(user, code, settings):
        return "recovery"
    return None



def prune_security_state(db: Session, settings: Settings, *, now: datetime | None = None) -> tuple[int, int]:
    """Bound growth of ephemeral session/throttling tables."""
    current = now or _now()
    session_cutoff = current - timedelta(days=7)
    rate_cutoff = current - timedelta(
        seconds=max(
            settings.login_rate_limit_window_seconds,
            settings.login_rate_limit_block_seconds,
            settings.mfa_step_up_rate_limit_window_seconds,
            settings.mfa_step_up_rate_limit_block_seconds,
        ) * 4
    )
    sessions = (
        db.query(AuthSession)
        .filter(
            or_(
                AuthSession.absolute_expires_at < session_cutoff,
                AuthSession.revoked_at < session_cutoff,
            )
        )
        .delete(synchronize_session=False)
    )
    rate_rows = (
        db.query(SecurityRateLimit)
        .filter(
            SecurityRateLimit.updated_at < rate_cutoff,
            or_(SecurityRateLimit.blocked_until.is_(None), SecurityRateLimit.blocked_until < current),
        )
        .delete(synchronize_session=False)
    )
    return int(sessions or 0), int(rate_rows or 0)

def create_auth_session(db: Session, user: User, settings: Settings, *, mfa_verified: bool) -> tuple[AuthSession, str, str]:
    now = _now()
    if secrets.randbelow(64) == 0:
        prune_security_state(db, settings, now=now)
    context = get_audit_request_context()
    sid = uuid4().hex
    session = AuthSession(
        session_id=sid,
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        absolute_expires_at=now + timedelta(minutes=settings.session_absolute_timeout_minutes),
        mfa_verified_at=now if mfa_verified else None,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    db.add(session)
    db.flush()
    token = create_access_token(
        user.email,
        timedelta(minutes=settings.session_absolute_timeout_minutes),
        session_id=sid,
    )
    csrf_token = secrets.token_urlsafe(32)
    return session, token, csrf_token


def set_auth_cookies(response: Response, token: str, csrf_token: str, settings: Settings) -> None:
    max_age = settings.session_absolute_timeout_minutes * 60
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/", secure=settings.session_cookie_secure, samesite="lax")
    response.delete_cookie(settings.csrf_cookie_name, path="/", secure=settings.session_cookie_secure, samesite="lax")


def validate_auth_session(db: Session, session_id: str, settings: Settings) -> AuthSession | None:
    session = db.query(AuthSession).filter(AuthSession.session_id == session_id).one_or_none()
    if session is None or session.revoked_at is not None:
        return None
    now = _now()
    if session.absolute_expires_at <= now:
        session.revoked_at = now
        db.commit()
        return None
    if session.last_seen_at + timedelta(minutes=settings.session_idle_timeout_minutes) <= now:
        session.revoked_at = now
        db.commit()
        return None
    if (now - session.last_seen_at).total_seconds() >= settings.session_touch_interval_seconds:
        session.last_seen_at = now
        db.commit()
    return session


def revoke_session(db: Session, session_id: str) -> bool:
    session = db.query(AuthSession).filter(AuthSession.session_id == session_id).one_or_none()
    if session is None or session.revoked_at is not None:
        return False
    session.revoked_at = _now()
    db.flush()
    return True


def revoke_user_sessions(db: Session, user_id: int, *, except_session_id: str | None = None) -> int:
    query = db.query(AuthSession).filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if except_session_id:
        query = query.filter(AuthSession.session_id != except_session_id)
    count = 0
    for row in query.all():
        row.revoked_at = _now()
        count += 1
    return count


def _bucket_key(kind: str, value: str) -> str:
    digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()
    return f"login:{kind}:{digest}"


def _bucket_values(username: str, ip_address: str | None) -> Iterable[tuple[str, str]]:
    yield _bucket_key("user", username), "user"
    if ip_address:
        yield _bucket_key("ip", ip_address), "ip"


def login_block_remaining_seconds(db: Session, username: str, ip_address: str | None, settings: Settings) -> int:
    now = _now()
    remaining = 0
    for key, _kind in _bucket_values(username, ip_address):
        row = db.query(SecurityRateLimit).filter(SecurityRateLimit.bucket_key == key).with_for_update().one_or_none()
        if row and row.blocked_until and row.blocked_until > now:
            remaining = max(remaining, int((row.blocked_until - now).total_seconds()) + 1)
    return remaining


def record_login_failure(db: Session, username: str, ip_address: str | None, settings: Settings) -> None:
    now = _now()
    if secrets.randbelow(64) == 0:
        prune_security_state(db, settings, now=now)
    window = timedelta(seconds=settings.login_rate_limit_window_seconds)
    block = timedelta(seconds=settings.login_rate_limit_block_seconds)
    for key, kind in _bucket_values(username, ip_address):
        row = db.query(SecurityRateLimit).filter(SecurityRateLimit.bucket_key == key).with_for_update().one_or_none()
        if row is None:
            row = SecurityRateLimit(bucket_key=key, attempts=0, window_started_at=now, updated_at=now)
            db.add(row)
        if row.window_started_at + window <= now:
            row.attempts = 0
            row.window_started_at = now
            row.blocked_until = None
        row.attempts += 1
        row.updated_at = now
        threshold = settings.login_rate_limit_attempts if kind == "user" else settings.login_ip_rate_limit_attempts
        if row.attempts >= threshold:
            row.blocked_until = now + block
    db.flush()


def clear_login_user_bucket(db: Session, username: str) -> None:
    row = db.get(SecurityRateLimit, _bucket_key("user", username))
    if row is not None:
        db.delete(row)
        db.flush()


def _step_up_bucket_values(session_id: str, ip_address: str | None) -> Iterable[str]:
    yield _bucket_key("mfa-step-up-session", session_id)
    if ip_address:
        yield _bucket_key("mfa-step-up-ip", ip_address)


def step_up_block_remaining_seconds(
    db: Session,
    session_id: str,
    ip_address: str | None,
    settings: Settings,
) -> int:
    now = _now()
    remaining = 0
    for key in _step_up_bucket_values(session_id, ip_address):
        row = db.query(SecurityRateLimit).filter(SecurityRateLimit.bucket_key == key).with_for_update().one_or_none()
        if row and row.blocked_until and row.blocked_until > now:
            remaining = max(remaining, int((row.blocked_until - now).total_seconds()) + 1)
    return remaining


def require_step_up_not_rate_limited(
    db: Session,
    session_id: str,
    ip_address: str | None,
    settings: Settings,
) -> None:
    remaining = step_up_block_remaining_seconds(db, session_id, ip_address, settings)
    if remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Túl sok sikertelen MFA megerősítési kísérlet. Próbáld újra később.",
            headers={"Retry-After": str(remaining)},
        )


def record_step_up_failure(
    db: Session,
    session_id: str,
    ip_address: str | None,
    settings: Settings,
) -> None:
    now = _now()
    window = timedelta(seconds=settings.mfa_step_up_rate_limit_window_seconds)
    block = timedelta(seconds=settings.mfa_step_up_rate_limit_block_seconds)
    for key in _step_up_bucket_values(session_id, ip_address):
        row = db.query(SecurityRateLimit).filter(SecurityRateLimit.bucket_key == key).with_for_update().one_or_none()
        if row is None:
            row = SecurityRateLimit(bucket_key=key, attempts=0, window_started_at=now, updated_at=now)
            db.add(row)
        if row.window_started_at + window <= now:
            row.attempts = 0
            row.window_started_at = now
            row.blocked_until = None
        row.attempts += 1
        row.updated_at = now
        if row.attempts >= settings.mfa_step_up_rate_limit_attempts:
            row.blocked_until = now + block
    db.flush()


def clear_step_up_session_bucket(db: Session, session_id: str) -> None:
    # A successful session may clear only its own failures. The shared IP
    # bucket must not be reset by another authenticated session.
    key = _bucket_key("mfa-step-up-session", session_id)
    db.query(SecurityRateLimit).filter(SecurityRateLimit.bucket_key == key).delete(synchronize_session=False)
    db.flush()


def require_not_rate_limited(db: Session, username: str, ip_address: str | None, settings: Settings) -> None:
    remaining = login_block_remaining_seconds(db, username, ip_address, settings)
    if remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Túl sok sikertelen bejelentkezési kísérlet. Próbáld újra később.",
            headers={"Retry-After": str(remaining)},
        )
