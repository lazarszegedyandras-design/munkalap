import csv
from io import StringIO
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..deps import get_current_user
from ..models import Asset, User, WorkOrder
from ..services.asset_display import visible_internal_id
from ..services.maintenance_schedule import maintenance_snapshot

router = APIRouter(prefix="/export", tags=["export"])


def _safe_csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def csv_response(filename: str, headers: list[str], rows: list[list]):
    buffer = StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow([_safe_csv_cell(value) for value in headers])
    writer.writerows([[_safe_csv_cell(value) for value in row] for row in rows])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/assets.csv")
def export_assets(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    assets = db.query(Asset).options(joinedload(Asset.customer), joinedload(Asset.current_location)).order_by(Asset.internal_id).all()
    rows = []
    for a in assets:
        maintenance = maintenance_snapshot(a)
        rows.append([
            visible_internal_id(a.internal_id) or "",
            a.serial_number,
            a.type,
            a.manufacturer,
            a.model,
            a.category,
            a.status,
            a.company_code or (a.customer.company_code if a.customer else ""),
            a.customer.name if a.customer else "",
            a.current_location.name if a.current_location else "",
            a.purchase_date,
            a.warranty_expiry,
            a.last_maintenance_date,
            maintenance["maintenance_cycle_label"] or "",
            maintenance["effective_next_maintenance_date"],
            maintenance["maintenance_state_label"],
            a.import_source or "",
            a.import_row or "",
        ])
    return csv_response(
        "eszkozok.csv",
        ["belső azonosító", "gyári szám", "típus", "gyártó", "modell", "kategória", "állapot", "cég", "ügyfél", "helyszín", "vásárlás", "garancia", "utolsó karbantartás", "szerződéses ciklus", "következő karbantartás", "karbantartási állapot", "import forrás", "excel sor"],
        rows,
    )


@router.get("/work-orders.csv")
def export_work_orders(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    orders = db.query(WorkOrder).options(joinedload(WorkOrder.customer), joinedload(WorkOrder.technician), joinedload(WorkOrder.secondary_technician)).order_by(WorkOrder.created_at.desc()).all()
    rows = [
        [
            o.number,
            o.status,
            o.priority,
            o.customer.name if o.customer else "",
            ", ".join(name for name in (o.technician.full_name if o.technician else None, o.secondary_technician.full_name if o.secondary_technician else None) if name),
            o.planned_date,
            o.started_at,
            o.completed_at,
            o.labor_hours,
            o.work_type or "",
            o.contract_type or "",
            o.description,
        ]
        for o in orders
    ]
    return csv_response("munkalapok.csv", ["munkalapszám", "státusz", "prioritás", "ügyfél", "technikus", "tervezett dátum", "kezdés", "befejezés", "munkaidő", "munka típusa", "szerződés típusa", "leírás"], rows)
