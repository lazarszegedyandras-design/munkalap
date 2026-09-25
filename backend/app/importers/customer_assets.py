from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Asset, AssetHistory, Customer, CustomerContact, Location, User
from ..services.asset_display import IMPORT_INTERNAL_ID_RE

IMPORT_BATCH = "customer_assets_20260616"
IMPORT_SOURCE = "Ügyfél_lista_20260616 másolata.xlsx"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "customer_assets_20260616.json"


@dataclass
class ImportResult:
    rows: int = 0
    customers_created: int = 0
    customers_updated: int = 0
    locations_created: int = 0
    contacts_created: int = 0
    assets_created: int = 0
    assets_updated: int = 0
    asset_notes_cleared: int = 0
    skipped: int = 0


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text or None


def eq_clean(left: str | None, right: str | None) -> bool:
    return clean(left) == clean(right)


def append_note(existing: str | None, line: str | None) -> str | None:
    line = clean(line)
    if not line:
        return existing
    existing = existing or ""
    if line in existing:
        return existing or None
    if existing:
        return f"{existing}\n{line}"
    return line


def first_non_empty(*values: str | None) -> str | None:
    for value in values:
        value = clean(value)
        if value:
            return value
    return None


def normalize_key(value: str | None) -> str:
    return (clean(value) or "").casefold()


def parse_machine_type(machine_type: str | None) -> tuple[str | None, str | None, str | None]:
    raw = clean(machine_type)
    if not raw:
        return None, None, None
    text = raw.casefold()
    manufacturer: str | None = None
    model = raw
    category = "Egyéb eszköz"

    rules = [
        ("pitney bowes", "Pitney Bowes", ["pitney bowes", "pb ", "relay", "di ", "di3", "di4", "di5", "di6"]),
        ("ricoh", "Ricoh", ["ricoh", "mp ", "im ", "sp "]),
        ("neopost", "Neopost", ["neopost", "ds", "di68"]),
        ("francotyp", "Francotyp-Postalia", ["fpi", "fp ", "postbase"]),
        ("brother", "Brother", ["brother"]),
        ("quadient", "Quadient", ["quadient"]),
    ]
    for _, label, tokens in rules:
        if any(token in f" {text} " for token in tokens):
            manufacturer = label
            break

    if manufacturer == "Pitney Bowes":
        model = raw.replace("Pitney Bowes", "").replace("PB", "").strip(" -") or raw
    elif manufacturer == "Ricoh":
        model = raw.replace("RICOH", "").replace("Ricoh", "").strip(" -") or raw
    elif manufacturer == "Neopost":
        model = raw.replace("Neopost", "").strip(" -") or raw
    elif manufacturer == "Francotyp-Postalia":
        model = raw
    elif manufacturer == "Brother":
        model = raw.replace("Brother", "").strip(" -") or raw

    if any(token in text for token in ["relay", " di", "di ", "di3", "di4", "di5", "di6", "ds", "fpi", "si-", "si ", "borít", "omr"]):
        category = "Borítékoló gép"
    elif any(token in text for token in ["ricoh", "brother", "nyomtat", "printer", "mfp", "sp ", "mp ", "im "]):
        category = "Nyomtató / MFP"

    return manufacturer, model, category


def source_file() -> Path:
    runtime_file = Path(get_settings().runtime_dir) / DATA_FILE.name
    return runtime_file if runtime_file.is_file() else DATA_FILE


def source_available() -> bool:
    return source_file().is_file()


def load_builtin_rows() -> list[dict[str, Any]]:
    path = source_file()
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def find_customer(db: Session, company_code: str | None, customer_name: str) -> Customer | None:
    if company_code:
        candidates = db.query(Customer).filter(Customer.company_code == company_code).all()
    else:
        candidates = db.query(Customer).filter(Customer.company_code.is_(None)).all()
    name_key = normalize_key(customer_name)
    for customer in candidates:
        if normalize_key(customer.name) == name_key:
            return customer
    return None


