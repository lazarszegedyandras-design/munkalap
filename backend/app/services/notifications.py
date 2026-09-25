from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session, joinedload

from ..access_control import (
    PERMISSION_CRM_ACCESS,
    PERMISSION_CRM_CONTRACT_MANAGE,
    PERMISSION_HR_ACCESS,
    PERMISSION_HR_LEAVE_APPROVE,
    PERMISSION_HR_LEAVE_SELF,
    PERMISSION_SERVICE_ACCESS,
    PERMISSION_PROCUREMENT_APPROVE,
)
from ..models import CrmActivity, CrmContract, EmployeeProfile, LeaveRequest, Notification, ProcurementRequest, ROLE_ADMIN, User, WorkOrder
from .push_notifications import enqueue_push_for_notification


def _has(user: User, code: str) -> bool:
    return user.role.name == ROLE_ADMIN or code in user.permissions


def create_notification(
    db: Session,
    *,
    user_id: int,
    module: str,
    notification_type: str,
    title: str,
    dedupe_key: str,
    message: str | None = None,
    link: str | None = None,
    source_type: str | None = None,
    source_id: str | int | None = None,
) -> Notification:
    row = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.dedupe_key == dedupe_key,
    ).first()
    if row:
        return row
    row = Notification(
        user_id=user_id,
        module=module,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link,
        source_type=source_type,
        source_id=str(source_id) if source_id is not None else None,
        dedupe_key=dedupe_key,
    )
    db.add(row)
    enqueue_push_for_notification(db, row)
    return row


