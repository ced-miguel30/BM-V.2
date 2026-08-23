"""Parsea OCR TPV (formato Dynamics) a JSON de líneas."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OCR = ROOT / "docs" / "añadidos manual" / "_comidas_nuevos_ocr.txt"
OUT = ROOT / "docs" / "añadidos manual" / "_tpv_nuevos_parsed.json"

DATE_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s*(PV\d+)?\s*$", re.I)
DATE_PV_INLINE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s*(PV\d+)\s*$", re.I)
DATE_PV_GLUED = re.compile(r"^(\d{2}/\d{2}/\d{4})(PV\d+)\s*$", re.I)
MONEY_RE = re.compile(r"^-?\d+[.,]\d{2}$")
SKIP_PREFIX = (
    "VENTAS",
    "PAG.",
    "DYNAMICS",
    "FECHA",
    "PRODUCTO",
    "DESCRIPCION",
    "IMPORTE",
    "-----",
)


def _norm_money(s: str) -> float:
    return float(s.replace(".", "").replace(",", ".")) if s.count(",") == 1 and s.count(".") > 1 else float(s.replace(",", "."))


def parse_ocr(text: str) -> list[dict]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    rows: list[dict] = []
    cat = "bebidas"
    i = 0
    while i < len(lines):
        ln = lines[i]
        up = ln.upper().replace(" ", "")
        if "101ALIMENT" in up or "ALIMENTACION" in ln.upper():
            cat = "comida"
            i += 1
            continue
        if "104BEBID" in up or ( "BEBIDAS" in ln.upper() and "CATEGORIA" in ln.upper()):
            cat = "bebidas"
            i += 1
            continue
        if ln.upper().startswith("FECHA:"):
            i += 1
            continue
        if any(ln.upper().startswith(p) for p in SKIP_PREFIX):
            i += 1
            continue

        # Pattern A: DATE [PV] / NAME / MONEY  (3 lines)
        # Pattern B: NAME / DATE PV / MONEY
        # Pattern C: DATEPV glued / NAME / MONEY
        fecha = None
        pv = ""
        nombre = None
        importe = None

        m = DATE_PV_GLUED.match(ln.replace(" ", "")) or DATE_PV_INLINE.match(ln) or DATE_RE.match(ln)
        if m:
            fecha = m.group(1)
            pv = (m.group(2) or "") if m.lastindex and m.lastindex >= 2 else ""
            # next non-meta lines: name then money OR money then name (rare)
            if i + 2 < len(lines):
                a, b = lines[i + 1], lines[i + 2]
                if MONEY_RE.match(b.replace(" ", "")) and not MONEY_RE.match(a.replace(" ", "")):
                    nombre, importe = a, _norm_money(b.replace(" ", ""))
                    i += 3
                elif MONEY_RE.match(a.replace(" ", "")) and not MONEY_RE.match(b.replace(" ", "")):
                    importe, nombre = _norm_money(a.replace(" ", "")), b
                    i += 3
                else:
                    i += 1
                    continue
            else:
                i += 1
                continue
        else:
            # NAME then DATE+PV then MONEY
            if i + 2 < len(lines):
                a, b, c = ln, lines[i + 1], lines[i + 2]
                mb = DATE_PV_GLUED.match(b.replace(" ", "")) or DATE_PV_INLINE.match(b) or DATE_RE.match(b)
                if mb and MONEY_RE.match(c.replace(" ", "")):
                    nombre = a
                    fecha = mb.group(1)
                    pv = (mb.group(2) or "") if mb.lastindex and mb.lastindex >= 2 else ""
                    importe = _norm_money(c.replace(" ", ""))
                    i += 3
                else:
                    i += 1
                    continue
            else:
                i += 1
                continue

        if not fecha or not nombre or importe is None:
            continue
        if importe < 0:
            # devoluciones: ignorar por ahora (no deshacer stock automático)
            continue
        if nombre.upper().startswith("CATEGORIA") or nombre.upper().startswith("FECHA"):
            continue
        rows.append(
            {
                "fecha": fecha,
                "pv": pv or "",
                "nombre": nombre.strip(),
                "importe": round(importe, 2),
                "cat": cat,
            }
        )
    return rows


def main() -> int:
    text = OCR.read_text(encoding="utf-8")
    rows = parse_ocr(text)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter

    print("lines", len(rows))
    print("by date", dict(sorted(Counter(r["fecha"] for r in rows).items())))
    print("by cat", dict(Counter(r["cat"] for r in rows)))
    print("unique names", len({r["nombre"] for r in rows}))
    for n, c in Counter(r["nombre"] for r in rows).most_common(25):
        print(f"  {c:3} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
