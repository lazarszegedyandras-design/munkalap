from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from ..access_control import PERMISSION_CRM_ACCESS
from ..database import get_db
from ..deps import RequireCrmContractManage, RequireCrmWrite, get_current_user
from ..models import (
    Asset,
    CrmActivity,
    CrmContract,
    CrmContractArchive,
    CrmContractAsset,
    CrmContractLocation,
    CrmContractServiceLine,
    CrmOpportunity,
    Customer,
    CustomerContact,
    Location,
    ROLE_ADMIN,
    User,
    WorkOrder,
)
from ..schemas import (
    CrmActivityCreate,
    CrmActivityOpportunityCreate,
    CrmActivityRead,
    CrmActivityUpdate,
    CrmAssetSummary,
    CrmContractArchiveRead,
    CrmContractCreate,
    CrmContractRead,
    CrmContractUpdate,
    CrmCustomerDetail,
    CrmCustomerSummary,
    CrmDashboardRead,
    CrmOpportunityCreate,
    CrmOpportunityRead,
    CrmOpportunityUpdate,
    CrmUserSummary,
    CrmWorkOrderSummary,
    CustomerContactCreate,
    CustomerContactRead,
    CustomerContactUpdate,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
)
from ..config import get_settings
from ..deps import RequireAdmin
from ..services.audit import add_audit_log, snapshot_entity
from ..services.contract_archive_numbers import next_contract_archive_number
from ..services.contract_archive_storage import contract_archive_path, delete_contract_archive_file, finalize_contract_archive_deletion, rollback_contract_archive_deletion, stage_contract_archive_deletion, store_contract_pdf

router = APIRouter(prefix="/crm", tags=["crm"])
OPEN_STAGES = ("új", "kapcsolatfelvétel", "igényfelmérés", "ajánlat", "tárgyalás")
ALL_STAGES = (*OPEN_STAGES, "nyert", "elvesztett")


def _customer_options():
    return (
        selectinload(Customer.locations),
        selectinload(Customer.contacts).selectinload(CustomerContact.location),
    )


def _opportunity_options():
    return (
        joinedload(CrmOpportunity.customer),
        joinedload(CrmOpportunity.contact),
        joinedload(CrmOpportunity.owner).joinedload(User.role),
    )


def _activity_options():
    return (
        joinedload(CrmActivity.customer),
        joinedload(CrmActivity.contact),
        joinedload(CrmActivity.opportunity),
        joinedload(CrmActivity.work_order),
        joinedload(CrmActivity.owner).joinedload(User.role),
    )


def _contract_options():
    return (
        joinedload(CrmContract.customer),
        selectinload(CrmContract.location_links).joinedload(CrmContractLocation.location),
        selectinload(CrmContract.asset_links).joinedload(CrmContractAsset.asset),
        selectinload(CrmContract.service_lines),
    )


def _get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Ügyfél nem található")
    return customer


def _validate_contact(db: Session, customer_id: int, contact_id: int | None) -> CustomerContact | None:
    if contact_id is None:
        return None
    contact = db.get(CustomerContact, contact_id)
    if not contact or contact.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="A kapcsolattartó nem a megadott ügyfélhez tartozik")
    return contact


def _validate_location(
    db: Session,
    customer_id: int,
    location_id: int | None,
    *,
    existing_location_id: int | None = None,
) -> Location | None:
    if location_id is None:
        return None
    location = db.get(Location, location_id)
    if not location or location.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="A helyszín nem a megadott ügyfélhez tartozik")
    if not location.is_active and location.id != existing_location_id:
        raise HTTPException(status_code=400, detail="Inaktív helyszín nem választható új CRM-kapcsolathoz")
    return location


def _validate_owner(db: Session, owner_user_id: int | None) -> User | None:
    if owner_user_id is None:
        return None
    owner = db.query(User).options(joinedload(User.role), selectinload(User.permission_links)).filter(User.id == owner_user_id).first()
    if not owner or not owner.is_active:
        raise HTTPException(status_code=400, detail="A CRM-felelős nem aktív felhasználó")
    if owner.role.name != ROLE_ADMIN and PERMISSION_CRM_ACCESS not in owner.permissions:
        raise HTTPException(status_code=400, detail="A CRM-felelősnek CRM modul-hozzáféréssel kell rendelkeznie")
    return owner


