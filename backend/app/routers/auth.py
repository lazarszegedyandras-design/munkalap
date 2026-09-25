from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy.orm import Session, joinedload, selectinload

from ..config import get_settings
from ..database import get_db
from ..deps import get_authenticated_user
from ..models import AuthSession, ROLE_ADMIN, User, UserPermission
from ..request_context import get_audit_request_context
from ..schemas import (
    MfaChallengeRequest,
    MfaConfirmRead,
    MfaSetupRead,
    MfaStatusRead,
    MfaStepUpRead,
    MfaStepUpRequest,
    MfaVerifyRequest,
    PasswordChangeRequest,
    Token,
    UserRead,
)
from ..security import create_mfa_challenge_token, decode_mfa_challenge, get_password_hash, verify_password, verify_password_with_dummy
from ..services.auth_security import (
    build_totp_uri,
    clear_auth_cookies,
    clear_login_user_bucket,
    create_auth_session,
    encrypt_mfa_secret,
    generate_recovery_codes,
    generate_totp_secret,
    mfa_required_for_user,
    record_login_failure,
    record_step_up_failure,
    require_not_rate_limited,
    require_step_up_not_rate_limited,
    revoke_session,
    revoke_user_sessions,
    set_auth_cookies,
    verify_mfa_code,
    verify_totp,
    clear_step_up_session_bucket,
)
from ..services.audit import (
    AUDIT_RESULT_FAILURE,
    AUDIT_SEVERITY_WARNING,
    add_audit_log,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _load_user(db: Session, email: str) -> User | None:
    return (
        db.query(User)
        .options(joinedload(User.role), selectinload(User.permission_links).joinedload(UserPermission.permission))
        .filter(User.email == email)
        .first()
    )


def _challenge_user(db: Session, challenge_token: str, *, expected_purpose: str | None = None) -> tuple[User, dict]:
    claims = decode_mfa_challenge(challenge_token, expected_purpose=expected_purpose)
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Az MFA munkamenet lejárt vagy érvénytelen")
    user = (
        db.query(User)
        .options(joinedload(User.role), selectinload(User.permission_links).joinedload(UserPermission.permission))
        .filter(User.email == str(claims["sub"]))
        .with_for_update()
        .first()
    )
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Az MFA munkamenet lejárt vagy érvénytelen")
    return user, claims


def _complete_login(db: Session, response: Response, user: User, *, mfa_verified: bool) -> Token:
    settings = get_settings()
    session, token, csrf_token = create_auth_session(db, user, settings, mfa_verified=mfa_verified)
    set_auth_cookies(response, token, csrf_token, settings)
    add_audit_log(
        db,
        user,
        "LOGIN_SUCCESS",
        "auth",
        user.id,
        "Sikeres bejelentkezés",
        entity_display_id=user.email,
        session_id=session.session_id,
    )
    db.commit()
    # Browser sessions are stored only in HttpOnly cookies. Do not expose the
    # bearer JWT to page JavaScript; the later mobile API gets a separate token flow.
    return Token()


@router.post("/login", response_model=Token)
def login(
    request: Request,
    response: Response,
    username: str = Form(..., max_length=255),
    password: str = Form("", max_length=128),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    context = get_audit_request_context()
    normalized_username = username.strip().lower()
    try:
        require_not_rate_limited(db, normalized_username, context.ip_address, settings)
    except HTTPException:
        add_audit_log(
            db,
            None,
            "LOGIN_RATE_LIMITED",
            "security",
            normalized_username or "unknown",
            "Bejelentkezés átmenetileg korlátozva túl sok sikertelen próbálkozás miatt",
            entity_display_id=normalized_username or None,
            result=AUDIT_RESULT_FAILURE,
            severity=AUDIT_SEVERITY_WARNING,
        )
        db.commit()
        raise

    user = _load_user(db, normalized_username)
    empty_password_allowed = bool(
        user
        and password == ""
        and user.must_change_password
        and user.role.name == ROLE_ADMIN
        and not settings.is_production
    )
    # Always perform one password-hash verification for non-empty passwords,
    # including unknown users, to reduce timing-based account enumeration.
    verified_hash = verify_password_with_dummy(password, user.password_hash if user else None) if password != "" else False
    password_valid = bool(
        user
        and user.is_active
        and ((password == "" and empty_password_allowed) or (password != "" and verified_hash))
    )
    if not password_valid:
        record_login_failure(db, normalized_username, context.ip_address, settings)
        add_audit_log(
            db,
            user,
            "LOGIN_FAILED",
            "auth",
            normalized_username or "unknown",
            "Sikertelen bejelentkezési kísérlet",
            entity_display_id=normalized_username or None,
            result=AUDIT_RESULT_FAILURE,
            severity=AUDIT_SEVERITY_WARNING,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Hibás email vagy jelszó")

    clear_login_user_bucket(db, normalized_username)
    if mfa_required_for_user(user, settings):
        if not user.mfa_enabled:
            challenge = create_mfa_challenge_token(user.email, "setup")
            add_audit_log(
                db, user, "MFA_SETUP_REQUIRED", "security", user.id,
                "A bejelentkezéshez kötelező MFA regisztráció szükséges",
                entity_display_id=user.email,
            )
            db.commit()
            return Token(mfa_setup_required=True, challenge_token=challenge)
        challenge = create_mfa_challenge_token(user.email, "verify")
        add_audit_log(
            db, user, "MFA_CHALLENGE_CREATED", "security", user.id,
            "MFA ellenőrzés szükséges a bejelentkezés befejezéséhez",
            entity_display_id=user.email,
        )
        db.commit()
        return Token(mfa_required=True, challenge_token=challenge)

    return _complete_login(db, response, user, mfa_verified=False)


@router.post("/mfa/setup", response_model=MfaSetupRead)
def mfa_setup(payload: MfaChallengeRequest, db: Session = Depends(get_db)):
    user, _ = _challenge_user(db, payload.challenge_token, expected_purpose="setup")
    if user.mfa_enabled:
        raise HTTPException(status_code=409, detail="Az MFA már be van állítva")
    settings = get_settings()
    secret = generate_totp_secret()
    user.mfa_secret_encrypted = encrypt_mfa_secret(secret, settings)
    user.mfa_last_counter = None
    user.mfa_recovery_codes = None
    add_audit_log(
        db, user, "MFA_SETUP_STARTED", "security", user.id,
        "MFA regisztráció megkezdve",
        entity_display_id=user.email,
    )
    db.commit()
    return MfaSetupRead(secret=secret, otpauth_uri=build_totp_uri(user, secret, settings))


@router.post("/mfa/confirm", response_model=MfaConfirmRead)
def mfa_confirm(request: Request, response: Response, payload: MfaVerifyRequest, db: Session = Depends(get_db)):
    user, _ = _challenge_user(db, payload.challenge_token, expected_purpose="setup")
    settings = get_settings()
    context = get_audit_request_context()
    require_not_rate_limited(db, user.email, context.ip_address, settings)
    if user.mfa_enabled or not user.mfa_secret_encrypted or not verify_totp(user, payload.code, settings, consume=True):
        record_login_failure(db, user.email, context.ip_address, settings)
        add_audit_log(
            db, user, "MFA_SETUP_FAILED", "security", user.id,
            "Sikertelen MFA regisztrációs kód ellenőrzés",
            entity_display_id=user.email,
            result=AUDIT_RESULT_FAILURE,
            severity=AUDIT_SEVERITY_WARNING,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Hibás vagy már felhasznált MFA kód")

    recovery_codes, recovery_hashes = generate_recovery_codes(settings)
    user.mfa_enabled = True
    user.mfa_recovery_codes = recovery_hashes
    from datetime import datetime
    user.mfa_enrolled_at = datetime.utcnow()
    clear_login_user_bucket(db, user.email)
    add_audit_log(
        db, user, "MFA_ENABLED", "security", user.id,
        "MFA sikeresen engedélyezve",
        entity_display_id=user.email,
    )
    token_response = _complete_login(db, response, user, mfa_verified=True)
    return MfaConfirmRead(**token_response.model_dump(), recovery_codes=recovery_codes)


@router.post("/mfa/verify", response_model=Token)
def mfa_verify(request: Request, response: Response, payload: MfaVerifyRequest, db: Session = Depends(get_db)):
    user, _ = _challenge_user(db, payload.challenge_token, expected_purpose="verify")
    settings = get_settings()
    context = get_audit_request_context()
    require_not_rate_limited(db, user.email, context.ip_address, settings)
    method = verify_mfa_code(user, payload.code, settings)
    if not user.mfa_enabled or method is None:
        record_login_failure(db, user.email, context.ip_address, settings)
        add_audit_log(
            db, user, "MFA_FAILED", "security", user.id,
            "Sikertelen MFA ellenőrzés",
            entity_display_id=user.email,
            result=AUDIT_RESULT_FAILURE,
            severity=AUDIT_SEVERITY_WARNING,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Hibás vagy már felhasznált MFA/recovery kód")
    clear_login_user_bucket(db, user.email)
    add_audit_log(
        db, user, "MFA_SUCCESS", "security", user.id,
        f"Sikeres MFA ellenőrzés ({method})",
        entity_display_id=user.email,
    )
    return _complete_login(db, response, user, mfa_verified=True)


@router.get("/mfa/status", response_model=MfaStatusRead)
def mfa_status(current_user: User = Depends(get_authenticated_user)):
    settings = get_settings()
    return MfaStatusRead(
        enabled=current_user.mfa_enabled,
        required=mfa_required_for_user(current_user, settings),
        recovery_codes_remaining=len(current_user.mfa_recovery_codes or []),
    )


@router.post("/mfa/step-up", response_model=MfaStepUpRead)
def mfa_step_up(
    request: Request,
    payload: MfaStepUpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "A folytatáshoz meg kell változtatni a jelszót."},
        )
    settings = get_settings()
    session_id = getattr(request.state, "auth_session_id", None)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Érvénytelen webes munkamenet")
    context = get_audit_request_context()
    try:
        require_step_up_not_rate_limited(db, session_id, context.ip_address, settings)
    except HTTPException:
        add_audit_log(
            db, current_user, "MFA_STEP_UP_FAILED", "security", session_id,
            "MFA step-up ellenőrzés rate limit miatt elutasítva",
            entity_display_id=current_user.email,
            result=AUDIT_RESULT_FAILURE,
            severity=AUDIT_SEVERITY_WARNING,
        )
        db.commit()
        raise

    user = (
        db.query(User)
        .options(joinedload(User.role), selectinload(User.permission_links).joinedload(UserPermission.permission))
        .filter(User.id == current_user.id)
        .with_for_update()
        .one()
    )
    auth_session = (
        db.query(AuthSession)
        .filter(AuthSession.session_id == session_id, AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .with_for_update()
        .one_or_none()
    )
    method = verify_mfa_code(user, payload.code, settings) if user.mfa_enabled else None
    if auth_session is None or method is None:
        record_step_up_failure(db, session_id, context.ip_address, settings)
        add_audit_log(
            db, user, "MFA_STEP_UP_FAILED", "security", session_id,
            "Sikertelen MFA step-up ellenőrzés",
            entity_display_id=user.email,
            result=AUDIT_RESULT_FAILURE,
            severity=AUDIT_SEVERITY_WARNING,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hibás vagy már felhasznált MFA/recovery kód")

    from datetime import datetime
    verified_at = datetime.utcnow()
    auth_session.mfa_verified_at = verified_at
    clear_step_up_session_bucket(db, session_id)
    add_audit_log(
        db, user, "MFA_STEP_UP_SUCCESS", "security", session_id,
        f"Sikeres MFA step-up ellenőrzés ({method})",
        entity_display_id=user.email,
    )
    db.commit()
    return MfaStepUpRead(ok=True, verified_at=verified_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    settings = get_settings()
    session_id = getattr(request.state, "auth_session_id", None)
    if session_id:
        revoke_session(db, session_id)
    add_audit_log(
        db, current_user, "LOGOUT", "auth", current_user.id,
        "Felhasználói kijelentkezés",
        entity_display_id=current_user.email,
        session_id=session_id,
    )
    db.commit()
    clear_auth_cookies(response, settings)
    return None


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_authenticated_user)):
    return current_user


@router.post("/change-password", response_model=UserRead)
def change_password(
    request: Request,
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        add_audit_log(
            db,
            current_user,
            "PASSWORD_CHANGE_FAILED",
            "user",
            current_user.id,
            "Saját jelszó módosítása sikertelen: a jelenlegi jelszó hibás",
            entity_display_id=current_user.email,
            result=AUDIT_RESULT_FAILURE,
            severity=AUDIT_SEVERITY_WARNING,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="A jelenlegi jelszó hibás")
    if verify_password(payload.new_password, current_user.password_hash):
        add_audit_log(
            db,
            current_user,
            "PASSWORD_CHANGE_FAILED",
            "user",
            current_user.id,
            "Saját jelszó módosítása sikertelen: az új jelszó megegyezik a jelenlegivel",
            entity_display_id=current_user.email,
            result=AUDIT_RESULT_FAILURE,
            severity=AUDIT_SEVERITY_WARNING,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Az új jelszó nem egyezhet meg a jelenlegi jelszóval")

    before = {"must_change_password": current_user.must_change_password}
    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    session_id = getattr(request.state, "auth_session_id", None)
    revoked = revoke_user_sessions(db, current_user.id, except_session_id=session_id)
    add_audit_log(
        db,
        current_user,
        "jelszócsere",
        "user",
        current_user.id,
        f"Saját jelszó módosítva; {revoked} további aktív munkamenet visszavonva",
        entity_display_id=current_user.email,
        before=before,
        after={"must_change_password": False},
    )
    db.commit()
    db.refresh(current_user)
    return current_user
