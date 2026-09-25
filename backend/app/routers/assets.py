from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Query as SqlAlchemyQuery, Session, joinedload
from ..database import get_db
from ..deps import RequireOfficeOrAdmin, get_current_user
from ..models import Asset, AssetHistory, CrmContractAsset, Customer, Location, User, WorkOrder, WorkOrderArchiveAsset, WorkOrderAsset
from ..schemas import AssetCreate, AssetPage, AssetRead, AssetUpdate
from ..services.asset_display import asset_display_name, is_hidden_internal_id, visible_internal_id
from ..services.asset_list import (
    asset_list_summary,
    build_asset_list_summaries,
    filter_asset_list_rows,
    paginate_asset_list_rows,
    sort_asset_list_rows,
)
from ..services.audit import add_asset_history, add_audit_log
from ..services.maintenance_schedule import maintenance_snapshot
from .work_orders import base_query as work_order_base_query, work_order_to_dict

router = APIRouter(prefix="/assets", tags=["assets"])


def validate_asset_customer_location(
    db: Session,
    customer_id: int | None,
    location_id: int | None,
    *,
    existing_location_id: int | None = None,
):
    if customer_id and not db.get(Customer, customer_id):
        raise HTTPException(status_code=400, detail="Érvénytelen ügyfél")
    if location_id:
        location = db.get(Location, location_id)
        if not location:
            raise HTTPException(status_code=400, detail="Érvénytelen helyszín")
        if customer_id and location.customer_id != customer_id:
            raise HTTPException(status_code=400, detail="A helyszín nem a megadott ügyfélhez tartozik")
        if not location.is_active and location.id != existing_location_id:
            raise HTTPException(status_code=400, detail="Inaktív helyszín nem választható új eszközkapcsolathoz")


def asset_to_dict(asset: Asset) -> dict:
    maintenance = maintenance_snapshot(asset)
    return {
        "id": asset.id,
        "internal_id": asset.internal_id,
        "display_internal_id": visible_internal_id(asset.internal_id),
        "internal_id_hidden": is_hidden_internal_id(asset.internal_id),
        "display_name": asset_display_name(asset),
        "serial_number": asset.serial_number,
        "type": asset.type,
        "manufacturer": asset.manufacturer,
        "model": asset.model,
        "category": asset.category,
        "status": asset.status,
        "current_location_id": asset.current_location_id,
        "customer_id": asset.customer_id,
        "internal_use": asset.internal_use,
        "purchase_date": asset.purchase_date,
        "warranty_expiry": asset.warranty_expiry,
        "last_maintenance_date": asset.last_maintenance_date,
        "maintenance_cycle_months": asset.maintenance_cycle_months,
        "maintenance_cycle_note": asset.maintenance_cycle_note,
        "next_maintenance_date": asset.next_maintenance_date,
        **maintenance,
        "note": asset.note,
        "company_code": asset.company_code,
        "import_source": asset.import_source,
        "import_batch": asset.import_batch,
        "import_row": asset.import_row,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
        "customer_name": asset.customer.name if asset.customer else None,
        "location_name": asset.current_location.name if asset.current_location else None,
    }


def _asset_query(
    db: Session,
    *,
    q: str | None = None,
    internal_id: str | None = None,
    serial_number: str | None = None,
    type: str | None = None,
    manufacturer: str | None = None,
    category: str | None = None,
    company_code: str | None = None,
    customer_id: int | None = None,
    location_id: int | None = None,
    status_filter: str | None = None,
    status_group: str | None = None,
) -> SqlAlchemyQuery:
    query = (
        db.query(Asset)
        .outerjoin(Customer, Asset.customer_id == Customer.id)
        .outerjoin(Location, Asset.current_location_id == Location.id)
        .options(joinedload(Asset.customer), joinedload(Asset.current_location))
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Asset.internal_id.ilike(like),
                Asset.serial_number.ilike(like),
                Asset.type.ilike(like),
                Asset.model.ilike(like),
                Asset.manufacturer.ilike(like),
                Asset.category.ilike(like),
                Asset.company_code.ilike(like),
                Customer.name.ilike(like),
                Location.name.ilike(like),
            )
        )
    if internal_id:
        query = query.filter(Asset.internal_id.ilike(f"%{internal_id}%"))
    if serial_number:
        query = query.filter(Asset.serial_number.ilike(f"%{serial_number}%"))
    if type:
        query = query.filter(Asset.type == type)
    if manufacturer:
        query = query.filter(Asset.manufacturer == manufacturer)
    if category:
        query = query.filter(Asset.category == category)
    if company_code:
        query = query.filter(Asset.company_code == company_code)
    if customer_id:
        query = query.filter(Asset.customer_id == customer_id)
    if location_id:
        query = query.filter(Asset.current_location_id == location_id)
    if status_filter:
        query = query.filter(Asset.status == status_filter)
    if status_group == "problem":
        query = query.filter(Asset.status.in_(["hibás", "javítás alatt"]))
    return query