def _validate_opportunity(db: Session, customer_id: int, opportunity_id: int | None) -> CrmOpportunity | None:
    if opportunity_id is None:
        return None
    opportunity = db.get(CrmOpportunity, opportunity_id)
    if not opportunity or opportunity.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="A lehetőség nem a megadott ügyfélhez tartozik")
    return opportunity


def _validate_work_order(db: Session, customer_id: int, work_order_id: int | None) -> WorkOrder | None:
    if work_order_id is None:
        return None
    work_order = db.get(WorkOrder, work_order_id)
    if not work_order or work_order.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="A munkalap nem a megadott ügyfélhez tartozik")
    return work_order


def _validate_contract_scope(
    db: Session,
    customer_id: int,
    location_ids: list[int],
    asset_ids: list[int],
    *,
    existing_location_ids: set[int] | None = None,
) -> None:
    existing_location_ids = existing_location_ids or set()
    for location_id in sorted(set(location_ids or [])):
        location = db.get(Location, location_id)
        if not location or location.customer_id != customer_id:
            raise HTTPException(status_code=400, detail=f"A(z) {location_id} telephely nem a szerződés ügyfeléhez tartozik")
        if not location.is_active and location.id not in existing_location_ids:
            raise HTTPException(status_code=400, detail=f"A(z) {location_id} telephely inaktív, új szerződéshez nem választható")
    for asset_id in sorted(set(asset_ids or [])):
        asset = db.get(Asset, asset_id)
        if not asset or asset.customer_id != customer_id:
            raise HTTPException(status_code=400, detail=f"A(z) {asset_id} eszköz nem a szerződés ügyfeléhez tartozik")


def _set_contract_scope(contract: CrmContract, location_ids: list[int], asset_ids: list[int]) -> None:
    contract.location_links.clear()
    contract.asset_links.clear()
    for location_id in sorted(set(location_ids or [])):
        contract.location_links.append(CrmContractLocation(location_id=location_id))
    for asset_id in sorted(set(asset_ids or [])):
        contract.asset_links.append(CrmContractAsset(asset_id=asset_id))


def _set_contract_service_lines(contract: CrmContract, rows: list[dict] | None) -> None:
    if rows is None:
        return
    contract.service_lines.clear()
    for index, row in enumerate(rows):
        cleaned = {key: value for key, value in row.items() if value not in (None, "")}
        contract.service_lines.append(CrmContractServiceLine(sort_order=index, **cleaned))


def _archive_to_dict(row: CrmContractArchive) -> dict:
    return {
        "id": row.id, "archive_number": row.archive_number, "contract_id": row.contract_id,
        "note": row.note, "original_filename": row.original_filename, "mime_type": row.mime_type,
        "size_bytes": row.size_bytes, "sha256": row.sha256, "uploaded_by_user_id": row.uploaded_by_user_id,
        "uploaded_by_name": row.uploaded_by.full_name if row.uploaded_by else None, "created_at": row.created_at,
    }


class ContractArchiveDeleteConfirmation(BaseModel):
    confirmation: str


