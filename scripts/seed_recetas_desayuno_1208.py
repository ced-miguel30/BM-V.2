"""Carga recetas (docs/recetas.xlsx + Cortado) y registra DESAYUNO 1208 en datos hotel.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\seed_recetas_desayuno_1208.py
"""

from __future__ import annotations

import os
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

from app.bootstrap import configure_for_flet, reset_container, get_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.models import CategoriaReceta, IngredienteReceta
from app.core.services import desayuno_service as des
from app.core.services import receta_service as rec_svc
from app.core.services import stock_service as stock_svc
from app.core.services.inventory_batch_service import stock_disponible
from app.core.services.unidad_service import convertir_a_unidad_producto

ROOT = Path(__file__).resolve().parents[1]
HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
FECHA = date(2026, 8, 12)
CLAVE = "desayuno-1208-seed-v1"


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


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _ing(data, producto_id: str, cantidad: float, unidad: str | None = None) -> IngredienteReceta:
    prod = next(p for p in data.productos if p.id == producto_id)
    qty = float(cantidad)
    if unidad is None or unidad == prod.unidad.value:
        return IngredienteReceta(producto_id, qty, qty, prod.unidad.value)

    u = "gr" if unidad == "g" else unidad
    nativa: float
    if u in ("ml", "cl", "L") and prod.unidad.value == "Ud":
        # Brik/botella ≈ 1 L → fracción de Ud.
        nativa = round(qty * {"ml": 0.001, "cl": 0.01, "L": 1.0}[u], 6)
    elif u in ("mg", "gr", "Kg") and prod.unidad.value == "Ud":
        pack_kg = PACK_KG.get(producto_id)
        gramos = qty * {"mg": 0.001, "gr": 1.0, "Kg": 1000.0}[u]
        if pack_kg and pack_kg > 0:
            nativa = round(gramos / (pack_kg * 1000.0), 6)
        else:
            nativa = qty
    else:
        nativa = convertir_a_unidad_producto(qty, u, prod.unidad)

    if nativa <= 0:
        nativa = qty
    return IngredienteReceta(producto_id, nativa, qty, u)


# Peso aproximado del pack cuando el producto está en Ud pero el pack tiene masa.
PACK_KG: dict[str, float] = {
    "p117": 3.0,  # champiñón laminado 3kg
    "p286": 3.0,  # alubia tomate 3kg
    "p87": 1.0,  # panko 1kg
    "p207": 0.5,  # pan rallado 500g
    "p126": 1.0,  # miel 1kg
    "p165": 1.0,  # soja 1L ~1kg dens.
    "p16": 1.8,  # teriyaki botella
    "p108": 1.0,  # salsa brava approx
    "p226": 0.38,  # crema modena
    "p206": 0.25,  # AOVE 250ml
    "p109": 1.0,  # arroz 1kg
    "p304": 3.0,  # cóctel frutas
    "p185": 0.2,  # espinacas bolsa ~200g
    "p60": 0.25,  # lechuga pieza ~250g
    "p181": 0.4,  # romana
    "p66": 0.18,  # plátano
    "p24": 0.5,  # nachos bolsa 500g
    "p43": 0.45,  # mayonesa botella ~450g
    "p405": 2.5,  # frutos bosque pack
}


def _ensure_stock(data, producto_id: str, minimo: float) -> None:
    actual = stock_disponible(data, producto_id)
    if actual >= minimo:
        return
    falta = max(minimo - actual, minimo * 0.25, 1.0)
    precio = max(1.0, round(falta * 2.5, 2))
    r = stock_svc.registrar_lote(
        producto_id,
        precio_total=precio,
        cantidad=round(falta, 3),
        fecha_compra=FECHA,
        marca_proveedor="SEED-1208",
    )
    print(f"  lote {producto_id}: +{falta:g} -> {r.ok} {r.mensaje}")


