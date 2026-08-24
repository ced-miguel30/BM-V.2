"""Export productos (stock/coste) y recetas (coste por ración) desde datos locales."""

from __future__ import annotations

import csv
import os
import tempfile
from datetime import datetime
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

SRC = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
TD = Path(tempfile.mkdtemp())
DST = TD / "datos_hotel.json"
DST.write_bytes(SRC.read_bytes())
os.environ["BM_DEMO_FILE"] = str(DST)

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import AuthSession, clear_test_session, set_test_session
from app.core.services import receta_service

reset_container()
clear_test_session()
configure_for_flet()
set_test_session(
    AuthSession(
        True,
        "usuario",
        "u1",
        "Dir",
        ROL_DIRECCION,
        "s1",
        datetime.now().isoformat(timespec="seconds"),
    )
)

data = get_container().app_data_store.get()
out_dir = Path("docs") / "exports"
out_dir.mkdir(parents=True, exist_ok=True)
prod_path = out_dir / "productos_stock_coste.csv"
rec_path = out_dir / "recetas_coste_por_racion.csv"

rows_p: list[dict] = []
for p in sorted(data.productos, key=lambda x: (x.nombre or "").lower()):
    if not getattr(p, "activo", True):
        continue
    rest = 0.0
    for lote in data.lotes or []:
        if lote.producto_id == p.id and not getattr(lote, "anulado", False):
            rest += float(getattr(lote, "cantidad_restante", 0) or 0)
    cu = None
    lotes_p = [
        x
        for x in (data.lotes or [])
        if x.producto_id == p.id and not getattr(x, "anulado", False)
    ]
    lotes_p.sort(key=lambda z: str(getattr(z, "fecha_entrada", "") or ""), reverse=True)
    for lote in lotes_p:
        pt = float(getattr(lote, "precio_total", 0) or 0)
        ci = float(getattr(lote, "cantidad_inicial", 0) or 0)
        cr = float(getattr(lote, "cantidad_restante", 0) or 0)
        base = ci if ci > 0 else cr
        if base > 0 and pt > 0:
            cu = pt / base
            break
    if cu is None:
        for m in reversed(list(data.movimientos or [])):
            if m.producto_id == p.id and getattr(m, "coste_unitario_snapshot", None) is not None:
                try:
                    cu = float(m.coste_unitario_snapshot)
                    break
                except (TypeError, ValueError):
                    pass
    uni = p.unidad.value if hasattr(p.unidad, "value") else str(p.unidad)
    rows_p.append(
        {
            "producto_id": p.id,
            "nombre": p.nombre,
            "unidad": uni,
            "codigo": getattr(p, "codigo", None) or "",
            "stock_restante_lotes": round(rest, 4),
            "coste_unitario_estimado": round(cu, 6) if cu is not None else "",
            "valor_stock_estimado": round(rest * cu, 4) if cu is not None else "",
        }
    )

with prod_path.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_p[0].keys()))
    w.writeheader()
    w.writerows(rows_p)

rows_r: list[dict] = []
for rec in sorted(data.recetas or [], key=lambda x: (x.nombre or "").lower()):
    if not getattr(rec, "activo", True):
        continue
    res = receta_service.valorar_receta(rec.id)
    ings: list[str] = []
    if res.ok:
        for ln in res.lineas or []:
            ings.append(
                f"{ln.nombre}:{ln.cantidad_nativa}{ln.unidad_nativa}=EUR{ln.coste_estimado}"
            )
    cat = getattr(rec, "categoria", "")
    if hasattr(cat, "value"):
        cat = cat.value
    rows_r.append(
        {
            "receta_id": rec.id,
            "nombre": rec.nombre,
            "categoria": cat,
            "porciones_estandar": getattr(rec, "porciones_estandar", ""),
            "ok": res.ok,
            "coste_total": res.coste_total if res.ok else "",
            "coste_por_racion": res.coste_por_racion if res.ok else "",
            "coste_completo": res.coste_completo if res.ok else "",
            "mensaje": (res.mensaje or "")[:160],
            "desglose_ingredientes": " | ".join(ings),
        }
    )

with rec_path.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_r[0].keys()))
    w.writeheader()
    w.writerows(rows_r)

print("SOURCE", SRC)
print("PRODUCTOS", len(rows_p), "->", prod_path.resolve())
print("RECETAS", len(rows_r), "->", rec_path.resolve())
print("--- HUEVOS ---")
for r in rows_p:
    if "huevo" in r["nombre"].lower():
        print(r)
print("--- RECETAS CON HUEVO (coste/racion) ---")
for r in rows_r:
    if "huevo" in r["desglose_ingredientes"].lower() or "huevo" in r["nombre"].lower():
        print(
            f"{r['nombre']}: coste/racion={r['coste_por_racion']} completo={r['coste_completo']}"
        )

print("--- DESCUADRE HUEVO CASCARA p48 ---")
rest = sum(
    float(getattr(L, "cantidad_restante", 0) or 0)
    for L in data.lotes
    if L.producto_id == "p48" and not getattr(L, "anulado", False)
)
ent = sal = 0.0
by_tipo: dict[str, float] = {}
for m in data.movimientos or []:
    if m.producto_id != "p48":
        continue
    q = float(m.cantidad or 0)
    t = str(getattr(m.tipo, "value", m.tipo))
    by_tipo[t] = by_tipo.get(t, 0.0) + q
    if str(getattr(m.direccion, "value", m.direccion)) == "entrada":
        ent += q
    else:
        sal += q
print("restante_lotes", rest)
print("ledger_entrada", ent, "salida", sal, "neto", ent - sal)
print("by_tipo_qty", by_tipo)
sum_pt = sum(
    float(getattr(L, "precio_total", 0) or 0)
    for L in data.lotes
    if L.producto_id == "p48" and not getattr(L, "anulado", False)
)
print("sum_precio_total_lotes_p48", sum_pt)
