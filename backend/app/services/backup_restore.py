from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select, text
from sqlalchemy.engine import Connection, Engine

from ..config import Settings, export_application_settings, runtime_settings_path
from ..models import Base
from ..version import APP_VERSION
from .work_order_archive_storage import archive_path, archive_root
from .contract_archive_storage import contract_archive_path, contract_archive_root
from .work_order_signature_storage import signature_path, signature_root
from .work_order_photo_storage import photo_path, photo_root

BACKUP_FORMAT = "munkalap-eszkoz-backup"
BACKUP_VERSION = 16
SUPPORTED_BACKUP_VERSIONS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}
MAX_BACKUP_SIZE = 500 * 1024 * 1024

APP_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
APP_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
STATIC_COMPANY_PROFILES = APP_DATA_DIR / "company_profiles.json"
STATIC_WORK_ORDER_TEMPLATE = APP_TEMPLATE_DIR / "work_order_template.xlsx"
EPHEMERAL_TABLES = {"work_order_edit_sessions", "auth_sessions", "security_rate_limits", "mobile_sessions", "push_delivery_outbox"}
LEGACY_OPTIONAL_TABLES = {"asset_meter_readings", "asset_components", "asset_component_replacements", "work_order_saved_views", "work_order_archives", "work_order_archive_assets", "permissions", "user_permissions", "audit_chain_state", "employee_profiles", "leave_entitlements", "leave_requests", "work_calendar_days", "crm_opportunities", "crm_activities", "crm_contracts", "crm_contract_locations", "crm_contract_assets", "notifications", "hr_leave_import_people", "hr_leave_import_absences", "crm_contract_service_lines", "crm_contract_archives", "mobile_devices", "work_order_completion_snapshots", "work_order_signatures", "work_order_photos"}


class BackupValidationError(ValueError):
    pass


def _encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, bytes):
        return {"__type__": "bytes", "value": base64.b64encode(value).decode("ascii")}
    return {"__type__": "string", "value": str(value)}


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict) or "__type__" not in value:
        return value
    value_type = value.get("__type__")
    raw = value.get("value")
    if value_type == "datetime":
        return datetime.fromisoformat(raw)
    if value_type == "date":
        return date.fromisoformat(raw)
    if value_type == "decimal":
        return Decimal(raw)
    if value_type == "bytes":
        return base64.b64decode(raw)
    return raw


def _connection(bind: Engine | Connection):
    if isinstance(bind, Connection):
        class _NoClose:
            def __enter__(self):
                return bind

            def __exit__(self, exc_type, exc, tb):
                return False

        return _NoClose()
    return bind.connect()


def _database_payload(bind: Engine | Connection) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    with _connection(bind) as connection:
        for table in Base.metadata.sorted_tables:
            if table.name in EPHEMERAL_TABLES:
                continue
            rows = connection.execute(select(table)).mappings().all()
            encoded_rows = [
                {column.name: _encode_value(row[column.name]) for column in table.columns}
                for row in rows
            ]
            if table.name == "mobile_devices":
                # FCM registration tokens are environment/device credentials, not
                # business data. Never move them through backup/restore.
                for row in encoded_rows:
                    row["push_token"] = None
                    row["push_enabled"] = False
                    row["push_token_updated_at"] = None
            tables[table.name] = {
                "columns": [column.name for column in table.columns],
                "rows": encoded_rows,
            }
    return {"tables": tables}