def _crear_receta(
    data,
    nombre: str,
    ingredientes: list[IngredienteReceta],
    *,
    categoria: CategoriaReceta,
    servicios: list[str],
    porciones: float = 1.0,
) -> str | None:
    existente = next(
        (r for r in data.recetas if _norm(r.nombre) == _norm(nombre) and getattr(r, "activo", True)),
        None,
    )
    if existente:
        print(f"  skip receta existente: {existente.id} {existente.nombre}")
        return existente.id
    r = rec_svc.crear_receta(
        nombre,
        ingredientes,
        categoria,
        servicios_disponibles=servicios,
        porciones_estandar=porciones,
    )
    print(f"  crear «{nombre}»: {r.ok} {r.mensaje}")
    if not r.ok:
        return None
    data = get_container().app_data_store.get()
    rec = next(x for x in data.recetas if _norm(x.nombre) == _norm(nombre))
    return rec.id


def build_catalog(data) -> dict[str, str]:
    """Alias lógico -> producto_id."""
    # IDs estables del catálogo hotel (import PRECIO).
    return {
        "huevo": "p48",
        "huevo_liq": "p46",
        "bacon": "p14",
        "salchicha": "p20",
        "hashbrown": "p29",
        "cafe_illy": "p266",
        "leche_entera": "p127",
        "leche_desnatada": "p128",
        "pan_tostada": "p03",  # mini chapata
        "pan_molde": "p09",
        "pan_integral": "p11",
        "pan_bao": "p26",
        "pan_brioche": "p332",
        "salmon": "p32",
        "aguacate": "b05",
        "tomate": "p51",
        "cherry": "p52",
        "espinaca": "p185",
        "jamon_cocido": "p102",
        "queso_loncha": "p169",
        "queso_cheddar": "p44",
        "queso_fresco": "p38",
        "queso_cabra": "p49",
        "champi": "p117",
        "judias": "p286",
        "mantequilla_porc": "p13",  # 8g
        "mantequilla": "p152",
        "chorizo": "p146",
        "lechuga": "p181",
        "cebolla_morada": "p58",
        "guacamole": "p15",
        "soja": "p165",
        "teriyaki": "p16",
        "pollo": "p31",
        "patata_frita": "p12",
        "salsa_brava": "p108",
        "ajo": "p63",
        "calamar": "p292",
        "langostino": "p36",
        "bacalao": "p167",
        "helado_vainilla": "p86",
        "helado_chocolate": "b07",
        "helado_fresa": "p194",
        "nata": "p210",
        "fruta_almibar": "p304",
        "fresa": "p306",
        "nuez": "p284",
        "miel": "p126",
        "modena": "p226",
        "aceite": "p206",
        "mango": "p25",
        "pepino": "p55",
        "zanahoria": "p54",
        "pina": "p68",
        "arroz": "p109",
        "tiramisu": "p394",
        "tarta_queso": "p173",
        "brownie": "p30",
        "platano": "p66",
        "panko": "p87",
        "harina": "p214",
        "mayonesa": "p43",
        "nachos": "p24",
        "lima": "p67",
        "gamba": "p36",  # proxy langostino/gamba
        "croqueta_jamon": "p298",
        "frutos_rojos": "p405",
    }