def _get_contract(db: Session, contract_id: int) -> CrmContract:
    contract = db.query(CrmContract).options(*_contract_options()).filter(CrmContract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Szerződés nem található")
    return contract


def _clear_primary_contact(db: Session, contact: CustomerContact) -> None:
    if not contact.is_primary:
        return
    query = db.query(CustomerContact).filter(
        CustomerContact.customer_id == contact.customer_id,
        CustomerContact.category == contact.category,
        CustomerContact.id != contact.id,
    )
    if contact.location_id is None:
        query = query.filter(CustomerContact.location_id.is_(None))
    else:
        query = query.filter(CustomerContact.location_id == contact.location_id)
    query.update({CustomerContact.is_primary: False}, synchronize_session=False)


def _customer_summary(db: Session, customer: Customer) -> CrmCustomerSummary:
    open_count, pipeline_value = db.query(
        func.count(CrmOpportunity.id),
        func.coalesce(func.sum(CrmOpportunity.estimated_value), 0),
    ).filter(CrmOpportunity.customer_id == customer.id, CrmOpportunity.stage.in_(OPEN_STAGES)).one()
    last_activity = db.query(func.max(CrmActivity.created_at)).filter(CrmActivity.customer_id == customer.id).scalar()
    return CrmCustomerSummary(
        id=customer.id,
        name=customer.name,
        company_code=customer.company_code,
        email=customer.email,
        phone=customer.phone,
        contact_count=db.query(func.count(CustomerContact.id)).filter(CustomerContact.customer_id == customer.id).scalar() or 0,
        location_count=db.query(func.count(Location.id)).filter(Location.customer_id == customer.id).scalar() or 0,
        asset_count=db.query(func.count(Asset.id)).filter(Asset.customer_id == customer.id).scalar() or 0,
        work_order_count=db.query(func.count(WorkOrder.id)).filter(WorkOrder.customer_id == customer.id).scalar() or 0,
        open_opportunity_count=open_count or 0,
        open_pipeline_value=Decimal(pipeline_value or 0),
        last_activity_at=last_activity,
    )


@router.get("/dashboard", response_model=CrmDashboardRead)
def dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    open_count, pipeline_value = db.query(
        func.count(CrmOpportunity.id),
        func.coalesce(func.sum(CrmOpportunity.estimated_value), 0),
    ).filter(CrmOpportunity.stage.in_(OPEN_STAGES)).one()
    stage_rows = db.query(CrmOpportunity.stage, func.count(CrmOpportunity.id)).group_by(CrmOpportunity.stage).all()
    by_stage = {stage: 0 for stage in ALL_STAGES}
    by_stage.update({stage: count for stage, count in stage_rows})
    overdue = db.query(func.count(CrmActivity.id)).filter(
        CrmActivity.completed_at.is_(None),
        CrmActivity.due_at.is_not(None),
        CrmActivity.due_at <= datetime.utcnow(),
    ).scalar() or 0
    recent_opportunities = db.query(CrmOpportunity).options(*_opportunity_options()).order_by(CrmOpportunity.updated_at.desc()).limit(8).all()
    recent_activities = db.query(CrmActivity).options(*_activity_options()).order_by(CrmActivity.created_at.desc()).limit(10).all()
    today = date.today()
    active_contracts = db.query(func.count(CrmContract.id)).filter(CrmContract.status == "aktív").scalar() or 0
    expiring_contracts = db.query(func.count(CrmContract.id)).filter(
        CrmContract.status == "aktív",
        CrmContract.end_date.is_not(None),
        CrmContract.end_date >= today,
        CrmContract.end_date <= today + timedelta(days=60),
    ).scalar() or 0
    return CrmDashboardRead(
        customer_count=db.query(func.count(Customer.id)).scalar() or 0,
        open_opportunity_count=open_count or 0,
        open_pipeline_value=Decimal(pipeline_value or 0),
        overdue_activity_count=overdue,
        active_contract_count=active_contracts,
        expiring_contract_count=expiring_contracts,
        opportunities_by_stage=by_stage,
        recent_opportunities=recent_opportunities,
        recent_activities=recent_activities,
    )


@router.get("/users", response_model=list[CrmUserSummary])
def list_crm_users(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    users = db.query(User).options(joinedload(User.role), selectinload(User.permission_links)).filter(User.is_active.is_(True)).order_by(User.full_name).all()
    return [CrmUserSummary(id=user.id, full_name=user.full_name, email=user.email) for user in users if user.role.name == ROLE_ADMIN or PERMISSION_CRM_ACCESS in user.permissions]


@router.get("/customers", response_model=list[CrmCustomerSummary])
def list_customers(
    q: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Customer)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Customer.name.ilike(like), Customer.company_code.ilike(like), Customer.email.ilike(like)))
    customers = query.order_by(Customer.name).all()
    return [_customer_summary(db, customer) for customer in customers]


