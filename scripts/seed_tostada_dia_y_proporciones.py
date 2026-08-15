"""7 tostadas por weekday + ajuste proporciones desayuno (pan molde 1/31).

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\seed_tostada_dia_y_proporciones.py
"""

from __future__ import annotations

import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.models import CategoriaReceta, IngredienteReceta
from app.core.services import receta_service as rec_svc
from app.core.services.receta_service import NOMBRES_TOSTADA_POR_WEEKDAY
from app.core.services.unidad_service import convertir_a_unidad_producto

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"

PAN_MOLDE = "p09"
REBANADAS_PAQUETE = 31.0
PACK_KG: dict[str, float] = {
    "p117": 3.0,
    "p185": 0.2,
    "p286": 3.0,
    "p405": 2.5,
}


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


def _to_nativa(data, producto_id: str, cantidad: float, unidad: str | None) -> float:
    prod = next(p for p in data.productos if p.id == producto_id)
    qty = float(cantidad)
    if unidad is None or unidad == prod.unidad.value:
        return qty
    u = "gr" if unidad == "g" else unidad
    if u == "reb" and producto_id == PAN_MOLDE and prod.unidad.value == "Ud":
        return round(qty / REBANADAS_PAQUETE, 6)
    if u in ("ml", "cl", "L") and prod.unidad.value == "Ud":
        return round(qty * {"ml": 0.001, "cl": 0.01, "L": 1.0}[u], 6)
    if u in ("ml", "cl", "L") and prod.unidad.value == "L":
        return round(qty * {"ml": 0.001, "cl": 0.01, "L": 1.0}[u], 6)
    if u in ("mg", "gr", "Kg") and prod.unidad.value == "Ud":
        gramos = qty * {"mg": 0.001, "gr": 1.0, "Kg": 1000.0}[u]
        pack = PACK_KG.get(producto_id)
        if pack and pack > 0:
            return round(gramos / (pack * 1000.0), 6)
        return qty
    if u in ("mg", "gr", "Kg") and prod.unidad.value == "Kg":
        return round(qty * {"mg": 0.000001, "gr": 0.001, "Kg": 1.0}[u], 6)
    nativa = convertir_a_unidad_producto(qty, u, prod.unidad)
    return nativa if nativa > 0 else qty


def _ing(data, producto_id: str, cantidad: float, unidad: str) -> IngredienteReceta:
    nativa = _to_nativa(data, producto_id, cantidad, unidad)
    if unidad == "reb":
        return IngredienteReceta(producto_id, nativa, float(cantidad), "Ud")
    u = "gr" if unidad == "g" else unidad
    return IngredienteReceta(producto_id, nativa, float(cantidad), u)


def _find(data, nombre: str):
    n = _norm(nombre)
    return next((r for r in data.recetas if _norm(r.nombre) == n), None)


def _ensure(nombre: str, ings: list[IngredienteReceta]) -> str:
    data = get_container().app_data_store.get()
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
            CategoriaReceta.DESAYUNO,
            servicios_disponibles=["desayuno"],
            porciones_estandar=1.0,
            extras_sugeridos=[],
        )
        if not rr.ok:
            raise SystemExit(f"Editar «{nombre}»: {rr.mensaje}")
        return rec.id
    rr = rec_svc.crear_receta(
        nombre,
        ings,
        CategoriaReceta.DESAYUNO,
        servicios_disponibles=["desayuno"],
        porciones_estandar=1.0,
    )
    if not rr.ok:
        raise SystemExit(f"Crear «{nombre}»: {rr.mensaje}")
    data = get_container().app_data_store.get()
    rec = _find(data, nombre)
    assert rec is not None
    return rec.id