def recipes_spec(C: dict[str, str], data) -> list[tuple]:
    """Lista (nombre, categoria, servicios, ings)."""
    D = CategoriaReceta.DESAYUNO
    M = CategoriaReceta.COMIDA
    B = CategoriaReceta.BEBIDAS
    des = ["desayuno"]
    com = ["comida"]
    beb = ["desayuno", "comida", "cena", "bebidas"]

    def I(key: str, qty: float, unit: str | None = None) -> IngredienteReceta:
        return _ing(data, C[key], qty, unit)

    specs: list[tuple] = []

    # ——— Desayunos (libro) ———
    specs += [
        ("Huevo frito", D, des, [I("huevo", 1, "Ud")]),
        ("Huevo pochado", D, des, [I("huevo", 1, "Ud")]),
        ("Huevo cocido", D, des, [I("huevo", 1, "Ud")]),
        ("Huevos revueltos (2)", D, des, [I("huevo", 2, "Ud")]),
        ("Tortilla de huevo", D, des, [I("huevo_liq", 30, "ml")]),
        (
            "Tostada del dia",
            D,
            des,
            [I("pan_tostada", 1, "Ud")],
        ),
        (
            "Tostada francesa",
            D,
            des,
            [
                I("pan_tostada", 1, "Ud"),
                I("huevo_liq", 5, "ml"),
                I("mantequilla", 15, "gr"),
                I("frutos_rojos", 10, "gr"),
            ],
        ),
        (
            "Tostada champinones",
            D,
            des,
            [
                I("pan_tostada", 1, "Ud"),
                I("huevo", 1, "Ud"),
                I("espinaca", 15, "gr"),
                I("champi", 20, "gr"),
            ],
        ),
        (
            "Desayuno ingles",
            D,
            des,
            [
                I("cherry", 40, "gr"),  # 4 cherry ~10g
                I("judias", 20, "gr"),
                I("champi", 20, "gr"),
                I("salchicha", 50, "gr"),
                I("hashbrown", 70, "gr"),
                I("bacon", 15, "gr"),
            ],
        ),
        (
            "Sandwich mixto",
            D,
            des,
            [
                I("pan_tostada", 2, "Ud"),
                I("jamon_cocido", 15, "gr"),
                I("queso_loncha", 20, "gr"),
            ],
        ),
        (
            "Sandwich de la casa",
            D,
            des,
            [
                I("pan_tostada", 2, "Ud"),
                I("tomate", 40, "gr"),
                I("queso_fresco", 30, "gr"),
                I("jamon_cocido", 15, "gr"),
            ],
        ),
        (
            "Sandwich vegetal",
            D,
            des,
            [
                I("pan_tostada", 2, "Ud"),
                I("huevo", 1, "Ud"),
                I("espinaca", 15, "gr"),
            ],
        ),
        # Cortado (no estaba en Excel): espresso Illy + leche entera
        (
            "Cortado",
            B,
            beb,
            [
                I("cafe_illy", 18, "gr"),
                I("leche_entera", 60, "ml"),
            ],
        ),
        # Variantes del servicio 12/08
        (
            "Pan aguacate y salmon",
            D,
            des,
            [
                I("pan_tostada", 1, "Ud"),
                I("aguacate", 60, "gr"),
                I("salmon", 40, "gr"),
            ],
        ),
        (
            "Pan y salmon",
            D,
            des,
            [I("pan_tostada", 1, "Ud"), I("salmon", 40, "gr")],
        ),
        (
            "Huevo revuelto y pan",
            D,
            des,
            [I("huevo", 1, "Ud"), I("pan_tostada", 1, "Ud")],
        ),
        (
            "Tortilla jamon y queso",
            D,
            des,
            [
                I("huevo_liq", 30, "ml"),
                I("jamon_cocido", 15, "gr"),
                I("queso_loncha", 20, "gr"),
            ],
        ),
        (
            "Huevos cocidos bacon y judias",
            D,
            des,
            [
                I("huevo", 2, "Ud"),
                I("bacon", 15, "gr"),
                I("judias", 20, "gr"),
            ],
        ),
        (
            "Huevos fritos bacon y aguacate",
            D,
            des,
            [
                I("huevo", 2, "Ud"),
                I("bacon", 15, "gr"),
                I("aguacate", 60, "gr"),
            ],
        ),
        (
            "Tostada champinones y cherry",
            D,
            des,
            [
                I("pan_tostada", 1, "Ud"),
                I("huevo", 1, "Ud"),
                I("espinaca", 15, "gr"),
                I("champi", 20, "gr"),
                I("cherry", 30, "gr"),
            ],
        ),
        (
            "Desayuno ingles sin champi sin huevo",
            D,
            des,
            [
                I("cherry", 40, "gr"),
                I("judias", 20, "gr"),
                I("salchicha", 50, "gr"),
                I("hashbrown", 70, "gr"),
                I("bacon", 15, "gr"),
            ],
        ),
        (
            "Huevo pochado con pan integral",
            D,
            des,
            [
                I("huevo", 1, "Ud"),
                I("pan_integral", 0.05, "Ud"),  # ~1 rebanada de molde 1kg
            ],
        ),
        (
            "Huevo revuelto pan salchicha bacon",
            D,
            des,
            [
                I("huevo", 1, "Ud"),
                I("pan_tostada", 1, "Ud"),
                I("salchicha", 50, "gr"),
                I("bacon", 15, "gr"),
            ],
        ),
        (
            "Tortilla jamon queso tomate",
            D,
            des,
            [
                I("huevo_liq", 30, "ml"),
                I("jamon_cocido", 15, "gr"),
                I("queso_loncha", 20, "gr"),
                I("tomate", 30, "gr"),
            ],
        ),
        (
            "Tortilla queso chorizo y salchicha",
            D,
            des,
            [
                I("huevo_liq", 30, "ml"),
                I("queso_loncha", 20, "gr"),
                I("chorizo", 25, "gr"),
                I("salchicha", 50, "gr"),
            ],
        ),
        (
            "Huevos revueltos bacon y judias",
            D,
            des,
            [
                I("huevo", 2, "Ud"),
                I("bacon", 15, "gr"),
                I("judias", 20, "gr"),
            ],
        ),
        (
            "Tostada con huevos revueltos",
            D,
            des,
            [I("pan_tostada", 1, "Ud"), I("huevo", 2, "Ud")],
        ),
        (
            "Salchicha bacon y huevo frito",
            D,
            des,
            [
                I("salchicha", 50, "gr"),
                I("bacon", 15, "gr"),
                I("huevo", 1, "Ud"),
            ],
        ),
        (
            "Tortilla bacon hashbrown tomate",
            D,
            des,
            [
                I("huevo_liq", 30, "ml"),
                I("bacon", 15, "gr"),
                I("hashbrown", 140, "gr"),  # 2 hashbrown
                I("tomate", 30, "gr"),
            ],
        ),
        ("Rodajas de tomate (2)", D, des, [I("tomate", 60, "gr")]),
        (
            "Tostada huevo revuelto jamon queso",
            D,
            des,
            [
                I("pan_tostada", 1, "Ud"),
                I("huevo", 2, "Ud"),
                I("jamon_cocido", 15, "gr"),
                I("queso_loncha", 20, "gr"),
            ],
        ),
        (
            "Tortilla espinaca y tomate",
            D,
            des,
            [
                I("huevo_liq", 30, "ml"),
                I("espinaca", 20, "gr"),
                I("tomate", 30, "gr"),
            ],
        ),
        (
            "Tortilla queso y salchicha",
            D,
            des,
            [
                I("huevo_liq", 30, "ml"),
                I("queso_loncha", 20, "gr"),
                I("salchicha", 50, "gr"),
            ],
        ),
        ("Dos huevos pochados", D, des, [I("huevo", 2, "Ud")]),
        ("Dos huevos cocidos", D, des, [I("huevo", 2, "Ud")]),
        ("Dos huevos revueltos", D, des, [I("huevo", 2, "Ud")]),
        ("Cuatro huevos revueltos", D, des, [I("huevo", 4, "Ud")]),
    ]

    # ——— Comidas (libro) con medidas estándar ———
    specs += [
        ("Plato pequeno de fruta", M, com, [I("fresa", 350, "gr")]),
        ("Fruta en almibar", M, com, [I("fruta_almibar", 375, "gr")]),
        ("Plato embutido", M, com, [I("jamon_cocido", 100, "gr")]),  # 10 lonchas ~10g
        (
            "Pan bao",
            M,
            com,
            [
                I("pollo", 180, "gr"),
                I("pan_bao", 1, "Ud"),
                I("lechuga", 70, "gr"),
                I("cebolla_morada", 20, "gr"),
                I("teriyaki", 35, "gr"),
                I("soja", 20, "gr"),
            ],
        ),
        (
            "Sandwich club",
            M,
            com,
            [
                I("bacon", 30, "gr"),
                I("lechuga", 25, "gr"),
                I("mayonesa", 40, "gr"),
                I("huevo", 1, "Ud"),
                I("queso_loncha", 40, "gr"),
                I("tomate", 35, "gr"),
                I("pan_tostada", 3, "Ud"),
            ],
        ),
        ("Patatas fritas", M, com, [I("patata_frita", 150, "gr")]),  # 2 puñados
        ("Papas arrugadas", M, com, [I("patata_frita", 300, "gr")]),  # 6 papas ~50g
        ("Croquetas jamon serrano", M, com, [I("croqueta_jamon", 120, "gr")]),
        (
            "Nachos con guacamole",
            M,
            com,
            [
                I("nachos", 70, "gr"),
                I("guacamole", 50, "gr"),
                I("cebolla_morada", 40, "gr"),
                I("tomate", 40, "gr"),
                I("lima", 15, "gr"),
            ],
        ),
        (
            "Ensalada queso de cabra y fresa",
            M,
            com,
            [
                I("lechuga", 70, "gr"),
                I("queso_cabra", 30, "gr"),
                I("nuez", 20, "gr"),
                I("fresa", 75, "gr"),  # 5 fresas
                I("miel", 15, "gr"),
                I("modena", 10, "gr"),
                I("aceite", 10, "gr"),
            ],
        ),
        (
            "Cocktail de gambas",
            M,
            com,
            [
                I("gamba", 90, "gr"),  # 6 × 15g
                I("pina", 40, "gr"),
                I("aguacate", 40, "gr"),
                I("lechuga", 40, "gr"),
            ],
        ),
        (
            "Ensalada cesar",
            M,
            com,
            [
                I("lechuga", 70, "gr"),
                I("bacon", 30, "gr"),
                I("cherry", 50, "gr"),
                I("queso_loncha", 30, "gr"),
                I("pan_tostada", 1, "Ud"),
            ],
        ),
        (
            "Tartar salmon con aguacate",
            M,
            com,
            [
                I("salmon", 70, "gr"),
                I("aguacate", 80, "gr"),
                I("soja", 10, "gr"),
            ],
        ),
        (
            "Poke bowl",
            M,
            com,
            [
                I("arroz", 150, "gr"),  # 1 cuenco
                I("salmon", 40, "gr"),
                I("mango", 45, "gr"),
                I("zanahoria", 45, "gr"),
                I("pepino", 45, "gr"),
            ],
        ),
        (
            "Ensalada aguacate tomate y jamon",
            M,
            com,
            [
                I("aguacate", 150, "gr"),
                I("tomate", 120, "gr"),
                I("jamon_cocido", 50, "gr"),
            ],
        ),
        (
            "Huevos rotos",
            M,
            com,
            [
                I("patata_frita", 150, "gr"),
                I("jamon_cocido", 40, "gr"),
                I("huevo", 2, "Ud"),
            ],
        ),
        (
            "Hamburguesa",
            M,
            com,
            [
                I("pollo", 180, "gr"),  # proxy carne si no hay burger meat stock
                I("pan_brioche", 1, "Ud"),
                I("aguacate", 40, "gr"),
                I("queso_cabra", 45, "gr"),
                I("bacon", 20, "gr"),
                I("lechuga", 20, "gr"),
                I("salsa_brava", 15, "gr"),
                I("patata_frita", 150, "gr"),
            ],
        ),
        (
            "Verduras a la parrilla",
            M,
            com,
            [
                I("zanahoria", 80, "gr"),
                I("pepino", 40, "gr"),
                I("tomate", 80, "gr"),
                I("cebolla_morada", 40, "gr"),
            ],
        ),
        (
            "Gambas al ajillo",
            M,
            com,
            [
                I("aceite", 20, "gr"),
                I("ajo", 5, "gr"),
                I("gamba", 90, "gr"),
            ],
        ),
        (
            "Calamares a la romana",
            M,
            com,
            [
                I("calamar", 100, "gr"),
                I("huevo", 1, "Ud"),
                I("panko", 30, "gr"),
            ],
        ),
        (
            "Langostinos crujientes",
            M,
            com,
            [
                I("langostino", 90, "gr"),
                I("huevo", 1, "Ud"),
                I("panko", 30, "gr"),
                I("lechuga", 20, "gr"),
                I("cherry", 20, "gr"),
            ],
        ),
        (
            "Bacalao en tempura",
            M,
            com,
            [
                I("bacalao", 120, "gr"),
                I("harina", 30, "gr"),
                I("lechuga", 20, "gr"),
                I("cherry", 20, "gr"),
            ],
        ),
        ("Bola de helado", M, com, [I("helado_vainilla", 0.08, "Ud")]),  # ~1 bola
        (
            "Banana split",
            M,
            com,
            [
                I("helado_vainilla", 0.08, "Ud"),
                I("helado_chocolate", 0.08, "Ud"),
                I("helado_fresa", 80, "gr"),
                I("platano", 1, "Ud"),
                I("nata", 30, "ml"),
            ],
        ),
        ("Tiramisu", M, com, [I("tiramisu", 1, "Ud")]),
        ("Brownie con helado", M, com, [I("brownie", 1, "Ud"), I("helado_vainilla", 0.08, "Ud")]),
        (
            "Tarta de queso con helado",
            M,
            com,
            [I("tarta_queso", 1, "Ud"), I("helado_vainilla", 0.08, "Ud")],
        ),
    ]
    return specs


