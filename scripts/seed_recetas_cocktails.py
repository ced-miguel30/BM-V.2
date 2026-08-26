"""Alta/actualización de recetas cocktail (categoría bebidas) en datos hotel.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\seed_recetas_cocktails.py
"""

from __future__ import annotations

import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.models import CategoriaReceta, ExtraSugeridoReceta, IngredienteReceta
from app.core.services import receta_service as rec_svc
from app.core.services.unidad_service import convertir_a_unidad_producto

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"

# Volumen del envase (L) cuando el producto está en Ud y no es ~1 L.
PACK_L: dict[str, float] = {
    "b84": 0.33,  # Sprite lata 33 cl
    "b51": 0.70,  # Tequila 70 cl
    "p240": 0.75,  # Cava Roger de Flor 75 cl
    "b14": 0.70,  # Triple seco típico 70 cl
    "b16": 0.70,  # Licor melocotón
    "b03": 0.70,  # Kahlúa típico 70 cl
    "p182": 0.05,  # Menta: ~50 g/Ud hoja → gramos vía PACK_KG abajo
}

PACK_KG: dict[str, float] = {
    "p182": 0.05,  # menta ~50 g/paquete
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
    if u in ("ml", "cl", "L") and prod.unidad.value == "Ud":
        litros = qty * {"ml": 0.001, "cl": 0.01, "L": 1.0}[u]
        pack = PACK_L.get(producto_id, 1.0)
        return round(litros / pack, 6) if pack > 0 else round(litros, 6)
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


def _ing(data, producto_id: str, cantidad: float, unidad: str | None = None) -> IngredienteReceta:
    prod = next(p for p in data.productos if p.id == producto_id)
    nativa = _to_nativa(data, producto_id, cantidad, unidad)
    u = unidad or prod.unidad.value
    if u == "g":
        u = "gr"
    return IngredienteReceta(producto_id, nativa, float(cantidad), u)


# Alias → producto_id
C = {
    "cachaca": "p246",
    "lima": "p67",
    "jarabe": "p245",
    "ron": "b38",
    "leche_coco": "p409",
    "nectar_pina": "p125",
    "pure_maracuya": "p138",
    "jarabe_blue": "p247",
    "vodka": "b12",
    "licor_melocoton": "b16",
    "zumo_naranja": "b28",
    "menta": "p182",
    "soda": "p261",
    "tequila": "b51",
    "triple_seco": "b14",
    "aperol": "p141",
    "cava": "p240",  # Roger de Flor siempre
    "vino_tinto": "b42",
    "sprite": "b84",
    "naranja": "b06",
    "pina_fruta": "p68",
}


def _find(data, nombre: str):
    n = _norm(nombre)
    return next((r for r in data.recetas if _norm(r.nombre) == n), None)


def _ensure(
    data,
    nombre: str,
    ings: list[IngredienteReceta],
    *,
    extras: list[tuple[str, float]] | None = None,
) -> str:
    extras_n = [
        ExtraSugeridoReceta(pid, float(cant))
        for pid, cant in (extras or [])
        if pid and cant > 0
    ]
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
            servicios_disponibles=["bebidas"],
            porciones_estandar=1.0,
            extras_sugeridos=extras_n,
        )
        if not rr.ok:
            raise SystemExit(f"Editar «{nombre}»: {rr.mensaje}")
        return rec.id
    rr = rec_svc.crear_receta(
        nombre,
        ings,
        CategoriaReceta.BEBIDAS,
        servicios_disponibles=["bebidas"],
        porciones_estandar=1.0,
        extras_sugeridos=extras_n,
    )
    if not rr.ok:
        raise SystemExit(f"Crear «{nombre}»: {rr.mensaje}")
    data = get_container().app_data_store.get()
    rec = _find(data, nombre)
    assert rec is not None
    return rec.id


