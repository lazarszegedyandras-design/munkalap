from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import RequireAdmin, RequireAdminBackupRestore, RequireRecentMfa, get_current_user
from ..models import ROLE_TECHNICIAN, Role, User, WorkOrder
from ..schemas import CompanyProfileUpdate, TechnicianCreate, TechnicianUpdate, UserRead
from ..security import get_password_hash
from ..services.audit import add_audit_log
from ..services.backup_restore import (
    BackupValidationError,
    MAX_BACKUP_SIZE,
    create_backup_archive,
    restore_backup_archive,
)
from ..services.company_profiles import get_company_profile, list_company_profiles, update_company_profile
from ..services.permissions import ensure_permission_catalog, grant_service_access_if_missing
from ..services.malware_scan import scan_bytes

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/companies")
def list_companies(_: User = Depends(get_current_user)):
    return [profile.to_dict() for profile in list_company_profiles()]


@router.put("/companies/{company_code}")
def edit_company_profile(
    company_code: str,
    payload: CompanyProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    current_profile = get_company_profile(company_code)
    if current_profile is None:
        raise HTTPException(status_code=404, detail="Cégprofil nem található")
    before = current_profile.to_dict()
    try:
        profile = update_company_profile(company_code, payload.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Cégprofil nem található") from exc
    add_audit_log(
        db,
        current_user,
        "módosítás",
        "company_profile",
        profile.code,
        f"Cégprofil módosítva: {profile.display_name}",
        entity_display_id=profile.code,
        before=before,
        after=profile.to_dict(),
    )
    db.commit()
    return profile.to_dict()


def _technician_role(db: Session) -> Role:
    role = db.query(Role).filter(Role.name == ROLE_TECHNICIAN).first()
    if role:
        return role
    role = Role(name=ROLE_TECHNICIAN)
    db.add(role)
    db.flush()
    return role


def _technician_or_404(db: Session, technician_id: int) -> User:
    technician = (
        db.query(User)
        .join(Role)
        .filter(User.id == technician_id, Role.name == ROLE_TECHNICIAN)
        .first()
    )
    if not technician:
        raise HTTPException(status_code=404, detail="Technikus nem található")
    return technician


@router.get("/technicians", response_model=list[UserRead])
def list_setting_technicians(db: Session = Depends(get_db), _: User = Depends(RequireAdmin)):
    return (
        db.query(User)
        .join(Role)
        .filter(Role.name == ROLE_TECHNICIAN)
        .order_by(User.full_name, User.email)
        .all()
    )


@router.post("/technicians", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_setting_technician(
    payload: TechnicianCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Ezzel az email címmel már van felhasználó")
    role = _technician_role(db)
    technician = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=get_password_hash(payload.password),
        must_change_password=True,
        is_active=payload.is_active,
        role_id=role.id,
    )
    db.add(technician)
    db.flush()
    ensure_permission_catalog(db)
    grant_service_access_if_missing(db, technician)
    add_audit_log(
        db,
        current_user,
        "létrehozás",
        "technician",
        technician.id,
        f"Technikus létrehozva: {technician.full_name} ({technician.email})",
    )
    db.commit()
    db.refresh(technician)
    return technician


@router.patch("/technicians/{technician_id}", response_model=UserRead)
def update_setting_technician(
    technician_id: int,
    payload: TechnicianUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    technician = _technician_or_404(db, technician_id)
    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] != technician.email:
        if db.query(User).filter(User.email == data["email"]).first():
            raise HTTPException(status_code=400, detail="Ezzel az email címmel már van felhasználó")
    if password := data.pop("password", None):
        technician.password_hash = get_password_hash(password)
        technician.must_change_password = True
    for field, value in data.items():
        setattr(technician, field, value)
    add_audit_log(
        db,
        current_user,
        "módosítás",
        "technician",
        technician.id,
        f"Technikus módosítva: {technician.full_name} ({technician.email})",
    )
    db.commit()
    db.refresh(technician)
    return technician


@router.delete("/technicians/{technician_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_setting_technician(
    technician_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdmin),
):
    technician = _technician_or_404(db, technician_id)
    db.query(WorkOrder).filter(WorkOrder.technician_id == technician.id).update(
        {WorkOrder.technician_id: None}, synchronize_session=False
    )
    db.query(WorkOrder).filter(WorkOrder.secondary_technician_id == technician.id).update(
        {WorkOrder.secondary_technician_id: None}, synchronize_session=False
    )
    add_audit_log(
        db,
        current_user,
        "törlés",
        "technician",
        technician.id,
        f"Technikus törölve: {technician.full_name} ({technician.email})",
    )
    db.delete(technician)
    db.commit()
    return None


@router.get("/backup")
def download_full_backup(
    db: Session = Depends(get_db),
    _: User = Depends(RequireAdmin),
):
    data, filename, _ = create_backup_archive(db.get_bind(), get_settings())
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/restore")
async def restore_full_backup(
    backup_file: UploadFile = File(...),
    confirmation: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdminBackupRestore),
    _: User = Depends(RequireRecentMfa),
):
    if confirmation.strip().upper() != "VISSZAÁLLÍTÁS":
        raise HTTPException(
            status_code=400,
            detail='A visszaállításhoz pontosan ezt írd be: VISSZAÁLLÍTÁS',
        )
    payload = await backup_file.read(MAX_BACKUP_SIZE + 1)
    if len(payload) > MAX_BACKUP_SIZE:
        raise HTTPException(status_code=413, detail="A mentési fájl legfeljebb 500 MB lehet")
    scan_bytes(payload, get_settings())
    bind = db.get_bind()
    db.rollback()
    db.close()
    try:
        return restore_backup_archive(bind, get_settings(), payload)
    except BackupValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"A visszaállítás nem sikerült: {exc}") from exc
