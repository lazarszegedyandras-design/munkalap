from __future__ import annotations

import hashlib
import io
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from PIL import Image as PilImage, UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import Settings
from .malware_scan import scan_bytes

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_SIGNATURE_PIXELS = 8_000_000


@dataclass(frozen=True)
class StoredEvidenceFile:
    storage_key: str
    sha256: str
    size_bytes: int


def signature_root(settings: Settings) -> Path:
    configured = settings.mobile_signature_dir.strip()
    return Path(configured) if configured else Path(settings.runtime_dir) / "work_order_signatures"


def signature_path(settings: Settings, storage_key: str) -> Path:
    root = signature_root(settings).resolve()
    path = (root / storage_key).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Érvénytelen aláírási tárhelyútvonal")
    return path


def _write_immutable_bytes(settings: Settings, suffix: str, data: bytes) -> StoredEvidenceFile:
    now = datetime.utcnow()
    storage_key = f"{now.year:04d}/{now.month:02d}/{uuid.uuid4().hex}{suffix}"
    target = signature_path(settings, storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="evidence-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        try:
            os.chmod(target, 0o440)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return StoredEvidenceFile(storage_key=storage_key, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))


def sanitize_and_store_signature_png(payload: bytes, settings: Settings) -> StoredEvidenceFile:
    max_size = settings.mobile_signature_max_size_kb * 1024
    if not payload:
        raise HTTPException(status_code=400, detail="Az aláírás képe üres")
    if len(payload) > max_size:
        raise HTTPException(status_code=413, detail=f"Az aláírás képe legfeljebb {settings.mobile_signature_max_size_kb} KB lehet")
    if not payload.startswith(PNG_SIGNATURE):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Az aláírás kizárólag PNG képként küldhető")
    scan_bytes(payload, settings)

    try:
        with PilImage.open(io.BytesIO(payload)) as source:
            width, height = source.size
            if width < 120 or height < 40 or width * height > MAX_SIGNATURE_PIXELS:
                raise HTTPException(status_code=400, detail="Az aláírás képének mérete érvénytelen")
            source.verify()
        with PilImage.open(io.BytesIO(payload)) as source:
            image = source.convert("RGBA")
            # A signature pad tipikusan fehér vagy átlátszó háttérrel dolgozik.
            # Legalább minimális mennyiségű, nem-fehér látható pixel szükséges,
            # így üres vászon nem fogadható el aláírásként.
            ink = 0
            for r, g, b, a in image.getdata():
                if a > 16 and min(r, g, b) < 235:
                    ink += 1
                    if ink >= 80:
                        break
            if ink < 80:
                raise HTTPException(status_code=400, detail="Az aláírás képe nem tartalmaz elegendő látható vonást")
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            sanitized = output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="A feltöltött PNG aláírás sérült vagy érvénytelen") from exc

    return _write_immutable_bytes(settings, "-signature.png", sanitized)


def _register_pdf_fonts() -> tuple[str, str]:
    regular_candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    ]
    bold_candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ]
    regular = next((p for p in regular_candidates if p.is_file()), None)
    bold = next((p for p in bold_candidates if p.is_file()), None)
    if regular and bold:
        if "WorkAppDejaVu" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("WorkAppDejaVu", str(regular)))
        if "WorkAppDejaVuBold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("WorkAppDejaVuBold", str(bold)))
        return "WorkAppDejaVu", "WorkAppDejaVuBold"
    return "Helvetica", "Helvetica-Bold"


