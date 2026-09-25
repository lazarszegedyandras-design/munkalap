from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from ..models import (
    Asset,
    AssetComponent,
    AssetHistory,
    AssetMeterReading,
    AuditChainState,
    AuditLog,
    CrmActivity,
    CrmOpportunity,
    Customer,
    CustomerContact,
    EmployeeProfile,
    LeaveEntitlement,
    Location,
    Material,
    ProcurementAttachment,
    ProcurementRequest,
    User,
    WorkOrder,
    WorkOrderArchive,
    WorkCalendarDay,
)
from ..request_context import get_audit_request_context

AUDIT_RESULT_SUCCESS = "success"
AUDIT_RESULT_FAILURE = "failure"
AUDIT_SEVERITY_INFO = "info"
AUDIT_SEVERITY_WARNING = "warning"
AUDIT_SEVERITY_ERROR = "error"
AUDIT_CHAIN_VERSION = 1

# Ezeket az adatokat semmilyen strukturált audit snapshot nem őrizheti meg.
# A normalizálás kisbetűs és elválasztófüggetlen összehasonlítást is végez.
SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "passwordhash",
    "token",
    "authorization",
    "cookie",
    "secret",
    "recoverycode",
    "recoverycodes",
    "apikey",
    "api_key",
    ".env",
    "environmentsecret",
)

ENTITY_MODEL_MAP = {
    "user": User,
    "technician": User,
    "customer": Customer,
    "location": Location,
    "customer_contact": CustomerContact,
    "crm_opportunity": CrmOpportunity,
    "crm_activity": CrmActivity,
    "employee_profile": EmployeeProfile,
    "leave_entitlement": LeaveEntitlement,
    "work_calendar_day": WorkCalendarDay,
    "asset": Asset,
    "asset_meter_reading": AssetMeterReading,
    "asset_component": AssetComponent,
    "work_order": WorkOrder,
    "work_order_archive": WorkOrderArchive,
    "material": Material,
    "procurement_request": ProcurementRequest,
    "procurement_attachment": ProcurementAttachment,
}

CREATE_ACTION_MARKERS = ("létrehoz", "feltölt")
DELETE_ACTION_MARKERS = ("törlés", "törölve", "archívum törlése")


def _is_sensitive_key(key: str) -> bool:
    compact = str(key).strip().lower().replace("-", "").replace("_", "")
    return any(fragment.replace("-", "").replace("_", "") in compact for fragment in SENSITIVE_KEY_FRAGMENTS)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                continue
            clean[str(key)] = _json_value(item)
        return clean
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def sanitize_audit_data(value: Any) -> Any:
    return _json_value(value)


def calculate_changes(before: dict | None, after: dict | None) -> dict | None:
    before = sanitize_audit_data(before) if before is not None else None
    after = sanitize_audit_data(after) if after is not None else None
    if before is None and after is None:
        return None
    if before is None:
        return {key: {"before": None, "after": value} for key, value in (after or {}).items()} or None
    if after is None:
        return {key: {"before": value, "after": None} for key, value in before.items()} or None
    changes: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if old != new:
            changes[key] = {"before": old, "after": new}
    return changes or None


def snapshot_entity(entity: Any) -> dict[str, Any] | None:
    if entity is None:
        return None
    try:
        mapper = sa_inspect(entity).mapper
    except Exception:
        return None
    data: dict[str, Any] = {}
    for column_attr in mapper.column_attrs:
        key = column_attr.key
        if _is_sensitive_key(key):
            continue
        try:
            data[key] = getattr(entity, key)
        except Exception:
            continue
    return sanitize_audit_data(data)


def _entity_display_id(entity: Any, entity_type: str) -> str | None:
    if entity is None:
        return None
    candidates = {
        "work_order": ("number",),
        "asset": ("internal_id", "serial_number", "model"),
        "customer": ("name",),
        "location": ("name",),
        "customer_contact": ("name", "email"),
        "crm_opportunity": ("title",),
        "crm_activity": ("subject",),
        "material": ("sku", "name"),
        "procurement_request": ("request_number", "subject"),
        "procurement_attachment": ("original_filename",),
        "user": ("email", "full_name"),
        "technician": ("email", "full_name"),
        "work_order_archive": ("archive_number", "original_filename"),
        "asset_component": ("name", "part_number"),
    }.get(entity_type, ())
    for key in candidates:
        value = getattr(entity, key, None)
        if value not in (None, ""):
            return str(value)
    return None


def _infer_entity_audit_state(db: Session, entity_type: str, entity_id: int | str, action: str):
    model = ENTITY_MODEL_MAP.get(entity_type)
    if model is None:
        return None, None, None
    try:
        pk = int(entity_id)
    except (TypeError, ValueError):
        return None, None, None
    with db.no_autoflush:
        entity = db.get(model, pk)
    if entity is None:
        return None, None, None

    current = snapshot_entity(entity)
    display_id = _entity_display_id(entity, entity_type)
    normalized_action = action.lower()
    if any(marker in normalized_action for marker in CREATE_ACTION_MARKERS):
        return None, current, display_id
    if any(marker in normalized_action for marker in DELETE_ACTION_MARKERS):
        return current, None, display_id

    try:
        state = sa_inspect(entity)
    except Exception:
        return None, current, display_id

    before = dict(current or {})
    changed = False
    for column_attr in state.mapper.column_attrs:
        key = column_attr.key
        if _is_sensitive_key(key):
            continue
        history = state.attrs[key].history
        if not history.has_changes():
            continue
        changed = True
        if history.deleted:
            before[key] = sanitize_audit_data(history.deleted[0])
        elif history.added and key not in before:
            before[key] = None
    if not changed:
        before = None
    return before, current, display_id


