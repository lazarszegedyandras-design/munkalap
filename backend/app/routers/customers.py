from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload
from ..database import get_db
from ..deps import RequireAdmin, RequireOfficeOrAdmin, get_current_user
from ..models import Asset, CrmActivity, CrmContract, CrmOpportunity, Customer, CustomerContact, Location, User, WorkOrder, WorkOrderAsset
from ..schemas import (
    BulkMaintenanceWorkOrdersResult,
    CustomerContactCreate,
    CustomerContactRead,
    CustomerContactUpdate,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    LocationCreate,
    LocationRead,
)
from ..services.asset_display import asset_display_name
from ..services.audit import add_asset_history, add_audit_log, snapshot_entity
from ..services.work_order_numbers import next_work_order_number

router = APIRouter(prefix="/customers", tags=["customers"])


def customer_options():
    return (
        selectinload(Customer.locations),
        selectinload(Customer.contacts).selectinload(CustomerContact.location),
    )


def validate_contact_payload(
    db: Session,
    customer_id: int,
    location_id: int | None,
    *,
    existing_location_id: int | None = None,
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Ügyfél nem található")
    if location_id is not None:
        location = db.get(Location, location_id)
        if not location:
            raise HTTPException(status_code=400, detail="Érvénytelen helyszín")
        if location.customer_id != customer_id:
            raise HTTPException(status_code=400, detail="A kapcsolattartó helyszíne nem a megadott ügyfélhez tartozik")
        if not location.is_active and location.id != existing_location_id:
            raise HTTPException(status_code=400, detail="Inaktív helyszín nem választható új kapcsolattartóhoz")
    return customer


def clear_primary_if_needed(db: Session, contact: CustomerContact):
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


@router.get("", response_model=list[CustomerRead])
def list_customers(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = db.query(Customer).options(*customer_options())
    if q:
        like = f"%{q}%"
        query = query.outerjoin(CustomerContact).filter(
            Customer.name.ilike(like)
            | Customer.company_code.ilike(like)
            | Customer.contact_person.ilike(like)
            | Customer.phone.ilike(like)
            | Customer.email.ilike(like)
            | Customer.address.ilike(like)
            | CustomerContact.name.ilike(like)
            | CustomerContact.phone.ilike(like)
            | CustomerContact.email.ilike(like)
            | CustomerContact.category.ilike(like)
        )
    return query.order_by(Customer.name).all()


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.flush()
    add_audit_log(db, current_user, "létrehozás", "customer", customer.id, f"Ügyfél létrehozva: {customer.name}")
    db.commit()
    customer = db.query(Customer).options(*customer_options()).filter(Customer.id == customer.id).first()
    return customer




def choose_bulk_maintenance_contact(customer: Customer, location_id: int | None) -> CustomerContact | None:
    contacts = list(customer.contacts or [])
    if not contacts:
        return None
    for category in ("Szerviz", "Sales", "Egyéb"):
        candidates = [contact for contact in contacts if contact.category == category]
        for contact in candidates:
            if contact.is_primary and contact.location_id == location_id:
                return contact
        for contact in candidates:
            if contact.is_primary and contact.location_id is None:
                return contact
        for contact in candidates:
            if contact.location_id == location_id:
                return contact
        for contact in candidates:
            if contact.location_id is None:
                return contact
    return contacts[0]


@router.post("/{customer_id}/maintenance-work-orders", response_model=BulkMaintenanceWorkOrdersResult)
def create_customer_maintenance_work_orders(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireOfficeOrAdmin),
):
    # A tranzakciós advisory lock megakadályozza, hogy két párhuzamos kattintás
    # ugyanahhoz az ügyfélhez duplikált nyitott karbantartási munkalapokat hozzon létre.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:namespace, :customer_id)"), {"namespace": 74121, "customer_id": customer_id})

    customer = (
        db.query(Customer)
        .options(*customer_options())
        .filter(Customer.id == customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Ügyfél nem található")

    assets = db.query(Asset).filter(Asset.customer_id == customer_id).order_by(Asset.id).all()
    if not assets:
        return BulkMaintenanceWorkOrdersResult(
            customer_id=customer_id,
            total_assets=0,
            created_count=0,
            skipped_count=0,
            created_work_order_ids=[],
            skipped_assets=[],
        )

    open_statuses = ["új", "ütemezve", "folyamatban", "várakozik", "kész"]
    existing_rows = (
        db.query(WorkOrderAsset.asset_id)
        .join(WorkOrder, WorkOrder.id == WorkOrderAsset.work_order_id)
        .filter(
            WorkOrder.customer_id == customer_id,
            WorkOrder.work_type == "karbantartás",
            WorkOrder.status.in_(open_statuses),
        )
        .all()
    )
    existing_asset_ids = {row[0] for row in existing_rows}

    created_ids: list[int] = []
    skipped_assets: list[dict] = []
    for asset in assets:
        display_name = asset_display_name(asset)
        if asset.id in existing_asset_ids:
            skipped_assets.append({
                "asset_id": asset.id,
                "display_name": display_name,
                "reason": "Már van nyitott karbantartási munkalap az eszközhöz.",
            })
            continue

        location_id = asset.current_location_id
        if location_id is not None:
            location = db.get(Location, location_id)
            if not location or location.customer_id != customer_id or not location.is_active:
                location_id = None
        contact = choose_bulk_maintenance_contact(customer, location_id)
        order = WorkOrder(
            number=next_work_order_number(db),
            customer_id=customer_id,
            location_id=location_id,
            contact_id=contact.id if contact else None,
            status="új",
            priority="normál",
            description="Tervezett karbantartás",
            work_type="karbantartás",
        )
        db.add(order)
        db.flush()
        db.add(WorkOrderAsset(work_order_id=order.id, asset_id=asset.id))
        add_asset_history(
            db,
            asset.id,
            current_user,
            "munkalaphoz kapcsolás",
            f"Kapcsolva a(z) {order.number} karbantartási munkalaphoz",
            order.id,
        )
        add_audit_log(
            db,
            current_user,
            "létrehozás",
            "work_order",
            order.id,
            f"Tömeges karbantartási munkalap létrehozva: {order.number} – {display_name}",
        )
        created_ids.append(order.id)

    add_audit_log(
        db,
        current_user,
        "tömeges létrehozás",
        "customer",
        customer.id,
        f"Karbantartási munkalapok: {len(created_ids)} létrehozva, {len(skipped_assets)} kihagyva",
    )
    db.commit()

    return BulkMaintenanceWorkOrdersResult(
        customer_id=customer_id,
        total_assets=len(assets),
        created_count=len(created_ids),
        skipped_count=len(skipped_assets),
        created_work_order_ids=created_ids,
        skipped_assets=skipped_assets,
    )


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    customer = db.query(Customer).options(*customer_options()).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Ügyfél nem található")
    return customer


@router.put("/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Ügyfél nem található")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    add_audit_log(db, current_user, "módosítás", "customer", customer.id, f"Ügyfél módosítva: {customer.name}")
    db.commit()
    customer = db.query(Customer).options(*customer_options()).filter(Customer.id == customer_id).first()
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Ügyfél nem található")
    related_assets = db.query(Asset).filter(Asset.customer_id == customer.id).count()
    related_orders = db.query(WorkOrder).filter(WorkOrder.customer_id == customer.id).count()
    related_crm = db.query(CrmOpportunity).filter(CrmOpportunity.customer_id == customer.id).count() + db.query(CrmActivity).filter(CrmActivity.customer_id == customer.id).count() + db.query(CrmContract).filter(CrmContract.customer_id == customer.id).count()
    if related_assets or related_orders or related_crm:
        raise HTTPException(status_code=400, detail="Az ügyfél nem törölhető, mert eszköz, munkalap vagy CRM előzmény kapcsolódik hozzá")
    add_audit_log(db, current_user, "törlés", "customer", customer.id, f"Ügyfél törölve: {customer.name}")
    db.delete(customer)
    db.commit()
    return None


@router.get("/{customer_id}/locations", response_model=list[LocationRead])
def list_customer_locations(customer_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Location).filter(Location.customer_id == customer_id).order_by(Location.name).all()


@router.post("/{customer_id}/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(customer_id: int, payload: LocationCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    if not db.get(Customer, customer_id):
        raise HTTPException(status_code=404, detail="Ügyfél nem található")
    location = Location(customer_id=customer_id, **payload.model_dump(exclude={"customer_id"}))
    db.add(location)
    db.flush()
    add_audit_log(db, current_user, "létrehozás", "location", location.id, f"Helyszín létrehozva: {location.name}")
    db.commit()
    db.refresh(location)
    return location


@router.get("/{customer_id}/contacts", response_model=list[CustomerContactRead])
def list_customer_contacts(customer_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if not db.get(Customer, customer_id):
        raise HTTPException(status_code=404, detail="Ügyfél nem található")
    return (
        db.query(CustomerContact)
        .options(selectinload(CustomerContact.location))
        .filter(CustomerContact.customer_id == customer_id)
        .order_by(CustomerContact.category, CustomerContact.name)
        .all()
    )


@router.post("/{customer_id}/contacts", response_model=CustomerContactRead, status_code=status.HTTP_201_CREATED)
def create_customer_contact(customer_id: int, payload: CustomerContactCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    validate_contact_payload(db, customer_id, payload.location_id)
    contact = CustomerContact(customer_id=customer_id, **payload.model_dump())
    db.add(contact)
    db.flush()
    clear_primary_if_needed(db, contact)
    add_audit_log(db, current_user, "létrehozás", "customer_contact", contact.id, f"Kapcsolattartó létrehozva: {contact.name} ({contact.category})")
    db.commit()
    contact = db.query(CustomerContact).options(selectinload(CustomerContact.location)).filter(CustomerContact.id == contact.id).first()
    return contact


@router.put("/{customer_id}/contacts/{contact_id}", response_model=CustomerContactRead)
def update_customer_contact(customer_id: int, contact_id: int, payload: CustomerContactUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    contact = db.query(CustomerContact).filter(CustomerContact.id == contact_id, CustomerContact.customer_id == customer_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Kapcsolattartó nem található")
    before = snapshot_entity(contact)
    data = payload.model_dump(exclude_unset=True)
    validate_contact_payload(
        db,
        customer_id,
        data.get("location_id", contact.location_id),
        existing_location_id=contact.location_id,
    )
    for field, value in data.items():
        setattr(contact, field, value)
    db.flush()
    clear_primary_if_needed(db, contact)
    add_audit_log(
        db,
        current_user,
        "módosítás",
        "customer_contact",
        contact.id,
        f"Kapcsolattartó módosítva: {contact.name} ({contact.category})",
        before=before,
        after=snapshot_entity(contact),
    )
    db.commit()
    contact = db.query(CustomerContact).options(selectinload(CustomerContact.location)).filter(CustomerContact.id == contact_id).first()
    return contact


@router.delete("/{customer_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_contact(customer_id: int, contact_id: int, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    contact = db.query(CustomerContact).filter(CustomerContact.id == contact_id, CustomerContact.customer_id == customer_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Kapcsolattartó nem található")
    related_orders = db.query(WorkOrder).filter(WorkOrder.contact_id == contact.id).count()
    related_crm = db.query(CrmOpportunity).filter(CrmOpportunity.contact_id == contact.id).count() + db.query(CrmActivity).filter(CrmActivity.contact_id == contact.id).count()
    if related_orders or related_crm:
        raise HTTPException(status_code=400, detail="A kapcsolattartó nem törölhető, mert munkalap vagy CRM előzmény kapcsolódik hozzá")
    add_audit_log(db, current_user, "törlés", "customer_contact", contact.id, f"Kapcsolattartó törölve: {contact.name} ({contact.category})")
    db.delete(contact)
    db.commit()
    return None
