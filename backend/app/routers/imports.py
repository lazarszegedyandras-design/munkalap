from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from datetime import datetime
from io import BytesIO
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import RequireAdmin
from ..importers.customer_assets import IMPORT_BATCH, IMPORT_SOURCE, import_builtin_customer_assets, load_builtin_rows, source_available
from ..importers.meter_readings import import_meter_workbook
from ..importers.maintenance_dates import import_maintenance_workbook
from ..importers.maintenance_cycles import import_maintenance_cycle_workbook
from ..importers.global_workbook import import_global_workbook
from ..importers.global_template import TEMPLATE_FILENAME, build_global_import_template
from ..exporters.global_workbook import EXPORT_FILENAME_PREFIX, build_global_database_export
from ..models import Asset, Customer, User
from ..services.asset_display import asset_display_name, visible_internal_id
from ..services.audit import add_audit_log
from ..services.upload_validation import read_excel_upload

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("/global/template")
def download_global_import_template(_: User = Depends(RequireAdmin)):
    content = build_global_import_template()
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{TEMPLATE_FILENAME}"'},
    )


@router.get("/global/export")
def download_global_database_export(db: Session = Depends(get_db), _: User = Depends(RequireAdmin)):
    content = build_global_database_export(db)
    filename = f"{EXPORT_FILENAME_PREFIX}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/global/preview")
