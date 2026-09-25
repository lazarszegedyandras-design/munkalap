from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload, selectinload

from .access_control import (
    PERMISSION_SERVICE_ACCESS,
    PERMISSION_HR_ACCESS,
    PERMISSION_HR_LEAVE_SELF,
    PERMISSION_HR_LEAVE_REQUEST,
    PERMISSION_HR_LEAVE_APPROVE,
    PERMISSION_HR_SUMMARY_VIEW,
    PERMISSION_HR_ADMIN,
    PERMISSION_CRM_ACCESS,
    PERMISSION_CRM_WRITE,
    PERMISSION_CRM_CONTRACT_MANAGE,
    PERMISSION_CRM_ADMIN,
    PERMISSION_ADMIN_ACCESS,
    PERMISSION_ADMIN_BACKUP_MANAGE,
    PERMISSION_ADMIN_BACKUP_RESTORE,
    PERMISSION_PROCUREMENT_APPROVE,
)
from .config import get_settings
from .database import get_db
from .models import AuthSession, User, UserPermission, ROLE_ADMIN, ROLE_OFFICE, ROLE_TECHNICIAN
from .security import decode_token_claims
from .services.auth_security import mfa_required_for_user, validate_auth_session
from .services.audit import AUDIT_RESULT_FAILURE, AUDIT_SEVERITY_WARNING, add_audit_log

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _audit_denied(db: Session, user: User | None, action: str, description: str, *, entity_id: str = "access") -> None:
    try:
        add_audit_log(
            db,
            user,
            action,
            "security",
            entity_id,
            description,
            result=AUDIT_RESULT_FAILURE,
            severity=AUDIT_SEVERITY_WARNING,
        )
        db.commit()
    except Exception:
        db.rollback()


def get_authenticated_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    presented_token = token or request.cookies.get(settings.session_cookie_name)
    claims = decode_token_claims(presented_token) if presented_token else None
    if not claims:
        if presented_token:
            _audit_denied(db, None, "AUTH_TOKEN_INVALID", "Érvénytelen vagy lejárt hozzáférési token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Érvénytelen vagy lejárt token")

    subject = str(claims.get("sub"))
    session_id = str(claims.get("sid"))
    auth_session = validate_auth_session(db, session_id, settings)
    if auth_session is None:
        _audit_denied(db, None, "AUTH_SESSION_INVALID", "Lejárt, visszavont vagy ismeretlen munkamenet", entity_id=session_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A munkamenet lejárt vagy visszavonásra került")

    user = (
        db.query(User)
        .options(
            joinedload(User.role),
            selectinload(User.permission_links).joinedload(UserPermission.permission),
        )
        .filter(User.id == auth_session.user_id, User.email == subject)
        .first()
    )
    if not user or not user.is_active:
        _audit_denied(db, user, "AUTH_USER_INACTIVE", "A tokenhez tartozó felhasználó nem létezik vagy inaktív", entity_id=subject)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inaktív vagy nem létező felhasználó")
    if mfa_required_for_user(user, settings) and auth_session.mfa_verified_at is None:
        _audit_denied(db, user, "AUTH_MFA_REQUIRED", "A munkamenethez kötelező MFA ellenőrzés hiányzik", entity_id=subject)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA ellenőrzés szükséges")

    request.state.auth_session_id = session_id
    request.state.auth_via_cookie = token is None and bool(request.cookies.get(settings.session_cookie_name))
    return user


def get_current_user(current_user: User = Depends(get_authenticated_user)) -> User:
    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "A folytatáshoz meg kell változtatni a jelszót."},
        )
    return current_user


def RequireRecentMfa(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    settings = get_settings()
    session_id = getattr(request.state, "auth_session_id", None)
    auth_session = (
        db.query(AuthSession)
        .filter(AuthSession.session_id == session_id, AuthSession.user_id == current_user.id)
        .one_or_none()
        if session_id
        else None
    )
    if not current_user.mfa_enabled:
        detail = {
            "code": "mfa_setup_required",
            "message": "Ehhez a művelethez MFA szükséges.",
        }
    elif auth_session is None or auth_session.mfa_verified_at is None or auth_session.mfa_verified_at < (
        datetime.utcnow() - timedelta(seconds=settings.sensitive_mfa_max_age_seconds)
    ):
        detail = {
            "code": "recent_mfa_required",
            "max_age_seconds": settings.sensitive_mfa_max_age_seconds,
            "message": "A művelethez friss MFA megerősítés szükséges.",
        }
    else:
        return current_user

    _audit_denied(
        db,
        current_user,
        "SENSITIVE_ACTION_MFA_REQUIRED",
        detail["message"],
        entity_id=str(session_id or "unknown-session"),
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def require_roles(*role_names: str):
    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.role.name not in role_names:
            _audit_denied(
                db,
                current_user,
                "ACCESS_DENIED_ROLE",
                f"Szerepkör alapú hozzáférés megtagadva; szükséges szerepkörök: {', '.join(role_names)}",
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nincs jogosultság ehhez a művelethez")
        return current_user
    return checker


def require_permission(permission_code: str):
    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # Az Admin továbbra is rendszer-szintű szuperfelhasználó. A normál
        # felhasználók modul- és funkcióhozzáférése kizárólag adatbázisból jön,
        # nem kerül a JWT tokenbe, így admin módosítás után azonnal érvényes.
        if current_user.role.name == ROLE_ADMIN:
            return current_user
        if permission_code not in current_user.permissions:
            _audit_denied(
                db,
                current_user,
                "ACCESS_DENIED_PERMISSION",
                f"Jogosultság alapú hozzáférés megtagadva: {permission_code}",
                entity_id=permission_code,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "permission_required",
                    "permission": permission_code,
                    "message": "Nincs jogosultság ehhez a modulhoz vagy művelethez.",
                },
            )
        return current_user
    return checker


RequireAdmin = require_roles(ROLE_ADMIN)
RequireOfficeOrAdmin = require_roles(ROLE_ADMIN, ROLE_OFFICE)
RequireAnyRole = require_roles(ROLE_ADMIN, ROLE_OFFICE, ROLE_TECHNICIAN)
RequireServiceAccess = require_permission(PERMISSION_SERVICE_ACCESS)
RequireHrAccess = require_permission(PERMISSION_HR_ACCESS)
RequireHrLeaveSelf = require_permission(PERMISSION_HR_LEAVE_SELF)
RequireHrLeaveRequest = require_permission(PERMISSION_HR_LEAVE_REQUEST)
RequireHrLeaveApprove = require_permission(PERMISSION_HR_LEAVE_APPROVE)
RequireHrSummaryView = require_permission(PERMISSION_HR_SUMMARY_VIEW)
RequireHrAdmin = require_permission(PERMISSION_HR_ADMIN)
RequireCrmAccess = require_permission(PERMISSION_CRM_ACCESS)
RequireCrmWrite = require_permission(PERMISSION_CRM_WRITE)
RequireCrmContractManage = require_permission(PERMISSION_CRM_CONTRACT_MANAGE)
RequireCrmAdmin = require_permission(PERMISSION_CRM_ADMIN)
RequireAdminAccess = require_permission(PERMISSION_ADMIN_ACCESS)
RequireAdminBackupManage = require_permission(PERMISSION_ADMIN_BACKUP_MANAGE)
RequireAdminBackupRestore = require_permission(PERMISSION_ADMIN_BACKUP_RESTORE)
RequireProcurementApprove = require_permission(PERMISSION_PROCUREMENT_APPROVE)