def _read_runtime_or_static(settings: Settings, filename: str, static_path: Path) -> bytes:
    runtime_path = Path(settings.runtime_dir) / filename
    source = runtime_path if runtime_path.exists() else static_path
    return source.read_bytes()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_backup_archive(bind: Engine | Connection, settings: Settings) -> tuple[bytes, str, dict[str, int]]:
    database_bytes = json.dumps(
        _database_payload(bind), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    application_settings_bytes = json.dumps(
        export_application_settings(settings), ensure_ascii=False, indent=2
    ).encode("utf-8")
    company_profiles_bytes = _read_runtime_or_static(settings, "company_profiles.json", STATIC_COMPANY_PROFILES)
    template_bytes = _read_runtime_or_static(settings, "work_order_template.xlsx", STATIC_WORK_ORDER_TEMPLATE)

    files = {
        "database.json": database_bytes,
        "settings/application_settings.json": application_settings_bytes,
        "settings/company_profiles.json": company_profiles_bytes,
        "settings/work_order_template.xlsx": template_bytes,
    }
    database_payload = json.loads(database_bytes)
    for row in database_payload.get("tables", {}).get("work_order_archives", {}).get("rows", []):
        storage_key = row.get("storage_key")
        if not storage_key:
            raise BackupValidationError("Az archív munkalap tárhelyazonosítója hiányzik")
        source = archive_path(settings, storage_key)
        if not source.is_file():
            raise BackupValidationError(f"Hiányzó archív munkalapfájl: {storage_key}")
        files[f"archives/{storage_key}"] = source.read_bytes()
    for row in database_payload.get("tables", {}).get("crm_contract_archives", {}).get("rows", []):
        storage_key = row.get("storage_key")
        if not storage_key:
            raise BackupValidationError("A szerződés-archívum tárhelyazonosítója hiányzik")
        source = contract_archive_path(settings, storage_key)
        if not source.is_file():
            raise BackupValidationError(f"Hiányzó szerződés-archív PDF: {storage_key}")
        files[f"contract_archives/{storage_key}"] = source.read_bytes()
    for row in database_payload.get("tables", {}).get("work_order_signatures", {}).get("rows", []):
        for field in ("signature_storage_key", "signed_pdf_storage_key"):
            storage_key = row.get(field)
            if not storage_key:
                raise BackupValidationError("Az aláírt munkalap tárhelyazonosítója hiányzik")
            source = signature_path(settings, storage_key)
            if not source.is_file():
                raise BackupValidationError(f"Hiányzó aláírási bizonyíték: {storage_key}")
            files[f"work_order_signatures/{storage_key}"] = source.read_bytes()
    for row in database_payload.get("tables", {}).get("work_order_photos", {}).get("rows", []):
        storage_key = row.get("storage_key")
        if not storage_key:
            raise BackupValidationError("A munkalap-fénykép tárhelyazonosítója hiányzik")
        source = photo_path(settings, storage_key)
        if not source.is_file():
            raise BackupValidationError(f"Hiányzó munkalap-fénykép: {storage_key}")
        files[f"work_order_photos/{storage_key}"] = source.read_bytes()
    table_counts = {
        name: len(payload.get("rows", []))
        for name, payload in database_payload.get("tables", {}).items()
    }
    manifest = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "application": settings.app_name,
        "application_version": APP_VERSION,
        "table_counts": table_counts,
        "checksums": {name: _sha256(content) for name, content in files.items()},
        "notes": {
            "deployment_settings": "A PostgreSQL kapcsolatot és a Docker portokat a célgép .env fájlja adja; ezeket a mentés nem írja felül.",
            "restart_required": "A visszaállított token-, CORS- és egyéb alkalmazásbeállítások backend újraindítás után lépnek életbe.",
        },
    }

    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, content in files.items():
            archive.writestr(name, content)
    data = output.getvalue()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return data, f"munkalap-teljes-mentes-v{APP_VERSION}-{timestamp}.zip", table_counts