@router.post("/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmWrite)):
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.flush()
    after = snapshot_entity(customer)
    add_audit_log(db, current_user, "CRM_CUSTOMER_CREATED", "customer", customer.id, f"CRM ügyfél létrehozva: {customer.name}", after=after)
    db.commit()
    return db.query(Customer).options(*_customer_options()).filter(Customer.id == customer.id).one()


@router.put("/customers/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmWrite)):
    customer = _get_customer(db, customer_id)
    before = snapshot_entity(customer)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    after = snapshot_entity(customer)
    add_audit_log(db, current_user, "CRM_CUSTOMER_UPDATED", "customer", customer.id, f"CRM ügyfél módosítva: {customer.name}", before=before, after=after)
    db.commit()
    return db.query(Customer).options(*_customer_options()).filter(Customer.id == customer.id).one()


@router.post("/customers/{customer_id}/contacts", response_model=CustomerContactRead, status_code=status.HTTP_201_CREATED)
def create_contact(customer_id: int, payload: CustomerContactCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmWrite)):
    _get_customer(db, customer_id)
    _validate_location(db, customer_id, payload.location_id)
    contact = CustomerContact(customer_id=customer_id, **payload.model_dump())
    db.add(contact)
    db.flush()
    _clear_primary_contact(db, contact)
    after = snapshot_entity(contact)
    add_audit_log(db, current_user, "CRM_CONTACT_CREATED", "customer_contact", contact.id, f"CRM kapcsolattartó létrehozva: {contact.name}", after=after)
    db.commit()
    return db.query(CustomerContact).options(joinedload(CustomerContact.location)).filter(CustomerContact.id == contact.id).one()


@router.put("/customers/{customer_id}/contacts/{contact_id}", response_model=CustomerContactRead)
def update_contact(customer_id: int, contact_id: int, payload: CustomerContactUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmWrite)):
    contact = _validate_contact(db, customer_id, contact_id)
    assert contact is not None
    data = payload.model_dump(exclude_unset=True)
    if "location_id" in data:
        _validate_location(db, customer_id, data["location_id"], existing_location_id=contact.location_id)
    before = snapshot_entity(contact)
    for field, value in data.items():
        setattr(contact, field, value)
    db.flush()
    _clear_primary_contact(db, contact)
    after = snapshot_entity(contact)
    add_audit_log(db, current_user, "CRM_CONTACT_UPDATED", "customer_contact", contact.id, f"CRM kapcsolattartó módosítva: {contact.name}", before=before, after=after)
    db.commit()
    return db.query(CustomerContact).options(joinedload(CustomerContact.location)).filter(CustomerContact.id == contact.id).one()


@router.get("/customers/{customer_id}", response_model=CrmCustomerDetail)
def customer_detail(customer_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    customer = db.query(Customer).options(*_customer_options()).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Ügyfél nem található")
    assets = db.query(Asset).filter(Asset.customer_id == customer_id).order_by(Asset.internal_id).all()
    work_orders = db.query(WorkOrder).filter(WorkOrder.customer_id == customer_id).order_by(WorkOrder.created_at.desc()).limit(25).all()
    opportunities = db.query(CrmOpportunity).options(*_opportunity_options()).filter(CrmOpportunity.customer_id == customer_id).order_by(CrmOpportunity.updated_at.desc()).all()
    activities = db.query(CrmActivity).options(*_activity_options()).filter(CrmActivity.customer_id == customer_id).order_by(CrmActivity.created_at.desc()).limit(50).all()
    contracts = db.query(CrmContract).options(*_contract_options()).filter(CrmContract.customer_id == customer_id).order_by(CrmContract.end_date.desc(), CrmContract.id.desc()).all()
    return CrmCustomerDetail(
        customer=CustomerRead.model_validate(customer),
        summary=_customer_summary(db, customer),
        assets=[CrmAssetSummary.model_validate(asset, from_attributes=True) for asset in assets],
        work_orders=[CrmWorkOrderSummary.model_validate(order, from_attributes=True) for order in work_orders],
        opportunities=opportunities,
        activities=activities,
        contracts=contracts,
    )


@router.get("/contracts", response_model=list[CrmContractRead])
def list_contracts(
    customer_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    company_code: str | None = Query(default=None, pattern="^(DRH|SP|GXR)$"),
    q: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(CrmContract).options(*_contract_options())
    if customer_id is not None:
        query = query.filter(CrmContract.customer_id == customer_id)
    if status_filter:
        query = query.filter(CrmContract.status == status_filter)
    if company_code:
        query = query.filter(CrmContract.company_code == company_code)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(CrmContract.contract_number.ilike(like), CrmContract.contract_type.ilike(like), CrmContract.subject.ilike(like), CrmContract.billing_model.ilike(like)))
    return query.order_by(CrmContract.end_date.desc(), CrmContract.id.desc()).all()


@router.get("/contracts/{contract_id}", response_model=CrmContractRead)
def get_contract(contract_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get_contract(db, contract_id)


@router.post("/contracts", response_model=CrmContractRead, status_code=status.HTTP_201_CREATED)
def create_contract(payload: CrmContractCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmContractManage)):
    _get_customer(db, payload.customer_id)
    if payload.start_date and payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="A szerződés vége nem lehet korábbi a kezdeténél")
    _validate_contract_scope(db, payload.customer_id, payload.location_ids, payload.asset_ids)
    data = payload.model_dump(exclude={"location_ids", "asset_ids", "service_lines"})
    contract = CrmContract(**data)
    db.add(contract)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A szerződésszám már létezik") from exc
    _set_contract_scope(contract, payload.location_ids, payload.asset_ids)
    _set_contract_service_lines(contract, [row.model_dump() for row in payload.service_lines])
    db.flush()
    after = snapshot_entity(contract)
    after["location_ids"] = contract.location_ids
    after["asset_ids"] = contract.asset_ids
    after["service_lines"] = [snapshot_entity(row) for row in contract.service_lines]
    add_audit_log(db, current_user, "CRM_CONTRACT_CREATED", "crm_contract", contract.id, f"CRM szerződés létrehozva: {contract.contract_number}", entity_display_id=contract.contract_number, after=after)
    db.commit()
    return _get_contract(db, contract.id)


