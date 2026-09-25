from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from ..models import WorkOrder

STATIC_COMPANY_PROFILES_PATH = Path(__file__).resolve().parents[1] / "data" / "company_profiles.json"


def company_profiles_path() -> Path:
    settings = get_settings()
    runtime_path = Path(settings.runtime_dir) / "company_profiles.json"
    return runtime_path if runtime_path.exists() else STATIC_COMPANY_PROFILES_PATH


@dataclass(frozen=True)
class CompanyProfile:
    code: str
    aliases: tuple[str, ...]
    short_name: str
    legal_name: str
    tax_number: str
    company_registration_number: str
    registered_address: str
    contact_address: str
    phone: str
    mobile_phone: str
    email: str
    worksheet_phone: str
    worksheet_email: str
    website: str
    contact_person: str
    activity: str
    source_urls: tuple[str, ...]
    source_note: str
    source: str = "builtin"

    @property
    def display_name(self) -> str:
        return self.short_name or self.legal_name

    @property
    def address_for_worksheet(self) -> str:
        return self.contact_address or self.registered_address

    @property
    def phone_for_worksheet(self) -> str:
        # A vezetékes számot részesítjük előnyben: korábbi profilokban a
        # mobile_phone személyhez kötött telefonszámot is tartalmazhatott.
        return self.worksheet_phone or self.phone or self.mobile_phone

    @property
    def email_for_worksheet(self) -> str:
        return self.worksheet_email or self.email

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "display_name": self.display_name,
            "address_for_worksheet": self.address_for_worksheet,
            "aliases": list(self.aliases),
            "short_name": self.short_name,
            "legal_name": self.legal_name,
            "tax_number": self.tax_number,
            "company_registration_number": self.company_registration_number,
            "registered_address": self.registered_address,
            "contact_address": self.contact_address,
            "phone": self.phone,
            "mobile_phone": self.mobile_phone,
            "email": self.email,
            "worksheet_phone": self.worksheet_phone,
            "worksheet_email": self.worksheet_email,
            "phone_for_worksheet": self.phone_for_worksheet,
            "email_for_worksheet": self.email_for_worksheet,
            "website": self.website,
            "contact_person": self.contact_person,
            "activity": self.activity,
            "source_urls": list(self.source_urls),
            "source_note": self.source_note,
            "source": self.source,
        }


