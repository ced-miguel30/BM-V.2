"""Desglose: productos BM ausentes en Compras prov.pdf y productos sin coste.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\export_auditoria_bm_vs_compras_pdf.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import AuthSession, clear_test_session, set_test_session
from app.core.services.inventory_batch_service import (
    coste_unidad_lote,
    valorizar_cantidad_fifo,
)
from app.core.services.money import normalizar_codigo_funcional
from scripts.import_compras_proveedores_pdf import parsear_pdf, PDF_DEFAULT

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
OUT_DIR = ROOT / "docs" / "añadidos manual"
OUT_JSON = OUT_DIR / "_auditoria_bm_vs_compras_prov.json"
OUT_CSV_SIN_PDF = OUT_DIR / "_productos_bm_sin_compra_pdf.csv"
OUT_CSV_SIN_COSTE = OUT_DIR / "_productos_bm_sin_coste.csv"


def _boot() -> None:
    reset_container()
    clear_test_session()
    configure_for_flet(data_path=str(HOTEL))
    set_test_session(
        AuthSession(
            True,
            "usuario",
            "audit",
            "Auditoría compras",
            ROL_DIRECCION,
            "audit-session",
            datetime.now().isoformat(timespec="seconds"),
        )
    )


def _coste_referencia(data, producto_id: str) -> tuple[float | None, str, float]:
    """Devuelve (coste_unitario, motivo, stock_disponible)."""
    lotes = [
        l
        for l in data.lotes
        if l.producto_id == producto_id and not getattr(l, "anulado", False)
    ]
    stock = sum(float(l.cantidad_restante or 0) for l in lotes)
    if not lotes:
        return None, "sin_lotes", stock

    val = valorizar_cantidad_fifo(data, producto_id, 1.0)
    if val.coste_unitario_aplicable is not None and val.coste_unitario_aplicable > 0:
        return float(val.coste_unitario_aplicable), "fifo", stock

    # Lotes existentes pero sin precio utilizable
    precios = [coste_unidad_lote(l) for l in lotes if l.cantidad > 0]
    if precios and max(precios) > 0:
        ultimo = sorted(lotes, key=lambda l: (l.fecha_compra or date.min, l.id))[-1]
        return coste_unidad_lote(ultimo), "ultimo_lote", stock

    if all(l.precio_total <= 0 for l in lotes):
        return None, "lotes_precio_cero", stock
    return None, "sin_coste_valorable", stock


def main() -> int:
    if not HOTEL.is_file():
        print(f"No existe {HOTEL}")
        return 1
    if not PDF_DEFAULT.is_file():
        print(f"No existe PDF {PDF_DEFAULT}")
        return 1

    _, compras = parsear_pdf(PDF_DEFAULT)
    codigos_pdf = {
        normalizar_codigo_funcional(ln.codigo) or ln.codigo.strip().upper()
        for ln in compras
    }

    _boot()
    data = get_container().app_data_store.get()

    sin_pdf: list[dict] = []
    sin_coste: list[dict] = []
    activos = 0

    for p in sorted(data.productos, key=lambda x: (x.nombre or "").lower()):
        if not getattr(p, "activo", True):
            continue
        activos += 1
        cod = normalizar_codigo_funcional(getattr(p, "codigo", None))
        uni = p.unidad.value if hasattr(p.unidad, "value") else str(p.unidad)
        cu, motivo, stock = _coste_referencia(data, p.id)

        if not cod or cod not in codigos_pdf:
            sin_pdf.append(
                {
                    "producto_id": p.id,
                    "codigo": cod or "",
                    "nombre": p.nombre,
                    "unidad": uni,
                    "stock": round(stock, 4),
                    "coste_unitario_eur": round(cu, 6) if cu is not None else "",
                    "motivo_coste": motivo,
                    "categoria": getattr(p, "categoria_inventario", None) or "",
                    "es_bebida": bool(getattr(p, "es_bebida", False)),
                }
            )

        if cu is None or cu <= 0:
            sin_coste.append(
                {
                    "producto_id": p.id,
                    "codigo": cod or "",
                    "nombre": p.nombre,
                    "unidad": uni,
                    "stock": round(stock, 4),
                    "motivo": motivo,
                    "en_compras_pdf": "Si" if cod and cod in codigos_pdf else "No",
                    "categoria": getattr(p, "categoria_inventario", None) or "",
                }
            )

    reporte = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "pdf": str(PDF_DEFAULT),
        "codigos_en_pdf": len(codigos_pdf),
        "productos_bm_activos": activos,
        "productos_bm_sin_aparicion_pdf": len(sin_pdf),
        "productos_bm_sin_coste": len(sin_coste),
        "sin_pdf": sin_pdf,
        "sin_coste": sin_coste,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")

    for path, rows, fields in (
        (OUT_CSV_SIN_PDF, sin_pdf, None),
        (OUT_CSV_SIN_COSTE, sin_coste, None),
    ):
        if rows:
            fields = fields or list(rows[0].keys())
            with path.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)

    print(f"Productos BM activos: {activos}")
    print(f"Códigos en PDF compras: {len(codigos_pdf)}")
    print(f"BM sin aparición en PDF: {len(sin_pdf)} -> {OUT_CSV_SIN_PDF.name}")
    print(f"BM sin coste: {len(sin_coste)} -> {OUT_CSV_SIN_COSTE.name}")
    print(f"Informe JSON: {OUT_JSON.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