def _safe_archive_members(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > 20000:
        raise BackupValidationError("A mentés túl sok belső fájlt tartalmaz")
    total_uncompressed = 0
    for info in infos:
        path = Path(info.filename)
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        is_symlink = (unix_mode & 0o170000) == 0o120000
        if path.is_absolute() or ".." in path.parts or "\\" in info.filename or ":" in info.filename or is_symlink:
            raise BackupValidationError("A mentés veszélyes fájlútvonalat tartalmaz")
        if info.file_size > MAX_BACKUP_SIZE:
            raise BackupValidationError("A mentés egyik fájlja túl nagy")
        total_uncompressed += max(0, info.file_size)
        if total_uncompressed > MAX_BACKUP_SIZE * 2:
            raise BackupValidationError("A mentés kibontott összmérete túl nagy")
        if info.compress_size > 0 and info.file_size > 10 * 1024 * 1024 and info.file_size / info.compress_size > 200:
            raise BackupValidationError("A mentés gyanús tömörítési arányt tartalmaz")


def _load_and_validate_archive(data: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not data:
        raise BackupValidationError("A feltöltött mentés üres")
    if len(data) > MAX_BACKUP_SIZE:
        raise BackupValidationError("A feltöltött mentés túl nagy")
    try:
        with zipfile.ZipFile(BytesIO(data), "r") as archive:
            _safe_archive_members(archive)
            required = {
                "manifest.json",
                "database.json",
                "settings/application_settings.json",
                "settings/company_profiles.json",
                "settings/work_order_template.xlsx",
            }
            names = set(archive.namelist())
            missing = required - names
            if missing:
                raise BackupValidationError(f"Hiányos mentés, hiányzó fájlok: {', '.join(sorted(missing))}")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != BACKUP_FORMAT or manifest.get("version") not in SUPPORTED_BACKUP_VERSIONS:
                raise BackupValidationError("Nem támogatott mentési formátum vagy verzió")
            checksums = manifest.get("checksums") or {}
            missing_checksum_files = set(checksums) - names
            if missing_checksum_files:
                raise BackupValidationError(
                    "Hiányos mentés, hiányzó ellenőrzött fájlok: " + ", ".join(sorted(missing_checksum_files))
                )
            files = {name: archive.read(name) for name in checksums}
    except zipfile.BadZipFile as exc:
        raise BackupValidationError("A feltöltött fájl nem érvényes ZIP mentés") from exc
    except json.JSONDecodeError as exc:
        raise BackupValidationError("A mentés JSON tartalma sérült") from exc

    checksums = manifest.get("checksums") or {}
    for name, content in files.items():
        expected = checksums.get(name)
        if not expected or _sha256(content) != expected:
            raise BackupValidationError(f"Sérült vagy módosított mentési elem: {name}")
    return manifest, files


def _validate_archive_files(manifest: dict[str, Any], database_payload: dict[str, Any], files: dict[str, bytes]) -> None:
    expected = {
        f"archives/{row.get('storage_key')}"
        for row in database_payload.get("tables", {}).get("work_order_archives", {}).get("rows", [])
        if row.get("storage_key")
    }
    actual = {name for name in files if name.startswith("archives/")}
    if manifest.get("version", 0) >= 5 and expected != actual:
        missing = expected - actual
        extra = actual - expected
        details = []
        if missing:
            details.append("hiányzó archív fájlok: " + ", ".join(sorted(missing)))
        if extra:
            details.append("ismeretlen archív fájlok: " + ", ".join(sorted(extra)))
        raise BackupValidationError("Az archív munkalapfájlok nem egyeznek az adatbázissal (" + "; ".join(details) + ")")

    contract_expected = {
        f"contract_archives/{row.get('storage_key')}"
        for row in database_payload.get("tables", {}).get("crm_contract_archives", {}).get("rows", [])
        if row.get("storage_key")
    }
    contract_actual = {name for name in files if name.startswith("contract_archives/")}
    if manifest.get("version", 0) >= 12 and contract_expected != contract_actual:
        missing = contract_expected - contract_actual; extra = contract_actual - contract_expected; details = []
        if missing: details.append("hiányzó szerződés PDF-ek: " + ", ".join(sorted(missing)))
        if extra: details.append("ismeretlen szerződés PDF-ek: " + ", ".join(sorted(extra)))
        raise BackupValidationError("A szerződés-archív PDF-ek nem egyeznek az adatbázissal (" + "; ".join(details) + ")")

    signature_expected = {
        f"work_order_signatures/{row.get(field)}"
        for row in database_payload.get("tables", {}).get("work_order_signatures", {}).get("rows", [])
        for field in ("signature_storage_key", "signed_pdf_storage_key")
        if row.get(field)
    }
    signature_actual = {name for name in files if name.startswith("work_order_signatures/")}
    if manifest.get("version", 0) >= 14 and signature_expected != signature_actual:
        missing = signature_expected - signature_actual; extra = signature_actual - signature_expected; details = []
        if missing: details.append("hiányzó aláírási fájlok: " + ", ".join(sorted(missing)))
        if extra: details.append("ismeretlen aláírási fájlok: " + ", ".join(sorted(extra)))
        raise BackupValidationError("Az aláírt munkalap-fájlok nem egyeznek az adatbázissal (" + "; ".join(details) + ")")

    photo_expected = {
        f"work_order_photos/{row.get('storage_key')}"
        for row in database_payload.get("tables", {}).get("work_order_photos", {}).get("rows", [])
        if row.get("storage_key")
    }
    photo_actual = {name for name in files if name.startswith("work_order_photos/")}
    if manifest.get("version", 0) >= 15 and photo_expected != photo_actual:
        missing = photo_expected - photo_actual; extra = photo_actual - photo_expected; details = []
        if missing: details.append("hiányzó munkalap-fényképek: " + ", ".join(sorted(missing)))
        if extra: details.append("ismeretlen munkalap-fényképek: " + ", ".join(sorted(extra)))
        raise BackupValidationError("A munkalap-fényképek nem egyeznek az adatbázissal (" + "; ".join(details) + ")")


def _restore_archive_files(settings: Settings, files: dict[str, bytes]) -> None:
    root = archive_root(settings)
    parent = root.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}-restore-", dir=parent))
    try:
        for name, content in files.items():
            if not name.startswith("archives/"):
                continue
            storage_key = name.removeprefix("archives/")
            target = (staging / storage_key).resolve()
            staging_root = staging.resolve()
            if staging_root != target and staging_root not in target.parents:
                raise BackupValidationError("A mentés veszélyes archív fájlútvonalat tartalmaz")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        old = root.with_name(f".{root.name}-old")
        if old.exists():
            shutil.rmtree(old)
        if root.exists():
            os.replace(root, old)
        os.replace(staging, root)
        if old.exists():
            shutil.rmtree(old)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def _restore_contract_archive_files(settings: Settings, files: dict[str, bytes]) -> None:
    root = contract_archive_root(settings)
    parent = root.parent; parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}-restore-", dir=parent))
    try:
        for name, content in files.items():
            if not name.startswith("contract_archives/"): continue
            storage_key = name.removeprefix("contract_archives/")
            target = (staging / storage_key).resolve(); staging_root = staging.resolve()
            if staging_root != target and staging_root not in target.parents:
                raise BackupValidationError("A mentés veszélyes szerződés-archív fájlútvonalat tartalmaz")
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
        old = root.with_name(f".{root.name}-old")
        if old.exists(): shutil.rmtree(old)
        if root.exists(): os.replace(root, old)
        os.replace(staging, root)
        if old.exists(): shutil.rmtree(old)
    except Exception:
        if staging.exists(): shutil.rmtree(staging, ignore_errors=True)
        raise


