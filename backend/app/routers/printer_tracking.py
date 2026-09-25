from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import RequireOfficeOrAdmin, get_current_user
from ..models import (
    Asset,
    AssetComponent,
    AssetComponentReplacement,
    AssetMeterReading,
    Material,
    User,
    WorkOrder,
    WorkOrderAsset,
)
from ..schemas import (
    AssetComponentCreate,
    AssetComponentReplacementCreate,
    AssetComponentUpdate,
    AssetMeterReadingCreate,
)
from ..services.asset_display import asset_display_name
from ..services.audit import add_asset_history, add_audit_log
from ..services.printer_tracking import asset_printer_overview, latest_meter_reading

router = APIRouter(prefix="/assets", tags=["printer_tracking"])


def _asset_or_404(db: Session, asset_id: int) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Eszköz nem található")
    return asset


def _validate_work_order_asset(db: Session, asset_id: int, work_order_id: int | None) -> WorkOrder | None:
    if work_order_id is None:
        return None
    order = db.get(WorkOrder, work_order_id)
    if not order:
        raise HTTPException(status_code=400, detail="A megadott munkalap nem található")
    linked = db.query(WorkOrderAsset).filter(
        WorkOrderAsset.work_order_id == work_order_id,
        WorkOrderAsset.asset_id == asset_id,
    ).first()
    if not linked:
        raise HTTPException(status_code=400, detail="A munkalap nincs összekapcsolva ezzel az eszközzel")
    return order


METER_FIELDS = {
    "value": "összes számláló",
    "black_white_value": "FF számláló",
    "color_value": "színes számláló",
    "scan_value": "scan számláló",
}


def _validate_meter_sequence(db: Session, asset_id: int, values: dict[str, int | None], recorded_at: datetime) -> None:
    # Az összes számláló az eszköz életciklusának elsődleges, monoton mérőszáma.
    # A részletes csatornák eszköz- vagy vezérlőcsere miatt újraindulhatnak, ezért
    # azokat csak ugyanazon időpont eltérő értéke ellen védjük.
    value = values.get("value")
    if value is None:
        return
    previous = (
        db.query(AssetMeterReading)
        .filter(AssetMeterReading.asset_id == asset_id, AssetMeterReading.recorded_at < recorded_at)
        .order_by(AssetMeterReading.recorded_at.desc(), AssetMeterReading.id.desc())
        .first()
    )
    following = (
        db.query(AssetMeterReading)
        .filter(AssetMeterReading.asset_id == asset_id, AssetMeterReading.recorded_at > recorded_at)
        .order_by(AssetMeterReading.recorded_at.asc(), AssetMeterReading.id.asc())
        .first()
    )
    if previous and value < previous.value:
        raise HTTPException(status_code=400, detail=f"Az összes számláló nem lehet kisebb a korábbi {previous.value:,} értéknél")
    if following and value > following.value:
        raise HTTPException(status_code=400, detail=f"Az összes számláló nem lehet nagyobb a későbbi {following.value:,} értéknél")


def _create_meter_reading(
    db: Session,
    asset: Asset,
    current_user: User,
    value: int,
    recorded_at: datetime,
    work_order_id: int | None,
    black_white_value: int | None = None,
    color_value: int | None = None,
    scan_value: int | None = None,
    note: str | None = None,
) -> AssetMeterReading:
    _validate_work_order_asset(db, asset.id, work_order_id)
    existing = db.query(AssetMeterReading).filter(
        AssetMeterReading.asset_id == asset.id,
        AssetMeterReading.recorded_at == recorded_at,
    ).first()
    incoming = {
        "value": value,
        "black_white_value": black_white_value,
        "color_value": color_value,
        "scan_value": scan_value,
    }
    if black_white_value is not None and color_value is not None and black_white_value + color_value != value:
        raise HTTPException(status_code=400, detail="Az összes számláló nem egyezik az FF + színes számlálók összegével")
    if existing:
        if existing.value != value:
            raise HTTPException(status_code=400, detail="Erre az időpontra már van eltérő összes számlálóállás")
        changed = False
        for field in ("black_white_value", "color_value", "scan_value"):
            incoming_value = incoming[field]
            current_value = getattr(existing, field)
            if incoming_value is None:
                continue
            if current_value is not None and current_value != incoming_value:
                raise HTTPException(status_code=400, detail=f"Erre az időpontra már van eltérő {METER_FIELDS[field]}")
            if current_value is None:
                setattr(existing, field, incoming_value)
                changed = True
        if changed:
            _validate_meter_sequence(db, asset.id, incoming, recorded_at)
        return existing
    _validate_meter_sequence(db, asset.id, incoming, recorded_at)
    row = AssetMeterReading(
        asset_id=asset.id,
        value=value,
        black_white_value=black_white_value,
        color_value=color_value,
        scan_value=scan_value,
        recorded_at=recorded_at,
        work_order_id=work_order_id,
        recorded_by_user_id=current_user.id,
        note=note,
    )
    db.add(row)
    db.flush()
    add_asset_history(
        db,
        asset.id,
        current_user,
        "számlálóállás",
        f"Számlálóállás rögzítve: {value:,} oldal".replace(",", " "),
        work_order_id,
    )
    return row


