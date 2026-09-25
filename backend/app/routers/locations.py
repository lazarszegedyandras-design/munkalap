from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import RequireAdmin, get_current_user
from ..models import Asset, CrmContractLocation, CustomerContact, Location, User, WorkOrder
from ..schemas import LocationRead, LocationUpdate
from ..services.audit import add_audit_log, snapshot_entity

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationRead])
def list_locations(customer_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = db.query(Location)
    if customer_id:
        query = query.filter(Location.customer_id == customer_id)
    return query.order_by(Location.name).all()


@router.put("/{location_id}", response_model=LocationRead)
def update_location(location_id: int, payload: LocationUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Helyszín nem található")
    before = snapshot_entity(location)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(location, field, value)
    action = "módosítás"
    message = f"Helyszín módosítva: {location.name}"
    if "is_active" in data and data["is_active"] != before.get("is_active"):
        action = "aktiválás" if location.is_active else "inaktiválás"
        message = f"Helyszín {'aktiválva' if location.is_active else 'inaktiválva'}: {location.name}"
    add_audit_log(
        db,
        current_user,
        action,
        "location",
        location.id,
        message,
        before=before,
        after=snapshot_entity(location),
    )
    db.commit()
    db.refresh(location)
    return location


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(location_id: int, db: Session = Depends(get_db), current_user: User = Depends(RequireAdmin)):
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Helyszín nem található")
    related_assets = db.query(Asset).filter(Asset.current_location_id == location.id).count()
    related_orders = db.query(WorkOrder).filter(WorkOrder.location_id == location.id).count()
    related_contacts = db.query(CustomerContact).filter(CustomerContact.location_id == location.id).count()
    related_contracts = db.query(CrmContractLocation).filter(CrmContractLocation.location_id == location.id).count()
    if related_assets or related_orders or related_contacts or related_contracts:
        raise HTTPException(
            status_code=400,
            detail="A helyszín nem törölhető, mert eszköz, munkalap, kapcsolattartó vagy CRM szerződés kapcsolódik hozzá",
        )
    add_audit_log(db, current_user, "törlés", "location", location.id, f"Helyszín törölve: {location.name}")
    db.delete(location)
    db.commit()
    return None
