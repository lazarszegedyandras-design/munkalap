from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from .database import SessionLocal
from .models import MobileDevice, PushDeliveryOutbox, User
from .services.push_notifications import enqueue_test_push_for_device

TERMINAL = {"sent", "failed_permanent", "cancelled"}


def _select_device(db, *, device_id: int | None, user_email: str | None) -> MobileDevice:
    query = db.query(MobileDevice).filter(
        MobileDevice.revoked_at.is_(None),
        MobileDevice.push_enabled.is_(True),
        MobileDevice.push_token.is_not(None),
    )
    if device_id is not None:
        device = query.filter(MobileDevice.id == device_id).first()
        if device is None:
            raise RuntimeError(f"Nincs aktív push regisztrációjú mobil eszköz ezzel az ID-val: {device_id}")
        return device
    if user_email:
        user = db.query(User).filter(User.email == user_email).first()
        if user is None:
            raise RuntimeError(f"Felhasználó nem található: {user_email}")
        query = query.filter(MobileDevice.user_id == user.id)
    device = query.order_by(MobileDevice.last_seen_at.desc(), MobileDevice.id.desc()).first()
    if device is None:
        raise RuntimeError("Nincs aktív push regisztrációjú mobil eszköz")
    return device


def main() -> int:
    parser = argparse.ArgumentParser(description="FCM production smoke test egy regisztrált Android eszközre")
    parser.add_argument("--device-id", type=int)
    parser.add_argument("--user-email")
    parser.add_argument("--wait", type=int, default=45, help="Maximális várakozás másodpercben")
    args = parser.parse_args()
    if args.wait < 5 or args.wait > 180:
        parser.error("--wait 5 és 180 másodperc között legyen")

    db = SessionLocal()
    try:
        device = _select_device(db, device_id=args.device_id, user_email=args.user_email)
        delivery = enqueue_test_push_for_device(db, device, actor_user_id=0)
        db.commit()
        delivery_id = delivery.id
        print(f"QUEUED delivery_id={delivery_id} device_id={device.id} device={device.device_name or device.device_uuid}", flush=True)
    except Exception as exc:
        db.rollback()
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()

    deadline = time.monotonic() + args.wait
    last_status = None
    while time.monotonic() < deadline:
        db = SessionLocal()
        try:
            row = db.get(PushDeliveryOutbox, delivery_id)
            if row is None:
                print("FAIL: a smoke-test outbox rekord eltűnt", file=sys.stderr)
                return 3
            if row.status != last_status:
                print(
                    f"STATUS delivery_id={row.id} status={row.status} attempts={row.attempt_count} "
                    f"provider={row.provider_message_id or '-'} error={row.last_error or '-'}",
                    flush=True,
                )
                last_status = row.status
            if row.status == "sent":
                print(f"PASS: FCM provider elfogadta a teszt push üzenetet ({row.provider_message_id or 'sent'})")
                return 0
            if row.status in TERMINAL:
                print(f"FAIL: push smoke test terminal status={row.status}; error={row.last_error or '-'}", file=sys.stderr)
                return 4
        finally:
            db.close()
        time.sleep(1)

    print(f"FAIL: push smoke test timeout {args.wait}s; utolsó állapot={last_status or 'ismeretlen'}", file=sys.stderr)
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
