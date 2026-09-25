from datetime import date, timedelta
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import (
    Asset,
    AssetHistory,
    Customer,
    CustomerContact,
    Location,
    Material,
    ROLE_ADMIN,
    ROLE_OFFICE,
    ROLE_TECHNICIAN,
    Role,
    User,
    WorkOrder,
    WorkOrderAsset,
    WorkOrderMaterial,
)
from .security import get_password_hash
from .config import get_settings
from .passwords import validate_password_policy
from .importers.customer_assets import import_builtin_customer_assets, source_available as customer_source_available
from .services.work_order_numbers import next_work_order_number
from .services.permissions import ensure_permission_catalog, grant_service_access_if_missing, grant_service_access_to_all_users


def get_or_create_role(db: Session, name: str) -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if not role:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def run_seed() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        permission_catalog_was_empty = ensure_permission_catalog(db)
        admin_role = get_or_create_role(db, ROLE_ADMIN)
        office_role = get_or_create_role(db, ROLE_OFFICE)
        tech_role = get_or_create_role(db, ROLE_TECHNICIAN)

        admin_email = settings.bootstrap_admin_email.strip().lower() or "admin@example.com"
        admin = db.query(User).filter(User.email == admin_email).first()
        # Upgrade safety: an existing installation may have renamed the original
        # administrator account. In production, reuse any existing Admin user
        # instead of silently trying to bootstrap a second well-known account.
        if admin is None and settings.is_production:
            admin = (
                db.query(User)
                .join(Role, User.role_id == Role.id)
                .filter(Role.name == ROLE_ADMIN)
                .order_by(User.id.asc())
                .first()
            )
        admin_created = admin is None
        if not admin:
            if settings.is_production:
                bootstrap_password = settings.bootstrap_admin_password
                if not bootstrap_password:
                    raise RuntimeError(
                        "Production bootstrap requires BOOTSTRAP_ADMIN_PASSWORD or BOOTSTRAP_ADMIN_PASSWORD_FILE "
                        "when no administrator account exists"
                    )
                validate_password_policy(bootstrap_password)
                password_hash = get_password_hash(bootstrap_password)
            else:
                password_hash = get_password_hash("")
            admin = User(
                email=admin_email,
                full_name="Rendszeradminisztrátor",
                password_hash=password_hash,
                must_change_password=True,
                role_id=admin_role.id,
                is_active=True,
            )
            db.add(admin)

        # Public production must never seed well-known demo credentials or demo
        # customer/work-order data. Existing real data is left untouched.
        if settings.is_production:
            db.flush()
            if permission_catalog_was_empty:
                grant_service_access_to_all_users(db)
            elif admin_created:
                grant_service_access_if_missing(db, admin)
            db.commit()
            return

        technician = db.query(User).filter(User.email == "technikus@example.com").first()
        technician_created = technician is None
        if not technician:
            technician = User(
                email="technikus@example.com",
                full_name="Minta Technikus",
                password_hash=get_password_hash("Technikus!123"),
                must_change_password=True,
                role_id=tech_role.id,
                is_active=True,
            )
            db.add(technician)

        office = db.query(User).filter(User.email == "iroda@example.com").first()
        office_created = office is None
        if not office:
            office = User(
                email="iroda@example.com",
                full_name="Irodai Felhasználó",
                password_hash=get_password_hash("Iroda!123"),
                must_change_password=True,
                role_id=office_role.id,
                is_active=True,
            )
            db.add(office)

        db.flush()

        if permission_catalog_was_empty:
            # Régi, jogosultsági táblák nélküli mentés visszaállítása után a
            # meglévő felhasználók megtartják a korábbi Szerviz-hozzáférésüket.
            grant_service_access_to_all_users(db)
        else:
            for created, user in ((admin_created, admin), (technician_created, technician), (office_created, office)):
                if created:
                    grant_service_access_if_missing(db, user)
        db.flush()

        if not db.query(Customer).first():
            c1 = Customer(name="Alfa Irodaház Kft.", contact_person="Kovács Péter", phone="+36 30 111 1111", email="peter@alfa.example", address="1111 Budapest, Fő utca 1.", note="Kiemelt ügyfél")
            c2 = Customer(name="Beta Gyártó Zrt.", contact_person="Nagy Anna", phone="+36 20 222 2222", email="anna@beta.example", address="9021 Győr, Ipar út 8.")
            db.add_all([c1, c2])
            db.flush()
            l1 = Location(customer_id=c1.id, name="Alfa központ", address="1111 Budapest, Fő utca 1.", gps_lat="47.4979", gps_lng="19.0402")
            l2 = Location(customer_id=c1.id, name="Alfa raktár", address="2040 Budaörs, Raktár körút 3.")
            l3 = Location(customer_id=c2.id, name="Beta gyártócsarnok", address="9021 Győr, Ipar út 8.")
            db.add_all([l1, l2, l3])
            db.flush()
            cc1 = CustomerContact(customer_id=c1.id, location_id=l1.id, category="Szerviz", name="Kovács Péter", phone="+36 30 111 1111", email="peter@alfa.example", is_primary=True)
            cc2 = CustomerContact(customer_id=c1.id, category="Sales", name="Tóth Éva", phone="+36 30 111 1112", email="sales@alfa.example")
            cc3 = CustomerContact(customer_id=c2.id, location_id=l3.id, category="Szerviz", name="Nagy Anna", phone="+36 20 222 2222", email="anna@beta.example", is_primary=True)
            db.add_all([cc1, cc2, cc3])
            db.flush()

            m1 = Material(sku="SZURO-001", name="Finomszűrő betét", unit="db", unit_price=3500, stock=24)
            m2 = Material(sku="KABEL-UTP", name="UTP kábel", unit="m", unit_price=180, stock=300)
            m3 = Material(sku="CSAVAR-M6", name="M6 rögzítő csavar", unit="db", unit_price=40, stock=500)
            db.add_all([m1, m2, m3])
            db.flush()

            a1 = Asset(
                internal_id="ESZK-0001",
                serial_number="SN-A1001",
                type="Klímaberendezés",
                manufacturer="Daikin",
                model="FTXM35R",
                category="HVAC",
                status="aktív",
                customer_id=c1.id,
                current_location_id=l1.id,
                purchase_date=date.today() - timedelta(days=500),
                warranty_expiry=date.today() + timedelta(days=230),
                last_maintenance_date=date.today() - timedelta(days=160),
                maintenance_cycle_months=6,
                next_maintenance_date=date.today(),
                note="Éves karbantartás esedékes",
            )
            a2 = Asset(
                internal_id="ESZK-0002",
                serial_number="SN-B2002",
                type="Kompresszor",
                manufacturer="Atlas Copco",
                model="GA 11",
                category="Ipari gép",
                status="javítás alatt",
                customer_id=c2.id,
                current_location_id=l3.id,
                next_maintenance_date=date.today() - timedelta(days=10),
            )
            a3 = Asset(
                internal_id="BELSO-0001",
                serial_number="LAP-9981",
                type="Laptop",
                manufacturer="Lenovo",
                model="ThinkPad T14",
                category="Belső IT",
                status="raktáron",
                internal_use=True,
            )
            db.add_all([a1, a2, a3])
            db.flush()
            db.add_all([
                AssetHistory(asset_id=a1.id, user_id=admin.id, action="létrehozás", description="Seed eszköz létrehozva"),
                AssetHistory(asset_id=a2.id, user_id=admin.id, action="létrehozás", description="Seed eszköz létrehozva"),
                AssetHistory(asset_id=a3.id, user_id=admin.id, action="létrehozás", description="Seed eszköz létrehozva"),
            ])

            wo1 = WorkOrder(
                number=next_work_order_number(db),
                customer_id=c1.id,
                location_id=l1.id,
                contact_id=cc1.id,
                status="ütemezve",
                priority="sürgős",
                technician_id=technician.id,
                description="Klímaberendezés éves karbantartása és szűrőcsere.",
                work_type="karbantartás",
                planned_date=date.today(),
                internal_note="Ügyfél reggel 8 után elérhető.",
                customer_note="A munkavégzés várható ideje 1-2 óra.",
            )
            db.add(wo1)
            db.flush()

            wo2 = WorkOrder(
                number=next_work_order_number(db),
                customer_id=c2.id,
                location_id=l3.id,
                status="folyamatban",
                priority="normál",
                technician_id=technician.id,
                description="Kompresszor hiba feltárása, nyomásvesztés vizsgálata.",
                work_type="javítás",
                planned_date=date.today() + timedelta(days=1),
            )
            db.add(wo2)
            db.flush()
            db.add_all([
                WorkOrderAsset(work_order_id=wo1.id, asset_id=a1.id),
                WorkOrderAsset(work_order_id=wo2.id, asset_id=a2.id),
                WorkOrderMaterial(work_order_id=wo1.id, material_id=m1.id, quantity=2, unit_price=m1.unit_price, note="Szűrőcsere"),
            ])

        if customer_source_available():
            import_builtin_customer_assets(db, admin)

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
