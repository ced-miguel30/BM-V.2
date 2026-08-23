"""Estándar buffet desayuno diario + registro agosto 1–15.

Actualiza/crea recetas desayuno y registra consumo buffet por día
(clave import-ago26-buffet-YYYY-MM-DD).
"""
from __future__ import annotations

import os
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.models import CategoriaReceta, IngredienteReceta
from app.core.services import desayuno_service as des
from app.core.services import receta_service as rec_svc
from app.core.services import stock_service as stock_svc
from app.core.services.inventory_batch_service import stock_disponible
from app.core.services.unidad_service import convertir_a_unidad_producto

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
CLAVE_PREFIX = "import-ago26-buffet"
FECHA_INI = date(2026, 8, 1)
FECHA_FIN = date(2026, 8, 15)

# Ud con peso neto aprox. para convertir gramos → Ud
PACK_KG: dict[str, float] = {
    "p117": 3.0,
    "p185": 0.2,
    "p286": 3.0,
    "p122": 0.85,  # melocotón en su jugo (lata/bote)
    "p304": 3.0,
    "p405": 2.5,
}

# Loncha ≈ 10 g
LONCHA_G = 10.0
# Cuña queso ≈ 1 kg → 1/5
CUNA_FRAC = 1.0 / 5.0
# Fruta fresca por pieza/tipo en buffet (ajustable fin de mes)
FRUTA_G = 150.0


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="seed-dir",
            actor_label="Seed Dirección",
            role=ROL_DIRECCION,
            session_id="seed-session",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="seed",
        )
    )


def _boot():
    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()
    return get_container()


def _to_nativa(data, producto_id: str, cantidad: float, unidad: str | None) -> float:
    prod = next(p for p in data.productos if p.id == producto_id)
    qty = float(cantidad)
    if unidad is None or unidad == prod.unidad.value:
        return qty
    u = "gr" if unidad == "g" else unidad
    if u in ("mg", "gr", "Kg") and prod.unidad.value == "Ud":
        gramos = qty * {"mg": 0.001, "gr": 1.0, "Kg": 1000.0}[u]
        pack = PACK_KG.get(producto_id)
        if pack and pack > 0:
            return round(gramos / (pack * 1000.0), 4)
        raise ValueError(
            f"Producto {producto_id} ({prod.nombre}) en Ud sin PACK_KG para {qty} {u}"
        )
    if u in ("mg", "gr", "Kg") and prod.unidad.value == "Kg":
        return round(qty * {"mg": 0.000001, "gr": 0.001, "Kg": 1.0}[u], 6)
    nativa = convertir_a_unidad_producto(qty, u, prod.unidad)
    return nativa if nativa > 0 else qty


def _ing(data, pid: str, qty: float, unit: str | None = None) -> IngredienteReceta:
    prod = next(p for p in data.productos if p.id == pid)
    nativa = _to_nativa(data, pid, qty, unit)
    u = unit or prod.unidad.value
    if u == "g":
        u = "gr"
    return IngredienteReceta(pid, nativa, float(qty), u)


def _find(data, nombre: str):
    n = _norm(nombre)
    return next((r for r in data.recetas if _norm(r.nombre) == n), None)


def _ensure(data, nombre: str, ings: list[IngredienteReceta], *, categoria: CategoriaReceta) -> str:
    servicios = ["desayuno"]
    rec = _find(data, nombre)
    if rec:
        if not getattr(rec, "activo", True):
            rr = rec_svc.reactivar_receta(rec.id)
            if not rr.ok:
                raise SystemExit(f"Reactivar «{nombre}»: {rr.mensaje}")
        rr = rec_svc.editar_receta(
            rec.id,
            nombre,
            ings,
            categoria,
            servicios_disponibles=servicios,
            porciones_estandar=1.0,
        )
        if not rr.ok:
            raise SystemExit(f"Editar «{nombre}»: {rr.mensaje}")
        return rec.id
    rr = rec_svc.crear_receta(
        nombre,
        ings,
        categoria,
        servicios_disponibles=servicios,
        porciones_estandar=1.0,
    )
    if not rr.ok:
        raise SystemExit(f"Crear «{nombre}»: {rr.mensaje}")
    data = get_container().app_data_store.get()
    rec = _find(data, nombre)
    assert rec is not None
    return rec.id


