"""Sincroniza recetas con docs/recetas.xlsx y reescribe DESAYUNO 1208 como receta+extras.

- Desayuno: solo platos del bloque DESAYUNOS del Excel (desactiva variantes).
- Comida: solo platos del Excel; crea «Paquete de pan» si falta.
- Registro 12/08: lo que no es receta canónica entra como producto extra
  (mods en la receta, o líneas sueltas si no hay receta base).

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\sync_recetas_excel_desayuno_extras.py
"""

from __future__ import annotations

import os
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.models import CategoriaReceta, IngredienteReceta
from app.core.services import anulacion_registro_service as anul
from app.core.services import desayuno_service as des
from app.core.services import receta_service as rec_svc
from app.core.services import stock_service as stock_svc
from app.core.services.inventory_batch_service import stock_disponible
from app.core.services.unidad_service import convertir_a_unidad_producto

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
FECHA = date(2026, 8, 12)
CLAVE_OLD = "desayuno-1208-seed-v1"
CLAVE_NEW = "desayuno-1208-seed-v2-extras"

PACK_KG: dict[str, float] = {
    "p117": 3.0,
    "p286": 3.0,
    "p185": 0.2,
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


def _ing(data, producto_id: str, cantidad: float, unidad: str | None = None) -> IngredienteReceta:
    prod = next(p for p in data.productos if p.id == producto_id)
    nativa = _to_nativa(data, producto_id, cantidad, unidad)
    u = unidad or prod.unidad.value
    if u == "g":
        u = "gr"
    return IngredienteReceta(producto_id, nativa, float(cantidad), u)


CATALOG = {
    "huevo": "p48",
    "huevo_liq": "p46",
    "bacon": "p14",
    "salchicha": "p20",
    "hashbrown": "p29",
    "cafe_illy": "p266",
    "leche_entera": "p127",
    "pan_tostada": "p03",
    "pan_integral": "p11",
    "pan_bao": "p26",
    "salmon": "p32",
    "aguacate": "b05",
    "tomate": "p51",
    "cherry": "p52",
    "espinaca": "p185",
    "jamon_cocido": "p102",
    "queso_loncha": "p169",
    "queso_fresco": "p38",
    "champi": "p117",
    "judias": "p286",
    "mantequilla": "p152",
    "chorizo": "p146",
    "frutos_rojos": "p405",
}

# Nombres canónicos Excel DESAYUNOS
KEEP_DESAYUNO = {
    "Huevo frito",
    "Huevo pochado",
    "Huevo cocido",
    "Tortilla",
    "Tostada del dia",
    "Tostada francesa",
    "Tostada champinones",
    "Desayuno ingles",
    "Sandwich mixto",
    "Sandwich de la casa",
    "Sandwich vegetal",
}

KEEP_BEBIDAS = {"Cortado"}

KEEP_COMIDA = {
    "Plato pequeno de fruta",
    "Fruta en almibar",
    "Plato embutido",
    "Pan bao",
    "Sandwich club",
    "Paquete de pan",
    "Patatas fritas",
    "Papas arrugadas",
    "Croquetas jamon serrano",
    "Nachos con guacamole",
    "Ensalada queso de cabra y fresa",
    "Cocktail de gambas",
    "Ensalada cesar",
    "Tartar salmon con aguacate",
    "Poke bowl",
    "Ensalada aguacate tomate y jamon",
    "Huevos rotos",
    "Hamburguesa",
    "Verduras a la parrilla",
    "Gambas al ajillo",
    "Calamares a la romana",
    "Langostinos crujientes",
    "Bacalao en tempura",
    "Bola de helado",
    "Tiramisu",
    "Brownie con helado",
    "Tarta de queso con helado",
    "Banana split",
}


def _ensure_stock(data, producto_id: str, minimo: float) -> None:
    actual = stock_disponible(data, producto_id)
    if actual >= minimo:
        return
    falta = max(minimo - actual, 1.0)
    stock_svc.registrar_lote(
        producto_id,
        precio_total=max(1.0, round(falta * 2.5, 2)),
        cantidad=round(falta, 3),
        fecha_compra=FECHA,
        marca_proveedor="SYNC-EXCEL",
    )


def _find_receta(data, nombre: str):
    n = _norm(nombre)
    return next((r for r in data.recetas if _norm(r.nombre) == n), None)


def _ensure_receta(
    data,
    nombre: str,
    categoria: CategoriaReceta,
    servicios: list[str],
    ings: list[IngredienteReceta],
) -> str:
    rec = _find_receta(data, nombre)
    if rec:
        if not getattr(rec, "activo", True):
            rr = rec_svc.reactivar_receta(rec.id)
            if not rr.ok:
                raise SystemExit(f"No se pudo reactivar «{nombre}»: {rr.mensaje}")
            data = get_container().app_data_store.get()
            rec = _find_receta(data, nombre)
        assert rec is not None
        # Actualizar ingredientes al Excel (p. ej. Tortilla → 30 ml huevina).
        rr = rec_svc.editar_receta(
            rec.id,
            nombre,
            ings,
            categoria,
            servicios_disponibles=servicios,
            porciones_estandar=1.0,
        )
        if not rr.ok:
            raise SystemExit(f"No se pudo actualizar «{nombre}»: {rr.mensaje}")
        return rec.id
    r = rec_svc.crear_receta(
        nombre,
        ings,
        categoria,
        servicios_disponibles=servicios,
        porciones_estandar=1.0,
    )
    if not r.ok:
        raise SystemExit(f"No se pudo crear «{nombre}»: {r.mensaje}")
    data = get_container().app_data_store.get()
    rec = _find_receta(data, nombre)
    assert rec is not None
    return rec.id


def _specs_desayuno(data) -> list[tuple[str, list[IngredienteReceta]]]:
    C = CATALOG

    def I(k, q, u=None):
        return _ing(data, C[k], q, u)

    return [
        ("Huevo frito", [I("huevo", 1, "Ud")]),
        ("Huevo pochado", [I("huevo", 1, "Ud")]),
        ("Huevo cocido", [I("huevo", 1, "Ud")]),
        ("Tortilla", [I("huevo_liq", 30, "ml")]),
        ("Tostada del dia", [I("pan_tostada", 1, "Ud")]),
        (
            "Tostada francesa",
            [
                I("pan_tostada", 1, "Ud"),
                I("huevo_liq", 5, "ml"),
                I("mantequilla", 15, "gr"),
                I("frutos_rojos", 10, "gr"),
            ],
        ),
        (
            "Tostada champinones",
            [
                I("pan_tostada", 1, "Ud"),
                I("huevo", 1, "Ud"),
                I("espinaca", 15, "gr"),
                I("champi", 20, "gr"),
            ],
        ),
        (
            "Desayuno ingles",
            [
                I("cherry", 40, "gr"),
                I("judias", 20, "gr"),
                I("champi", 20, "gr"),
                I("salchicha", 50, "gr"),
                I("hashbrown", 70, "gr"),
                I("bacon", 15, "gr"),
                I("huevo", 1, "Ud"),  # huevo frito de la ficha
            ],
        ),
        (
            "Sandwich mixto",
            [
                I("pan_tostada", 2, "Ud"),
                I("jamon_cocido", 15, "gr"),
                I("queso_loncha", 20, "gr"),
            ],
        ),
        (
            "Sandwich de la casa",
            [
                I("pan_tostada", 2, "Ud"),
                I("tomate", 40, "gr"),
                I("queso_fresco", 30, "gr"),
                I("jamon_cocido", 15, "gr"),
            ],
        ),
        (
            "Sandwich vegetal",
            [I("pan_tostada", 2, "Ud"), I("huevo", 1, "Ud"), I("espinaca", 15, "gr")],
        ),
        (
            "Cortado",
            [I("cafe_illy", 18, "gr"), I("leche_entera", 60, "ml")],
        ),
    ]


# Cada línea del Excel DESAYUNO 1208:
# (receta_canónica|None, porciones, extras[(catalog_key, qty, unit)])
PEDIDOS: list[tuple[str | None, float, list[tuple[str, float, str]]]] = [
    (None, 0, [("huevo", 2, "Ud")]),  # 2 HUEVOS REVUELTOS
    ("Tostada del dia", 1, [("aguacate", 60, "gr"), ("salmon", 40, "gr")]),
    (None, 0, [("huevo", 4, "Ud")]),  # 4 HUEVOS REVUELTO
    ("Tostada del dia", 1, [("salmon", 40, "gr")]),
    ("Tostada del dia", 1, []),
    ("Tostada del dia", 1, [("huevo", 1, "Ud")]),  # huevo revuelto + pan
    # Cortado = bebidas → productos sueltos (no entra en catálogo desayuno)
    (None, 0, [("cafe_illy", 18, "gr"), ("leche_entera", 60, "ml")]),
    ("Tortilla", 1, [("jamon_cocido", 20, "gr"), ("queso_loncha", 20, "gr")]),
    ("Huevo cocido", 2, [("bacon", 20, "gr"), ("judias", 30, "gr")]),
    ("Huevo frito", 1, [("bacon", 20, "gr"), ("aguacate", 50, "gr")]),
    ("Huevo frito", 1, [("bacon", 20, "gr"), ("aguacate", 50, "gr")]),
    ("Sandwich vegetal", 1, []),
    ("Tostada champinones", 1, [("cherry", 30, "gr")]),
    (
        None,
        0,
        [
            ("cherry", 40, "gr"),
            ("judias", 20, "gr"),
            ("salchicha", 50, "gr"),
            ("hashbrown", 70, "gr"),
            ("bacon", 15, "gr"),
        ],
    ),
    ("Huevo pochado", 1, [("pan_integral", 1, "Ud")]),
    (
        "Tostada del dia",
        1,
        [("huevo", 1, "Ud"), ("salchicha", 50, "gr"), ("bacon", 15, "gr")],
    ),
    (
        "Tortilla",
        1,
        [("jamon_cocido", 20, "gr"), ("queso_loncha", 20, "gr"), ("tomate", 30, "gr")],
    ),
    (
        "Tortilla",
        1,
        [("queso_loncha", 20, "gr"), ("chorizo", 30, "gr"), ("salchicha", 50, "gr")],
    ),
    (None, 0, [("huevo", 2, "Ud"), ("bacon", 20, "gr"), ("judias", 30, "gr")]),
    ("Huevo cocido", 2, []),
    ("Tostada del dia", 1, [("huevo", 1, "Ud")]),
    ("Huevo frito", 1, [("salchicha", 50, "gr"), ("bacon", 15, "gr")]),
    ("Huevo cocido", 2, []),
    ("Tostada del dia", 1, []),
    ("Huevo cocido", 1, []),
    (
        "Tortilla",
        1,
        [("bacon", 20, "gr"), ("hashbrown", 140, "gr"), ("tomate", 30, "gr")],
    ),
    (None, 0, [("tomate", 60, "gr")]),
    (
        "Tostada del dia",
        1,
        [("huevo", 1, "Ud"), ("jamon_cocido", 20, "gr"), ("queso_loncha", 20, "gr")],
    ),
    (
        "Tostada del dia",
        1,
        [("huevo", 1, "Ud"), ("jamon_cocido", 20, "gr"), ("queso_loncha", 20, "gr")],
    ),
    ("Huevo cocido", 1, []),
    ("Tortilla", 1, [("espinaca", 20, "gr"), ("tomate", 30, "gr")]),
    ("Huevo pochado", 2, []),
    ("Sandwich mixto", 1, []),
    ("Tortilla", 1, [("queso_loncha", 20, "gr"), ("salchicha", 50, "gr")]),
]


def main() -> None:
    assert HOTEL.exists(), f"No existe {HOTEL}"
    assert len(PEDIDOS) == 34, f"PEDIDOS={len(PEDIDOS)} esperado 34"

    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()
    data = get_container().app_data_store.get()

    print("== Asegurar recetas canónicas ==")
    for nombre, ings in _specs_desayuno(data):
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
        cat = CategoriaReceta.BEBIDAS if nombre == "Cortado" else CategoriaReceta.DESAYUNO
        serv = (
            ["desayuno", "comida", "cena", "bebidas"]
            if nombre == "Cortado"
            else ["desayuno"]
        )
        rid = _ensure_receta(data, nombre, cat, serv, ings2)
        print(f"  OK {nombre} -> {rid}")

    data = get_container().app_data_store.get()
    if not _find_receta(data, "Paquete de pan"):
        rid = _ensure_receta(
            data,
            "Paquete de pan",
            CategoriaReceta.COMIDA,
            ["comida"],
            [_ing(data, CATALOG["pan_tostada"], 31, "Ud")],
        )
        print(f"  OK Paquete de pan -> {rid}")

    print("\n== Desactivar recetas fuera del Excel ==")
    keep = KEEP_DESAYUNO | KEEP_BEBIDAS | KEEP_COMIDA
    data = get_container().app_data_store.get()
    for r in list(data.recetas):
        if not getattr(r, "activo", True):
            continue
        cat = r.categoria.value if hasattr(r.categoria, "value") else str(r.categoria)
        if cat not in ("desayuno", "comida", "bebidas"):
            continue
        if r.nombre in keep:
            continue
        # Alias Tortilla de huevo → off si ya hay Tortilla
        if cat == "bebidas" and r.nombre != "Cortado":
            rr = rec_svc.desactivar_receta(r.id)
            print(f"  off [{cat}] {r.nombre}: {rr.ok}")
            continue
        if cat in ("desayuno", "comida"):
            rr = rec_svc.desactivar_receta(r.id)
            print(f"  off [{cat}] {r.nombre}: {rr.ok} {rr.mensaje}")

    print("\n== Anular desayuno seed anterior ==")
    data = get_container().app_data_store.get()
    for d in data.desayunos:
        clave = getattr(d, "clave_idempotencia", None)
        if clave in (CLAVE_OLD, CLAVE_NEW) and not getattr(d, "anulado", False):
            r = anul.anular_desayuno(d.id, "Resincronización recetas Excel + extras")
            print(f"  anular {d.id}: {r.ok} {r.mensaje}")

    print("\n== Stock mínimo ==")
    mins = {
        "huevo": 80,
        "huevo_liq": 2,
        "bacon": 2,
        "salchicha": 3,
        "hashbrown": 3,
        "cafe_illy": 1,
        "leche_entera": 5,
        "pan_tostada": 50,
        "pan_integral": 5,
        "salmon": 2,
        "aguacate": 3,
        "tomate": 2,
        "cherry": 2,
        "espinaca": 2,
        "jamon_cocido": 2,
        "queso_loncha": 2,
        "champi": 2,
        "judias": 2,
        "chorizo": 1,
        "mantequilla": 1,
        "frutos_rojos": 1,
    }
    for key, minimo in mins.items():
        data = get_container().app_data_store.get()
        _ensure_stock(data, CATALOG[key], minimo)

    print("\n== Registrar desayuno 12/08 (receta + extras) ==")
    des.limpiar_cesta()
    data = get_container().app_data_store.get()
    name_to_id = {
        r.nombre: r.id for r in data.recetas if getattr(r, "activo", True)
    }

    for i, (rec_nombre, porciones, extras) in enumerate(PEDIDOS, 1):
        data = get_container().app_data_store.get()
        if rec_nombre:
            rid = name_to_id.get(rec_nombre)
            if not rid:
                raise SystemExit(f"Línea {i}: falta receta «{rec_nombre}»")
            for key, qty, unit in extras:
                pid = CATALOG[key]
                cant = _to_nativa(data, pid, qty, unit)
                r = des.anadir_mod_pendiente_receta(pid, float(cant))
                if not r.ok:
                    raise SystemExit(f"Línea {i} mod {key}: {r.mensaje}")
            r = des.anadir_receta_a_cesta(rid, float(porciones))
            if not r.ok:
                raise SystemExit(f"Línea {i} receta «{rec_nombre}»: {r.mensaje}")
        else:
            for key, qty, unit in extras:
                pid = CATALOG[key]
                cant = _to_nativa(data, pid, qty, unit)
                r = des.anadir_a_cesta(pid, float(cant))
                if not r.ok:
                    raise SystemExit(f"Línea {i} producto {key}: {r.mensaje}")

    resultado = des.registrar_desayuno(
        FECHA,
        len(PEDIDOS),
        clave_idempotencia=CLAVE_NEW,
        observaciones="DESAYUNO 1208: recetas Excel + extras de productos",
    )
    print(resultado.ok, resultado.mensaje)

    data = get_container().app_data_store.get()
    activas_d = sorted(
        r.nombre
        for r in data.recetas
        if r.activo and r.categoria == CategoriaReceta.DESAYUNO
    )
    activas_c = sorted(
        r.nombre
        for r in data.recetas
        if r.activo and r.categoria == CategoriaReceta.COMIDA
    )
    print(f"\nDesayuno activas ({len(activas_d)}): {activas_d}")
    print(f"Comida activas ({len(activas_c)}): {activas_c}")
    ult = [
        d
        for d in data.desayunos
        if getattr(d, "clave_idempotencia", None) == CLAVE_NEW
        and not getattr(d, "anulado", False)
    ]
    if ult:
        d = ult[-1]
        recs = getattr(d, "registros_recetas", None) or []
        n_extras = sum(len(getattr(rr, "extras", []) or []) for rr in recs)
        print(
            f"Desayuno {d.id} huespedes={d.num_huespedes} "
            f"lineas={len(d.lineas)} recetas={len(recs)} extras_en_recetas={n_extras}"
        )
        for rr in recs[:10]:
            ex_parts = []
            for e in getattr(rr, "extras", []) or []:
                prod = next((p for p in data.productos if p.id == e.producto_id), None)
                ex_parts.append(f"{prod.nombre if prod else e.producto_id}:{e.cantidad:g}")
            print(
                f"  · {rr.nombre_receta} x{rr.porciones:g}"
                + (f" +[{', '.join(ex_parts)}]" if ex_parts else "")
            )
        if len(recs) > 10:
            print(f"  … +{len(recs) - 10} más")
        sueltos = [ln for ln in d.lineas if ln.es_extra]
        # productos solo-extra (no en base de ninguna receta del registro) ≈ líneas con es_extra
        print(f"  lineas marcadas extra (agregado): {len(sueltos)}")


if __name__ == "__main__":
    main()