@router.put("/contracts/{contract_id}", response_model=CrmContractRead)
def update_contract(contract_id: int, payload: CrmContractUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmContractManage)):
    contract = _get_contract(db, contract_id)
    if contract.version != payload.version:
        raise HTTPException(status_code=409, detail="A szerződést időközben más módosította. Frissítsd az adatokat.")
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    location_ids = data.pop("location_ids", None)
    asset_ids = data.pop("asset_ids", None)
    service_lines = data.pop("service_lines", None)
    customer_id = data.get("customer_id", contract.customer_id)
    _get_customer(db, customer_id)
    start_date = data.get("start_date", contract.start_date)
    end_date = data.get("end_date", contract.end_date)
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="A szerződés vége nem lehet korábbi a kezdeténél")
    next_locations = contract.location_ids if location_ids is None else location_ids
    next_assets = contract.asset_ids if asset_ids is None else asset_ids
    _validate_contract_scope(
        db,
        customer_id,
        next_locations,
        next_assets,
        existing_location_ids=set(contract.location_ids) if customer_id == contract.customer_id else set(),
    )
    if customer_id != contract.customer_id and contract.work_orders:
        raise HTTPException(status_code=409, detail="Munkalaphoz kapcsolt szerződés ügyfele nem módosítható")
    before = snapshot_entity(contract)
    before["location_ids"] = contract.location_ids
    before["asset_ids"] = contract.asset_ids
    before["service_lines"] = [snapshot_entity(row) for row in contract.service_lines]
    for field, value in data.items():
        setattr(contract, field, value)
    if location_ids is not None or asset_ids is not None:
        _set_contract_scope(contract, next_locations, next_assets)
    _set_contract_service_lines(contract, service_lines)
    contract.version += 1
    contract.updated_at = datetime.utcnow()
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A szerződésszám már létezik") from exc
    after = snapshot_entity(contract)
    after["location_ids"] = contract.location_ids
    after["asset_ids"] = contract.asset_ids
    after["service_lines"] = [snapshot_entity(row) for row in contract.service_lines]
    add_audit_log(db, current_user, "CRM_CONTRACT_UPDATED", "crm_contract", contract.id, f"CRM szerződés módosítva: {contract.contract_number}", entity_display_id=contract.contract_number, before=before, after=after)
    db.commit()
    return _get_contract(db, contract.id)