def ensure_stock(producto_id: str, minimo: float, fecha: date) -> str | None:
    data = get_container().app_data_store.get()
    have = stock_disponible(data, producto_id)
    if have + 1e-9 >= minimo:
        return None
    falta = max(minimo - have, 0.01)
    prod = next((p for p in data.productos if p.id == producto_id), None)
    if prod and prod.unidad.value == "Ud" and falta < 1:
        falta = max(1.0, round(falta + 0.49))
    r = stock_svc.registrar_lote(
        producto_id,
        precio_total=max(1.0, round(falta * 2.5, 2)),
        cantidad=round(falta, 4),
        fecha_compra=fecha - timedelta(days=1),
        marca_proveedor="BUFFET-AGO26",
    )
    return f"repo {producto_id} +{falta:.4g}" if r.ok else f"FAIL {producto_id}: {r.mensaje}"


def build_specs(data) -> list[tuple[str, list[IngredienteReceta]]]:
    """Recetas del estándar diario."""

    def I(pid: str, q: float, u: str | None = None) -> IngredienteReceta:
        return _ing(data, pid, q, u)

    fruta = [
        I("p71", FRUTA_G, "gr"),   # kiwi
        I("p70", FRUTA_G, "gr"),   # papaya
        I("p69", FRUTA_G, "gr"),   # melón
        I("p83", FRUTA_G, "gr"),   # sandía
        I("p99", FRUTA_G, "gr"),   # pomelo
        I("b06", FRUTA_G, "gr"),   # naranja
        I("p66", 2, "Ud"),      # plátano (Ud; ~2 piezas)
        I("p68", FRUTA_G, "gr"),   # piña
        I("p122", 375, "gr"),      # melocotón almíbar
    ]

    embutido = [
        I("p358", 10 * LONCHA_G, "gr"),  # jamón (paleta ibérica; no hay serrano)
        I("p146", 10 * LONCHA_G, "gr"),  # chorizo
        I("p89", 10 * LONCHA_G, "gr"),   # mortadela
        I("p34", 10 * LONCHA_G, "gr"),   # salami ≈ salchichón ibérico
        I("p102", 10 * LONCHA_G, "gr"),  # jamón cocido
        I("p168", 10 * LONCHA_G, "gr"),  # gouda
        I("p37", CUNA_FRAC, "Kg"),   # gofio
        I("b04", CUNA_FRAC, "Kg"),   # pimentón
        I("p38", CUNA_FRAC, "Kg"),   # fresco
    ]

    panes_bolleria = [
        I("p05", 2, "Ud"),    # pan grande (gallego barra)
        I("p357", 2, "Ud"),   # pan millo / maíz
        I("p276", 4, "Ud"),   # centeno
        I("p252", 8, "Ud"),   # baguettes
        I("p251", 6, "Ud"),   # nap chocolate
        I("p294", 12, "Ud"),  # 6 crema + 6 cremas (chic crema)
        I("p250", 8, "Ud"),   # lazos
        I("p249", 9, "Ud"),   # croissant mantequilla
        I("b01", 9, "Ud"),    # croissant chocolate
        I("p08", 0.4, "Kg"),  # surtido repostería ≈ 5–6 piezas
    ]

    return [
        ("Plato pequeno de fruta", fruta),
        ("Plato embutido", embutido),
        (
            "Estándar buffet desayuno diario",
            fruta + embutido + panes_bolleria,
        ),
    ]


def needs_from_cesta() -> dict[str, float]:
    need: dict[str, float] = {}
    for lin in des.get_cesta():
        need[lin.producto_id] = need.get(lin.producto_id, 0) + float(lin.cantidad)
    for g in des.get_cesta_recetas():
        for ing in g.ingredientes:
            if getattr(ing, "es_omision", False):
                continue
            need[ing.producto_id] = need.get(ing.producto_id, 0) + float(ing.cantidad)
    return need


