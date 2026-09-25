from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
from ..config import get_settings
from ..database import get_db
from ..deps import RequireOfficeOrAdmin, get_current_user
from ..models import Asset, AssetHistory, AuditLog, CrmContract, CrmContractAsset, CrmContractLocation, Customer, CustomerContact, Location, Material, ROLE_TECHNICIAN, Role, User, WorkOrder, WorkOrderAsset, WorkOrderMaterial, WorkOrderSavedView, WorkOrderSignature
from ..schemas import BulkWorkOrderUpdate, BulkWorkOrderUpdateResult, WorkOrderClose, WorkOrderContractOption, WorkOrderCreate, WorkOrderEditHeartbeat, WorkOrderPage, WorkOrderSavedViewCreate, WorkOrderSavedViewRead, WorkOrderSavedViewUpdate, WorkOrderUpdate
from ..services.asset_display import asset_display_name, visible_internal_id
from ..services.audit import add_asset_history, add_audit_log
from ..services.company_profiles import resolve_work_order_company_profile
from ..services.work_order_template import XLSX_MEDIA_TYPE, build_work_order_workbook, work_order_template_filename
from ..services.work_order_signature_storage import signature_path
from ..services.work_order_concurrency import commit_with_optimistic_lock, require_current_version
from ..services.work_order_numbers import next_work_order_number
from ..services.work_order_notifications import capture_work_order_notification_state, notify_work_order_changes
from ..services.work_order_edit_presence import (
    get_edit_presence,
    heartbeat_edit_session,
    start_edit_session,
    stop_edit_session,
)

router = APIRouter(prefix="/work-orders", tags=["work_orders"])