# Mapeo líneas DESAYUNO 1208 -> nombre de receta (1 por comensal)
ORDER_MAP: list[str] = [
    "Dos huevos revueltos",  # 2 HUEVOS REVUELTOS
    "Pan aguacate y salmon",
    "Cuatro huevos revueltos",
    "Pan y salmon",
    "Tostada del dia",
    "Huevo revuelto y pan",
    "Cortado",
    "Tortilla jamon y queso",
    "Huevos cocidos bacon y judias",
    "Huevos fritos bacon y aguacate",
    "Huevos fritos bacon y aguacate",
    "Sandwich vegetal",
    "Tostada champinones y cherry",
    "Desayuno ingles sin champi sin huevo",
    "Huevo pochado con pan integral",
    "Huevo revuelto pan salchicha bacon",
    "Tortilla jamon queso tomate",
    "Tortilla queso chorizo y salchicha",
    "Huevos revueltos bacon y judias",
    "Dos huevos cocidos",
    "Tostada con huevos revueltos",
    "Salchicha bacon y huevo frito",
    "Dos huevos cocidos",
    "Tostada del dia",
    "Huevo cocido",
    "Tortilla bacon hashbrown tomate",
    "Rodajas de tomate (2)",
    "Tostada huevo revuelto jamon queso",
    "Tostada huevo revuelto jamon queso",
    "Huevo cocido",
    "Tortilla espinaca y tomate",
    "Dos huevos pochados",
    "Sandwich mixto",
    "Tortilla queso y salchicha",
]