def normalize_company_code(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _profile_from_dict(row: dict[str, Any]) -> CompanyProfile:
    code = normalize_company_code(row.get("code"))
    return CompanyProfile(
        code=code,
        aliases=tuple(normalize_company_code(alias) for alias in row.get("aliases", [])),
        short_name=row.get("short_name") or "",
        legal_name=row.get("legal_name") or "",
        tax_number=row.get("tax_number") or "",
        company_registration_number=row.get("company_registration_number") or "",
        registered_address=row.get("registered_address") or "",
        contact_address=row.get("contact_address") or "",
        phone=row.get("phone") or "",
        mobile_phone=row.get("mobile_phone") or "",
        email=row.get("email") or "",
        worksheet_phone=row.get("worksheet_phone") or "",
        worksheet_email=row.get("worksheet_email") or "",
        website=row.get("website") or "",
        contact_person=row.get("contact_person") or "",
        activity=row.get("activity") or "",
        source_urls=tuple(row.get("source_urls", [])),
        source_note=row.get("source_note") or "",
        source=row.get("source") or "builtin",
    )


@lru_cache(maxsize=8)
def _load_company_profiles_cached(path_string: str, modified_ns: int) -> dict[str, CompanyProfile]:
    # A modified_ns a cache-kulcs része. Több Uvicorn worker esetén minden
    # folyamat automatikusan újraolvassa a fájlt, amint egy másik worker
    # adminmódosítást ír bele.
    rows = json.loads(Path(path_string).read_text(encoding="utf-8"))
    profiles: dict[str, CompanyProfile] = {}
    for row in rows:
        profile = _profile_from_dict(row)
        for key in {profile.code, *profile.aliases}:
            if key:
                profiles[key] = profile
    return profiles


def load_company_profiles() -> dict[str, CompanyProfile]:
    path = company_profiles_path()
    if not path.is_file():
        return {}
    return _load_company_profiles_cached(str(path), path.stat().st_mtime_ns)


def _clear_company_profile_cache() -> None:
    _load_company_profiles_cached.cache_clear()


# Visszamenőleges kompatibilitás a meglévő hívásokkal és tesztekkel.
load_company_profiles.cache_clear = _clear_company_profile_cache  # type: ignore[attr-defined]


def list_company_profiles() -> list[CompanyProfile]:
    seen: set[str] = set()
    ordered: list[CompanyProfile] = []
    for profile in load_company_profiles().values():
        if profile.code in seen:
            continue
        seen.add(profile.code)
        ordered.append(profile)
    return sorted(ordered, key=lambda item: item.code)


def get_company_profile(code: str | None) -> CompanyProfile | None:
    return load_company_profiles().get(normalize_company_code(code))


def _fallback_profile_from_settings(settings: Settings) -> CompanyProfile | None:
    if not any([settings.supplier_name, settings.supplier_address, settings.supplier_phone, settings.supplier_email, settings.supplier_contact]):
        return None
    return CompanyProfile(
        code="ENV",
        aliases=("ENV",),
        short_name=settings.supplier_name,
        legal_name=settings.supplier_name,
        tax_number="",
        company_registration_number="",
        registered_address=settings.supplier_address,
        contact_address=settings.supplier_address,
        phone=settings.supplier_phone,
        mobile_phone=settings.supplier_phone,
        email=settings.supplier_email,
        worksheet_phone=settings.supplier_phone,
        worksheet_email=settings.supplier_email,
        website="",
        contact_person=settings.supplier_contact,
        activity="",
        source_urls=(),
        source_note=".env SUPPLIER_* változókból betöltött szállítói adatok.",
        source="env",
    )


def resolve_work_order_company_profile(order: WorkOrder, settings: Settings) -> CompanyProfile | None:
    candidates: list[str | None] = []
    if order.customer:
        candidates.append(order.customer.company_code)
    for link in order.asset_links:
        if link.asset:
            candidates.append(link.asset.company_code)
            if link.asset.customer:
                candidates.append(link.asset.customer.company_code)

    for candidate in candidates:
        profile = get_company_profile(candidate)
        if profile:
            return profile
    return _fallback_profile_from_settings(settings)


def update_company_profile(code: str, changes: dict[str, Any]) -> CompanyProfile:
    normalized_code = normalize_company_code(code)
    current = get_company_profile(normalized_code)
    if not current:
        raise KeyError(code)

    rows = []
    for profile in list_company_profiles():
        row = profile.to_dict()
        row.pop("display_name", None)
        row.pop("address_for_worksheet", None)
        row.pop("phone_for_worksheet", None)
        row.pop("email_for_worksheet", None)
        rows.append(row)
    updated_row: dict[str, Any] | None = None
    for row in rows:
        if normalize_company_code(row.get("code")) != current.code:
            continue
        for key, value in changes.items():
            if value is None or key in {"code", "source", "source_urls"}:
                continue
            if key == "aliases":
                aliases = [normalize_company_code(item) for item in value if normalize_company_code(item)]
                row[key] = sorted(set([current.code, *aliases]))
            else:
                row[key] = value
        row["code"] = current.code
        row["source"] = "admin"
        updated_row = row
        break

    if updated_row is None:
        raise KeyError(code)

    settings = get_settings()
    target = Path(settings.runtime_dir) / "company_profiles.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=".company_profiles.", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise

    load_company_profiles.cache_clear()
    updated = get_company_profile(current.code)
    if not updated:
        raise RuntimeError("A mentett cégprofil nem tölthető vissza")
    return updated
