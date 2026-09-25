from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import RequireAdminBackupManage, RequireAdminBackupRestore, RequireRecentMfa
from ..models import AuthSession, MobileSession, SecurityRateLimit, User
from ..schemas import BackupRecoveryClearRequest, BackupRestoreEvent, BackupRestoreRequest, BackupScheduleUpdate
from ..services.audit import AUDIT_RESULT_FAILURE, AUDIT_SEVERITY_WARNING, add_audit_log, verify_audit_chain
from ..services.backup_agent import agent_get, agent_post, agent_put
from ..config import get_settings

router = APIRouter(prefix="/backups", tags=["backups"])


@router.get("/status")
def backup_status(_: User = Depends(RequireAdminBackupManage)):
    return agent_get("/status")


@router.get("/schedule")
def backup_schedule(_: User = Depends(RequireAdminBackupManage)):
    return agent_get("/schedule")


@router.put("/schedule")
def update_backup_schedule(
    payload: BackupScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdminBackupManage),
):
    before = agent_get("/schedule")
    updated = agent_put("/schedule", payload.model_dump())
    add_audit_log(
        db,
        current_user,
        "BACKUP_SCHEDULE_UPDATE",
        "backup_schedule",
        "primary",
        "Automatikus biztonsági mentés ütemezése módosítva",
        entity_display_id="Biztonsági mentés ütemezés",
        before=before,
        after=updated,
    )
    db.commit()
    return updated


@router.get("")
def list_backups(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(RequireAdminBackupManage),
):
    return agent_get("/backups", params={"limit": limit})


@router.post("/master", status_code=202)
def create_master_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdminBackupManage),
):
    result = agent_post(
        "/backups/master",
        {
            "requested_by_user_id": current_user.id,
            "requested_by_name": current_user.full_name,
            "requested_by_email": current_user.email,
        },
    )
    add_audit_log(
        db,
        current_user,
        "BACKUP_MASTER_REQUESTED",
        "backup_job",
        result.get("job_id", "unknown"),
        "Manuális MASTER biztonsági mentés elindítva",
        entity_display_id=result.get("job_id"),
        after=result,
    )
    db.commit()
    return result


@router.post("/{backup_id}/validate")
def validate_backup(
    backup_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdminBackupManage),
):
    result = agent_post(f"/backups/{backup_id}/validate")
    add_audit_log(
        db,
        current_user,
        "BACKUP_VALIDATE",
        "backup_job",
        backup_id,
        "Biztonsági mentés integritásellenőrzése sikeres",
        entity_display_id=backup_id,
        after=result,
    )
    db.commit()
    return result


@router.get("/restores")
def list_restores(
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(RequireAdminBackupRestore),
):
    return agent_get("/restores", params={"limit": limit})


@router.get("/restores/{restore_id}")
def get_restore(
    restore_id: str,
    _: User = Depends(RequireAdminBackupRestore),
):
    return agent_get(f"/restores/{restore_id}")


@router.post("/{backup_id}/restore", status_code=202)
def restore_backup(
    backup_id: str,
    payload: BackupRestoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdminBackupRestore),
    _: User = Depends(RequireRecentMfa),
):
    result = agent_post(
        f"/backups/{backup_id}/restore",
        {
            "confirmation": payload.confirmation,
            "requested_by_user_id": current_user.id,
            "requested_by_name": current_user.full_name,
            "requested_by_email": current_user.email,
        },
    )
    add_audit_log(
        db,
        current_user,
        "BACKUP_RESTORE_REQUESTED",
        "backup_restore",
        result.get("restore_id", "unknown"),
        "Rendszerszintű visszaállítás elindítva",
        entity_display_id=result.get("restore_id"),
        after=result,
        severity=AUDIT_SEVERITY_WARNING,
    )
    db.commit()
    return result


def _require_agent_token(x_backup_agent_token: str | None = Header(default=None)) -> None:
    expected = get_settings().backup_agent_token
    import hmac
    if not expected or not x_backup_agent_token or not hmac.compare_digest(x_backup_agent_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Backup-agent hitelesítés sikertelen")


@router.post("/internal/restore-event")
def internal_restore_event(
    payload: BackupRestoreEvent,
    db: Session = Depends(get_db),
    _: None = Depends(_require_agent_token),
):
    chain_before = verify_audit_chain(db)
    if not chain_before.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "A restore utáni audit hash-chain már az esemény rögzítése előtt sérült", "audit_chain": chain_before},
        )

    actor = None
    if payload.requested_by_user_id is not None:
        actor = db.get(User, payload.requested_by_user_id)
    if actor is None and payload.requested_by_email:
        actor = db.query(User).filter(User.email == str(payload.requested_by_email)).first()

    # Physical PostgreSQL restore can bring back session rows that were valid at
    # the backup point but revoked later. Treat authentication/throttling state as
    # ephemeral and invalidate it after both successful restore and rollback.
    invalidated_sessions = db.query(AuthSession).delete(synchronize_session=False)
    invalidated_mobile_sessions = db.query(MobileSession).delete(synchronize_session=False)
    db.query(SecurityRateLimit).delete(synchronize_session=False)

    succeeded = payload.outcome == "success"
    add_audit_log(
        db,
        actor,
        "BACKUP_RESTORE_COMPLETED" if succeeded else "BACKUP_RESTORE_FAILED_ROLLED_BACK",
        "backup_restore",
        payload.restore_id,
        "Rendszerszintű visszaállítás sikeresen befejeződött" if succeeded else "A rendszerszintű visszaállítás sikertelen volt; a pre-restore MASTER visszaállítása megtörtént",
        entity_display_id=payload.restore_id,
        after={
            "backup_id": payload.backup_id,
            "pre_restore_backup_id": payload.pre_restore_backup_id,
            "post_restore_backup_id": payload.post_restore_backup_id,
            "rollback_restore_backup_id": payload.rollback_restore_backup_id,
            "requested_by_name": payload.requested_by_name,
            "requested_by_email": str(payload.requested_by_email) if payload.requested_by_email else None,
            "outcome": payload.outcome,
            "checks": payload.checks,
            "auth_sessions_invalidated": invalidated_sessions,
            "mobile_sessions_invalidated": invalidated_mobile_sessions,
        },
        result="success" if succeeded else AUDIT_RESULT_FAILURE,
        severity="info" if succeeded else AUDIT_SEVERITY_WARNING,
    )
    db.commit()
    chain_after = verify_audit_chain(db)
    if not chain_after.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "A restore esemény után az audit hash-chain ellenőrzése sikertelen", "audit_chain": chain_after},
        )
    return {"ok": True, "audit_chain": chain_after}


@router.post("/recovery/clear")
def clear_restore_recovery_lock(
    payload: BackupRecoveryClearRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireAdminBackupRestore),
    _: User = Depends(RequireRecentMfa),
):
    result = agent_post("/recovery/clear", {"confirmation": payload.confirmation})
    add_audit_log(
        db,
        current_user,
        "BACKUP_RESTORE_RECOVERY_CLEARED",
        "backup_restore",
        "recovery-lock",
        "Megszakadt restore utáni biztonsági zárolás feloldva a host-szintű helyreállítás ellenőrzése után",
        entity_display_id="Restore recovery lock",
        after=result,
        severity=AUDIT_SEVERITY_WARNING,
    )
    db.commit()
    return result
