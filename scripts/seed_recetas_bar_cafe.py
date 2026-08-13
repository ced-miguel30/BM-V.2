"""Alta/actualización de recetas café + barra (ración, no botella entera salvo vinos).

- Café/té/Cola Cao: dosis por taza
- Spirits/aperitivos/licores: 4 cl
- Copa de vino: 15 cl
- Botella vino/cava/champagne: 1 Ud

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\seed_recetas_bar_cafe.py
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

# Volumen del envase (L) cuando el producto está en Ud.
PACK_L: dict[str, float] = {
    # 75 cl
    "p234": 0.75,  # Montecillo Crianza
    "p235": 0.75,  # Montecillo Reserva
    "p106": 0.75,  # El Grifo
    "b55": 0.75,  # Ederra
    "p139": 0.75,  # Codorníu Prima Vides
    "b44": 0.75,  # Piper Brut
    "b45": 0.75,  # Piper Rosé
    # 70 cl
    "b20": 0.70,  # Magno
    "b52": 0.70,
    "b50": 0.70,  # Carlos I (aprox.)
    "p145": 0.70,  # Nordés
    "p144": 0.70,  # Martin Miller's
    "b13": 0.70,  # Tequila Gold
    "b39": 0.70,  # Grey Goose
    "p198": 0.70,  # Sambuca
    "p136": 0.70,  # Baileys (típico 70 cl)
    # 20 cl mini
    "p140": 0.20,  # Anna Codorníu Mini
}

PACK_KG: dict[str, float] = {}


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


# Productos
CAFE = "p266"
LECHE = "p127"
NATA = "p210"
JARABE = "p245"
JACK = "b21"
BAILEYS = "p136"
TE_NEGRO = "p130"
TE_VERDE = "p92"
TE_ROJO = "p94"
TE_FRUTAS = "p192"
MANZANILLA = "p93"
COLA_CAO = "b64"

MONTECILLO_CRIANZA = "p234"
MONTECILLO_RESERVA = "p235"
EL_GRIFO = "p106"
EDERRA = "b55"
ANNA_MINI = "p140"
CODORNIU_PRIMA = "p139"
PIPER_BRUT = "b44"
PIPER_ROSE = "b45"

SPIRITS_4CL: list[tuple[str, str]] = [
    ("Beefeater", "b78"),
    ("Gordon's", "p143"),
    ("Tanqueray", "p241"),
    ("Nordes", "p145"),
    ("Martin Miller's", "p144"),
    ("Jack Daniel's", "b21"),
    ("Johnnie Walker", "p288"),  # Black Label (no Red en stock)
    ("Smirnoff", "b12"),
    ("Absolut", "b80"),
    ("Grey Goose", "b39"),
    ("Tequila Gold", "b13"),
    ("Aperol", "p141"),
    ("Campari", "p242"),
    ("Martini Rosso", "p197"),
    ("Martini Bianco", "p196"),
    ("Martini Dry", "p316"),
    ("Baileys", "p136"),
    ("Ron Miel", "b19"),
    ("Amaretto", "b17"),
    ("Tia Maria", "p142"),
    ("Sambuca", "p198"),
    ("Jagermeister", "p243"),
    ("Magno", "b20"),
    ("Carlos I", "b50"),
]


def _specs(data) -> list[tuple[str, list[IngredienteReceta], list[tuple[str, float]] | None]]:
    def I(pid: str, qty: float, unit: str) -> IngredienteReceta:
        return _ing(data, pid, qty, unit)

    out: list[tuple[str, list[IngredienteReceta], list[tuple[str, float]] | None]] = [
        ("Espresso", [I(CAFE, 18, "gr")], None),
        ("Americano", [I(CAFE, 18, "gr")], None),
        ("Cafe con leche", [I(CAFE, 18, "gr"), I(LECHE, 120, "ml")], None),
        (
            "Capuchino",
            [I(CAFE, 18, "gr"), I(LECHE, 100, "ml"), I(NATA, 20, "ml")],
            None,
        ),
        (
            "Cafe irlandes",
            [
                I(CAFE, 18, "gr"),
                I(JACK, 40, "ml"),
                I(JARABE, 10, "ml"),
                I(NATA, 30, "ml"),
            ],
            None,
        ),
        (
            "Cafe Baileys",
            [I(CAFE, 18, "gr"), I(BAILEYS, 40, "ml"), I(LECHE, 60, "ml")],
            None,
        ),
        (
            "Seleccion de te",
            [I(TE_NEGRO, 1, "Ud")],
            [
                (TE_VERDE, 1.0),
                (TE_ROJO, 1.0),
                (TE_FRUTAS, 1.0),
                (MANZANILLA, 1.0),
            ],
        ),
        ("Cola Cao", [I(COLA_CAO, 1, "Ud"), I(LECHE, 200, "ml")], None),
        # Copas 15 cl
        ("Copa Montecillo Crianza", [I(MONTECILLO_CRIANZA, 15, "cl")], None),
        ("Copa El Grifo", [I(EL_GRIFO, 15, "cl")], None),
        # Botellas 1 Ud
        ("Botella Montecillo Crianza", [I(MONTECILLO_CRIANZA, 1, "Ud")], None),
        ("Botella Ederra", [I(EDERRA, 1, "Ud")], None),
        ("Botella El Grifo", [I(EL_GRIFO, 1, "Ud")], None),
        ("Botella Montecillo Reserva", [I(MONTECILLO_RESERVA, 1, "Ud")], None),
        ("Botella Anna Codorniu Mini", [I(ANNA_MINI, 1, "Ud")], None),
        ("Botella Codorniu Prima Vides", [I(CODORNIU_PRIMA, 1, "Ud")], None),
        ("Botella Piper Heidsieck Brut", [I(PIPER_BRUT, 1, "Ud")], None),
        ("Botella Piper Heidsieck Rose", [I(PIPER_ROSE, 1, "Ud")], None),
    ]

    for nombre, pid in SPIRITS_4CL:
        out.append((nombre, [I(pid, 40, "ml")], None))

    return out


def main() -> None:
    assert HOTEL.exists(), f"No existe {HOTEL}"
    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()

    data = get_container().app_data_store.get()
    needed = {
        CAFE,
        LECHE,
        NATA,
        JARABE,
        JACK,
        BAILEYS,
        TE_NEGRO,
        TE_VERDE,
        TE_ROJO,
        TE_FRUTAS,
        MANZANILLA,
        COLA_CAO,
        MONTECILLO_CRIANZA,
        MONTECILLO_RESERVA,
        EL_GRIFO,
        EDERRA,
        ANNA_MINI,
        CODORNIU_PRIMA,
        PIPER_BRUT,
        PIPER_ROSE,
        *[pid for _, pid in SPIRITS_4CL],
    }
    missing = [pid for pid in needed if not any(p.id == pid for p in data.productos)]
    if missing:
        raise SystemExit(f"Faltan productos: {missing}")

    print("== Cafe + barra ==")
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
        rid = _ensure(data, nombre, ings2, extras=extras)
        print(f"  OK {nombre} -> {rid}")

    data = get_container().app_data_store.get()
    bebidas = sorted(
        r.nombre
        for r in data.recetas
        if r.activo and r.categoria == CategoriaReceta.BEBIDAS
    )
    print(f"\nBebidas activas ({len(bebidas)}):")
    for n in bebidas:
        print(f"  · {n}")

    # Spot-check raciones
    checks = [
        ("Copa Montecillo Crianza", MONTECILLO_CRIANZA, 0.2),  # 15cl / 75cl
        ("Beefeater", "b78", 0.04),  # 40ml / 1L
        ("Botella Montecillo Crianza", MONTECILLO_CRIANZA, 1.0),
        ("Espresso", CAFE, 0.018),  # 18g / Kg
    ]
    print("\n== Verificacion raciones ==")
    for nombre, pid, expected in checks:
        r = _find(data, nombre)
        assert r, nombre
        ing = next(i for i in r.ingredientes if i.producto_id == pid)
        ok = abs(ing.cantidad - expected) < 0.001
        print(
            f"  {'OK' if ok else 'FAIL'} {nombre}: nat={ing.cantidad:g} "
            f"(esperado ~{expected:g})"
        )


if __name__ == "__main__":
    main()
