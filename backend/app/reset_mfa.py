from __future__ import annotations

import argparse
import sys
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import User
from .services.audit import add_audit_log
from .services.auth_security import revoke_user_sessions


class MfaResetError(RuntimeError):
    pass


def reset_user_mfa(db: Session, *, email: str) -> User:
    normalized = email.strip()
    user = db.query(User).filter(func.lower(User.email) == normalized.lower()).one_or_none()
    if user is None:
        raise MfaResetError(f"Nem található felhasználó ezzel az email címmel: {normalized}")
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    user.mfa_recovery_codes = None
    user.mfa_last_counter = None
    user.mfa_enrolled_at = None
    revoked = revoke_user_sessions(db, user.id)
    add_audit_log(
        db,
        None,
        "MFA_RESET_LOCAL",
        "user",
        user.id,
        f"MFA helyi helyreállító paranccsal törölve; {revoked} aktív munkamenet visszavonva. A következő kötelező MFA belépéskor újraregisztráció szükséges.",
        entity_display_id=user.email,
    )
    db.commit()
    db.refresh(user)
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description="MFA helyi vészhelyzeti visszaállítása. Kizárólag szerverkonzolról használd.")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        user = reset_user_mfa(db, email=args.email)
    except (MfaResetError, SQLAlchemyError) as exc:
        db.rollback()
        print(f"Hiba: {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()
    print(f"MFA visszaállítva: {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