@router.get("/contracts/{contract_id}/archives", response_model=list[CrmContractArchiveRead])
def list_contract_archives(contract_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    _get_contract(db, contract_id)
    rows = db.query(CrmContractArchive).options(joinedload(CrmContractArchive.uploaded_by)).filter(CrmContractArchive.contract_id == contract_id).order_by(CrmContractArchive.created_at.desc()).all()
    return [_archive_to_dict(row) for row in rows]


@router.post("/contracts/{contract_id}/archives", response_model=CrmContractArchiveRead, status_code=status.HTTP_201_CREATED)
async def upload_contract_archive(
    contract_id: int,
    archive_file: UploadFile = File(...),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireCrmContractManage),
):
    contract = _get_contract(db, contract_id)
    stored = await store_contract_pdf(archive_file, get_settings())
    row = CrmContractArchive(
        archive_number=next_contract_archive_number(db), contract_id=contract.id,
        note=(note or "").strip() or None, original_filename=stored.original_filename,
        storage_key=stored.storage_key, mime_type=stored.mime_type, size_bytes=stored.size_bytes,
        sha256=stored.sha256, uploaded_by_user_id=current_user.id,
    )
    try:
        db.add(row); db.flush()
        add_audit_log(db, current_user, "CRM_CONTRACT_ARCHIVE_UPLOADED", "crm_contract_archive", row.id, f"Szerződés PDF archiválva: {contract.contract_number} · {stored.original_filename}", entity_display_id=row.archive_number)
        db.commit()
    except Exception:
        db.rollback(); delete_contract_archive_file(get_settings(), stored.storage_key); raise
    row = db.query(CrmContractArchive).options(joinedload(CrmContractArchive.uploaded_by)).filter(CrmContractArchive.id == row.id).one()
    return _archive_to_dict(row)


def _get_contract_archive(db: Session, archive_id: int) -> CrmContractArchive:
    row = db.query(CrmContractArchive).options(joinedload(CrmContractArchive.uploaded_by), joinedload(CrmContractArchive.contract)).filter(CrmContractArchive.id == archive_id).first()
    if not row: raise HTTPException(status_code=404, detail="Szerződés-archívum nem található")
    return row