def main() -> None:
    assert HOTEL.exists(), f"No existe {HOTEL}"
    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()
    data = get_container().app_data_store.get()
    print(f"Hotel JSON: {HOTEL}")
    print(f"productos={len(data.productos)} recetas={len(data.recetas)} desayunos={len(data.desayunos)}")

    C = build_catalog(data)
    missing = [k for k, v in C.items() if not any(p.id == v for p in data.productos)]
    if missing:
        raise SystemExit(f"Productos faltantes en catálogo: {missing}")

    print("\n== Crear / asegurar recetas ==")
    name_to_id: dict[str, str] = {}
    for nombre, cat, servicios, ings in recipes_spec(C, data):
        # re-bind ings against fresh data each time (ids stable)
        data = get_container().app_data_store.get()
        ings2 = []
        for ing in ings:
            ings2.append(
                _ing(
                    data,
                    ing.producto_id,
                    ing.cantidad_presentacion or ing.cantidad,
                    ing.unidad_presentacion,
                )
            )
        rid = _crear_receta(data, nombre, ings2, categoria=cat, servicios=servicios)
        if rid:
            name_to_id[nombre] = rid

    # Stock mínimo para el desayuno del día
    print("\n== Asegurar stock para desayuno ==")
    data = get_container().app_data_store.get()
    need = {
        C["huevo"]: 80,
        C["huevo_liq"]: 2,
        C["bacon"]: 1,
        C["salchicha"]: 2,
        C["hashbrown"]: 2,
        C["cafe_illy"]: 1,
        C["leche_entera"]: 5,
        C["pan_tostada"]: 40,
        C["pan_integral"]: 2,
        C["salmon"]: 1,
        C["aguacate"]: 2,
        C["tomate"]: 1,
        C["cherry"]: 1,
        C["espinaca"]: 2,
        C["jamon_cocido"]: 1,
        C["queso_loncha"]: 1,
        C["champi"]: 2,
        C["judias"]: 2,
        C["chorizo"]: 1,
        C["mantequilla"]: 1,
        C["frutos_rojos"]: 1,
        C["pollo"]: 2,
        C["pan_brioche"]: 5,
        C["aceite"]: 2,
        C["nata"]: 2,
        C["fruta_almibar"]: 2,
        C["tarta_queso"]: 2,
    }
    for pid, minimo in need.items():
        _ensure_stock(data, pid, minimo)
        data = get_container().app_data_store.get()

    print("\n== Registrar desayuno 12/08 ==")
    des.limpiar_cesta()
    for nombre in ORDER_MAP:
        rid = name_to_id.get(nombre)
        if not rid:
            # buscar por nombre en data
            data = get_container().app_data_store.get()
            rec = next((r for r in data.recetas if _norm(r.nombre) == _norm(nombre)), None)
            if not rec:
                raise SystemExit(f"Receta no encontrada para pedido: {nombre}")
            rid = rec.id
            name_to_id[nombre] = rid
        r = des.anadir_receta_a_cesta(rid, 1.0)
        if not r.ok:
            raise SystemExit(f"No se pudo añadir «{nombre}» a cesta: {r.mensaje}")

    n = len(ORDER_MAP)
    resultado = des.registrar_desayuno(
        FECHA,
        n,
        clave_idempotencia=CLAVE,
        observaciones="Seed DESAYUNO 1208.xlsx + recetas.xlsx (incl. Cortado)",
    )
    print(resultado.ok, resultado.mensaje, getattr(resultado, "codigo", ""))

    data = get_container().app_data_store.get()
    print(
        f"\nResumen final: recetas={len(data.recetas)} desayunos={len(data.desayunos)} "
        f"movimientos={len(getattr(data, 'movimientos', []) or [])}"
    )
    ult = [d for d in data.desayunos if getattr(d, "clave_idempotencia", None) == CLAVE]
    if ult:
        d = ult[-1]
        coste = sum(getattr(l, "coste", 0) or 0 for l in d.lineas)
        print(
            f"Desayuno {d.id} fecha={d.fecha} huespedes={d.num_huespedes} "
            f"lineas={len(d.lineas)} coste={coste:.2f}"
        )


if __name__ == "__main__":
    main()