def main() -> None:
    assert HOTEL.exists(), f"No existe {HOTEL}"
    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()
    data = get_container().app_data_store.get()
    if not any(p.id == PAN_MOLDE for p in data.productos):
        raise SystemExit(f"Falta pan molde {PAN_MOLDE}")

    def I(pid: str, qty: float, unit: str) -> IngredienteReceta:
        return _ing(get_container().app_data_store.get(), pid, qty, unit)

    def pan(n: float = 1.0) -> IngredienteReceta:
        return I(PAN_MOLDE, n, "reb")

    print("== Tostadas por dia ==")
    specs_tostada: list[tuple[str, list[IngredienteReceta]]] = [
        (NOMBRES_TOSTADA_POR_WEEKDAY[0], [pan(), I("p32", 25, "gr"), I("b05", 40, "gr")]),
        (
            NOMBRES_TOSTADA_POR_WEEKDAY[1],
            [pan(), I("p102", 20, "gr"), I("p38", 25, "gr"), I("p51", 30, "gr")],
        ),
        (
            NOMBRES_TOSTADA_POR_WEEKDAY[2],
            [pan(), I("p46", 50, "ml"), I("p102", 15, "gr"), I("p169", 15, "gr")],
        ),
        (
            NOMBRES_TOSTADA_POR_WEEKDAY[3],
            [pan(), I("p14", 15, "gr"), I("p48", 1, "Ud"), I("p169", 15, "gr")],
        ),
        (
            NOMBRES_TOSTADA_POR_WEEKDAY[4],
            [pan(), I("p48", 1, "Ud"), I("p102", 20, "gr"), I("p51", 30, "gr")],
        ),
        (
            NOMBRES_TOSTADA_POR_WEEKDAY[5],
            [pan(), I("p38", 25, "gr"), I("p32", 25, "gr"), I("b05", 40, "gr")],
        ),
        (
            NOMBRES_TOSTADA_POR_WEEKDAY[6],
            [pan(), I("p46", 50, "ml"), I("p185", 15, "gr"), I("p117", 15, "gr")],
        ),
    ]
    for nombre, ings in specs_tostada:
        rid = _ensure(nombre, ings)
        print(f"  OK {nombre} -> {rid}")

    data = get_container().app_data_store.get()
    antigua = _find(data, "Tostada del dia")
    if antigua and getattr(antigua, "activo", True):
        rr = rec_svc.desactivar_receta(antigua.id)
        print(f"  off Tostada del dia: {rr.ok}")

    print("\n== Proporciones desayuno ==")
    otros = [
        ("Tortilla", [I("p46", 50, "ml")]),
        (
            "Tostada francesa",
            [pan(), I("p46", 20, "ml"), I("p152", 8, "gr"), I("p405", 8, "gr")],
        ),
        (
            "Tostada champinones",
            [pan(), I("p48", 1, "Ud"), I("p185", 10, "gr"), I("p117", 15, "gr")],
        ),
        (
            "Desayuno ingles",
            [
                I("p52", 30, "gr"),
                I("p286", 25, "gr"),
                I("p117", 20, "gr"),
                I("p20", 40, "gr"),
                I("p29", 50, "gr"),
                I("p14", 12, "gr"),
            ],
        ),
        ("Sandwich mixto", [pan(2), I("p102", 20, "gr"), I("p169", 20, "gr")]),
        (
            "Sandwich de la casa",
            [pan(2), I("p51", 35, "gr"), I("p38", 25, "gr"), I("p102", 15, "gr")],
        ),
        ("Sandwich vegetal", [pan(2), I("p48", 1, "Ud"), I("p185", 12, "gr")]),
    ]
    for nombre, ings in otros:
        rid = _ensure(nombre, ings)
        print(f"  OK {nombre} -> {rid}")

    data = get_container().app_data_store.get()
    from datetime import date

    hoy = rec_svc.receta_tostada_del_dia(date.today())
    print(f"\nHoy ({date.today().isoformat()} weekday={date.today().weekday()}): {hoy.nombre if hoy else None}")
    print("Desayuno activas:")
    for r in sorted(
        (x for x in data.recetas if x.activo and x.categoria == CategoriaReceta.DESAYUNO),
        key=lambda x: x.nombre.lower(),
    ):
        pan_i = next((i for i in r.ingredientes if i.producto_id == PAN_MOLDE), None)
        extra = f" pan={pan_i.cantidad:g}" if pan_i else ""
        print(f"  · {r.nombre}{extra}")


if __name__ == "__main__":
    main()
