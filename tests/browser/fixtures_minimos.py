"""Fixture mínima para browser E2E (nunca el demo canónico)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from decimal import Decimal

from app.core.auth.passwords import hash_password
from app.core.models import (
    AppData,
    CategoriaReceta,
    ConfiguracionHotel,
    IngredienteReceta,
    LoteStock,
    Producto,
    Proveedor,
    Receta,
    RelacionProductoProveedor,
    ResponsableMerma,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.data.serializers import appdata_to_dict, save_json

# Credenciales solo para fixture temporal de UI (no producción).
PASS_DIR = "UiTestPass1"
PASS_ADM = "UiTestPass1"
PASS_REST = "UiTestPass1"

LOGIN_DIR = "dir_ui"
LOGIN_ADM = "adm_ui"
LOGIN_REST = "rest_ui"


def build_browser_fixture(*, hoy: date | None = None) -> AppData:
    hoy = hoy or date.today()
    pwd = hash_password(PASS_DIR)
    servicios_all = ["desayuno", "comida", "cena", "bebidas"]
    leche = Producto(
        "bp_leche",
        "Leche UI",
        UnidadProducto.L,
        stock_minimo=1.0,
        activo=True,
        servicios_disponibles=["desayuno", "comida"],
    )
    avena = Producto(
        "bp_avena",
        "Avena UI",
        UnidadProducto.KG,
        stock_minimo=0.5,
        activo=True,
        servicios_disponibles=["desayuno"],
    )
    zumo = Producto(
        "bp_zumo",
        "Zumo UI",
        UnidadProducto.L,
        stock_minimo=1.0,
        activo=True,
        es_bebida=True,
        servicios_disponibles=["desayuno", "bebidas"],
    )
    agua = Producto(
        "bp_agua",
        "Agua UI",
        UnidadProducto.L,
        stock_minimo=1.0,
        activo=True,
        es_bebida=True,
        servicios_disponibles=["bebidas", "comida", "cena"],
    )
    pan = Producto(
        "bp_pan",
        "Pan UI",
        UnidadProducto.UD,
        stock_minimo=5.0,
        activo=True,
        servicios_disponibles=["comida", "cena", "desayuno"],
    )
    caja = Producto(
        "bp_caja_zumo",
        "Caja zumo UI",
        UnidadProducto.UD,
        stock_minimo=0.0,
        activo=True,
        servicios_disponibles=[],
    )
    products = [leche, avena, zumo, agua, pan, caja]
    lotes = [
        LoteStock(
            "bl_leche", "bp_leche", 10.0, 20.0, 20.0,
            hoy - timedelta(days=2), hoy + timedelta(days=20), "ProveedorUI",
        ),
        LoteStock(
            "bl_avena", "bp_avena", 8.0, 5.0, 5.0,
            hoy - timedelta(days=3), hoy + timedelta(days=40), "ProveedorUI",
        ),
        LoteStock(
            "bl_zumo", "bp_zumo", 6.0, 10.0, 10.0,
            hoy - timedelta(days=1), hoy + timedelta(days=5), "ProveedorUI",
        ),
        LoteStock(
            "bl_agua", "bp_agua", 4.0, 30.0, 30.0,
            hoy - timedelta(days=1), hoy + timedelta(days=100), "ProveedorUI",
        ),
        LoteStock(
            "bl_pan", "bp_pan", 5.0, 40.0, 40.0,
            hoy - timedelta(days=1), hoy + timedelta(days=3), "ProveedorUI",
        ),
        # Caducado: para workbench caducidad
        LoteStock(
            "bl_exp", "bp_pan", 2.0, 5.0, 5.0,
            hoy - timedelta(days=10), hoy - timedelta(days=1), "ProveedorUI",
        ),
    ]
    recetas = [
        Receta(
            "br_porridge",
            "Porridge UI",
            [
                IngredienteReceta("bp_leche", 0.5),
                IngredienteReceta("bp_avena", 0.25),
            ],
            CategoriaReceta.DESAYUNO,
            servicios_disponibles=["desayuno"],
            porciones_estandar=4.0,
            activo=True,
        ),
        Receta(
            "br_tostada",
            "Tostada UI",
            [IngredienteReceta("bp_pan", 1.0)],
            CategoriaReceta.COMIDA,
            servicios_disponibles=["comida", "cena"],
            porciones_estandar=1.0,
            activo=True,
        ),
    ]
    usuarios = [
        Usuario("bu_dir", "Dir UI", RolUsuario.DIRECCION, True, LOGIN_DIR, pwd),
        Usuario(
            "bu_adm",
            "Adm UI",
            RolUsuario.ADMINISTRACION,
            True,
            LOGIN_ADM,
            hash_password(PASS_ADM),
        ),
        Usuario(
            "bu_rest",
            "Rest UI",
            RolUsuario.RESTAURANTE,
            True,
            LOGIN_REST,
            hash_password(PASS_REST),
        ),
    ]
    proveedor = Proveedor("bprov1", "Proveedor UI Test", activo=True)
    relacion = RelacionProductoProveedor(
        id="brel1",
        producto_id="bp_caja_zumo",
        proveedor_id="bprov1",
        proveedor_nombre_snapshot="Proveedor UI Test",
        unidad_compra="Caja",
        factor_compra=Decimal("6"),
        activo=True,
    )
    return AppData(
        productos=products,
        lotes=lotes,
        recetas=recetas,
        usuarios=usuarios,
        configuracion=ConfiguracionHotel(
            nombre_establecimiento="Hotel UI Test",
            moneda="EUR",
            simbolo_moneda="€",
        ),
        usuario_actual_id="bu_dir",
        responsables_merma=[ResponsableMerma("brm1", "Cocina UI", True)],
        proveedores=[proveedor],
        relaciones_producto_proveedor=[relacion],
    )


def write_browser_fixture(path: Path, data: AppData | None = None) -> AppData:
    payload = data or build_browser_fixture()
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json(path, appdata_to_dict(payload))
    return payload