def validate_time_ranges(
    planned_start_at: datetime | None,
    planned_end_at: datetime | None,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> None:
    if planned_start_at and planned_end_at and planned_end_at <= planned_start_at:
        raise HTTPException(status_code=400, detail="A tervezett befejezésnek a tervezett kezdés után kell lennie")
    if started_at and completed_at and completed_at <= started_at:
        raise HTTPException(status_code=400, detail="A tényleges befejezésnek a tényleges kezdés után kell lennie")


def _validate_technician(db: Session, technician_id: int | None, label: str) -> None:
    if technician_id is None:
        return
    technician = (
        db.query(User)
        .join(Role)
        .filter(User.id == technician_id, User.is_active.is_(True), Role.name == ROLE_TECHNICIAN)
        .first()
    )
    if technician is None:
        raise HTTPException(status_code=400, detail=f"A(z) {label} nem aktív technikus")


def validate_work_order_refs(
    db: Session,
    customer_id: int | None,
    location_id: int | None,
    technician_id: int | None,
    secondary_technician_id: int | None = None,
    contact_id: int | None = None,
    *,
    existing_location_id: int | None = None,
):
    if customer_id is not None and not db.get(Customer, customer_id):
        raise HTTPException(status_code=400, detail="Érvénytelen ügyfél")
    if location_id is not None:
        location = db.get(Location, location_id)
        if not location:
            raise HTTPException(status_code=400, detail="Érvénytelen helyszín")
        if customer_id is not None and location.customer_id != customer_id:
            raise HTTPException(status_code=400, detail="A helyszín nem a megadott ügyfélhez tartozik")
        if not location.is_active and location.id != existing_location_id:
            raise HTTPException(status_code=400, detail="Inaktív helyszín nem választható új munkalaphoz")
    if contact_id is not None:
        contact = db.get(CustomerContact, contact_id)
        if not contact:
            raise HTTPException(status_code=400, detail="Érvénytelen kapcsolattartó")
        if customer_id is not None and contact.customer_id != customer_id:
            raise HTTPException(status_code=400, detail="A kapcsolattartó nem a kiválasztott ügyfélhez tartozik")
        if location_id is not None and contact.location_id is not None and contact.location_id != location_id:
            raise HTTPException(status_code=400, detail="A kapcsolattartó nem a kiválasztott helyszínhez tartozik")
    _validate_technician(db, technician_id, "elsődleges technikus")
    _validate_technician(db, secondary_technician_id, "második technikus")
    if technician_id is not None and technician_id == secondary_technician_id:
        raise HTTPException(status_code=400, detail="Ugyanaz a technikus nem választható ki kétszer")


def validate_contract_for_work_order(
    db: Session,
    contract_id: int | None,
    customer_id: int,
    location_id: int | None,
    asset_ids: list[int],
    *,
    existing_contract_id: int | None = None,
) -> CrmContract | None:
    if contract_id is None:
        return None
    contract = (
        db.query(CrmContract)
        .options(selectinload(CrmContract.location_links), selectinload(CrmContract.asset_links))
        .filter(CrmContract.id == contract_id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=400, detail="A kiválasztott szerződés nem található")
    if contract.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="A kiválasztott szerződés nem a munkalap ügyfeléhez tartozik")
    if contract.status != "aktív" and contract.id != existing_contract_id:
        raise HTTPException(status_code=400, detail="Új munkalaphoz csak aktív szerződés rendelhető")
    allowed_locations = {link.location_id for link in contract.location_links}
    if allowed_locations and location_id not in allowed_locations:
        raise HTTPException(status_code=400, detail="A kiválasztott helyszínre ez a szerződés nem érvényes")
    allowed_assets = {link.asset_id for link in contract.asset_links}
    invalid_assets = sorted(set(asset_ids or []) - allowed_assets) if allowed_assets else []
    if invalid_assets:
        raise HTTPException(status_code=400, detail="A munkalap egyik kiválasztott eszközére a szerződés nem érvényes")
    return contract


def validate_asset_for_work_order(asset: Asset, work_order: WorkOrder):
    if asset.customer_id != work_order.customer_id:
        raise HTTPException(
            status_code=400,
            detail=f"A(z) {asset_display_name(asset)} eszköz nem a kiválasztott ügyfélhez tartozik",
        )
    if work_order.location_id and asset.current_location_id and asset.current_location_id != work_order.location_id:
        raise HTTPException(
            status_code=400,
            detail=f"A(z) {asset_display_name(asset)} eszköz nem a kiválasztott helyszínhez tartozik",
        )


def validate_existing_assets(db: Session, work_order: WorkOrder):
    for link in work_order.asset_links:
        asset = db.get(Asset, link.asset_id)
        if asset:
            validate_asset_for_work_order(asset, work_order)


def set_assets(db: Session, work_order: WorkOrder, asset_ids: list[int], current_user: User):
    old_ids = {link.asset_id for link in work_order.asset_links}
    new_ids = set(asset_ids or [])
    for asset_id in new_ids:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(status_code=400, detail=f"Érvénytelen eszköz azonosító: {asset_id}")
        validate_asset_for_work_order(asset, work_order)
    removed_ids = old_ids - new_ids
    for asset_id in removed_ids:
        add_asset_history(db, asset_id, current_user, "munkalapról leválasztás", f"Leválasztva a(z) {work_order.number} munkalapról", work_order.id)

    work_order.asset_links.clear()
    db.flush()
    for asset_id in new_ids:
        work_order.asset_links.append(WorkOrderAsset(asset_id=asset_id))
        if asset_id not in old_ids:
            add_asset_history(db, asset_id, current_user, "munkalaphoz kapcsolás", f"Kapcsolva a(z) {work_order.number} munkalaphoz", work_order.id)


def set_materials(db: Session, work_order: WorkOrder, lines: list):
    work_order.material_lines.clear()
    db.flush()
    for line in lines or []:
        material = db.get(Material, line.material_id)
        if not material:
            raise HTTPException(status_code=400, detail=f"Érvénytelen anyag azonosító: {line.material_id}")
        work_order.material_lines.append(
            WorkOrderMaterial(
                material_id=line.material_id,
                quantity=line.quantity,
                unit_price=line.unit_price if line.unit_price is not None else material.unit_price,
                note=line.note,
            )
        )


def update_assets_after_maintenance_close(
    db: Session,
    work_order: WorkOrder,
    current_user: User,
) -> None:
    """Frissíti a kapcsolt eszközök utolsó karbantartási dátumát.

    Csak karbantartás típusú, lezárt munkalapnál hívandó. Az utolsó
    karbantartási dátumot nem engedi egy régebbi munkalappal visszaállítani,
    de a karbantartási eseményt minden első lezáráskor rögzíti a történetben.
    """
    if work_order.work_type != "karbantartás":
        return

    maintenance_at = work_order.completed_at or work_order.closed_at or datetime.utcnow()
    maintenance_date = maintenance_at.date()

    for link in work_order.asset_links:
        asset = link.asset or db.get(Asset, link.asset_id)
        if not asset:
            continue

        previous_date = asset.last_maintenance_date
        date_updated = previous_date is None or maintenance_date > previous_date
        if date_updated:
            asset.last_maintenance_date = maintenance_date
            asset.updated_at = datetime.utcnow()

        description = f"Karbantartás elvégezve a(z) {work_order.number} munkalap alapján ({maintenance_date.isoformat()})"
        if not date_updated and previous_date and previous_date > maintenance_date:
            description += f"; az utolsó karbantartás dátuma változatlan maradt ({previous_date.isoformat()})"
        add_asset_history(
            db,
            asset.id,
            current_user,
            "karbantartás elvégezve",
            description,
            work_order.id,
        )
        add_audit_log(
            db,
            current_user,
            "módosítás",
            "asset",
            asset.id,
            f"Utolsó karbantartás feldolgozva a(z) {work_order.number} munkalap lezárásakor",
        )


def choose_default_contact(order: WorkOrder) -> CustomerContact | None:
    if order.contact:
        return order.contact
    contacts = list(order.customer.contacts or []) if order.customer else []
    if not contacts:
        return None
    location_id = order.location_id
    ordered_categories = ["Szerviz", "Sales", "Egyéb"]
    for category in ordered_categories:
        for contact in contacts:
            if contact.category == category and contact.is_primary and contact.location_id == location_id:
                return contact
        for contact in contacts:
            if contact.category == category and contact.is_primary and contact.location_id is None:
                return contact
        for contact in contacts:
            if contact.category == category and contact.location_id == location_id:
                return contact
        for contact in contacts:
            if contact.category == category and contact.location_id is None:
                return contact
    return contacts[0]


def contact_to_dict(contact: CustomerContact | None) -> dict | None:
    if not contact:
        return None
    return {
        "id": contact.id,
        "customer_id": contact.customer_id,
        "location_id": contact.location_id,
        "location_name": contact.location.name if contact.location else None,
        "category": contact.category,
        "name": contact.name,
        "title": contact.title,
        "phone": contact.phone,
        "email": contact.email,
        "note": contact.note,
        "is_primary": contact.is_primary,
    }


def work_order_to_dict(order: WorkOrder) -> dict:
    supplier = resolve_work_order_company_profile(order, get_settings())
    contact = choose_default_contact(order)
    return {
        "id": order.id,
        "number": order.number,
        "customer_id": order.customer_id,
        "customer_name": order.customer.name if order.customer else None,
        "customer_address": order.customer.address if order.customer else None,
        "customer_contact_person": contact.name if contact else (order.customer.contact_person if order.customer else None),
        "customer_phone": contact.phone if contact else (order.customer.phone if order.customer else None),
        "customer_email": contact.email if contact else (order.customer.email if order.customer else None),
        "customer_company_code": order.customer.company_code if order.customer else None,
        "location_id": order.location_id,
        "location_name": order.location.name if order.location else None,
        "location_address": order.location.address if order.location else None,
        "contact_id": order.contact_id,
        "contact": contact_to_dict(contact),
        "contract_id": order.contract_id,
        "contract_number": order.contract.contract_number if order.contract else None,
        "contract_status": order.contract.status if order.contract else None,
        "status": order.status,
        "priority": order.priority,
        "technician_id": order.technician_id,
        "technician_name": order.technician.full_name if order.technician else None,
        "secondary_technician_id": order.secondary_technician_id,
        "secondary_technician_name": order.secondary_technician.full_name if order.secondary_technician else None,
        "technician_ids": [user_id for user_id in (order.technician_id, order.secondary_technician_id) if user_id is not None],
        "technician_names": [name for name in (order.technician.full_name if order.technician else None, order.secondary_technician.full_name if order.secondary_technician else None) if name],
        "description": order.description,
        "planned_date": order.planned_date,
        "planned_start_at": order.planned_start_at,
        "planned_end_at": order.planned_end_at,
        "started_at": order.started_at,
        "completed_at": order.completed_at,
        "work_done": order.work_done,
        "final_status": order.final_status,
        "labor_hours": float(order.labor_hours) if order.labor_hours is not None else None,
        "work_type": order.work_type,
        "contract_type": order.contract_type,
        "internal_note": order.internal_note,
        "customer_note": order.customer_note,
        "closed_at": order.closed_at,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "version": order.version,
        "supplier": supplier.to_dict() if supplier else None,
        "assets": [
            {
                "id": link.asset.id,
                "internal_id": visible_internal_id(link.asset.internal_id),
                "display_name": asset_display_name(link.asset),
                "serial_number": link.asset.serial_number,
                "type": link.asset.type,
                "manufacturer": link.asset.manufacturer,
                "model": link.asset.model,
                "status": link.asset.status,
                "company_code": link.asset.company_code,
                "last_maintenance_date": link.asset.last_maintenance_date,
                "latest_meter_value": latest.value if (latest := max(link.asset.meter_readings, key=lambda reading: (reading.recorded_at, reading.id), default=None)) else None,
                "latest_meter_black_white_value": latest.black_white_value if latest else None,
                "latest_meter_color_value": latest.color_value if latest else None,
                "latest_meter_scan_value": latest.scan_value if latest else None,
                "latest_meter_at": latest.recorded_at if latest else None,
            }
            for link in order.asset_links
        ],
        "asset_ids": [link.asset_id for link in order.asset_links],
        "materials": [
            {
                "id": line.id,
                "material_id": line.material_id,
                "sku": line.material.sku,
                "name": line.material.name,
                "unit": line.material.unit,
                "quantity": float(line.quantity),
                "unit_price": float(line.unit_price) if line.unit_price is not None else None,
                "note": line.note,
            }
            for line in order.material_lines
        ],
    }


def base_query(db: Session):
    return db.query(WorkOrder).options(
        joinedload(WorkOrder.customer).selectinload(Customer.contacts).selectinload(CustomerContact.location),
        joinedload(WorkOrder.location),
        joinedload(WorkOrder.contact).joinedload(CustomerContact.location),
        joinedload(WorkOrder.contract),
        joinedload(WorkOrder.technician),
        joinedload(WorkOrder.secondary_technician),
        selectinload(WorkOrder.asset_links).joinedload(WorkOrderAsset.asset).selectinload(Asset.meter_readings),
        selectinload(WorkOrder.material_lines).joinedload(WorkOrderMaterial.material),
    )


@router.get("/contract-options", response_model=list[WorkOrderContractOption])
def contract_options(
    customer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    contracts = (
        db.query(CrmContract)
        .options(selectinload(CrmContract.location_links), selectinload(CrmContract.asset_links))
        .filter(CrmContract.customer_id == customer_id)
        .order_by(CrmContract.status, CrmContract.end_date.desc(), CrmContract.contract_number)
        .all()
    )
    return [WorkOrderContractOption.model_validate(contract, from_attributes=True) for contract in contracts]


@router.get("")
def list_work_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: str | None = None,
    date_to: str | None = None,
    customer_id: int | None = None,
    technician_id: int | None = None,
    priority: str | None = None,
    asset_id: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = base_query(db)
    if status_filter:
        query = query.filter(WorkOrder.status == status_filter)
    if date_from:
        query = query.filter(WorkOrder.planned_date >= date_from)
    if date_to:
        query = query.filter(WorkOrder.planned_date <= date_to)
    if customer_id:
        query = query.filter(WorkOrder.customer_id == customer_id)
    if technician_id:
        query = query.filter(or_(WorkOrder.technician_id == technician_id, WorkOrder.secondary_technician_id == technician_id))
    if priority:
        query = query.filter(WorkOrder.priority == priority)
    if q:
        like = f"%{q}%"
        query = query.filter(WorkOrder.number.ilike(like) | WorkOrder.description.ilike(like))
    if asset_id:
        query = query.join(WorkOrderAsset).filter(WorkOrderAsset.asset_id == asset_id)
    rows = query.order_by(WorkOrder.created_at.desc()).all()
    return [work_order_to_dict(order) for order in rows]


WORK_ORDER_SORT_FIELDS = {
    "number": WorkOrder.number,
    "status": WorkOrder.status,
    "priority": WorkOrder.priority,
    "description": WorkOrder.description,
    "planned_date": WorkOrder.planned_date,
    "work_type": WorkOrder.work_type,
    "created_at": WorkOrder.created_at,
    "updated_at": WorkOrder.updated_at,
}
WORK_ORDER_VIEW_COLUMNS = {
    "number", "status", "priority", "customer", "location", "assets", "description",
    "technician", "planned", "work_type", "created_at", "updated_at",
}
WORK_ORDER_VIEW_STATE_KEYS = {
    "q", "status", "priority", "customer_id", "technician_id", "asset_id",
    "date_from", "date_to", "work_type", "company_code", "open_state",
    "page_size", "sort", "order", "columns",
}


def _apply_work_order_filters(
    query,
    *,
    status_filter: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: int | None = None,
    technician_id: int | None = None,
    priority: str | None = None,
    asset_id: int | None = None,
    q: str | None = None,
    work_type: str | None = None,
    company_code: str | None = None,
    open_state: str | None = None,
):
    if status_filter:
        query = query.filter(WorkOrder.status == status_filter)
    if date_from:
        query = query.filter(WorkOrder.planned_date >= date_from)
    if date_to:
        query = query.filter(WorkOrder.planned_date <= date_to)
    if customer_id:
        query = query.filter(WorkOrder.customer_id == customer_id)
    if technician_id:
        query = query.filter(or_(WorkOrder.technician_id == technician_id, WorkOrder.secondary_technician_id == technician_id))
    if priority:
        query = query.filter(WorkOrder.priority == priority)
    if work_type:
        query = query.filter(WorkOrder.work_type == work_type)
    if asset_id:
        query = query.filter(WorkOrder.asset_links.any(WorkOrderAsset.asset_id == asset_id))
    if company_code:
        normalized_code = company_code.strip()
        query = query.filter(
            or_(
                WorkOrder.customer.has(Customer.company_code == normalized_code),
                WorkOrder.asset_links.any(WorkOrderAsset.asset.has(Asset.company_code == normalized_code)),
            )
        )
    if open_state == "open":
        query = query.filter(WorkOrder.status.notin_(["lezárva", "törölve / sztornózva"]))
    elif open_state == "closed":
        query = query.filter(WorkOrder.status == "lezárva")
    elif open_state == "cancelled":
        query = query.filter(WorkOrder.status == "törölve / sztornózva")
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                WorkOrder.number.ilike(like),
                WorkOrder.description.ilike(like),
                WorkOrder.customer.has(Customer.name.ilike(like)),
                WorkOrder.location.has(Location.name.ilike(like)),
                WorkOrder.technician.has(User.full_name.ilike(like)),
                WorkOrder.secondary_technician.has(User.full_name.ilike(like)),
                WorkOrder.asset_links.any(
                    WorkOrderAsset.asset.has(
                        or_(
                            Asset.internal_id.ilike(like),
                            Asset.serial_number.ilike(like),
                            Asset.type.ilike(like),
                            Asset.manufacturer.ilike(like),
                            Asset.model.ilike(like),
                        )
                    )
                ),
            )
        )
    return query