def _safe_text(value) -> str:
    if value is None:
        return "-"
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_signed_work_order_pdf(
    *,
    snapshot: dict,
    snapshot_revision: int,
    snapshot_sha256: str,
    signer_name: str,
    signer_role: str | None,
    acceptance_text: str,
    signed_at: datetime,
    technician_name: str,
    signature_png: bytes,
) -> bytes:
    regular_font, bold_font = _register_pdf_fonts()
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("WorkAppNormal", parent=styles["Normal"], fontName=regular_font, fontSize=9, leading=12, spaceAfter=2)
    small = ParagraphStyle("WorkAppSmall", parent=normal, fontSize=7.5, leading=10)
    heading = ParagraphStyle("WorkAppHeading", parent=styles["Heading1"], fontName=bold_font, fontSize=16, leading=19, alignment=TA_LEFT, spaceAfter=8)
    subheading = ParagraphStyle("WorkAppSubHeading", parent=styles["Heading2"], fontName=bold_font, fontSize=11, leading=14, spaceBefore=6, spaceAfter=4)

    work = snapshot.get("work_order") or {}
    customer = snapshot.get("customer") or {}
    location = snapshot.get("location") or {}
    contact = snapshot.get("contact") or {}
    supplier = snapshot.get("supplier") or {}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Aláírt munkalap {work.get('number', '')}",
        author=supplier.get("name") or "Munkalap rendszer",
    )
    story = []
    story.append(Paragraph(f"Munkalap {_safe_text(work.get('number'))}", heading))
    if supplier:
        story.append(Paragraph(f"<b>Szolgáltató:</b> {_safe_text(supplier.get('name'))} · {_safe_text(supplier.get('address'))}", normal))
    story.append(Spacer(1, 3 * mm))

    details = [
        ["Ügyfél", customer.get("name")],
        ["Helyszín", f"{location.get('name') or ''} {location.get('address') or ''}".strip()],
        ["Kapcsolattartó", contact.get("name")],
        ["Munka típusa", work.get("work_type")],
        ["Tervezett idő", work.get("planned_start_at") or work.get("planned_date")],
        ["Tényleges kezdés", work.get("started_at")],
        ["Tényleges befejezés", work.get("completed_at")],
        ["Technikus", technician_name],
    ]
    table = Table([[Paragraph(f"<b>{_safe_text(label)}</b>", normal), Paragraph(_safe_text(value), normal)] for label, value in details], colWidths=[42 * mm, 130 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    story.append(Paragraph("Bejelentett feladat", subheading))
    story.append(Paragraph(_safe_text(work.get("description")), normal))
    story.append(Paragraph("Elvégzett munka", subheading))
    story.append(Paragraph(_safe_text(work.get("work_done")), normal))
    if work.get("customer_note"):
        story.append(Paragraph("Ügyfélnek szóló megjegyzés", subheading))
        story.append(Paragraph(_safe_text(work.get("customer_note")), normal))

    photos = snapshot.get("photos") or []
    if photos:
        labels = {"before": "Előtte", "after": "Utána", "damage": "Sérülés", "meter": "Számláló", "other": "Egyéb"}
        story.append(Paragraph("Fényképes bizonyítékok", subheading))
        rows = [[Paragraph("<b>Kategória</b>", normal), Paragraph("<b>Megjegyzés</b>", normal), Paragraph("<b>SHA-256</b>", normal)]]
        for photo in photos:
            rows.append([
                Paragraph(_safe_text(labels.get(photo.get("category"), photo.get("category"))), small),
                Paragraph(_safe_text(photo.get("note")), small),
                Paragraph(_safe_text(photo.get("sha256")), small),
            ])
        photo_table = Table(rows, colWidths=[30 * mm, 62 * mm, 80 * mm])
        photo_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(photo_table)

    assets = snapshot.get("assets") or []
    if assets:
        story.append(Paragraph("Eszközök", subheading))
        rows = [[Paragraph("<b>Eszköz</b>", normal), Paragraph("<b>Gyári szám</b>", normal), Paragraph("<b>Számláló</b>", normal)]]
        for asset in assets:
            meter = asset.get("latest_meter") or {}
            rows.append([
                Paragraph(_safe_text(asset.get("display_name")), normal),
                Paragraph(_safe_text(asset.get("serial_number")), normal),
                Paragraph(_safe_text(meter.get("value")), normal),
            ])
        t = Table(rows, colWidths=[95 * mm, 42 * mm, 35 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6"))]))
        story.append(t)

    materials = snapshot.get("materials") or []
    if materials:
        story.append(Paragraph("Felhasznált anyagok", subheading))
        rows = [[Paragraph("<b>Cikkszám</b>", normal), Paragraph("<b>Megnevezés</b>", normal), Paragraph("<b>Mennyiség</b>", normal)]]
        for item in materials:
            rows.append([
                Paragraph(_safe_text(item.get("sku")), normal),
                Paragraph(_safe_text(item.get("name")), normal),
                Paragraph(_safe_text(f"{item.get('quantity')} {item.get('unit') or ''}".strip()), normal),
            ])
        t = Table(rows, colWidths=[38 * mm, 99 * mm, 35 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6"))]))
        story.append(t)

    story.append(Paragraph("Ügyfél igazolása", subheading))
    story.append(Paragraph(_safe_text(acceptance_text), normal))
    story.append(Spacer(1, 2 * mm))
    sig_buffer = io.BytesIO(signature_png)
    sig_image = Image(sig_buffer, width=70 * mm, height=24 * mm, kind="proportional")
    sig_table = Table([
        [sig_image, ""],
        [Paragraph(f"<b>Aláíró:</b> {_safe_text(signer_name)}", normal), Paragraph(f"<b>Beosztás:</b> {_safe_text(signer_role)}", normal)],
        [Paragraph(f"<b>Aláírás időpontja:</b> {_safe_text(signed_at.isoformat())} UTC", small), ""],
    ], colWidths=[90 * mm, 82 * mm])
    sig_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    story.append(sig_table)

    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Integritási adatok", subheading))
    story.append(Paragraph(f"Snapshot revision: {snapshot_revision}", small))
    story.append(Paragraph(f"Snapshot SHA-256: {_safe_text(snapshot_sha256)}", small))
    story.append(Paragraph("A dokumentum a szerver által rögzített, aláíráskori munkalap-snapshotból készült.", small))

    doc.build(story)
    return buffer.getvalue()


def store_signed_pdf(pdf_bytes: bytes, settings: Settings) -> StoredEvidenceFile:
    if not pdf_bytes.startswith(b"%PDF-"):
        raise RuntimeError("A generált aláírt dokumentum nem érvényes PDF")
    return _write_immutable_bytes(settings, "-signed.pdf", pdf_bytes)


def remove_evidence_file(settings: Settings, storage_key: str | None) -> None:
    if not storage_key:
        return
    try:
        path = signature_path(settings, storage_key)
        if path.is_file():
            path.chmod(0o600)
            path.unlink()
    except OSError:
        pass