def get_or_create_customer(db: Session, row: dict[str, Any], current_user: User | None) -> tuple[Customer, bool, bool]:
    company_code = clean(row.get("company_code"))
    customer_name = clean(row.get("customer_name"))
    if not customer_name:
        raise ValueError("Hiányzó ügyfélnév")

    customer = find_customer(db, company_code, customer_name)
    created = False
    updated = False
    row_note = (
        f"Excel import sor {row.get('source_row')}: "
        f"Cég={company_code or '-'}; "
        f"Kapcsolattartó={clean(row.get('contact_person')) or '-'}; "
        f"Telefon={clean(row.get('phone')) or '-'}; "
        f"Email={clean(row.get('email')) or '-'}; "
        f"Szerződött cím={clean(row.get('customer_address')) or '-'}"
    )

    if not customer:
        customer = Customer(
            name=customer_name,
            company_code=company_code,
            contact_person=clean(row.get("contact_person")),
            phone=clean(row.get("phone")),
            email=clean(row.get("email")),
            address=clean(row.get("customer_address")),
            note=f"Import forrás: {IMPORT_SOURCE}\n{row_note}",
        )
        db.add(customer)
        db.flush()
        created = True
        return customer, created, updated

    for field, row_key in [
        ("contact_person", "contact_person"),
        ("phone", "phone"),
        ("email", "email"),
        ("address", "customer_address"),
    ]:
        value = clean(row.get(row_key))
        current = clean(getattr(customer, field))
        if value and not current:
            setattr(customer, field, value)
            updated = True
        elif value and current and not eq_clean(current, value):
            new_note = append_note(customer.note, row_note)
            if new_note != customer.note:
                customer.note = new_note
                updated = True

    if company_code and not customer.company_code:
        customer.company_code = company_code
        updated = True
    return customer, created, updated


def location_display_name(row: dict[str, Any], customer: Customer) -> str:
    explicit_name = clean(row.get("location_name"))
    if explicit_name:
        return explicit_name
    service_address = first_non_empty(row.get("location_address"), row.get("customer_address"))
    if not service_address or eq_clean(service_address, customer.address):
        return "Alapértelmezett helyszín"
    return f"Helyszín - {service_address[:90]}"


def find_location(db: Session, customer_id: int, name: str, address: str | None) -> Location | None:
    candidates = db.query(Location).filter(Location.customer_id == customer_id).all()
    name_key = normalize_key(name)
    address_key = normalize_key(address)
    for location in candidates:
        if normalize_key(location.name) == name_key and normalize_key(location.address) == address_key:
            return location
    return None


def get_or_create_location(db: Session, row: dict[str, Any], customer: Customer) -> tuple[Location, bool]:
    service_address = first_non_empty(row.get("location_address"), row.get("customer_address"))
    name = location_display_name(row, customer)
    location = find_location(db, customer.id, name, service_address)
    if location:
        if not location.is_active:
            raise ValueError(f"Az importált helyszín inaktív; előbb aktiváld: {location.name}")
        return location, False

    location = Location(
        customer_id=customer.id,
        name=name,
        address=service_address,
        note=(
            f"Import forrás: {IMPORT_SOURCE}; Excel sor: {row.get('source_row')}; "
            f"Telephely név: {clean(row.get('location_name')) or '-'}; "
            f"Telephely cím: {clean(row.get('location_address')) or '-'}"
        ),
    )
    db.add(location)
    db.flush()
    return location, True


def find_contact(db: Session, customer_id: int, name: str | None, phone: str | None, email: str | None, location_id: int | None) -> CustomerContact | None:
    name_key = normalize_key(name)
    phone_key = normalize_key(phone)
    email_key = normalize_key(email)
    for contact in db.query(CustomerContact).filter(CustomerContact.customer_id == customer_id).all():
        if normalize_key(contact.name) != name_key:
            continue
        if email_key and normalize_key(contact.email) == email_key:
            return contact
        if phone_key and normalize_key(contact.phone) == phone_key:
            return contact
        if not email_key and not phone_key and contact.location_id == location_id:
            return contact
    return None


def get_or_create_contact(db: Session, row: dict[str, Any], customer: Customer, location: Location) -> tuple[CustomerContact | None, bool]:
    contact_name = clean(row.get("contact_person"))
    phone = clean(row.get("phone"))
    email = clean(row.get("email"))
    if not contact_name and not phone and not email:
        return None, False
    if not contact_name:
        contact_name = email or phone or "Importált kapcsolattartó"
    contact = find_contact(db, customer.id, contact_name, phone, email, location.id)
    if contact:
        for attr, value in [("phone", phone), ("email", email), ("location_id", location.id)]:
            if value and not getattr(contact, attr):
                setattr(contact, attr, value)
        if not contact.category:
            contact.category = "Szerviz"
        return contact, False
    contact = CustomerContact(
        customer_id=customer.id,
        location_id=location.id,
        category="Szerviz",
        name=contact_name,
        phone=phone,
        email=email,
        is_primary=False,
        note=f"Excel import kapcsolattartó; forrás: {IMPORT_SOURCE}; sor: {row.get('source_row')}",
    )
    db.add(contact)
    db.flush()
    return contact, True