def refresh_user_notifications(db: Session, user: User) -> None:
    now = datetime.utcnow()
    today = date.today()

    # A már nem cselekvést igénylő értesítéseket automatikusan lezárjuk, így
    # a jelvény nem ragad bent egy időközben elvégzett feladat miatt.
    actionable = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read.is_(False)).all()
    for notice in actionable:
        resolved = False
        try:
            source_id = int(notice.source_id) if notice.source_id else None
        except (TypeError, ValueError):
            source_id = None
        if notice.notification_type == "leave_approval_pending" and source_id:
            row = db.get(LeaveRequest, source_id)
            resolved = row is None or row.status != "pending" or row.approver_user_id != user.id
        elif notice.notification_type == "leave_cancellation_pending" and source_id:
            row = db.get(LeaveRequest, source_id)
            resolved = row is None or row.cancellation_status != "pending" or row.cancellation_approver_user_id != user.id
        elif notice.notification_type.startswith("crm_activity_") and source_id:
            row = db.get(CrmActivity, source_id)
            resolved = row is None or row.completed_at is not None or row.owner_user_id != user.id
        elif notice.notification_type == "contract_expiring" and source_id:
            row = db.get(CrmContract, source_id)
            resolved = row is None or row.status != "aktív" or row.end_date is None or row.end_date < today
        elif notice.notification_type.startswith("work_order_") and source_id:
            row = db.get(WorkOrder, source_id)
            resolved = row is None or row.status in {"lezárva", "törölve / sztornózva"} or user.id not in {row.technician_id, row.secondary_technician_id}
        elif notice.notification_type == "procurement_approval_pending" and source_id:
            row = db.get(ProcurementRequest, source_id)
            resolved = (
                row is None
                or row.status != "pending"
                or row.requester_user_id == user.id
                or not _has(user, PERMISSION_PROCUREMENT_APPROVE)
            )
        if resolved:
            notice.is_read = True
            notice.read_at = now

    if _has(user, PERMISSION_HR_ACCESS):
        if _has(user, PERMISSION_HR_LEAVE_APPROVE):
            pending = (
                db.query(LeaveRequest)
                .options(joinedload(LeaveRequest.employee).joinedload(EmployeeProfile.user))
                .filter(LeaveRequest.approver_user_id == user.id, LeaveRequest.status == "pending")
                .all()
            )
            for req in pending:
                create_notification(
                    db,
                    user_id=user.id,
                    module="hr",
                    notification_type="leave_approval_pending",
                    title="Jóváhagyásra váró szabadságigény",
                    message=f"{req.employee.user.full_name}: {req.requested_days} nap szabadság jóváhagyásra vár.",
                    link="/hr/approvals",
                    source_type="leave_request",
                    source_id=req.id,
                    dedupe_key=f"hr:leave:{req.id}:pending-approval",
                )
            pending_cancellations = (
                db.query(LeaveRequest)
                .options(joinedload(LeaveRequest.employee).joinedload(EmployeeProfile.user))
                .filter(
                    LeaveRequest.cancellation_approver_user_id == user.id,
                    LeaveRequest.cancellation_status == "pending",
                    LeaveRequest.status == "approved",
                )
                .all()
            )
            for req in pending_cancellations:
                create_notification(
                    db,
                    user_id=user.id,
                    module="hr",
                    notification_type="leave_cancellation_pending",
                    title="Jóváhagyásra váró szabadság-visszavonás",
                    message=f"{req.employee.user.full_name}: {req.requested_days} nap szabadság visszavonása jóváhagyásra vár.",
                    link="/hr/approvals",
                    source_type="leave_request",
                    source_id=req.id,
                    dedupe_key=f"hr:leave:{req.id}:pending-cancellation:{req.version}",
                )
        if _has(user, PERMISSION_HR_LEAVE_SELF) and user.employee_profile:
            recent = (
                db.query(LeaveRequest)
                .filter(
                    LeaveRequest.employee_id == user.employee_profile.id,
                    LeaveRequest.status.in_(["approved", "rejected"]),
                    LeaveRequest.decided_at.is_not(None),
                    LeaveRequest.decided_at >= now - timedelta(days=30),
                )
                .all()
            )
            for req in recent:
                label = "jóváhagyva" if req.status == "approved" else "elutasítva"
                create_notification(
                    db,
                    user_id=user.id,
                    module="hr",
                    notification_type=f"leave_{req.status}",
                    title=f"Szabadságigény {label}",
                    message=f"A {req.start_date.isoformat()} - {req.end_date.isoformat()} közötti igényed {label}.",
                    link="/hr/leave",
                    source_type="leave_request",
                    source_id=req.id,
                    dedupe_key=f"hr:leave:{req.id}:{req.status}",
                )
            recent_cancellations = (
                db.query(LeaveRequest)
                .filter(
                    LeaveRequest.employee_id == user.employee_profile.id,
                    LeaveRequest.cancellation_status.in_(["approved", "rejected"]),
                    LeaveRequest.cancellation_decided_at.is_not(None),
                    LeaveRequest.cancellation_decided_at >= now - timedelta(days=30),
                )
                .all()
            )
            for req in recent_cancellations:
                label = "jóváhagyva" if req.cancellation_status == "approved" else "elutasítva"
                outcome = "jóváhagyták" if req.cancellation_status == "approved" else "elutasították"
                create_notification(
                    db,
                    user_id=user.id,
                    module="hr",
                    notification_type=f"leave_cancellation_{req.cancellation_status}",
                    title=f"Szabadság-visszavonás {label}",
                    message=f"A {req.start_date.isoformat()} - {req.end_date.isoformat()} közötti szabadságod visszavonását {outcome}.",
                    link="/hr/leave",
                    source_type="leave_request",
                    source_id=req.id,
                    dedupe_key=f"hr:leave:{req.id}:cancellation:{req.cancellation_status}:{req.version}",
                )

    if _has(user, PERMISSION_PROCUREMENT_APPROVE):
        pending_procurement = (
            db.query(ProcurementRequest)
            .options(joinedload(ProcurementRequest.requester))
            .filter(
                ProcurementRequest.status == "pending",
                ProcurementRequest.requester_user_id != user.id,
            )
            .all()
        )
        for req in pending_procurement:
            create_notification(
                db,
                user_id=user.id,
                module="procurement",
                notification_type="procurement_approval_pending",
                title="Jóváhagyásra váró beszerzési igény",
                message=f"{req.requester.full_name}: {req.subject} – {req.total_amount} {req.currency}",
                link=f"/procurement/requests/{req.id}",
                source_type="procurement_request",
                source_id=req.id,
                dedupe_key=f"procurement:request:{req.id}:pending",
            )

    if _has(user, PERMISSION_CRM_ACCESS):
        due_limit = now + timedelta(days=1)
        activities = db.query(CrmActivity).filter(
            CrmActivity.owner_user_id == user.id,
            CrmActivity.completed_at.is_(None),
            CrmActivity.due_at.is_not(None),
            CrmActivity.due_at <= due_limit,
        ).all()
        for activity in activities:
            overdue = activity.due_at < now
            kind = "overdue" if overdue else "due_soon"
            create_notification(
                db,
                user_id=user.id,
                module="crm",
                notification_type=f"crm_activity_{kind}",
                title="Lejárt CRM feladat" if overdue else "CRM feladat hamarosan esedékes",
                message=activity.subject,
                link=f"/crm/activities?edit={activity.id}",
                source_type="crm_activity",
                source_id=activity.id,
                dedupe_key=f"crm:activity:{activity.id}:{kind}",
            )
        if _has(user, PERMISSION_CRM_CONTRACT_MANAGE):
            contracts = db.query(CrmContract).filter(
                CrmContract.status == "aktív",
                CrmContract.end_date.is_not(None),
                CrmContract.end_date >= today,
                CrmContract.end_date <= today + timedelta(days=30),
            ).all()
            for contract in contracts:
                days = (contract.end_date - today).days
                create_notification(
                    db,
                    user_id=user.id,
                    module="crm",
                    notification_type="contract_expiring",
                    title="Lejáró CRM szerződés",
                    message=f"{contract.contract_number} szerződés {days} napon belül lejár.",
                    link=f"/crm/contracts?edit={contract.id}",
                    source_type="crm_contract",
                    source_id=contract.id,
                    dedupe_key=f"crm:contract:{contract.id}:expiring:{contract.end_date.isoformat()}",
                )

    if _has(user, PERMISSION_SERVICE_ACCESS):
        open_statuses = ["új", "ütemezve", "folyamatban", "várakozik", "kész"]
        assigned = db.query(WorkOrder).filter(
            WorkOrder.status.in_(open_statuses),
            (WorkOrder.technician_id == user.id) | (WorkOrder.secondary_technician_id == user.id),
            WorkOrder.planned_date.is_not(None),
            WorkOrder.planned_date <= today,
        ).all()
        for order in assigned:
            overdue = order.planned_date < today
            kind = "overdue" if overdue else "today"
            create_notification(
                db,
                user_id=user.id,
                module="service",
                notification_type=f"work_order_{kind}",
                title="Lejárt tervezett munkalap" if overdue else "Mai munkalap",
                message=f"{order.number}: {order.description[:180]}",
                link=f"/service/work-orders/{order.id}",
                source_type="work_order",
                source_id=order.id,
                dedupe_key=f"service:work-order:{order.id}:{kind}:{order.planned_date.isoformat()}",
            )

    db.flush()