def _asset_rows(
    db: Session,
    *,
    q: str | None = None,
    internal_id: str | None = None,
    serial_number: str | None = None,
    type: str | None = None,
    manufacturer: str | None = None,
    category: str | None = None,
    company_code: str | None = None,
    customer_id: int | None = None,
    location_id: int | None = None,
    status_filter: str | None = None,
    status_group: str | None = None,
    maintenance_state: str | None = None,
    meter_state: str | None = None,
    forecast_state: str | None = None,
) -> list[dict]:
    assets = _asset_query(
        db,
        q=q,
        internal_id=internal_id,
        serial_number=serial_number,
        type=type,
        manufacturer=manufacturer,
        category=category,
        company_code=company_code,
        customer_id=customer_id,
        location_id=location_id,
        status_filter=status_filter,
        status_group=status_group,
    ).all()
    summaries = build_asset_list_summaries(db, assets)
    rows = [{**asset_to_dict(asset), **summaries.get(asset.id, {})} for asset in assets]
    return filter_asset_list_rows(
        rows,
        maintenance_state=maintenance_state,
        meter_state=meter_state,
        forecast_state=forecast_state,
    )


@router.get("", response_model=list[AssetRead])
def list_assets(
    q: str | None = None,
    internal_id: str | None = None,
    serial_number: str | None = None,
    type: str | None = None,
    manufacturer: str | None = None,
    category: str | None = None,
    company_code: str | None = None,
    customer_id: int | None = None,
    location_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    status_group: str | None = None,
    maintenance_state: str | None = None,
    meter_state: str | None = None,
    forecast_state: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = _asset_rows(
        db,
        q=q,
        internal_id=internal_id,
        serial_number=serial_number,
        type=type,
        manufacturer=manufacturer,
        category=category,
        company_code=company_code,
        customer_id=customer_id,
        location_id=location_id,
        status_filter=status_filter,
        status_group=status_group,
        maintenance_state=maintenance_state,
        meter_state=meter_state,
        forecast_state=forecast_state,
    )
    return sort_asset_list_rows(rows, "company_code", "asc")


@router.get("/paged", response_model=AssetPage)
def list_assets_paged(
    q: str | None = None,
    internal_id: str | None = None,
    serial_number: str | None = None,
    type: str | None = None,
    manufacturer: str | None = None,
    category: str | None = None,
    company_code: str | None = None,
    customer_id: int | None = None,
    location_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    status_group: str | None = None,
    maintenance_state: str | None = None,
    meter_state: str | None = None,
    forecast_state: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
    sort: str = Query(default="company_code"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = _asset_rows(
        db,
        q=q,
        internal_id=internal_id,
        serial_number=serial_number,
        type=type,
        manufacturer=manufacturer,
        category=category,
        company_code=company_code,
        customer_id=customer_id,
        location_id=location_id,
        status_filter=status_filter,
        status_group=status_group,
        maintenance_state=maintenance_state,
        meter_state=meter_state,
        forecast_state=forecast_state,
    )
    summary = asset_list_summary(rows)
    sorted_rows = sort_asset_list_rows(rows, sort, order)
    items, normalized_page, total, pages = paginate_asset_list_rows(sorted_rows, page, page_size)
    return {
        "items": items,
        "page": normalized_page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
        "sort": sort,
        "order": order,
        "summary": summary,
    }


@router.get("/filter-options")
def asset_filter_options(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    def distinct_values(column):
        return [
            row[0]
            for row in db.query(column)
            .filter(column.isnot(None), func.trim(column) != "")
            .distinct()
            .order_by(column)
            .all()
        ]

    return {
        "company_codes": distinct_values(Asset.company_code),
        "manufacturers": distinct_values(Asset.manufacturer),
        "types": distinct_values(Asset.type),
        "categories": distinct_values(Asset.category),
    }


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    if db.query(Asset).filter(Asset.internal_id == payload.internal_id).first():
        raise HTTPException(status_code=400, detail="Ezzel a belső azonosítóval már van eszköz")
    validate_asset_customer_location(db, payload.customer_id, payload.current_location_id)
    asset = Asset(**payload.model_dump())
    db.add(asset)
    db.flush()
    add_asset_history(db, asset.id, current_user, "létrehozás", f"Eszköz létrehozva: {asset_display_name(asset)}")
    add_audit_log(db, current_user, "létrehozás", "asset", asset.id, f"Eszköz létrehozva: {asset_display_name(asset)}")
    db.commit()
    db.refresh(asset)
    return asset_to_dict(asset)


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    asset = db.query(Asset).options(joinedload(Asset.customer), joinedload(Asset.current_location)).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Eszköz nem található")
    return asset_to_dict(asset)


@router.put("/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: int, payload: AssetUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Eszköz nem található")
    data = payload.model_dump(exclude_unset=True)
    if "internal_id" in data and data["internal_id"] != asset.internal_id and db.query(Asset).filter(Asset.internal_id == data["internal_id"]).first():
        raise HTTPException(status_code=400, detail="Ezzel a belső azonosítóval már van eszköz")
    next_customer_id = data.get("customer_id", asset.customer_id)
    next_location_id = data.get("current_location_id", asset.current_location_id)
    validate_asset_customer_location(db, next_customer_id, next_location_id, existing_location_id=asset.current_location_id)
    old_status = asset.status
    old_location_id = asset.current_location_id
    for field, value in data.items():
        setattr(asset, field, value)
    if "status" in data and data["status"] != old_status:
        add_asset_history(db, asset.id, current_user, "státuszváltozás", f"Státusz: {old_status} → {asset.status}")
    if "current_location_id" in data and data["current_location_id"] != old_location_id:
        add_asset_history(db, asset.id, current_user, "helyszínváltozás", f"Helyszín azonosító: {old_location_id} → {asset.current_location_id}")
    add_audit_log(db, current_user, "módosítás", "asset", asset.id, f"Eszköz módosítva: {asset_display_name(asset)}")
    db.commit()
    db.refresh(asset)
    return asset_to_dict(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: int, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Eszköz nem található")
    if db.query(WorkOrderAsset).filter(WorkOrderAsset.asset_id == asset.id).count():
        raise HTTPException(status_code=400, detail="Az eszköz nem törölhető, mert munkalap kapcsolódik hozzá")
    if db.query(WorkOrderArchiveAsset).filter(WorkOrderArchiveAsset.asset_id == asset.id).count():
        raise HTTPException(status_code=400, detail="Az eszköz nem törölhető, mert archivált munkalap kapcsolódik hozzá")
    if db.query(CrmContractAsset).filter(CrmContractAsset.asset_id == asset.id).count():
        raise HTTPException(status_code=400, detail="Az eszköz nem törölhető, mert CRM szerződés kapcsolódik hozzá")
    add_audit_log(db, current_user, "törlés", "asset", asset.id, f"Eszköz törölve: {asset_display_name(asset)}")
    db.delete(asset)
    db.commit()
    return None


@router.get("/{asset_id}/work-orders")
def get_asset_work_orders(asset_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Minden olyan munkalap teljes tartalma, amely aktuálisan vagy korábban kapcsolódott az eszközhöz."""
    if not db.get(Asset, asset_id):
        raise HTTPException(status_code=404, detail="Eszköz nem található")

    current_link_ids = {
        row[0]
        for row in db.query(WorkOrderAsset.work_order_id)
        .filter(WorkOrderAsset.asset_id == asset_id)
        .all()
    }
    history_link_ids = {
        row[0]
        for row in db.query(AssetHistory.work_order_id)
        .filter(AssetHistory.asset_id == asset_id, AssetHistory.work_order_id.isnot(None))
        .all()
    }
    work_order_ids = current_link_ids | history_link_ids
    if not work_order_ids:
        return []

    orders = (
        work_order_base_query(db)
        .filter(WorkOrder.id.in_(work_order_ids))
        .order_by(WorkOrder.created_at.desc())
        .all()
    )
    return [work_order_to_dict(order) for order in orders]


@router.get("/{asset_id}/history")
def get_asset_history(asset_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if not db.get(Asset, asset_id):
        raise HTTPException(status_code=404, detail="Eszköz nem található")
    rows = (
        db.query(AssetHistory)
        .options(joinedload(AssetHistory.user), joinedload(AssetHistory.work_order))
        .filter(AssetHistory.asset_id == asset_id)
        .order_by(AssetHistory.changed_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "asset_id": row.asset_id,
            "action": row.action,
            "description": row.description,
            "changed_at": row.changed_at,
            "user_name": row.user.full_name if row.user else None,
            "work_order_number": row.work_order.number if row.work_order else None,
        }
        for row in rows
    ]