@router.get("/{asset_id}/printer-tracking")
def get_printer_tracking(asset_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    asset = _asset_or_404(db, asset_id)
    return asset_printer_overview(db, asset)


@router.post("/{asset_id}/meter-readings", status_code=status.HTTP_201_CREATED)
def create_meter_reading(
    asset_id: int,
    payload: AssetMeterReadingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = _asset_or_404(db, asset_id)
    recorded_at = payload.recorded_at or datetime.utcnow()
    try:
        row = _create_meter_reading(
            db,
            asset,
            current_user,
            payload.value,
            recorded_at,
            payload.work_order_id,
            payload.black_white_value,
            payload.color_value,
            payload.scan_value,
            payload.note,
        )
        add_audit_log(db, current_user, "létrehozás", "asset_meter_reading", row.id, f"Számláló rögzítve: {asset_display_name(asset)}")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Erre az időpontra már van számlálóállás") from exc
    return asset_printer_overview(db, asset)


@router.delete("/{asset_id}/meter-readings/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meter_reading(
    asset_id: int,
    reading_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    asset = _asset_or_404(db, asset_id)
    row = db.get(AssetMeterReading, reading_id)
    if not row or row.asset_id != asset.id:
        raise HTTPException(status_code=404, detail="Számlálóállás nem található")
    add_audit_log(db, current_user, "törlés", "asset_meter_reading", row.id, f"Számlálóállás törölve: {row.value}")
    db.delete(row)
    db.commit()
    return None


@router.post("/{asset_id}/components", status_code=status.HTTP_201_CREATED)
def create_component(
    asset_id: int,
    payload: AssetComponentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    asset = _asset_or_404(db, asset_id)
    row = AssetComponent(asset_id=asset.id, **payload.model_dump())
    db.add(row)
    db.flush()
    add_asset_history(db, asset.id, current_user, "alkatrész hozzáadása", f"Követett alkatrész: {row.name}")
    add_audit_log(db, current_user, "létrehozás", "asset_component", row.id, f"Alkatrész hozzáadva: {row.name}")
    db.commit()
    return asset_printer_overview(db, asset)


@router.put("/{asset_id}/components/{component_id}")
def update_component(
    asset_id: int,
    component_id: int,
    payload: AssetComponentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    asset = _asset_or_404(db, asset_id)
    row = db.get(AssetComponent, component_id)
    if not row or row.asset_id != asset.id:
        raise HTTPException(status_code=404, detail="Alkatrész nem található")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    add_audit_log(db, current_user, "módosítás", "asset_component", row.id, f"Alkatrész módosítva: {row.name}")
    db.commit()
    return asset_printer_overview(db, asset)


@router.delete("/{asset_id}/components/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_component(
    asset_id: int,
    component_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    asset = _asset_or_404(db, asset_id)
    row = db.get(AssetComponent, component_id)
    if not row or row.asset_id != asset.id:
        raise HTTPException(status_code=404, detail="Alkatrész nem található")
    if row.replacements:
        row.is_active = False
        add_audit_log(db, current_user, "inaktiválás", "asset_component", row.id, f"Alkatrész inaktiválva: {row.name}")
    else:
        add_audit_log(db, current_user, "törlés", "asset_component", row.id, f"Alkatrész törölve: {row.name}")
        db.delete(row)
    db.commit()
    return None


@router.post("/{asset_id}/component-replacements", status_code=status.HTTP_201_CREATED)
def create_component_replacement(
    asset_id: int,
    payload: AssetComponentReplacementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = _asset_or_404(db, asset_id)
    component = db.get(AssetComponent, payload.asset_component_id)
    if not component or component.asset_id != asset.id:
        raise HTTPException(status_code=400, detail="A kiválasztott alkatrész nem ehhez az eszközhöz tartozik")
    _validate_work_order_asset(db, asset.id, payload.work_order_id)
    if payload.material_id is not None and not db.get(Material, payload.material_id):
        raise HTTPException(status_code=400, detail="A kiválasztott anyag nem található")
    replaced_at = payload.replaced_at or datetime.utcnow()
    latest = latest_meter_reading(db, asset.id)
    if latest and payload.meter_value < latest.value and replaced_at >= latest.recorded_at:
        raise HTTPException(status_code=400, detail=f"A cserekori számláló nem lehet kisebb a jelenlegi {latest.value} értéknél")

    _create_meter_reading(
        db,
        asset,
        current_user,
        payload.meter_value,
        replaced_at,
        payload.work_order_id,
        note="Alkatrészcsere során rögzített számlálóállás",
    )
    replacement = AssetComponentReplacement(
        asset_id=asset.id,
        asset_component_id=component.id,
        material_id=payload.material_id,
        work_order_id=payload.work_order_id,
        technician_id=current_user.id,
        replaced_at=replaced_at,
        meter_value=payload.meter_value,
        note=payload.note,
    )
    db.add(replacement)
    component.last_replacement_at = replaced_at
    component.last_replacement_meter = payload.meter_value
    db.flush()
    work_order_number = db.get(WorkOrder, payload.work_order_id).number if payload.work_order_id else None
    description = f"{component.name} cserélve {payload.meter_value:,} oldalas számlálónál".replace(",", " ")
    if work_order_number:
        description += f" ({work_order_number})"
    add_asset_history(db, asset.id, current_user, "alkatrészcsere", description, payload.work_order_id)
    add_audit_log(db, current_user, "csere", "asset_component", component.id, description)
    db.commit()
    return asset_printer_overview(db, asset)
