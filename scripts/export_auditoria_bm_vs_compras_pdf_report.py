"""Genera PDF de revisión: BM vs Compras prov.pdf (sin PDF + sin coste).

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\export_auditoria_bm_vs_compras_pdf_report.py
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "docs" / "añadidos manual"
JSON_PATH = AUDIT_DIR / "_auditoria_bm_vs_compras_prov.json"
CSV_SIN_PDF = AUDIT_DIR / "_productos_bm_sin_compra_pdf.csv"
CSV_SIN_COSTE = AUDIT_DIR / "_productos_bm_sin_coste.csv"
TODAY = date.today().isoformat()
OUT_PDF = AUDIT_DIR / f"auditoria_bm_vs_compras_prov_{TODAY}.pdf"


def _esc(text: object) -> str:
    s = "" if text is None else str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _eur(val: object, d: int = 4) -> str:
    if val is None or val == "":
        return "—"
    try:
        return f"{float(val):.{d}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "—"


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _table(data: list[list], widths: list[float], *, header_rows: int = 1) -> Table:
    t = Table(data, colWidths=widths, repeatRows=header_rows)
    style = [
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.Color(0.22, 0.33, 0.48)),
        ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
        ("FONTNAME", (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    t.setStyle(TableStyle(style))
    return t


def _rows_sin_pdf(rows: list[dict], cell: ParagraphStyle) -> list[list]:
    header = [
        Paragraph("<b>Código</b>", cell),
        Paragraph("<b>Producto</b>", cell),
        Paragraph("<b>Ud</b>", cell),
        Paragraph("<b>Stock</b>", cell),
        Paragraph("<b>€/ud</b>", cell),
        Paragraph("<b>Cat.</b>", cell),
    ]
    out = [header]
    for r in rows:
        out.append(
            [
                Paragraph(_esc(r.get("codigo")), cell),
                Paragraph(_esc(r.get("nombre")), cell),
                Paragraph(_esc(r.get("unidad")), cell),
                Paragraph(_esc(r.get("stock")), cell),
                Paragraph(_eur(r.get("coste_unitario_eur")), cell),
                Paragraph(_esc(r.get("categoria")), cell),
            ]
        )
    return out


def _rows_sin_coste(rows: list[dict], cell: ParagraphStyle, *, solo_pdf: bool = False) -> list[list]:
    header = [
        Paragraph("<b>Código</b>", cell),
        Paragraph("<b>Producto</b>", cell),
        Paragraph("<b>Ud</b>", cell),
        Paragraph("<b>En PDF</b>", cell),
        Paragraph("<b>Cat.</b>", cell),
    ]
    out = [header]
    for r in rows:
        if solo_pdf and r.get("en_compras_pdf") != "Si":
            continue
        out.append(
            [
                Paragraph(_esc(r.get("codigo")), cell),
                Paragraph(_esc(r.get("nombre")), cell),
                Paragraph(_esc(r.get("unidad")), cell),
                Paragraph(_esc(r.get("en_compras_pdf")), cell),
                Paragraph(_esc(r.get("categoria")), cell),
            ]
        )
    return out


def build_pdf(
    *,
    sin_pdf: list[dict],
    sin_coste: list[dict],
    meta: dict,
    out: Path,
) -> Path:
    styles = getSampleStyleSheet()
    title = ParagraphStyle("T", parent=styles["Heading1"], fontSize=14, spaceAfter=8)
    h2 = ParagraphStyle("H", parent=styles["Heading2"], fontSize=10, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("B", parent=styles["Normal"], fontSize=8, leading=11)
    cell = ParagraphStyle("C", parent=styles["Normal"], fontSize=7, leading=8.5)

    n_pdf = meta.get("productos_bm_sin_aparicion_pdf", len(sin_pdf))
    n_coste = meta.get("productos_bm_sin_coste", len(sin_coste))
    n_activos = meta.get("productos_bm_activos", "")
    n_cod_pdf = meta.get("codigos_en_pdf", "")
    sin_coste_pdf = [r for r in sin_coste if r.get("en_compras_pdf") == "Si"]
    con_stock = [r for r in sin_pdf if float(r.get("stock") or 0) > 0]

    doc = SimpleDocTemplate(
        str(out),
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Auditoría BM vs Compras prov",
    )
    story: list = [
        Paragraph("Auditoría catálogo BM vs Compras prov.pdf", title),
        Paragraph(
            f"Fecha {TODAY} · Periodo compras PDF: 01/03/26–15/07/26 · "
            f"Productos BM activos: {n_activos} · Códigos en PDF: {n_cod_pdf}",
            body,
        ),
        Spacer(1, 4 * mm),
        Paragraph(
            "<b>Resumen</b><br/>"
            f"• <b>{n_pdf}</b> productos en BM que no aparecen en el informe de compras.<br/>"
            f"• <b>{n_coste}</b> productos sin coste (sin lote de stock en BM).<br/>"
            f"• <b>{len(sin_coste_pdf)}</b> de ellos sí se compraron según el PDF pero no tienen lote "
            "(prioridad para crear stock/coste).<br/>"
            f"• <b>{len(con_stock)}</b> productos fuera del PDF pero con stock y coste en BM.",
            body,
        ),
    ]

    # Sección urgente: sin coste pero en PDF
    story.append(Paragraph(
        f"1. Sin coste pero SÍ en PDF compras ({len(sin_coste_pdf)}) — revisar primero",
        h2,
    ))
    story.append(Paragraph(
        "Comprados en el periodo del informe; falta lote en BM para valorar.",
        body,
    ))
    if sin_coste_pdf:
        story.append(_table(
            _rows_sin_coste(sin_coste_pdf, cell, solo_pdf=True),
            [28 * mm, 120 * mm, 14 * mm, 18 * mm, 14 * mm],
        ))
    else:
        story.append(Paragraph("(ninguno)", body))

    # Sin coste completo
    story.append(Paragraph(f"2. Todos los productos sin coste ({n_coste})", h2))
    story.append(Paragraph("Motivo: sin lote de stock. Columna «En PDF» = compra en informe.", body))
    story.append(_table(
        _rows_sin_coste(sin_coste, cell),
        [28 * mm, 120 * mm, 14 * mm, 18 * mm, 14 * mm],
    ))

    # BM sin aparición en PDF — con stock
    sin_pdf_stock = sorted(
        [r for r in sin_pdf if float(r.get("stock") or 0) > 0],
        key=lambda x: -float(x.get("stock") or 0),
    )
    story.append(Paragraph(
        f"3. En BM, no en PDF, con stock ({len(sin_pdf_stock)})",
        h2,
    ))
    story.append(Paragraph(
        "Tienen coste en BM pero no compra en el periodo del informe.",
        body,
    ))
    if sin_pdf_stock:
        story.append(_table(
            _rows_sin_pdf(sin_pdf_stock, cell),
            [28 * mm, 95 * mm, 14 * mm, 18 * mm, 22 * mm, 14 * mm],
        ))

    # BM sin aparición — sin stock
    sin_pdf_nostock = [r for r in sin_pdf if float(r.get("stock") or 0) <= 0]
    story.append(Paragraph(
        f"4. En BM, no en PDF, sin stock ({len(sin_pdf_nostock)})",
        h2,
    ))
    story.append(_table(
        _rows_sin_pdf(sin_pdf_nostock, cell),
        [28 * mm, 95 * mm, 14 * mm, 18 * mm, 22 * mm, 14 * mm],
    ))

    doc.build(story)
    return out


def main() -> int:
    if not CSV_SIN_PDF.is_file() or not CSV_SIN_COSTE.is_file():
        print("Faltan CSV de auditoría. Ejecute antes:")
        print("  python scripts/export_auditoria_bm_vs_compras_pdf.py")
        return 1

    meta: dict = {}
    if JSON_PATH.is_file():
        meta = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    sin_pdf = _read_csv(CSV_SIN_PDF)
    sin_coste = _read_csv(CSV_SIN_COSTE)
    path = build_pdf(sin_pdf=sin_pdf, sin_coste=sin_coste, meta=meta, out=OUT_PDF)
    print(f"PDF generado: {path.resolve()}")
    print(f"  Sin PDF: {len(sin_pdf)} | Sin coste: {len(sin_coste)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