def _specs(data) -> list[tuple[str, list[IngredienteReceta], list[tuple[str, float]] | None]]:
    def I(key: str, qty: float, unit: str) -> IngredienteReceta:
        return _ing(data, C[key], qty, unit)

    # Sangría 1L base
    sangria_1l = [
        I("vino_tinto", 650, "ml"),
        I("triple_seco", 40, "ml"),
        I("sprite", 250, "ml"),
        I("naranja", 60, "gr"),
        I("pina_fruta", 60, "gr"),
    ]
    # Copa = 1/5
    sangria_copa = [
        I("vino_tinto", 130, "ml"),
        I("triple_seco", 8, "ml"),
        I("sprite", 50, "ml"),
        I("naranja", 12, "gr"),
        I("pina_fruta", 12, "gr"),
    ]
    zumo_extra_1l = [(C["zumo_naranja"], _to_nativa(data, C["zumo_naranja"], 100, "ml"))]
    zumo_extra_copa = [(C["zumo_naranja"], _to_nativa(data, C["zumo_naranja"], 20, "ml"))]

    return [
        (
            "Caipirinha",
            [I("cachaca", 50, "ml"), I("lima", 40, "gr"), I("jarabe", 15, "ml")],
            None,
        ),
        (
            "Piña Colada",
            [
                I("ron", 50, "ml"),
                I("leche_coco", 50, "ml"),
                I("nectar_pina", 90, "ml"),
            ],
            None,
        ),
        (
            "Royal Marina",
            [
                I("ron", 40, "ml"),
                I("pure_maracuya", 30, "ml"),
                I("nectar_pina", 80, "ml"),
                I("jarabe_blue", 15, "ml"),
            ],
            None,
        ),
        (
            "Sex on the Beach",
            [
                I("vodka", 40, "ml"),
                I("licor_melocoton", 20, "ml"),
                I("zumo_naranja", 40, "ml"),
                I("nectar_pina", 40, "ml"),
            ],
            None,
        ),
        (
            "Mojito",
            [
                I("ron", 50, "ml"),
                I("menta", 5, "gr"),
                I("lima", 40, "gr"),
                I("jarabe", 20, "ml"),
                I("soda", 100, "ml"),
            ],
            None,
        ),
        (
            "Daiquiri",
            [I("ron", 50, "ml"), I("lima", 40, "gr"), I("jarabe", 15, "ml")],
            None,
        ),
        (
            "Margarita",
            [I("tequila", 40, "ml"), I("triple_seco", 20, "ml"), I("lima", 30, "gr")],
            None,
        ),
        (
            "Blue Hawaii",
            [
                I("ron", 40, "ml"),
                I("jarabe_blue", 20, "ml"),
                I("nectar_pina", 90, "ml"),
                I("leche_coco", 20, "ml"),
            ],
            None,
        ),
        (
            "Espresso Martini",
            [
                I("vodka", 40, "ml"),
                # Kahlúa + 1 cápsula espresso (aprox. un shot).
                _ing(data, "b03", 20, "ml"),
                _ing(data, "p267", 1.0, None),
            ],
            None,
        ),
        (
            "Aperol Spritz",
            [I("aperol", 60, "ml"), I("cava", 90, "ml"), I("soda", 30, "ml")],
            None,
        ),
        ("Copa de sangria", sangria_copa, zumo_extra_copa),
        ("Sangria 1L", sangria_1l, zumo_extra_1l),
        (
            "Sangria de cava 1L",
            [
                I("cava", 650, "ml"),
                I("sprite", 300, "ml"),
                I("naranja", 60, "gr"),
                I("pina_fruta", 60, "gr"),
            ],
            zumo_extra_1l,
        ),
    ]


def main() -> None:
    assert HOTEL.exists(), f"No existe {HOTEL}"
    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()

    for key, pid in C.items():
        data = get_container().app_data_store.get()
        if not any(p.id == pid for p in data.productos):
            raise SystemExit(f"Falta producto {key}={pid}")

    print("== Cocktails bebidas ==")
    for nombre, ings, extras in _specs(get_container().app_data_store.get()):
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
        # extras ya en nativa
        rid = _ensure(data, nombre, ings2, extras=extras)
        print(f"  OK {nombre} -> {rid}")

    data = get_container().app_data_store.get()
    bebidas = sorted(
        (r.nombre, r.servicios_disponibles, len(r.ingredientes), len(r.extras_sugeridos or []))
        for r in data.recetas
        if r.activo and r.categoria == CategoriaReceta.BEBIDAS
    )
    print(f"\nBebidas activas ({len(bebidas)}):")
    for n, serv, ni, ne in bebidas:
        print(f"  · {n} | serv={serv} | ings={ni} | extras={ne}")


if __name__ == "__main__":
    main()