async def preview_global_import(
    import_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    content = await read_excel_upload(import_file, get_settings())
    result = import_global_workbook(
        db, current_user, content, import_file.filename or TEMPLATE_FILENAME, dry_run=True
    )
    return result.as_dict()


@router.post("/global/run")
async def run_global_import(
    import_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    content = await read_excel_upload(import_file, get_settings())
    result = import_global_workbook(
        db, current_user, content, import_file.filename or TEMPLATE_FILENAME, dry_run=False
    )
    add_audit_log(
        db,
        current_user,
        "globális Excel-import",
        "global_import",
        None,
        (
            f"Fájl={result.filename}; ügyfél létrehozva={result.customers_created}; "
            f"eszköz létrehozva={result.assets_created}; eszköz frissítve={result.assets_updated}; "
            f"kapcsolattartó létrehozva={result.contacts_created}; "
            f"számláló importálva={result.meter_readings_imported}; "
            f"karbantartási dátum frissítve={result.maintenance_dates_updated}; "
            f"ciklus frissítve={result.maintenance_cycles_updated}; kihagyva={result.skipped_count}"
        ),
    )
    db.commit()
    return result.as_dict()


def _customer_asset_import_status(db: Session) -> dict:
    source_rows = load_builtin_rows()
    imported_assets_count = db.query(Asset).filter(Asset.import_batch == IMPORT_BATCH).count()
    imported_customer_ids = {
        row[0]
        for row in db.query(Asset.customer_id)
        .filter(Asset.import_batch == IMPORT_BATCH, Asset.customer_id.isnot(None))
        .distinct()
        .all()
    }
    company_counts = [
        {"company_code": code or "-", "asset_count": count}
        for code, count in db.query(Asset.company_code, func.count(Asset.id))
        .filter(Asset.import_batch == IMPORT_BATCH)
        .group_by(Asset.company_code)
        .order_by(Asset.company_code)
        .all()
    ]
    samples = [
        {
            "id": asset.id,
            "internal_id": visible_internal_id(asset.internal_id),
            "display_name": asset_display_name(asset),
            "serial_number": asset.serial_number,
            "type": asset.type,
            "company_code": asset.company_code,
            "customer_name": asset.customer.name if asset.customer else None,
        }
        for asset in db.query(Asset)
        .filter(Asset.import_batch == IMPORT_BATCH)
        .order_by(Asset.import_row.asc().nullslast(), Asset.internal_id.asc())
        .limit(10)
        .all()
    ]
    return {
        "import_batch": IMPORT_BATCH,
        "import_source": IMPORT_SOURCE,
        "source_rows": len(source_rows),
        "imported_assets_count": imported_assets_count,
        "imported_customers_count": len(imported_customer_ids),
        "company_counts": company_counts,
        "samples": samples,
        "is_imported": imported_assets_count > 0,
    }


@router.get("/customer-assets/status")
def customer_assets_import_status(db: Session = Depends(get_db), _: User = Depends(RequireAdmin)):
    return _customer_asset_import_status(db)


@router.post("/customer-assets/run")
def run_customer_assets_import(db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    if not source_available():
        raise HTTPException(status_code=409, detail="Az ügyfél/eszköz import forrásfájl nincs telepítve.")
    result = import_builtin_customer_assets(db, current_user)
    add_audit_log(
        db,
        current_user,
        "excel import",
        "customer_assets",
        None,
        (
            f"Ügyfél/eszköz Excel import lefutott: sorok={result.rows}, "
            f"ügyfelek létrehozva={result.customers_created}, ügyfelek frissítve={result.customers_updated}, "
            f"helyszínek létrehozva={result.locations_created}, kapcsolattartók létrehozva={result.contacts_created}, eszközök létrehozva={result.assets_created}, "
            f"eszközök frissítve={result.assets_updated}, import megjegyzések törölve={result.asset_notes_cleared}, "
            f"kihagyva={result.skipped}"
        ),
    )
    db.commit()
    return {
        "result": {
            "rows": result.rows,
            "customers_created": result.customers_created,
            "customers_updated": result.customers_updated,
            "locations_created": result.locations_created,
            "contacts_created": result.contacts_created,
            "assets_created": result.assets_created,
            "assets_updated": result.assets_updated,
            "asset_notes_cleared": result.asset_notes_cleared,
            "skipped": result.skipped,
        },
        "status": _customer_asset_import_status(db),
    }


@router.post("/maintenance-dates/preview")
async def preview_maintenance_dates_import(
    import_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    content = await read_excel_upload(import_file, get_settings())
    result = import_maintenance_workbook(
        db,
        current_user,
        content,
        import_file.filename or "utolso_karbantartas_import.xlsx",
        dry_run=True,
    )
    return result.as_dict()


@router.post("/maintenance-dates/run")
async def run_maintenance_dates_import(
    import_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    content = await read_excel_upload(import_file, get_settings())
    result = import_maintenance_workbook(
        db,
        current_user,
        content,
        import_file.filename or "utolso_karbantartas_import.xlsx",
        dry_run=False,
    )
    add_audit_log(
        db,
        current_user,
        "excel import",
        "asset_last_maintenance_dates",
        None,
        (
            f"Utolsó karbantartási dátum Excel-import: fájl={result.filename}, "
            f"frissítve={result.updated_count}, változatlan={result.unchanged_count}, "
            f"ütközés={result.conflict_count}, hiányzó eszköz={result.missing_asset_count}, "
            f"hibás={result.invalid_count}"
        ),
    )
    db.commit()
    return result.as_dict()


@router.post("/maintenance-cycles/preview")
async def preview_maintenance_cycles_import(
    import_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    content = await read_excel_upload(import_file, get_settings())
    result = import_maintenance_cycle_workbook(
        db,
        current_user,
        content,
        import_file.filename or "karbantartasi_ciklus_import.xlsx",
        dry_run=True,
    )
    return result.as_dict()


@router.post("/maintenance-cycles/run")
async def run_maintenance_cycles_import(
    import_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    content = await read_excel_upload(import_file, get_settings())
    result = import_maintenance_cycle_workbook(
        db,
        current_user,
        content,
        import_file.filename or "karbantartasi_ciklus_import.xlsx",
        dry_run=False,
    )
    add_audit_log(
        db,
        current_user,
        "excel import",
        "asset_maintenance_cycles",
        None,
        (
            f"Karbantartási ciklus Excel-import: fájl={result.filename}, "
            f"frissítve={result.updated_count}, változatlan={result.unchanged_count}, "
            f"nem periodikus={result.non_periodic_count}, hiányzó eszköz={result.missing_asset_count}, "
            f"nem egyértelmű={result.ambiguous_asset_count}, hibás={result.invalid_count}"
        ),
    )
    db.commit()
    return result.as_dict()


@router.post("/meter-readings/preview")
async def preview_meter_readings_import(
    import_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    content = await read_excel_upload(import_file, get_settings())
    result = import_meter_workbook(
        db,
        current_user,
        content,
        import_file.filename or "szamlalo_import.xlsx",
        dry_run=True,
    )
    return result.as_dict()


@router.post("/meter-readings/run")
async def run_meter_readings_import(
    import_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    content = await read_excel_upload(import_file, get_settings())
    result = import_meter_workbook(
        db,
        current_user,
        content,
        import_file.filename or "szamlalo_import.xlsx",
        dry_run=False,
    )
    add_audit_log(
        db,
        current_user,
        "excel import",
        "asset_meter_readings",
        None,
        (
            f"Számláló Excel-import: fájl={result.filename}, importálva={result.imported_count}, "
            f"változatlan={result.unchanged_count}, ütközés={result.conflict_count}, "
            f"hiányzó eszköz={result.missing_asset_count}, hibás={result.invalid_count}"
        ),
    )
    db.commit()
    return result.as_dict()
