from __future__ import annotations

import argparse
import getpass
import sys
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import User
from .passwords import validate_password_policy
from .security import get_password_hash
from .services.audit import add_audit_log
from .services.auth_security import revoke_user_sessions


class PasswordResetError(RuntimeError):
    """A helyi jelszó-visszaállítás felhasználói hibája."""


def reset_user_password(
    db: Session,
    *,
    email: str,
    new_password: str,
    activate: bool = False,
) -> User:
    normalized_email = email.strip()
    if not normalized_email:
        raise PasswordResetError("Az email cím megadása kötelező.")

    validate_password_policy(new_password)

    user = (
        db.query(User)
        .filter(func.lower(User.email) == normalized_email.lower())
        .one_or_none()
    )
    if user is None:
        raise PasswordResetError(f"Nem található felhasználó ezzel az email címmel: {normalized_email}")

    user.password_hash = get_password_hash(new_password)
    user.must_change_password = True
    revoke_user_sessions(db, user.id)
    if activate:
        user.is_active = True

    add_audit_log(
        db,
        None,
        "jelszó-visszaállítás",
        "user",
        user.id,
        (
            f"Felhasználói jelszó helyi helyreállító paranccsal visszaállítva: {user.email}. "
            "A következő bejelentkezéskor kötelező jelszócsere szükséges."
        ),
    )
    db.commit()
    db.refresh(user)
    return user


def _read_new_password() -> str:
    while True:
        password = getpass.getpass("Új ideiglenes jelszó: ")
        confirmation = getpass.getpass("Új ideiglenes jelszó ismét: ")
        if password != confirmation:
            print("A két jelszó nem egyezik. Próbáld újra.", file=sys.stderr)
            continue
        try:
            return validate_password_policy(password)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Felhasználói jelszó helyi visszaállítása. Az új jelszó csak ideiglenes: "
            "a következő bejelentkezéskor kötelező lesz megváltoztatni."
        )
    )
    parser.add_argument(
        "--email",
        default="admin@example.com",
        help="A visszaállítandó felhasználó email címe (alapértelmezés: admin@example.com).",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="A felhasználót a jelszó-visszaállítással együtt aktiválja is.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    print(f"Jelszó-visszaállítás: {args.email}")
    print("A jelszó gépelés közben nem jelenik meg.")

    try:
        new_password = _read_new_password()
    except (EOFError, KeyboardInterrupt):
        print("\nA jelszó-visszaállítás megszakítva.", file=sys.stderr)
        return 130

    db = SessionLocal()
    try:
        user = reset_user_password(
            db,
            email=args.email,
            new_password=new_password,
            activate=args.activate,
        )
    except (PasswordResetError, ValueError) as exc:
        db.rollback()
        print(f"Hiba: {exc}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        db.rollback()
        print(f"Adatbázishiba: {exc}", file=sys.stderr)
        return 3
    finally:
        db.close()

    print(f"Sikeres jelszó-visszaállítás: {user.email}")
    print("A következő bejelentkezéskor kötelező új saját jelszót megadni.")
    if not user.is_active:
        print("Figyelem: a felhasználó inaktív maradt. Az aktiváláshoz használd az --activate kapcsolót.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
