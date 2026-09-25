from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import MobileDevice, Notification, PushDeliveryOutbox


RETRY_DELAYS_SECONDS = (60, 300, 900, 3600, 21600)
PUSH_NOTIFICATION_TYPES = {"work_order_assigned", "work_order_schedule_changed"}


def _string_data(data: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in (data or {}).items():
        if value is None:
            continue
        result[str(key)] = str(value)
    return result


def enqueue_push_for_notification(db: Session, notification: Notification) -> int:
    # v0.28 intentionally exposes only technician work-order events on the
    # Android lock screen. HR/CRM/procurement notifications remain in-app until
    # their mobile UX and privacy policy are explicitly designed.
    if notification.notification_type not in PUSH_NOTIFICATION_TYPES:
        return 0
    devices = (
        db.query(MobileDevice)
        .filter(
            MobileDevice.user_id == notification.user_id,
            MobileDevice.revoked_at.is_(None),
            MobileDevice.push_enabled.is_(True),
            MobileDevice.push_token.is_not(None),
        )
        .all()
    )
    data = _string_data({
        "notification_type": notification.notification_type,
        "module": notification.module,
        "source_type": notification.source_type,
        "source_id": notification.source_id,
        "link": notification.link,
    })
    created = 0
    now = datetime.utcnow()
    for device in devices:
        dedupe_key = notification.dedupe_key[:255]
        exists = db.query(PushDeliveryOutbox.id).filter(
            PushDeliveryOutbox.device_id == device.id,
            PushDeliveryOutbox.dedupe_key == dedupe_key,
        ).first()
        if exists:
            continue
        db.add(PushDeliveryOutbox(
            user_id=notification.user_id,
            device_id=device.id,
            notification_id=notification.id,
            dedupe_key=dedupe_key,
            title=notification.title,
            body=notification.message,
            data=data,
            status="pending",
            attempt_count=0,
            next_attempt_at=now,
            created_at=now,
        ))
        created += 1
    return created



def enqueue_test_push_for_device(db: Session, device: MobileDevice, *, actor_user_id: int) -> PushDeliveryOutbox:
    """Queue an explicit admin smoke-test push for one registered device.

    This intentionally bypasses the normal domain-event allowlist. It is only
    exposed from an Admin-only endpoint and never contains business data.
    """
    if device.revoked_at is not None:
        raise ValueError("A mobil eszköz vissza van vonva")
    if not device.push_enabled or not device.push_token:
        raise ValueError("A mobil eszközön nincs aktív push regisztráció")
    now = datetime.utcnow()
    delivery = PushDeliveryOutbox(
        user_id=device.user_id,
        device_id=device.id,
        notification_id=None,
        dedupe_key=f"admin-push-test:{actor_user_id}:{device.id}:{uuid4().hex}"[:255],
        title="Munkalap teszt értesítés",
        body="A push értesítési kapcsolat megfelelően működik.",
        data={
            "notification_type": "system_test",
            "source_type": "system",
            "source_id": str(device.id),
        },
        status="pending",
        attempt_count=0,
        next_attempt_at=now,
        created_at=now,
    )
    db.add(delivery)
    db.flush()
    return delivery

def register_push_token(db: Session, device: MobileDevice, token: str, *, enabled: bool = True) -> MobileDevice:
    token = token.strip()
    now = datetime.utcnow()
    stale = db.query(MobileDevice).filter(MobileDevice.id != device.id, MobileDevice.push_token == token).all()
    for other in stale:
        other.push_token = None
        other.push_enabled = False
        other.push_token_updated_at = None
    device.push_token = token
    device.push_enabled = bool(enabled)
    device.push_token_updated_at = now
    device.updated_at = now
    db.flush()
    return device


def clear_push_token(db: Session, device: MobileDevice) -> None:
    device.push_token = None
    device.push_enabled = False
    device.push_token_updated_at = None
    device.updated_at = datetime.utcnow()
    db.query(PushDeliveryOutbox).filter(
        PushDeliveryOutbox.device_id == device.id,
        PushDeliveryOutbox.status.in_(["pending", "processing", "failed"]),
    ).update({"status": "cancelled", "last_error": "push registration removed"}, synchronize_session=False)
    db.flush()


def next_retry_at(attempt_count: int, now: datetime | None = None) -> datetime:
    now = now or datetime.utcnow()
    index = max(0, min(attempt_count - 1, len(RETRY_DELAYS_SECONDS) - 1))
    return now + timedelta(seconds=RETRY_DELAYS_SECONDS[index])


class FcmSendError(RuntimeError):
    def __init__(self, message: str, *, permanent: bool = False, unregister_token: bool = False):
        super().__init__(message)
        self.permanent = permanent
        self.unregister_token = unregister_token


def _load_fcm_credentials(settings: Settings):
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise FcmSendError("google-auth dependency is not installed", permanent=True) from exc
    scopes = ["https://www.googleapis.com/auth/firebase.messaging"]
    try:
        credentials = service_account.Credentials.from_service_account_file(
            settings.fcm_service_account_file,
            scopes=scopes,
        )
        credentials.refresh(Request())
    except Exception as exc:
        raise FcmSendError(f"FCM credential error: {exc}") from exc
    if not credentials.token:
        raise FcmSendError("FCM OAuth access token is empty")
    return credentials.token


def send_fcm_delivery(delivery: PushDeliveryOutbox, device: MobileDevice, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if not settings.push_notifications_enabled:
        raise FcmSendError("push notifications are disabled", permanent=True)
    if not device.push_enabled or not device.push_token:
        raise FcmSendError("device has no active push registration", permanent=True)

    import httpx

    access_token = _load_fcm_credentials(settings)
    url = f"https://fcm.googleapis.com/v1/projects/{settings.fcm_project_id}/messages:send"
    message: dict[str, Any] = {
        "token": device.push_token,
        "notification": {"title": delivery.title, "body": delivery.body or ""},
        "data": _string_data(delivery.data),
        "android": {
            "priority": "high",
            "notification": {"channel_id": settings.push_android_channel_id, "sound": "default"},
        },
    }
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; UTF-8"},
            json={"message": message},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise FcmSendError(f"FCM network error: {exc}") from exc

    if response.is_success:
        payload = response.json()
        return str(payload.get("name") or "sent")

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    text = str(payload.get("error", {}).get("message") or response.text or f"HTTP {response.status_code}")[:1000]
    details = payload.get("error", {}).get("details") or []
    error_codes = {str(item.get("errorCode")) for item in details if isinstance(item, dict) and item.get("errorCode")}
    unregister = bool(error_codes & {"UNREGISTERED", "SENDER_ID_MISMATCH"})
    permanent = unregister or response.status_code in {400, 403, 404}
    raise FcmSendError(f"FCM HTTP {response.status_code}: {text}", permanent=permanent, unregister_token=unregister)
