"""Activa cafés, tés y Cola Cao en el registro de desayuno.

- Recetas de café/té/Cola Cao con servicio «desayuno»
- Variantes leche entera / semidesnatada
- No crea recetas de leche vegetal: espresso + ración de leche vegetal
  se registran a mano desde el catálogo de Bebidas del desayuno

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\seed_bebidas_desayuno.py
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
from app.core.services.unidad_service import convertir_a_unidad_producto

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"

CAFE = "p266"
LECHE_ENTERA = "p127"
LECHE_SEMI = "p128"
NATA = "p210"
TE_NEGRO = "p130"
TE_VERDE = "p92"
TE_ROJO = "p94"
TE_FRUTAS = "p192"
MANZANILLA = "p93"
COLA_CAO = "b64"
DESCAFEINADO = "p131"

SERVICIOS = ["desayuno", "comida", "cena", "bebidas"]


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
    # Brik 1L en Ud: ml/cl se tratan como fracción de litro (mismo criterio bar/café).
    if u in ("ml", "cl", "L") and prod.unidad.value == "Ud":
        litros = qty * {"ml": 0.001, "cl": 0.01, "L": 1.0}[u]
        return round(litros, 6)
    if u in ("ml", "cl", "L") and prod.unidad.value == "L":
        return round(qty * {"ml": 0.001, "cl": 0.01, "L": 1.0}[u], 6)
    if u in ("mg", "gr", "Kg") and prod.unidad.value == "Kg":
        return round(qty * {"mg": 0.000001, "gr": 0.001, "Kg": 1.0}[u], 6)
    nativa = convertir_a_unidad_producto(qty, u, prod.unidad)
    return nativa if nativa > 0 else qty


def _ing(data, producto_id: str, cantidad: float, unidad: str | None = None) -> IngredienteReceta:
    prod = next(p for p in data.productos if p.id == producto_id)
    nativa = _to_nativa(data, producto_id, cantidad, unidad)
    u = unidad or prod.unidad.value
    if u == "g":
        u = "gr"
    return IngredienteReceta(producto_id, nativa, float(cantidad), u)


def _find(data, nombre: str):
    n = _norm(nombre)
    return next((r for r in data.recetas if _norm(r.nombre) == n), None)


def _ensure(data, nombre: str, ings: list[IngredienteReceta]) -> str:
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
            CategoriaReceta.BEBIDAS,
            servicios_disponibles=SERVICIOS,
            porciones_estandar=1.0,
        )
        if not rr.ok:
            raise SystemExit(f"Editar «{nombre}»: {rr.mensaje}")
        return rec.id
    rr = rec_svc.crear_receta(
        nombre,
        ings,
        CategoriaReceta.BEBIDAS,
        servicios_disponibles=SERVICIOS,
        porciones_estandar=1.0,
    )
    if not rr.ok:
        raise SystemExit(f"Crear «{nombre}»: {rr.mensaje}")
    data = get_container().app_data_store.get()
    rec = _find(data, nombre)
    assert rec is not None
    return rec.id


def _specs(data) -> list[tuple[str, list[IngredienteReceta]]]:
    def I(pid: str, qty: float, unit: str) -> IngredienteReceta:
        return _ing(data, pid, qty, unit)

    cafe = I(CAFE, 18, "gr")
    descafe = I(DESCAFEINADO, 1, "Ud")  # sobre 2gr
    return [
        ("Espresso", [cafe]),
        ("Americano", [cafe]),
        ("Cortado", [cafe, I(LECHE_ENTERA, 60, "ml")]),
        ("Cortado semi", [cafe, I(LECHE_SEMI, 60, "ml")]),
        ("Cafe con leche", [cafe, I(LECHE_ENTERA, 120, "ml")]),
        ("Cafe con leche semi", [cafe, I(LECHE_SEMI, 120, "ml")]),
        (
            "Capuchino",
            [cafe, I(LECHE_ENTERA, 100, "ml"), I(NATA, 20, "ml")],
        ),
        (
            "Capuchino semi",
            [cafe, I(LECHE_SEMI, 100, "ml"), I(NATA, 20, "ml")],
        ),
        ("Cola Cao", [I(COLA_CAO, 1, "Ud"), I(LECHE_ENTERA, 200, "ml")]),
        ("Cola Cao semi", [I(COLA_CAO, 1, "Ud"), I(LECHE_SEMI, 200, "ml")]),
        ("Espresso descafeinado", [descafe]),
        ("Cafe con leche descafeinado", [descafe, I(LECHE_ENTERA, 120, "ml")]),
        ("Te negro", [I(TE_NEGRO, 1, "Ud")]),
        ("Te verde", [I(TE_VERDE, 1, "Ud")]),
        ("Te rojo", [I(TE_ROJO, 1, "Ud")]),
        ("Te frutas del bosque", [I(TE_FRUTAS, 1, "Ud")]),
        ("Manzanilla", [I(MANZANILLA, 1, "Ud")]),
        ("Seleccion de te", [I(TE_NEGRO, 1, "Ud")]),
    ]


def main() -> None:
    assert HOTEL.exists(), f"No existe {HOTEL}"
    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()

    data = get_container().app_data_store.get()
    needed = [
        CAFE,
        LECHE_ENTERA,
        LECHE_SEMI,
        NATA,
        TE_NEGRO,
        TE_VERDE,
        TE_ROJO,
        TE_FRUTAS,
        MANZANILLA,
        COLA_CAO,
        DESCAFEINADO,
    ]
    missing = [pid for pid in needed if not any(p.id == pid for p in data.productos)]
    if missing:
        raise SystemExit(f"Faltan productos: {missing}")

    print("== Bebidas desayuno ==")
    for nombre, ings in _specs(get_container().app_data_store.get()):
        data = get_container().app_data_store.get()
        ings2 = [
            _ing(
                data,
                ing.producto_id,
                ing.cantidad_presentacion or ing.cantidad,
                ing.unidad_presentacion,
            )
            for ing in ings
        ]
        rid = _ensure(data, nombre, ings2)
        print(f"  OK {nombre} -> {rid}")

    print("\nListo. En Terminal > Desayuno > Bebidas vera cafes, tes y Cola Cao.")
    print(
        "Leche vegetal: registre Espresso + racion de avena/soja/almendra "
        "desde el listado de leches."
    )


if __name__ == "__main__":
    main()