def _hash_payload(entry: AuditLog | dict[str, Any]) -> dict[str, Any]:
    get = entry.get if isinstance(entry, dict) else lambda key: getattr(entry, key)
    return {
        "chain_version": AUDIT_CHAIN_VERSION,
        "previous_hash": get("previous_hash"),
        "actor": {
            "user_id": get("actor_user_id"),
            "name": get("actor_name"),
            "email": get("actor_email"),
            "role": get("actor_role"),
        },
        "action": get("action"),
        "entity_type": get("entity_type"),
        "entity_id": get("entity_id"),
        "entity_display_id": get("entity_display_id"),
        "description": get("description"),
        "before_data": get("before_data"),
        "after_data": get("after_data"),
        "changes": get("changes"),
        "request_id": get("request_id"),
        "correlation_id": get("correlation_id"),
        "session_id": get("session_id"),
        "ip_address": get("ip_address"),
        "user_agent": get("user_agent"),
        "result": get("result"),
        "severity": get("severity"),
        "created_at": get("created_at"),
    }


def calculate_audit_hash(entry: AuditLog | dict[str, Any]) -> str:
    canonical = json.dumps(
        sanitize_audit_data(_hash_payload(entry)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lock_chain_state(db: Session) -> AuditChainState:
    cached = db.info.get("audit_chain_state")
    if cached is not None:
        return cached

    query = db.query(AuditChainState).filter(AuditChainState.id == 1)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    state = query.one_or_none()
    if state is None:
        last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        state = AuditChainState(
            id=1,
            last_hash=last.entry_hash if last else None,
            updated_at=datetime.utcnow(),
        )
        db.add(state)
    db.info["audit_chain_state"] = state
    return state


def add_audit_log(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: int | str,
    description: str,
    *,
    entity_display_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    changes: dict | None = None,
    result: str = AUDIT_RESULT_SUCCESS,
    severity: str = AUDIT_SEVERITY_INFO,
    request_id: str | None = None,
    correlation_id: str | None = None,
    session_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    if result not in {AUDIT_RESULT_SUCCESS, AUDIT_RESULT_FAILURE}:
        raise ValueError("Érvénytelen audit eredmény")
    if severity not in {AUDIT_SEVERITY_INFO, AUDIT_SEVERITY_WARNING, AUDIT_SEVERITY_ERROR}:
        raise ValueError("Érvénytelen audit súlyosság")

    if before is None and after is None:
        inferred_before, inferred_after, inferred_display_id = _infer_entity_audit_state(db, entity_type, entity_id, action)
        before = inferred_before
        after = inferred_after
        entity_display_id = entity_display_id or inferred_display_id

    before = sanitize_audit_data(before) if before is not None else None
    after = sanitize_audit_data(after) if after is not None else None
    changes = sanitize_audit_data(changes) if changes is not None else calculate_changes(before, after)

    context = get_audit_request_context()
    now = datetime.utcnow()
    chain_state = _lock_chain_state(db)

    entry = AuditLog(
        user_id=user.id if user else None,
        actor_user_id=user.id if user else None,
        actor_name=user.full_name if user else None,
        actor_email=user.email if user else None,
        actor_role=user.role.name if user and user.role else None,
        action=str(action)[:100],
        entity_type=str(entity_type)[:100],
        entity_id=str(entity_id)[:100],
        entity_display_id=str(entity_display_id)[:255] if entity_display_id else None,
        description=str(description),
        before_data=before,
        after_data=after,
        changes=changes,
        request_id=(request_id or context.request_id),
        correlation_id=(correlation_id or context.correlation_id),
        session_id=(session_id or context.session_id),
        ip_address=(ip_address or context.ip_address),
        user_agent=(user_agent or context.user_agent),
        result=result,
        severity=severity,
        previous_hash=chain_state.last_hash,
        entry_hash="pending",
        created_at=now,
    )
    entry.entry_hash = calculate_audit_hash(entry)
    # Szándékosan nincs flush: az audit segédfüggvény nem változtathatja meg
    # a hívó üzleti tranzakció flush-határait (pl. WorkOrder optimistic version).
    db.add(entry)
    chain_state.last_hash = entry.entry_hash
    chain_state.updated_at = now
    return entry


def verify_audit_chain(db: Session) -> dict[str, Any]:
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    previous_hash = None
    for index, row in enumerate(rows, start=1):
        if row.previous_hash != previous_hash:
            return {
                "valid": False,
                "checked_count": index - 1,
                "total_count": len(rows),
                "broken_audit_id": row.id,
                "reason": "previous_hash_mismatch",
                "chain_head": previous_hash,
            }
        expected = calculate_audit_hash(row)
        if row.entry_hash != expected:
            return {
                "valid": False,
                "checked_count": index - 1,
                "total_count": len(rows),
                "broken_audit_id": row.id,
                "reason": "entry_hash_mismatch",
                "chain_head": previous_hash,
            }
        previous_hash = row.entry_hash

    state = db.get(AuditChainState, 1)
    if state and state.last_hash != previous_hash:
        return {
            "valid": False,
            "checked_count": len(rows),
            "total_count": len(rows),
            "broken_audit_id": None,
            "reason": "chain_state_mismatch",
            "chain_head": previous_hash,
        }
    return {
        "valid": True,
        "checked_count": len(rows),
        "total_count": len(rows),
        "broken_audit_id": None,
        "reason": None,
        "chain_head": previous_hash,
    }


def add_asset_history(db: Session, asset_id: int, user: User | None, action: str, description: str, work_order_id: int | None = None) -> AssetHistory:
    entry = AssetHistory(
        asset_id=asset_id,
        user_id=user.id if user else None,
        work_order_id=work_order_id,
        action=action,
        description=description,
    )
    db.add(entry)
    return entry
