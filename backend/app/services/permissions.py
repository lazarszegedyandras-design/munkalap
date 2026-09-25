from __future__ import annotations

from sqlalchemy.orm import Session

from ..access_control import PERMISSION_CATALOG, PERMISSION_SERVICE_ACCESS, validate_permission_codes
from ..models import Permission, User, UserPermission


def ensure_permission_catalog(db: Session) -> bool:
    """Ensure the static permission catalog exists.

    Returns True when the catalog table was empty before this call. This is
    used to recognize a legacy backup restore where permission tables did not
    exist yet.
    """
    was_empty = db.query(Permission.id).first() is None
    existing = {row.code: row for row in db.query(Permission).all()}
    for item in PERMISSION_CATALOG:
        permission = existing.get(item["code"])
        if permission is None:
            permission = Permission(code=item["code"])
            db.add(permission)
        permission.module = item["module"]
        permission.name = item["name"]
        permission.description = item["description"]
        permission.is_module_access = bool(item["is_module_access"])
    db.flush()
    return was_empty


def set_user_permissions(db: Session, user: User, codes: list[str] | None) -> list[str]:
    normalized = validate_permission_codes(codes)
    permissions = {
        permission.code: permission
        for permission in db.query(Permission).filter(Permission.code.in_(normalized)).all()
    } if normalized else {}
    missing = [code for code in normalized if code not in permissions]
    if missing:
        raise ValueError("A jogosultsági katalógus hiányos: " + ", ".join(missing))

    # A relationshipen keresztüli csere tisztán tartja az SQLAlchemy identity
    # mapet is; így ismételt admin jogosultságmódosításnál sincs ütköző
    # association objektum a sessionben.
    user.permission_links.clear()
    db.flush()
    for code in normalized:
        user.permission_links.append(UserPermission(permission=permissions[code]))
    db.flush()
    return normalized


def grant_service_access_if_missing(db: Session, user: User) -> None:
    service_permission = db.query(Permission).filter(Permission.code == PERMISSION_SERVICE_ACCESS).one()
    exists = db.query(UserPermission).filter(
        UserPermission.user_id == user.id,
        UserPermission.permission_id == service_permission.id,
    ).first()
    if not exists:
        db.add(UserPermission(user_id=user.id, permission_id=service_permission.id))


def grant_service_access_to_all_users(db: Session) -> None:
    for user in db.query(User).all():
        grant_service_access_if_missing(db, user)