IMPORT_NOTE_PREFIXES = (
    "Import forrás:",
    "Excel sor:",
    "Cég:",
    "Ügyfél:",
    "Szerződött cím:",
    "Telephely név:",
    "Telephely cím:",
    "Kapcsolattartó:",
    "Telefon:",
    "Email:",
    "Gép típusa:",
    "Gyáriszám:",
)
def clean_asset_note_after_import(note: str | None) -> str | None:
    """Remove importer-generated metadata while preserving genuine manual notes."""
    if not note:
        return None
    lines = [line.strip() for line in str(note).splitlines() if line.strip()]
    has_import_block = any(line.startswith("Import forrás:") for line in lines) and any(
        line.startswith("Excel sor:") for line in lines
    )
    cleaned: list[str] = []
    for line in lines:
        if IMPORT_INTERNAL_ID_RE.fullmatch(line):
            continue
        if has_import_block and line.startswith(IMPORT_NOTE_PREFIXES):
            continue
        cleaned.append(line)
    return "\n".join(cleaned) or None


def upsert_asset(db: Session, row: dict[str, Any], customer: Customer, location: Location, current_user: User | None) -> tuple[Asset, bool, bool]:
    source_row = int(row["source_row"])
    internal_id = f"IMP-20260616-{source_row:04d}"
    machine_type = clean(row.get("machine_type")) or "Ismeretlen eszköz"
    manufacturer, model, category = parse_machine_type(machine_type)
    asset = (
        db.query(Asset)
        .filter(Asset.import_batch == IMPORT_BATCH, Asset.import_row == source_row)
        .first()
        or db.query(Asset).filter(Asset.internal_id == internal_id).first()
    )
    created = False
    note_cleared = False
    values = {
        "serial_number": clean(row.get("serial_number")),
        "type": machine_type,
        "manufacturer": manufacturer,
        "model": model,
        "category": category,
        "status": "aktív",
        "customer_id": customer.id,
        "current_location_id": location.id,
        "internal_use": False,
        "company_code": clean(row.get("company_code")),
        "import_source": IMPORT_SOURCE,
        "import_batch": IMPORT_BATCH,
        "import_row": source_row,
    }
    if not asset:
        asset = Asset(internal_id=internal_id, note=None, **values)
        db.add(asset)
        db.flush()
        db.add(
            AssetHistory(
                asset_id=asset.id,
                user_id=current_user.id if current_user else None,
                action="excel import",
                description=f"Eszköz importálva az ügyféllistából, Excel sor: {source_row}",
            )
        )
        created = True
    else:
        cleaned_note = clean_asset_note_after_import(asset.note)
        note_cleared = cleaned_note != asset.note
        asset.note = cleaned_note
        for key, value in values.items():
            setattr(asset, key, value)
    return asset, created, note_cleared


def import_customer_asset_rows(db: Session, rows: list[dict[str, Any]], current_user: User | None = None) -> ImportResult:
    result = ImportResult()
    for row in rows:
        result.rows += 1
        try:
            if not clean(row.get("customer_name")) or not clean(row.get("machine_type")):
                result.skipped += 1
                continue
            customer, customer_created, customer_updated = get_or_create_customer(db, row, current_user)
            if customer_created:
                result.customers_created += 1
            elif customer_updated:
                result.customers_updated += 1
            location, location_created = get_or_create_location(db, row, customer)
            if location_created:
                result.locations_created += 1
            _, contact_created = get_or_create_contact(db, row, customer, location)
            if contact_created:
                result.contacts_created += 1
            _, asset_created, note_cleared = upsert_asset(db, row, customer, location, current_user)
            if asset_created:
                result.assets_created += 1
            else:
                result.assets_updated += 1
            if note_cleared:
                result.asset_notes_cleared += 1
        except ValueError:
            result.skipped += 1
    return result


def import_builtin_customer_assets(db: Session, current_user: User | None = None) -> ImportResult:
    return import_customer_asset_rows(db, load_builtin_rows(), current_user)