def _sanitize_saved_view_state(state: dict) -> dict:
    sanitized = {key: value for key, value in (state or {}).items() if key in WORK_ORDER_VIEW_STATE_KEYS}
    columns = sanitized.get("columns")
    if columns is not None:
        if not isinstance(columns, list):
            raise HTTPException(status_code=400, detail="A mentett nézet oszloplistája érvénytelen")
        unique_columns = []
        for column in columns:
            if column in WORK_ORDER_VIEW_COLUMNS and column not in unique_columns:
                unique_columns.append(column)
        if "number" not in unique_columns:
            unique_columns.insert(0, "number")
        sanitized["columns"] = unique_columns
    page_size = sanitized.get("page_size")
    if page_size is not None:
        try:
            page_size = int(page_size)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="A mentett nézet oldalmérete érvénytelen") from exc
        sanitized["page_size"] = page_size if page_size in {25, 50, 100, 200} else 50
    if sanitized.get("sort") not in set(WORK_ORDER_SORT_FIELDS) | {"customer_name", "location_name", "technician_name"}:
        sanitized["sort"] = "created_at"
    if sanitized.get("order") not in {"asc", "desc"}:
        sanitized["order"] = "desc"
    return sanitized


@router.get("/paged", response_model=WorkOrderPage)
def list_work_orders_paged(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: int | None = None,
    technician_id: int | None = None,
    priority: str | None = None,
    asset_id: int | None = None,
    q: str | None = None,
    work_type: str | None = None,
    company_code: str | None = None,
    open_state: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if page_size not in {25, 50, 100, 200}:
        page_size = 50
    allowed_sorts = set(WORK_ORDER_SORT_FIELDS) | {"customer_name", "location_name", "technician_name"}
    if sort not in allowed_sorts:
        sort = "created_at"

    filter_kwargs = dict(
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        technician_id=technician_id,
        priority=priority,
        asset_id=asset_id,
        q=q,
        work_type=work_type,
        company_code=company_code,
        open_state=open_state,
    )
    count_query = _apply_work_order_filters(db.query(WorkOrder.id), **filter_kwargs)
    total = count_query.count()
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)

    query = _apply_work_order_filters(base_query(db), **filter_kwargs)
    sort_expression = WORK_ORDER_SORT_FIELDS.get(sort)
    if sort == "customer_name":
        query = query.outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        sort_expression = Customer.name
    elif sort == "location_name":
        query = query.outerjoin(Location, WorkOrder.location_id == Location.id)
        sort_expression = Location.name
    elif sort == "technician_name":
        query = query.outerjoin(User, WorkOrder.technician_id == User.id)
        sort_expression = User.full_name

    direction = asc if order == "asc" else desc
    query = query.order_by(direction(sort_expression), desc(WorkOrder.id))
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [work_order_to_dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
        "sort": sort,
        "order": order,
    }