def _restore_signature_files(settings: Settings, files: dict[str, bytes]) -> None:
    root = signature_root(settings)
    parent = root.parent; parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}-restore-", dir=parent))
    try:
        for name, content in files.items():
            if not name.startswith("work_order_signatures/"):
                continue
            storage_key = name.removeprefix("work_order_signatures/")
            target = (staging / storage_key).resolve(); staging_root = staging.resolve()
            if staging_root != target and staging_root not in target.parents:
                raise BackupValidationError("A mentés veszélyes aláírási fájlútvonalat tartalmaz")
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
        old = root.with_name(f".{root.name}-old")
        if old.exists(): shutil.rmtree(old)
        if root.exists(): os.replace(root, old)
        os.replace(staging, root)
        if old.exists(): shutil.rmtree(old)
    except Exception:
        if staging.exists(): shutil.rmtree(staging, ignore_errors=True)
        raise


def _restore_photo_files(settings: Settings, files: dict[str, bytes]) -> None:
    root = photo_root(settings)
    parent = root.parent; parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}-restore-", dir=parent))
    try:
        for name, content in files.items():
            if not name.startswith("work_order_photos/"):
                continue
            storage_key = name.removeprefix("work_order_photos/")
            target = (staging / storage_key).resolve(); staging_root = staging.resolve()
            if staging_root != target and staging_root not in target.parents:
                raise BackupValidationError("A mentés veszélyes munkalap-fénykép fájlútvonalat tartalmaz")
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
            try: os.chmod(target, 0o440)
            except OSError: pass
        old = root.with_name(f".{root.name}-old")
        if old.exists(): shutil.rmtree(old)
        if root.exists(): os.replace(root, old)
        os.replace(staging, root)
        if old.exists(): shutil.rmtree(old)
    except Exception:
        if staging.exists(): shutil.rmtree(staging, ignore_errors=True)
        raise