@router.get("/contract-archives/{archive_id}/preview")
def preview_contract_archive(archive_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = _get_contract_archive(db, archive_id); path = contract_archive_path(get_settings(), row.storage_key)
    if not path.is_file(): raise HTTPException(status_code=404, detail="Az archivált PDF hiányzik a tárhelyről")
    add_audit_log(db, current_user, "CRM_CONTRACT_ARCHIVE_PREVIEWED", "crm_contract_archive", row.id, f"Szerződés PDF előnézet: {row.archive_number}", entity_display_id=row.archive_number); db.commit()
    return FileResponse(path=path, media_type="application/pdf", filename=row.original_filename, content_disposition_type="inline", headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


@router.get("/contract-archives/{archive_id}/download")
def download_contract_archive(archive_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = _get_contract_archive(db, archive_id); path = contract_archive_path(get_settings(), row.storage_key)
    if not path.is_file(): raise HTTPException(status_code=404, detail="Az archivált PDF hiányzik a tárhelyről")
    add_audit_log(db, current_user, "CRM_CONTRACT_ARCHIVE_DOWNLOADED", "crm_contract_archive", row.id, f"Szerződés PDF letöltve: {row.archive_number}", entity_display_id=row.archive_number); db.commit()
    return FileResponse(path=path, media_type="application/pdf", filename=row.original_filename, headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


@router.delete("/contract-archives/{archive_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract_archive(archive_id: int, payload: ContractArchiveDeleteConfirmation, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    if payload.confirmation.strip() != "TÖRÖL": raise HTTPException(status_code=400, detail="A törléshez pontosan a TÖRÖL szót kell megadni")
    row = _get_contract_archive(db, archive_id); staged = None
    try: staged = stage_contract_archive_deletion(get_settings(), row.storage_key)
    except OSError as exc: raise HTTPException(status_code=500, detail="Az archív PDF nem helyezhető törlésre") from exc
    try:
        add_audit_log(db, current_user, "CRM_CONTRACT_ARCHIVE_DELETED", "crm_contract_archive", row.id, f"Szerződés PDF törölve: {row.archive_number} · {row.original_filename}", entity_display_id=row.archive_number)
        db.delete(row); db.commit()
    except Exception:
        db.rollback()
        try: rollback_contract_archive_deletion(staged)
        except OSError: pass
        raise
    try: finalize_contract_archive_deletion(staged)
    except OSError: pass
    return None


@router.get("/opportunities", response_model=list[CrmOpportunityRead])
def list_opportunities(
    customer_id: int | None = None,
    stage: str | None = None,
    owner_user_id: int | None = None,
    q: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(CrmOpportunity).options(*_opportunity_options())
    if customer_id is not None:
        query = query.filter(CrmOpportunity.customer_id == customer_id)
    if stage:
        query = query.filter(CrmOpportunity.stage == stage)
    if owner_user_id is not None:
        query = query.filter(CrmOpportunity.owner_user_id == owner_user_id)
    if q:
        query = query.filter(CrmOpportunity.title.ilike(f"%{q.strip()}%"))
    return query.order_by(CrmOpportunity.updated_at.desc()).all()


@router.post("/opportunities", response_model=CrmOpportunityRead, status_code=status.HTTP_201_CREATED)
def create_opportunity(payload: CrmOpportunityCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmWrite)):
    _get_customer(db, payload.customer_id)
    _validate_contact(db, payload.customer_id, payload.contact_id)
    owner_id = payload.owner_user_id if payload.owner_user_id is not None else current_user.id
    _validate_owner(db, owner_id)
    data = payload.model_dump()
    data["owner_user_id"] = owner_id
    opportunity = CrmOpportunity(**data)
    db.add(opportunity)
    db.flush()
    after = snapshot_entity(opportunity)
    add_audit_log(db, current_user, "CRM_OPPORTUNITY_CREATED", "crm_opportunity", opportunity.id, f"CRM lehetőség létrehozva: {opportunity.title}", entity_display_id=opportunity.title, after=after)
    db.commit()
    return db.query(CrmOpportunity).options(*_opportunity_options()).filter(CrmOpportunity.id == opportunity.id).one()


@router.put("/opportunities/{opportunity_id}", response_model=CrmOpportunityRead)
def update_opportunity(opportunity_id: int, payload: CrmOpportunityUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmWrite)):
    opportunity = db.get(CrmOpportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Lehetőség nem található")
    if opportunity.version != payload.version:
        raise HTTPException(status_code=409, detail="A lehetőséget időközben más módosította. Frissítsd az adatokat.")
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    customer_id = data.get("customer_id", opportunity.customer_id)
    _get_customer(db, customer_id)
    contact_id = data.get("contact_id", opportunity.contact_id)
    _validate_contact(db, customer_id, contact_id)
    if "owner_user_id" in data:
        _validate_owner(db, data["owner_user_id"])
    before = snapshot_entity(opportunity)
    for field, value in data.items():
        setattr(opportunity, field, value)
    opportunity.version += 1
    opportunity.updated_at = datetime.utcnow()
    after = snapshot_entity(opportunity)
    add_audit_log(db, current_user, "CRM_OPPORTUNITY_UPDATED", "crm_opportunity", opportunity.id, f"CRM lehetőség módosítva: {opportunity.title}", entity_display_id=opportunity.title, before=before, after=after)
    db.commit()
    return db.query(CrmOpportunity).options(*_opportunity_options()).filter(CrmOpportunity.id == opportunity.id).one()


@router.get("/activities", response_model=list[CrmActivityRead])
def list_activities(
    customer_id: int | None = None,
    opportunity_id: int | None = None,
    owner_user_id: int | None = None,
    open_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(CrmActivity).options(*_activity_options())
    if customer_id is not None:
        query = query.filter(CrmActivity.customer_id == customer_id)
    if opportunity_id is not None:
        query = query.filter(CrmActivity.opportunity_id == opportunity_id)
    if owner_user_id is not None:
        query = query.filter(CrmActivity.owner_user_id == owner_user_id)
    if open_only:
        query = query.filter(CrmActivity.completed_at.is_(None))
    return query.order_by(CrmActivity.created_at.desc()).all()


@router.post("/activities", response_model=CrmActivityRead, status_code=status.HTTP_201_CREATED)
def create_activity(payload: CrmActivityCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmWrite)):
    _get_customer(db, payload.customer_id)
    _validate_contact(db, payload.customer_id, payload.contact_id)
    _validate_opportunity(db, payload.customer_id, payload.opportunity_id)
    _validate_work_order(db, payload.customer_id, payload.work_order_id)
    owner_id = payload.owner_user_id if payload.owner_user_id is not None else current_user.id
    _validate_owner(db, owner_id)
    data = payload.model_dump()
    data["owner_user_id"] = owner_id
    activity = CrmActivity(**data)
    db.add(activity)
    db.flush()
    after = snapshot_entity(activity)
    add_audit_log(db, current_user, "CRM_ACTIVITY_CREATED", "crm_activity", activity.id, f"CRM aktivitás létrehozva: {activity.subject}", entity_display_id=activity.subject, after=after)
    db.commit()
    return db.query(CrmActivity).options(*_activity_options()).filter(CrmActivity.id == activity.id).one()


@router.post(
    "/activities/{activity_id}/opportunity",
    response_model=CrmOpportunityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_opportunity_from_activity(
    activity_id: int,
    payload: CrmActivityOpportunityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireCrmWrite),
):
    # PostgreSQL alatt a sorzár megakadályozza, hogy két párhuzamos kattintás
    # ugyanabból az aktivitásból két külön lehetőséget hozzon létre.
    activity = (
        db.query(CrmActivity)
        .filter(CrmActivity.id == activity_id)
        .with_for_update()
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Aktivitás nem található")
    if activity.version != payload.version:
        raise HTTPException(status_code=409, detail="Az aktivitást időközben más módosította. Frissítsd az adatokat.")
    if activity.opportunity_id is not None:
        raise HTTPException(status_code=409, detail="Az aktivitás már kapcsolódik egy lehetőséghez")

    _get_customer(db, activity.customer_id)
    _validate_contact(db, activity.customer_id, activity.contact_id)
    owner_id = activity.owner_user_id if activity.owner_user_id is not None else current_user.id
    _validate_owner(db, owner_id)

    activity_before = snapshot_entity(activity)
    opportunity = CrmOpportunity(
        customer_id=activity.customer_id,
        contact_id=activity.contact_id,
        owner_user_id=owner_id,
        title=activity.subject,
        stage="új",
        currency="HUF",
        source=f"CRM aktivitás #{activity.id}",
        next_step=(activity.description or "")[:4000] or None,
    )
    db.add(opportunity)
    db.flush()

    activity.opportunity_id = opportunity.id
    activity.version += 1
    activity.updated_at = datetime.utcnow()
    add_audit_log(
        db,
        current_user,
        "CRM_OPPORTUNITY_CREATED_FROM_ACTIVITY",
        "crm_opportunity",
        opportunity.id,
        f"CRM lehetőség létrehozva aktivitásból: {opportunity.title}",
        entity_display_id=opportunity.title,
        after=snapshot_entity(opportunity),
    )
    add_audit_log(
        db,
        current_user,
        "CRM_ACTIVITY_LINKED_TO_OPPORTUNITY",
        "crm_activity",
        activity.id,
        f"CRM aktivitás lehetőséghez kapcsolva: {opportunity.title}",
        entity_display_id=activity.subject,
        before=activity_before,
        after=snapshot_entity(activity),
    )
    db.commit()
    return (
        db.query(CrmOpportunity)
        .options(*_opportunity_options())
        .filter(CrmOpportunity.id == opportunity.id)
        .one()
    )


@router.put("/activities/{activity_id}", response_model=CrmActivityRead)
def update_activity(activity_id: int, payload: CrmActivityUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireCrmWrite)):
    activity = db.get(CrmActivity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Aktivitás nem található")
    if activity.version != payload.version:
        raise HTTPException(status_code=409, detail="Az aktivitást időközben más módosította. Frissítsd az adatokat.")
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    customer_id = data.get("customer_id", activity.customer_id)
    _get_customer(db, customer_id)
    _validate_contact(db, customer_id, data.get("contact_id", activity.contact_id))
    _validate_opportunity(db, customer_id, data.get("opportunity_id", activity.opportunity_id))
    _validate_work_order(db, customer_id, data.get("work_order_id", activity.work_order_id))
    if "owner_user_id" in data:
        _validate_owner(db, data["owner_user_id"])
    before = snapshot_entity(activity)
    for field, value in data.items():
        setattr(activity, field, value)
    activity.version += 1
    activity.updated_at = datetime.utcnow()
    after = snapshot_entity(activity)
    add_audit_log(db, current_user, "CRM_ACTIVITY_UPDATED", "crm_activity", activity.id, f"CRM aktivitás módosítva: {activity.subject}", entity_display_id=activity.subject, before=before, after=after)
    db.commit()
    return db.query(CrmActivity).options(*_activity_options()).filter(CrmActivity.id == activity.id).one()
