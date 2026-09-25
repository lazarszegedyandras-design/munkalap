from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Used only to equalize password-verification work for unknown accounts and
# reduce timing-based account enumeration. Never used as a real credential.
DUMMY_PASSWORD_HASH = pwd_context.hash("__workapp_unknown_account_padding__")
settings = get_settings()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)



def verify_password_with_dummy(plain_password: str, hashed_password: str | None) -> bool:
    return pwd_context.verify(plain_password, hashed_password or DUMMY_PASSWORD_HASH)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: str, expires_delta: timedelta | None = None, *, session_id: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.session_absolute_timeout_minutes))
    payload = {
        "sub": subject,
        "sid": session_id or uuid4().hex,
        "typ": "access",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_mfa_challenge_token(subject: str, purpose: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "typ": "mfa_challenge",
        "purpose": purpose,
        "nonce": uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=settings.mfa_challenge_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


def decode_token_claims(token: str) -> dict | None:
    payload = _decode_jwt(token)
    if not payload or payload.get("typ") != "access" or not payload.get("sub") or not payload.get("sid"):
        return None
    return payload


def decode_mfa_challenge(token: str, *, expected_purpose: str | None = None) -> dict | None:
    payload = _decode_jwt(token)
    if not payload or payload.get("typ") != "mfa_challenge" or not payload.get("sub"):
        return None
    if expected_purpose is not None and payload.get("purpose") != expected_purpose:
        return None
    return payload




def create_mobile_access_token(subject: str, session_id: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "sid": session_id,
        "typ": "mobile_access",
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_mobile_token_claims(token: str) -> dict | None:
    payload = _decode_jwt(token)
    if not payload or payload.get("typ") != "mobile_access" or not payload.get("sub") or not payload.get("sid"):
        return None
    return payload

def decode_token(token: str) -> str | None:
    payload = decode_token_claims(token)
    if not payload:
        return None
    return str(payload.get("sub"))