@router.get("/saved-views", response_model=list[WorkOrderSavedViewRead])
def list_saved_work_order_views(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(WorkOrderSavedView)
        .filter(WorkOrderSavedView.user_id == current_user.id)
        .order_by(WorkOrderSavedView.is_default.desc(), WorkOrderSavedView.name.asc())
        .all()
    )


@router.post("/saved-views", response_model=WorkOrderSavedViewRead, status_code=status.HTTP_201_CREATED)
def create_saved_work_order_view(
    payload: WorkOrderSavedViewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = payload.name.strip()
    state = _sanitize_saved_view_state(payload.state)
    if payload.is_default:
        db.query(WorkOrderSavedView).filter(WorkOrderSavedView.user_id == current_user.id).update({"is_default": False})
    view = WorkOrderSavedView(user_id=current_user.id, name=name, state=state, is_default=payload.is_default)
    db.add(view)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Már létezik ilyen nevű mentett nézet") from exc
    db.refresh(view)
    return view


@router.put("/saved-views/{view_id}", response_model=WorkOrderSavedViewRead)
def update_saved_work_order_view(
    view_id: int,
    payload: WorkOrderSavedViewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    view = db.query(WorkOrderSavedView).filter(
        WorkOrderSavedView.id == view_id,
        WorkOrderSavedView.user_id == current_user.id,
    ).first()
    if not view:
        raise HTTPException(status_code=404, detail="A mentett nézet nem található")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        view.name = data["name"].strip()
    if "state" in data:
        view.state = _sanitize_saved_view_state(data["state"])
    if data.get("is_default"):
        db.query(WorkOrderSavedView).filter(
            WorkOrderSavedView.user_id == current_user.id,
            WorkOrderSavedView.id != view.id,
        ).update({"is_default": False})
    if "is_default" in data:
        view.is_default = data["is_default"]
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Már létezik ilyen nevű mentett nézet") from exc
    db.refresh(view)
    return view


@router.delete("/saved-views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_work_order_view(
    view_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    view = db.query(WorkOrderSavedView).filter(
        WorkOrderSavedView.id == view_id,
        WorkOrderSavedView.user_id == current_user.id,
    ).first()
    if not view:
        raise HTTPException(status_code=404, detail="A mentett nézet nem található")
    db.delete(view)
    db.commit()
    return None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_work_order(payload: WorkOrderCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    validate_work_order_refs(db, payload.customer_id, payload.location_id, payload.technician_id, payload.secondary_technician_id, payload.contact_id)
    validate_time_ranges(payload.planned_start_at, payload.planned_end_at, payload.started_at, payload.completed_at)
    planned_date = payload.planned_date or (payload.planned_start_at.date() if payload.planned_start_at else None)
    contract = validate_contract_for_work_order(db, payload.contract_id, payload.customer_id, payload.location_id, payload.asset_ids)
    order = WorkOrder(
        number=next_work_order_number(db),
        customer_id=payload.customer_id,
        location_id=payload.location_id,
        contact_id=payload.contact_id,
        contract_id=payload.contract_id,
        status=payload.status,
        priority=payload.priority,
        technician_id=payload.technician_id,
        secondary_technician_id=payload.secondary_technician_id,
        description=payload.description,
        planned_date=planned_date,
        planned_start_at=payload.planned_start_at,
        planned_end_at=payload.planned_end_at,
        started_at=payload.started_at,
        completed_at=payload.completed_at,
        work_done=payload.work_done,
        labor_hours=payload.labor_hours,
        work_type=payload.work_type,
        contract_type=contract.contract_type if contract else payload.contract_type,
        internal_note=payload.internal_note,
        customer_note=payload.customer_note,
    )
    db.add(order)
    db.flush()
    set_assets(db, order, payload.asset_ids, current_user)
    set_materials(db, order, payload.materials)
    add_audit_log(db, current_user, "létrehozás", "work_order", order.id, f"Munkalap létrehozva: {order.number}")
    notify_work_order_changes(db, order)
    db.commit()
    order = base_query(db).filter(WorkOrder.id == order.id).first()
    return work_order_to_dict(order)


def _move_datetime_to_date(value: datetime | None, target_date: date) -> datetime | None:
    if value is None:
        return None
    return value.replace(year=target_date.year, month=target_date.month, day=target_date.day)


@router.post("/bulk-update", response_model=BulkWorkOrderUpdateResult)
def bulk_update_work_orders(
    payload: BulkWorkOrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    if not payload.apply_status and not payload.apply_planned_date and not payload.apply_technician and not payload.apply_secondary_technician:
        raise HTTPException(status_code=400, detail="Válassz legalább egy tömegesen módosítandó mezőt")
    if payload.apply_status and payload.status is None:
        raise HTTPException(status_code=400, detail="A státusz megadása kötelező")
    if payload.apply_planned_date and payload.planned_date is None:
        raise HTTPException(status_code=400, detail="A tervezett nap megadása kötelező")

    unique_items = {}
    for item in payload.items:
        if item.id in unique_items and unique_items[item.id] != item.version:
            raise HTTPException(status_code=400, detail=f"A(z) {item.id} munkalaphoz több eltérő verzió érkezett")
        unique_items[item.id] = item.version

    order_ids = list(unique_items)
    orders = base_query(db).filter(WorkOrder.id.in_(order_ids)).all()
    orders_by_id = {order.id: order for order in orders}
    missing_ids = [order_id for order_id in order_ids if order_id not in orders_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Nem található munkalap: {', '.join(map(str, missing_ids))}")

    technician = None
    if payload.apply_technician and payload.technician_id is not None:
        technician = (
            db.query(User)
            .join(Role)
            .filter(User.id == payload.technician_id, User.is_active.is_(True), Role.name == ROLE_TECHNICIAN)
            .first()
        )
        if technician is None:
            raise HTTPException(status_code=400, detail="A kiválasztott felhasználó nem aktív technikus")

    secondary_technician = None
    if payload.apply_secondary_technician and payload.secondary_technician_id is not None:
        secondary_technician = (
            db.query(User)
            .join(Role)
            .filter(User.id == payload.secondary_technician_id, User.is_active.is_(True), Role.name == ROLE_TECHNICIAN)
            .first()
        )
        if secondary_technician is None:
            raise HTTPException(status_code=400, detail="A kiválasztott második felhasználó nem aktív technikus")
    if (payload.apply_technician or payload.apply_secondary_technician):
        for order in orders_by_id.values():
            primary_id = payload.technician_id if payload.apply_technician else order.technician_id
            secondary_id = payload.secondary_technician_id if payload.apply_secondary_technician else order.secondary_technician_id
            if primary_id is not None and primary_id == secondary_id:
                raise HTTPException(status_code=400, detail="Ugyanaz a technikus nem választható ki kétszer")

    before_states = {}
    for order_id in order_ids:
        order = orders_by_id[order_id]
        require_current_version(order, unique_items[order_id])
        before_states[order_id] = capture_work_order_notification_state(order)

    changed_fields = []
    if payload.apply_planned_date:
        changed_fields.append(f"tervezett nap: {payload.planned_date.isoformat()}")
    if payload.apply_technician:
        changed_fields.append(f"felelős technikus: {technician.full_name if technician else 'nincs kijelölve'}")
    if payload.apply_secondary_technician:
        changed_fields.append(f"második technikus: {secondary_technician.full_name if secondary_technician else 'nincs kijelölve'}")

    for order_id in order_ids:
        order = orders_by_id[order_id]
        old_status = order.status
        order_changed_fields = list(changed_fields)
        if payload.apply_status:
            order.status = payload.status
            order_changed_fields.insert(0, f"státusz: {old_status} → {payload.status}")
            if old_status != "lezárva" and order.status == "lezárva":
                now = datetime.utcnow()
                order.completed_at = order.completed_at or now
                order.closed_at = order.closed_at or now
                update_assets_after_maintenance_close(db, order, current_user)
        if payload.apply_planned_date:
            order.planned_date = payload.planned_date
            order.planned_start_at = _move_datetime_to_date(order.planned_start_at, payload.planned_date)
            order.planned_end_at = _move_datetime_to_date(order.planned_end_at, payload.planned_date)
        if payload.apply_technician:
            order.technician_id = payload.technician_id
        if payload.apply_secondary_technician:
            order.secondary_technician_id = payload.secondary_technician_id
        order.updated_at = datetime.utcnow()
        description = "; ".join(order_changed_fields)
        add_audit_log(db, current_user, "tömeges módosítás", "work_order", order.id, f"Munkalap tömegesen módosítva: {order.number}; {description}")
        notify_work_order_changes(db, order, before_states[order_id])

    commit_with_optimistic_lock(db)
    return BulkWorkOrderUpdateResult(updated_count=len(order_ids), updated_work_order_ids=order_ids)


@router.get("/{order_id}/editing")
def read_edit_presence(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    try:
        return get_edit_presence(db, order_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{order_id}/editing/start")
def begin_editing_work_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    try:
        return start_edit_session(db, order_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{order_id}/editing/heartbeat")
def heartbeat_work_order_editing(
    order_id: int,
    payload: WorkOrderEditHeartbeat,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    try:
        return heartbeat_edit_session(db, order_id, current_user, payload.session_token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{order_id}/editing/{session_token}", status_code=status.HTTP_204_NO_CONTENT)
def end_editing_work_order(
    order_id: int,
    session_token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    stop_edit_session(db, order_id, current_user, session_token)
    return None


@router.get("/{order_id}")
def get_work_order(order_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    order = base_query(db).filter(WorkOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    return work_order_to_dict(order)


@router.get("/{order_id}/history")
def get_work_order_history(order_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    order = db.get(WorkOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")

    audit_rows = (
        db.query(AuditLog)
        .options(joinedload(AuditLog.user))
        .filter(AuditLog.entity_type == "work_order", AuditLog.entity_id == str(order_id))
        .all()
    )
    asset_rows = (
        db.query(AssetHistory)
        .options(joinedload(AssetHistory.user), joinedload(AssetHistory.asset))
        .filter(AssetHistory.work_order_id == order_id)
        .all()
    )

    history = [
        {
            "id": f"audit-{row.id}",
            "source": "audit",
            "action": row.action,
            "description": row.description,
            "user_name": row.actor_name or (row.user.full_name if row.user else None),
            "created_at": row.created_at,
            "asset_id": None,
            "asset_name": None,
        }
        for row in audit_rows
    ]
    history.extend(
        {
            "id": f"asset-{row.id}",
            "source": "asset_history",
            "action": row.action,
            "description": row.description,
            "user_name": row.user.full_name if row.user else None,
            "created_at": row.changed_at,
            "asset_id": row.asset_id,
            "asset_name": asset_display_name(row.asset) if row.asset else None,
        }
        for row in asset_rows
    )
    history.sort(key=lambda item: item["created_at"], reverse=True)
    return history




def _require_signature_access(order: WorkOrder, current_user: User) -> None:
    if current_user.role.name != ROLE_TECHNICIAN:
        return
    if current_user.id not in {order.technician_id, order.secondary_technician_id}:
        raise HTTPException(status_code=403, detail="A munkalap nincs hozzád rendelve")


@router.get("/{order_id}/signatures")
def list_work_order_signatures(order_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.get(WorkOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    _require_signature_access(order, current_user)
    rows = (
        db.query(WorkOrderSignature)
        .filter(WorkOrderSignature.work_order_id == order_id)
        .order_by(WorkOrderSignature.signed_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "snapshot_id": row.snapshot_id,
            "signer_name": row.signer_name,
            "signer_role": row.signer_role,
            "signed_at": row.signed_at,
            "snapshot_revision": row.snapshot.revision,
            "snapshot_sha256": row.snapshot.snapshot_sha256,
            "signed_pdf_sha256": row.signed_pdf_sha256,
            "signed_pdf_size_bytes": row.signed_pdf_size_bytes,
            "is_current": row.finalized_work_order_version == order.version,
        }
        for row in rows
    ]


@router.get("/{order_id}/signatures/{signature_id}/pdf")
def download_signed_work_order_pdf(order_id: int, signature_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = db.get(WorkOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    _require_signature_access(order, current_user)
    row = db.query(WorkOrderSignature).filter(WorkOrderSignature.id == signature_id, WorkOrderSignature.work_order_id == order_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Aláírt munkalap nem található")
    path = signature_path(get_settings(), row.signed_pdf_storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Az aláírt PDF hiányzik a tárhelyről")
    safe_number = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in order.number)
    return FileResponse(path, media_type="application/pdf", filename=f"{safe_number}-signed-r{row.snapshot.revision}.pdf")


@router.get("/{order_id}/worksheet.xlsx")
def download_work_order_template(order_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    order = base_query(db).filter(WorkOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    buffer = build_work_order_workbook(order, get_settings())
    filename = work_order_template_filename(order)
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/{order_id}")
def update_work_order(order_id: int, payload: WorkOrderUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    order = base_query(db).filter(WorkOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    require_current_version(order, payload.version)
    notification_before = capture_work_order_notification_state(order)
    data = payload.model_dump(exclude_unset=True, exclude={"asset_ids", "materials", "version"})
    customer_id = data.get("customer_id", order.customer_id)
    location_id = data.get("location_id", order.location_id)
    technician_id = data.get("technician_id", order.technician_id)
    secondary_technician_id = data.get("secondary_technician_id", order.secondary_technician_id)
    contact_id = data.get("contact_id", order.contact_id)
    validate_work_order_refs(db, customer_id, location_id, None, None, contact_id, existing_location_id=order.location_id)
    if "technician_id" in data:
        _validate_technician(db, technician_id, "elsődleges technikus")
    if "secondary_technician_id" in data:
        _validate_technician(db, secondary_technician_id, "második technikus")
    if technician_id is not None and technician_id == secondary_technician_id:
        raise HTTPException(status_code=400, detail="Ugyanaz a technikus nem választható ki kétszer")
    final_asset_ids = payload.asset_ids if payload.asset_ids is not None else [link.asset_id for link in order.asset_links]
    contract_id = data.get("contract_id", order.contract_id)
    contract_id_changed = "contract_id" in data and contract_id != order.contract_id
    contract = validate_contract_for_work_order(db, contract_id, customer_id, location_id, final_asset_ids, existing_contract_id=order.contract_id)
    if contract is not None:
        if contract_id_changed or order.contract_id is None:
            data["contract_type"] = contract.contract_type
        else:
            # A contract_type munkalapi snapshot: a szerződés későbbi módosítása
            # ne írja át visszamenőleg a korábbi munkalapot.
            data.pop("contract_type", None)
    planned_start_at = data.get("planned_start_at", order.planned_start_at)
    planned_end_at = data.get("planned_end_at", order.planned_end_at)
    started_at = data.get("started_at", order.started_at)
    completed_at = data.get("completed_at", order.completed_at)
    validate_time_ranges(planned_start_at, planned_end_at, started_at, completed_at)
    if "planned_start_at" in data and "planned_date" not in data and data["planned_start_at"]:
        data["planned_date"] = data["planned_start_at"].date()
    old_status = order.status
    for field, value in data.items():
        setattr(order, field, value)
    transitioned_to_closed = old_status != "lezárva" and order.status == "lezárva"
    if transitioned_to_closed:
        now = datetime.utcnow()
        order.completed_at = order.completed_at or now
        order.closed_at = order.closed_at or now
    if payload.asset_ids is not None:
        set_assets(db, order, payload.asset_ids, current_user)
    else:
        validate_existing_assets(db, order)
    if payload.materials is not None:
        set_materials(db, order, payload.materials)
    if transitioned_to_closed:
        update_assets_after_maintenance_close(db, order, current_user)
    # A kapcsolati sorok önálló módosítása esetén is frissüljön a szülő rekord,
    # így a verziószám minden mentésnél emelkedik.
    order.updated_at = datetime.utcnow()
    if order.status != old_status:
        add_audit_log(db, current_user, "státuszváltás", "work_order", order.id, f"Munkalap státusz: {old_status} → {order.status}")
    else:
        add_audit_log(db, current_user, "módosítás", "work_order", order.id, f"Munkalap módosítva: {order.number}")
    notify_work_order_changes(db, order, notification_before)
    commit_with_optimistic_lock(db)
    order = base_query(db).filter(WorkOrder.id == order_id).first()
    return work_order_to_dict(order)


@router.post("/{order_id}/close")
def close_work_order(order_id: int, payload: WorkOrderClose, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = base_query(db).filter(WorkOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    if order.status == "törölve / sztornózva":
        raise HTTPException(status_code=400, detail="Sztornózott munkalap nem zárható le")
    assigned_technician_ids = {technician_id for technician_id in (order.technician_id, order.secondary_technician_id) if technician_id is not None}
    if current_user.role.name == ROLE_TECHNICIAN and assigned_technician_ids and current_user.id not in assigned_technician_ids:
        raise HTTPException(status_code=403, detail="Csak saját vagy kijelöletlen munkalap zárható")
    require_current_version(order, payload.version)
    was_already_closed = order.status == "lezárva"
    order.status = "lezárva"
    order.work_done = payload.work_done
    order.final_status = payload.final_status
    order.labor_hours = payload.labor_hours
    order.started_at = payload.started_at or order.started_at
    order.completed_at = payload.completed_at or datetime.utcnow()
    validate_time_ranges(order.planned_start_at, order.planned_end_at, order.started_at, order.completed_at)
    order.closed_at = datetime.utcnow()
    primary_technician_id = payload.technician_id if payload.technician_id is not None else order.technician_id
    if primary_technician_id is None and current_user.role.name == ROLE_TECHNICIAN:
        primary_technician_id = current_user.id
    secondary_technician_id = payload.secondary_technician_id if payload.secondary_technician_id is not None else order.secondary_technician_id
    validate_work_order_refs(db, order.customer_id, order.location_id, None, None, order.contact_id, existing_location_id=order.location_id)
    if payload.technician_id is not None or (order.technician_id is None and current_user.role.name == ROLE_TECHNICIAN):
        _validate_technician(db, primary_technician_id, "elsődleges technikus")
    if payload.secondary_technician_id is not None:
        _validate_technician(db, secondary_technician_id, "második technikus")
    if primary_technician_id is not None and primary_technician_id == secondary_technician_id:
        raise HTTPException(status_code=400, detail="Ugyanaz a technikus nem választható ki kétszer")
    order.technician_id = primary_technician_id
    order.secondary_technician_id = secondary_technician_id
    if not was_already_closed:
        update_assets_after_maintenance_close(db, order, current_user)
    add_audit_log(db, current_user, "lezárás", "work_order", order.id, f"Munkalap lezárva: {order.number}")
    commit_with_optimistic_lock(db)
    order = base_query(db).filter(WorkOrder.id == order_id).first()
    return work_order_to_dict(order)


@router.delete("/{order_id}")
def cancel_work_order(
    order_id: int,
    version: int = Query(ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    order = db.get(WorkOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Munkalap nem található")
    require_current_version(order, version)
    order.status = "törölve / sztornózva"
    order.updated_at = datetime.utcnow()
    add_audit_log(db, current_user, "törlés", "work_order", order.id, f"Munkalap sztornózva: {order.number}")
    commit_with_optimistic_lock(db)
    return {"message": "Munkalap sztornózva", "version": order.version}