def main() -> int:
    _boot()
    data = get_container().app_data_store.get()

    pending = [
        "Yogur x6 (vaso tipo martini): no hay producto yogur en catálogo — indica SKU.",
        "Pan masa madre x1: no hay SKU — indica producto.",
        "Jamón (curado): usado paleta ibérica p358 (no hay jamón serrano).",
        "Salami: usado salchichón ibérico p34.",
        "Naranja: b06 NARANJA ZUMO (fruta/zumo).",
        "Fruta fresca: 150 g/tipo (excepto melocotón almíbar 375 g) — ajustar fin de mes.",
        "Surtido: 0,4 kg de surtido reposteria (~5-6 piezas; producto en Kg).",
        "Platano: 2 Ud (producto en piezas).",
    ]

    # Desactivar receta intermedia solo-panes
    data = get_container().app_data_store.get()
    old = _find(data, "Buffet panes y bolleria diario")
    if old and old.activo:
        rr = rec_svc.desactivar_receta(old.id)
        print(f"  desactivar r136: {rr.ok} {rr.mensaje}")


    print("== Recetas estándar buffet ==")
    # Actualizar platos comida (para carta) + receta desayuno única para registro diario
    for nombre, ings in build_specs(data):
        if nombre == "Estándar buffet desayuno diario":
            continue
        rid = _ensure(data, nombre, ings, categoria=CategoriaReceta.COMIDA)
        data = get_container().app_data_store.get()
        rec = next(r for r in data.recetas if r.id == rid)
        rr = rec_svc.editar_receta(
            rid,
            nombre,
            list(rec.ingredientes),
            CategoriaReceta.COMIDA,
            servicios_disponibles=["comida", "cena"],
            porciones_estandar=1.0,
        )
        if not rr.ok:
            raise SystemExit(rr.mensaje)
        print(f"  carta {nombre}: {rid}")
        data = get_container().app_data_store.get()

    buffet_ings = next(ings for n, ings in build_specs(data) if n == "Estándar buffet desayuno diario")
    buffet_id = _ensure(
        data,
        "Estándar buffet desayuno diario",
        buffet_ings,
        categoria=CategoriaReceta.DESAYUNO,
    )
    print(f"  buffet diario: {buffet_id}")

    print("\n== Registros buffet diarios ==")
    report_ok = []
    report_err = []
    day = FECHA_INI
    while day <= FECHA_FIN:
        clave = f"{CLAVE_PREFIX}-{day.isoformat()}"
        data = get_container().app_data_store.get()
        if any(
            getattr(d, "clave_idempotencia", None) == clave and not getattr(d, "anulado", False)
            for d in data.desayunos
        ):
            print(f"  skip {clave}")
            day += timedelta(days=1)
            continue

        des.limpiar_cesta()
        r = des.anadir_receta_a_cesta(buffet_id, 1.0)
        if not r.ok:
            report_err.append(f"{clave}: {r.mensaje}")
            day += timedelta(days=1)
            continue

        for pid, qty in needs_from_cesta().items():
            msg = ensure_stock(pid, qty, day)
            if msg:
                print(" ", msg)
        for pid, qty in needs_from_cesta().items():
            ensure_stock(pid, qty, day)

        res = des.registrar_desayuno(
            day,
            1,
            clave_idempotencia=clave,
            observaciones="Estándar buffet diario (fruta + embutido/queso + panes/bollería)",
        )
        if res.ok:
            data = get_container().app_data_store.get()
            reg = next(d for d in data.desayunos if getattr(d, "clave_idempotencia", None) == clave)
            report_ok.append({"fecha": day.isoformat(), "ref": reg.id, "coste": reg.coste_total})
            print(f"  {day} {reg.id} coste={reg.coste_total:.2f}")
        else:
            report_err.append(f"{clave}: {res.mensaje} {getattr(res, 'detalle_stock', None)}")
            print(f"  FAIL {day}: {res.mensaje}")
        des.limpiar_cesta()
        day += timedelta(days=1)

    print("\n== Pendiente / supuestos ==")
    for p in pending:
        print(f"  - {p}")
    print(f"\nOK {len(report_ok)} días | errores {len(report_err)}")
    if report_err:
        print(report_err)
    total = sum(x["coste"] for x in report_ok)
    print(f"Coste buffet total: {total:.2f} €")
    return 0 if not report_err else 1


if __name__ == "__main__":
    raise SystemExit(main())