def _validate_database_payload(payload: dict[str, Any]) -> None:
    expected_tables = {table.name: table for table in Base.metadata.sorted_tables if table.name not in EPHEMERAL_TABLES}
    backup_tables = payload.get("tables")
    if not isinstance(backup_tables, dict):
        raise BackupValidationError("A mentés adatbázisrésze érvénytelen")
    missing = set(expected_tables) - set(backup_tables)
    extra = set(backup_tables) - set(expected_tables)
    required_missing = missing - LEGACY_OPTIONAL_TABLES
    if required_missing or extra:
        details = []
        if required_missing:
            details.append(f"hiányzó táblák: {', '.join(sorted(required_missing))}")
        if extra:
            details.append(f"ismeretlen táblák: {', '.join(sorted(extra))}")
        raise BackupValidationError("A mentés adatbázissémája nem kompatibilis (" + "; ".join(details) + ")")
    for name, table in expected_tables.items():
        if name not in backup_tables and name in LEGACY_OPTIONAL_TABLES:
            continue
        data = backup_tables[name]
        columns = data.get("columns")
        expected_columns = [column.name for column in table.columns]
        legacy_work_order_column_sets = {
            tuple(column for column in expected_columns if column not in omitted)
            for omitted in (
                {"version"},
                {"secondary_technician_id"},
                {"version", "secondary_technician_id"},
            )
        }
        mfa_user_columns = {
            "mfa_enabled",
            "mfa_secret_encrypted",
            "mfa_recovery_codes",
            "mfa_last_counter",
            "mfa_enrolled_at",
        }
        legacy_user_column_sets = {
            tuple(column for column in expected_columns if column not in omitted)
            for omitted in (
                mfa_user_columns,
                mfa_user_columns | {"must_change_password"},
            )
        }
        legacy_asset_columns = [
            column for column in expected_columns
            if column not in {"maintenance_cycle_months", "maintenance_cycle_note"}
        ]
        legacy_location_columns = [column for column in expected_columns if column != "is_active"]
        legacy_employee_profile_columns = [column for column in expected_columns if column != "job_title"]
        legacy_mobile_device_columns = [column for column in expected_columns if column not in {"push_enabled", "push_token_updated_at"}]
        legacy_leave_entitlement_columns = [column for column in expected_columns if column not in {"child_days", "sick_leave_days"}]
        cancellation_columns = {
            "cancellation_status",
            "cancellation_approver_user_id",
            "cancellation_comment",
            "cancellation_approver_comment",
            "cancellation_requested_at",
            "cancellation_decided_at",
        }
        legacy_leave_request_column_sets = {
            tuple(column for column in expected_columns if column not in omitted)
            for omitted in (
                cancellation_columns,
                cancellation_columns | {"leave_type", "source", "source_reference", "source_record_date"},
            )
        }
        compatible = columns == expected_columns
        if name == "work_orders" and tuple(columns) in legacy_work_order_column_sets:
            compatible = True
        if name == "assets" and columns == legacy_asset_columns:
            compatible = True
        if name == "locations" and columns == legacy_location_columns:
            compatible = True
        if name == "users" and tuple(columns) in legacy_user_column_sets:
            compatible = True
        if name == "employee_profiles" and columns == legacy_employee_profile_columns:
            compatible = True
        if name == "mobile_devices" and columns == legacy_mobile_device_columns:
            compatible = True
        if name == "leave_entitlements" and columns == legacy_leave_entitlement_columns:
            compatible = True
        if name == "leave_requests" and tuple(columns) in legacy_leave_request_column_sets:
            compatible = True
        if name == "audit_logs":
            legacy_audit_columns = [
                column for column in expected_columns
                if column in {"id", "user_id", "action", "entity_type", "entity_id", "description", "created_at"}
            ]
            if columns == legacy_audit_columns:
                compatible = True
        if not compatible:
            raise BackupValidationError(f"A(z) {name} tábla oszlopai nem kompatibilisek")
        if not isinstance(data.get("rows"), list):
            raise BackupValidationError(f"A(z) {name} tábla sorai érvénytelenek")


def _reset_postgresql_sequences(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    for table in Base.metadata.sorted_tables:
        primary_keys = list(table.primary_key.columns)
        if len(primary_keys) != 1:
            continue
        pk = primary_keys[0]
        if not pk.autoincrement:
            continue
        quoted_table = connection.dialect.identifier_preparer.quote(table.name)
        quoted_column = connection.dialect.identifier_preparer.quote(pk.name)
        connection.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk.name}'), "
                f"COALESCE((SELECT MAX({quoted_column}) FROM {quoted_table}), 1), "
                f"(SELECT COUNT(*) > 0 FROM {quoted_table}))"
            )
        )


def _reset_work_order_number_sequence(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text(
            """
            SELECT setval(
                'work_order_number_seq',
                GREATEST(
                    COALESCE(
                        (
                            SELECT MAX((substring(number from '([0-9]+)$'))::bigint)
                            FROM work_orders
                            WHERE number ~ '[0-9]+$'
                        ),
                        0
                    ) + 1,
                    1
                ),
                false
            )
            """
        )
    )


