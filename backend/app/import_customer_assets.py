from __future__ import annotations

from .database import SessionLocal
from .importers.customer_assets import import_builtin_customer_assets
from .models import User


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@example.com").first()
        result = import_builtin_customer_assets(db, admin)
        db.commit()
        print(
            "Import kész: "
            f"sorok={result.rows}, "
            f"ügyfelek létrehozva={result.customers_created}, "
            f"ügyfelek frissítve={result.customers_updated}, "
            f"helyszínek létrehozva={result.locations_created}, "
            f"kapcsolattartók létrehozva={result.contacts_created}, "
            f"eszközök létrehozva={result.assets_created}, "
            f"eszközök frissítve={result.assets_updated}, "
            f"kihagyva={result.skipped}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
