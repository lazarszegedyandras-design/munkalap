from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import RequireOfficeOrAdmin, get_current_user
from ..models import Material, User, WorkOrderMaterial
from ..schemas import MaterialCreate, MaterialRead, MaterialUpdate
from ..services.audit import add_audit_log

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=list[MaterialRead])
def list_materials(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = db.query(Material)
    if q:
        like = f"%{q}%"
        query = query.filter(Material.sku.ilike(like) | Material.name.ilike(like))
    return query.order_by(Material.name).all()


@router.post("", response_model=MaterialRead, status_code=status.HTTP_201_CREATED)
def create_material(payload: MaterialCreate, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    if db.query(Material).filter(Material.sku == payload.sku).first():
        raise HTTPException(status_code=400, detail="Ezzel a cikkszámmal már van anyag")
    material = Material(**payload.model_dump())
    db.add(material)
    db.flush()
    add_audit_log(db, current_user, "létrehozás", "material", material.id, f"Anyag létrehozva: {material.sku}")
    db.commit()
    db.refresh(material)
    return material


@router.put("/{material_id}", response_model=MaterialRead)
def update_material(material_id: int, payload: MaterialUpdate, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Anyag nem található")
    data = payload.model_dump(exclude_unset=True)
    if "sku" in data and data["sku"] != material.sku and db.query(Material).filter(Material.sku == data["sku"]).first():
        raise HTTPException(status_code=400, detail="Ezzel a cikkszámmal már van anyag")
    for field, value in data.items():
        setattr(material, field, value)
    add_audit_log(db, current_user, "módosítás", "material", material.id, f"Anyag módosítva: {material.sku}")
    db.commit()
    db.refresh(material)
    return material


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(material_id: int, db: Session = Depends(get_db), current_user: User = Depends(RequireOfficeOrAdmin)):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Anyag nem található")
    if db.query(WorkOrderMaterial).filter(WorkOrderMaterial.material_id == material.id).count():
        raise HTTPException(status_code=400, detail="Az anyag nem törölhető, mert munkalaphoz kapcsolódik")
    add_audit_log(db, current_user, "törlés", "material", material.id, f"Anyag törölve: {material.sku}")
    db.delete(material)
    db.commit()
    return None