def _reset_work_order_archive_number_sequence(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text(
            """
            SELECT setval(
                'work_order_archive_number_seq',
                GREATEST(
                    COALESCE(
                        (
                            SELECT MAX((substring(archive_number from '([0-9]+)$'))::bigint)
                            FROM work_order_archives
                            WHERE archive_number ~ '[0-9]+$'
                        ),
                        0
                    ) + 1,
                    1
                ),
                false
            )
            """
        )
    )


def _reset_contract_archive_number_sequence(connection: Connection) -> None:
    if connection.dialect.name != "postgresql": return
    connection.execute(text("""
        SELECT setval('crm_contract_archive_number_seq', GREATEST(
            COALESCE((SELECT MAX((substring(archive_number from '([0-9]+)$'))::bigint) FROM crm_contract_archives WHERE archive_number ~ '[0-9]+$'), 0) + 1, 1), false)
    """))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _prepare_legacy_audit_rows(connection: Connection, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows or "entry_hash" in rows[0]:
        return rows

    # Régi (<= v0.10.x) mentésből strukturált audit snapshot és hash-lánc
    # készül. A jelszó/hash/token mezők eleve nem voltak az audit_logs táblában.
    from .audit import calculate_audit_hash

    actor_rows = connection.execute(
        text(
            """
            SELECT u.id, u.full_name, u.email, r.name AS role_name
            FROM users u
            LEFT JOIN roles r ON r.id = u.role_id
            """
        )
    ).mappings().all()
    actors = {row["id"]: row for row in actor_rows}
    prepared: list[dict[str, Any]] = []
    previous_hash = None
    for row in sorted(rows, key=lambda item: item.get("id") or 0):
        actor = actors.get(row.get("user_id"))
        enriched = dict(row)
        enriched.update(
            actor_user_id=row.get("user_id"),
            actor_name=actor.get("full_name") if actor else None,
            actor_email=actor.get("email") if actor else None,
            actor_role=actor.get("role_name") if actor else None,
            entity_display_id=None,
            before_data=None,
            after_data=None,
            changes=None,
            request_id=None,
            correlation_id=None,
            session_id=None,
            ip_address=None,
            user_agent=None,
            result="success",
            severity="info",
            previous_hash=previous_hash,
        )
        enriched["entry_hash"] = calculate_audit_hash(enriched)
        previous_hash = enriched["entry_hash"]
        prepared.append(enriched)
    return prepared


def _set_audit_append_only_trigger(connection: Connection, *, enabled: bool) -> None:
    if connection.dialect.name != "postgresql":
        return
    state = "ENABLE" if enabled else "DISABLE"
    connection.execute(text(f"ALTER TABLE audit_logs {state} TRIGGER trg_audit_logs_append_only"))


def restore_backup_archive(bind: Engine | Connection, settings: Settings, data: bytes) -> dict[str, Any]:
    manifest, files = _load_and_validate_archive(data)
    database_payload = json.loads(files["database.json"])
    _validate_database_payload(database_payload)
    _validate_archive_files(manifest, database_payload, files)
    try:
        application_settings = json.loads(files["settings/application_settings.json"])
    except json.JSONDecodeError as exc:
        raise BackupValidationError("Az alkalmazásbeállítások sérültek") from exc
    if not isinstance(application_settings, dict):
        raise BackupValidationError("Az alkalmazásbeállítások formátuma érvénytelen")

    tables_by_name = {table.name: table for table in Base.metadata.sorted_tables}
    table_counts: dict[str, int] = {}

    def restore_on_connection(connection: Connection) -> None:
        _set_audit_append_only_trigger(connection, enabled=False)
        try:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(delete(table))
            for table in Base.metadata.sorted_tables:
                if table.name in EPHEMERAL_TABLES:
                    table_counts[table.name] = 0
                    continue
                table_data = database_payload["tables"].get(table.name)
                if table_data is None and table.name in LEGACY_OPTIONAL_TABLES:
                    table_counts[table.name] = 0
                    continue
                decoded_rows = [
                    {key: _decode_value(value) for key, value in row.items()}
                    for row in table_data["rows"]
                ]
                if table.name == "work_orders":
                    for row in decoded_rows:
                        row.setdefault("version", 1)
                        row.setdefault("secondary_technician_id", None)
                if table.name == "users":
                    for row in decoded_rows:
                        row.setdefault("must_change_password", False)
                        row.setdefault("mfa_enabled", False)
                        row.setdefault("mfa_secret_encrypted", None)
                        row.setdefault("mfa_recovery_codes", None)
                        row.setdefault("mfa_last_counter", None)
                        row.setdefault("mfa_enrolled_at", None)
                if table.name == "assets":
                    for row in decoded_rows:
                        row.setdefault("maintenance_cycle_months", None)
                        row.setdefault("maintenance_cycle_note", None)
                if table.name == "locations":
                    for row in decoded_rows:
                        row.setdefault("is_active", True)
                if table.name == "employee_profiles":
                    for row in decoded_rows:
                        row.setdefault("job_title", None)
                if table.name == "mobile_devices":
                    for row in decoded_rows:
                        row["push_token"] = None
                        row["push_enabled"] = False
                        row["push_token_updated_at"] = None
                if table.name == "leave_entitlements":
                    for row in decoded_rows:
                        row.setdefault("child_days", Decimal("0"))
                        row.setdefault("sick_leave_days", Decimal("0"))
                if table.name == "crm_contracts":
                    for row in decoded_rows:
                        row.setdefault("company_code", "DRH")
                        for key in ("contracting_party_name","contracting_party_address","subject","term_text","billing_frequency","payment_terms","billing_name","service_confirmation","e_invoice_email","price_adjustment_terms"):
                            row.setdefault(key, None)
                if table.name == "leave_requests":
                    for row in decoded_rows:
                        row.setdefault("leave_type", "annual_leave")
                        row.setdefault("source", "workflow")
                        row.setdefault("source_reference", None)
                        row.setdefault("source_record_date", None)
                        row.setdefault("cancellation_status", None)
                        row.setdefault("cancellation_approver_user_id", None)
                        row.setdefault("cancellation_comment", None)
                        row.setdefault("cancellation_approver_comment", None)
                        row.setdefault("cancellation_requested_at", None)
                        row.setdefault("cancellation_decided_at", None)
                if table.name == "audit_logs":
                    decoded_rows = _prepare_legacy_audit_rows(connection, decoded_rows)
                if decoded_rows:
                    connection.execute(insert(tables_by_name[table.name]), decoded_rows)
                table_counts[table.name] = len(decoded_rows)

            if table_counts.get("audit_chain_state", 0) == 0:
                last_audit = connection.execute(
                    text("SELECT id, entry_hash FROM audit_logs ORDER BY id DESC LIMIT 1")
                ).mappings().first()
                connection.execute(
                    insert(tables_by_name["audit_chain_state"]),
                    [{
                        "id": 1,
                        "last_hash": last_audit["entry_hash"] if last_audit else None,
                        "updated_at": datetime.utcnow(),
                    }],
                )
                table_counts["audit_chain_state"] = 1

            _reset_postgresql_sequences(connection)
            _reset_work_order_number_sequence(connection)
            _reset_work_order_archive_number_sequence(connection)
            _reset_contract_archive_number_sequence(connection)
        finally:
            _set_audit_append_only_trigger(connection, enabled=True)

    if isinstance(bind, Engine):
        with bind.begin() as connection:
            restore_on_connection(connection)
    else:
        with bind.begin():
            restore_on_connection(bind)

    _restore_archive_files(settings, files)
    _restore_signature_files(settings, files)
    _restore_photo_files(settings, files)
    _restore_contract_archive_files(settings, files)

    runtime_dir = Path(settings.runtime_dir)
    _atomic_write(runtime_settings_path(settings), json.dumps(application_settings, ensure_ascii=False, indent=2).encode("utf-8"))
    _atomic_write(runtime_dir / "company_profiles.json", files["settings/company_profiles.json"])
    _atomic_write(runtime_dir / "work_order_template.xlsx", files["settings/work_order_template.xlsx"])

    # A cégprofil-cache azonnal üríthető. A többi beállítás biztonságosan a backend
    # újraindítása után lép életbe.
    from .company_profiles import load_company_profiles

    load_company_profiles.cache_clear()
    return {
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "backup_created_at": manifest.get("created_at"),
        "backup_application_version": manifest.get("application_version"),
        "table_counts": table_counts,
        "restart_required": True,
        "message": "A teljes adatbázis és az alkalmazásbeállítások visszaálltak. Indítsd újra a backend konténert, majd jelentkezz be a mentésben szereplő felhasználóval.",
    }
