from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import or_

from .config import get_settings
from .database import SessionLocal
from .models import MobileDevice, PushDeliveryOutbox
from .services.push_notifications import FcmSendError, next_retry_at, send_fcm_delivery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("push-worker")


def claim_delivery():
    settings = get_settings()
    now = datetime.utcnow()
    stale_before = now - timedelta(seconds=settings.push_worker_lock_timeout_seconds)
    with SessionLocal() as db:
        query = db.query(PushDeliveryOutbox).filter(
            PushDeliveryOutbox.attempt_count < settings.push_retry_max_attempts,
            PushDeliveryOutbox.next_attempt_at <= now,
            or_(
                PushDeliveryOutbox.status.in_(["pending", "failed"]),
                (PushDeliveryOutbox.status == "processing") & (PushDeliveryOutbox.locked_at < stale_before),
            ),
        ).order_by(PushDeliveryOutbox.next_attempt_at.asc(), PushDeliveryOutbox.id.asc())
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        row = query.first()
        if row is None:
            return None
        row.status = "processing"
        row.locked_at = now
        row.last_attempt_at = now
        row.attempt_count += 1
        delivery_id = row.id
        db.commit()
        return delivery_id


def process_delivery(delivery_id: int) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        delivery = db.get(PushDeliveryOutbox, delivery_id)
        if delivery is None or delivery.status != "processing":
            return
        device = db.get(MobileDevice, delivery.device_id)
        if device is None or device.revoked_at is not None or not device.push_enabled or not device.push_token:
            delivery.status = "cancelled"
            delivery.last_error = "device push registration is inactive"
            delivery.locked_at = None
            db.commit()
            return
        try:
            provider_id = send_fcm_delivery(delivery, device, settings)
        except FcmSendError as exc:
            delivery.last_error = str(exc)[:4000]
            delivery.locked_at = None
            if exc.unregister_token and device.push_token:
                device.push_token = None
                device.push_enabled = False
                device.push_token_updated_at = None
            if exc.permanent or delivery.attempt_count >= settings.push_retry_max_attempts:
                delivery.status = "failed_permanent"
            else:
                delivery.status = "failed"
                delivery.next_attempt_at = next_retry_at(delivery.attempt_count)
            db.commit()
            log.warning("Push %s failed: %s", delivery.id, exc)
            return
        delivery.status = "sent"
        delivery.provider_message_id = provider_id[:500]
        delivery.sent_at = datetime.utcnow()
        delivery.locked_at = None
        delivery.last_error = None
        db.commit()
        log.info("Push %s sent: %s", delivery.id, provider_id)


def main() -> None:
    settings = get_settings()
    log.info("Push worker started; enabled=%s project=%s", settings.push_notifications_enabled, settings.fcm_project_id)
    while True:
        if not settings.push_notifications_enabled:
            time.sleep(max(settings.push_worker_poll_seconds, 5))
            continue
        delivery_id = claim_delivery()
        if delivery_id is None:
            time.sleep(settings.push_worker_poll_seconds)
            continue
        process_delivery(delivery_id)


if __name__ == "__main__":
    main()
