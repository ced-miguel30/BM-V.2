"""Fase 6B — ubicaciones (catálogo + relación producto, sin stock por ubicación).

Ejecutar:

    py -m unittest tests.test_fase6b_ubicaciones -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application import espacios as esp
from app.core.application.context import AppContext, build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    Categoria,
    Departamento,
    LoteStock,
    Producto,
    Subcategoria,
    Ubicacion,
    UnidadProducto,
)
from app.core.services import catalogo_service as cat
from app.core.services.diagnostico_service import generar_diagnostico
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _ctx(data: AppData) -> AppContext:
    return build_app_context(uow=InMemoryUnitOfWork(data))


def _stock_total(data: AppData, producto_id: str) -> float:
    return sum(
        l.cantidad_restante for l in data.lotes if l.producto_id == producto_id
    )


class TestFase6BUbicaciones(unittest.TestCase):
    def test_01_json_antiguo_sin_ubicaciones(self) -> None:
        payload = {
            "meta": {},
            "productos": [{"id": "p1", "nombre": "Pan", "unidad": "Ud"}],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(data.ubicaciones, [])

    def test_02_producto_antiguo_sin_ubicacion_ids(self) -> None:
        payload = {
            "meta": {},
            "productos": [
                {
                    "id": "p1",
                    "nombre": "Pan",
                    "unidad": "Ud",
                    "departamento_ids": ["dep01"],
                }
            ],
            "departamentos": [{"id": "dep01", "nombre": "Cocina", "activo": True}],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(data.productos[0].ubicacion_ids, [])
        self.assertEqual(data.productos[0].departamento_ids, ["dep01"])

    def test_03_roundtrip_catalogo(self) -> None:
        data = AppData(ubicaciones=[Ubicacion("ubi01", "Economato", True)])
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.ubicaciones[0].id, "ubi01")
        self.assertEqual(back.ubicaciones[0].nombre, "Economato")

    def test_04_roundtrip_producto_una_ubicacion(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1", "Leche", UnidadProducto.L, ubicacion_ids=["ubi01"],
                )
            ],
            ubicaciones=[Ubicacion("ubi01", "Cámara")],
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.productos[0].ubicacion_ids, ["ubi01"])

    def test_05_roundtrip_varias_ubicaciones(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1",
                    "Aceite",
                    UnidadProducto.L,
                    ubicacion_ids=["ubi01", "ubi02"],
                )
            ],
            ubicaciones=[
                Ubicacion("ubi01", "Economato"),
                Ubicacion("ubi02", "Cocina"),
            ],
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.productos[0].ubicacion_ids, ["ubi01", "ubi02"])

    def test_06_creacion_duplicada(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        self.assertTrue(cat.crear_ubicacion("Bar", codigo="UBI-BAR", ctx=ctx).ok)
        self.assertFalse(cat.crear_ubicacion("Bar", codigo="UBI-BAR2", ctx=ctx).ok)

    def test_07_duplicado_ignorando_mayusculas(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        self.assertTrue(cat.crear_ubicacion("Cámara", codigo="UBI-CAM", ctx=ctx).ok)
        self.assertFalse(cat.crear_ubicacion("  cámara  ", codigo="UBI-CAM2", ctx=ctx).ok)

    def test_08_renombrado_duplicado(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        cat.crear_ubicacion("A", codigo="UA", ctx=ctx)
        cat.crear_ubicacion("B", codigo="UB", ctx=ctx)
        a_id = data.ubicaciones[0].id
        self.assertFalse(cat.renombrar_ubicacion(a_id, "B", ctx=ctx).ok)

    def test_09_renombrado_conserva_id(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        cat.crear_ubicacion("Antes", codigo="UANTES", ctx=ctx)
        uid = data.ubicaciones[0].id
        self.assertTrue(cat.renombrar_ubicacion(uid, "Después", ctx=ctx).ok)
        self.assertEqual(data.ubicaciones[0].id, uid)
        self.assertEqual(data.ubicaciones[0].nombre, "Después")

    def test_10_desactivar_no_elimina(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        cat.crear_ubicacion("Taller", codigo="UTALLER", ctx=ctx)
        uid = data.ubicaciones[0].id
        self.assertTrue(cat.desactivar_ubicacion(uid, ctx=ctx).ok)
        self.assertEqual(len(data.ubicaciones), 1)
        self.assertFalse(data.ubicaciones[0].activo)

    def test_11_desactivar_no_cambia_stock(self) -> None:
        data = AppData(
            productos=[Producto("p1", "Pan", UnidadProducto.UD)],
            lotes=[
                LoteStock("l1", "p1", 10.0, 5.0, 5.0, None, None, None, None),
            ],
            ubicaciones=[Ubicacion("ubi01", "Economato", True)],
        )
        antes = _stock_total(data, "p1")
        ctx = _ctx(data)
        cat.desactivar_ubicacion("ubi01", ctx=ctx)
        self.assertEqual(_stock_total(data, "p1"), antes)
        self.assertEqual(data.lotes[0].cantidad_restante, 5.0)

    def test_12_producto_conserva_ubicacion_inactiva(self) -> None:
        data = AppData(
            ubicaciones=[Ubicacion("ubi01", "Vieja", False)],
            productos=[
                Producto("p1", "Pan", UnidadProducto.UD, ubicacion_ids=["ubi01"]),
            ],
        )
        opts = cat.opciones_ubicacion_asignacion(data, conservar_ids=["ubi01"])
        self.assertEqual({u.id for u in opts}, {"ubi01"})
        r = cat.validar_referencias_producto(
            data,
            categoria_id=None,
            subcategoria_id=None,
            departamento_ids=[],
            ubicacion_ids=["ubi01"],
            ubicacion_ids_anteriores=["ubi01"],
        )
        self.assertTrue(r.ok)

    def test_13_ubicacion_inactiva_no_nueva_asignacion(self) -> None:
        data = AppData(
            ubicaciones=[Ubicacion("ubi01", "Vieja", False)],
        )
        r = cat.validar_referencias_producto(
            data,
            categoria_id=None,
            subcategoria_id=None,
            departamento_ids=[],
            ubicacion_ids=["ubi01"],
            ubicacion_ids_anteriores=[],
        )
        self.assertFalse(r.ok)
        opts = cat.opciones_ubicacion_asignacion(data)
        self.assertEqual(opts, [])

    def test_14_producto_ubicacion_inexistente(self) -> None:
        data = AppData()
        r = cat.validar_referencias_producto(
            data,
            categoria_id=None,
            subcategoria_id=None,
            departamento_ids=[],
            ubicacion_ids=["ubi_x"],
        )
        self.assertFalse(r.ok)

    def test_15_ids_repetidos_en_producto(self) -> None:
        data = AppData(ubicaciones=[Ubicacion("ubi01", "Bar")])
        r = cat.validar_referencias_producto(
            data,
            categoria_id=None,
            subcategoria_id=None,
            departamento_ids=[],
            ubicacion_ids=["ubi01", "ubi01"],
        )
        self.assertFalse(r.ok)

    def test_16_referencia_huerfana_carga_y_diagnostica(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1", "X", UnidadProducto.UD, ubicacion_ids=["ubi_fantasma"],
                )
            ]
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.productos[0].ubicacion_ids, ["ubi_fantasma"])
        self.assertEqual(
            cat.etiqueta_ubicacion(back, "ubi_fantasma"),
            cat.ETIQUETA_REF_NO_ENCONTRADA,
        )
        resumen = generar_diagnostico(back)
        self.assertTrue(
            any("ubicación inexistente" in i for i in resumen.incidencias_catalogo)
        )

    def test_17_diagnostico_no_modifica_datos(self) -> None:
        data = AppData(
            productos=[
                Producto("p1", "X", UnidadProducto.UD, ubicacion_ids=["ubi_x"]),
            ]
        )
        antes = copy.deepcopy(appdata_to_dict(data))
        generar_diagnostico(data)
        self.assertEqual(appdata_to_dict(data), antes)

    def test_18_campos_6a_intactos(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1",
                    "Leche",
                    UnidadProducto.L,
                    categoria_inventario="Lácteos",
                    categoria_id="cat01",
                    subcategoria_id="sub01",
                    departamento_ids=["dep01"],
                    ubicacion_ids=["ubi01"],
                )
            ],
            departamentos=[Departamento("dep01", "Cocina")],
            categorias=[Categoria("cat01", "Lácteos")],
            subcategorias=[Subcategoria("sub01", "Leches", "cat01")],
            ubicaciones=[Ubicacion("ubi01", "Cámara")],
        )
        back = dict_to_appdata(appdata_to_dict(data))
        p = back.productos[0]
        self.assertEqual(p.categoria_inventario, "Lácteos")
        self.assertEqual(p.categoria_id, "cat01")
        self.assertEqual(p.subcategoria_id, "sub01")
        self.assertEqual(p.departamento_ids, ["dep01"])
        self.assertEqual(p.ubicacion_ids, ["ubi01"])

    def test_19_matriz_espacios_f5_intacta(self) -> None:
        self.assertEqual(
            esp.SECCIONES_POR_ESPACIO[esp.ESPACIO_INVENTARIO],
            (esp.SECCION_STOCK, esp.SECCION_RECETAS),
        )
        self.assertEqual(esp.ESPACIO_DEFAULT, esp.ESPACIO_GESTOR)

    def test_20_asignar_ubicacion_no_crea_lotes(self) -> None:
        data = AppData(
            productos=[Producto("p1", "Pan", UnidadProducto.UD)],
            ubicaciones=[Ubicacion("ubi01", "Economato")],
        )
        n_lotes = len(data.lotes)
        data.productos[0].ubicacion_ids = ["ubi01"]
        self.assertEqual(len(data.lotes), n_lotes)

    def test_21_fifo_modulo_no_importado_por_catalogo(self) -> None:
        path = ROOT / "app" / "core" / "services" / "catalogo_service.py"
        src = path.read_text(encoding="utf-8")
        self.assertNotIn("inventory_batch_service", src)
        self.assertNotIn("aplicar_descuento", src)

    def test_22_stock_total_no_cambia_al_modificar_ubicacion_ids(self) -> None:
        data = AppData(
            productos=[
                Producto("p1", "Pan", UnidadProducto.UD, ubicacion_ids=[]),
            ],
            lotes=[
                LoteStock("l1", "p1", 20.0, 10.0, 8.0, None, None, None, None),
            ],
            ubicaciones=[Ubicacion("ubi01", "Economato")],
        )
        antes = _stock_total(data, "p1")
        r = cat.validar_referencias_producto(
            data,
            categoria_id=None,
            subcategoria_id=None,
            departamento_ids=[],
            ubicacion_ids=["ubi01"],
        )
        self.assertTrue(r.ok)
        data.productos[0].ubicacion_ids = ["ubi01"]
        self.assertEqual(_stock_total(data, "p1"), antes)
        self.assertEqual(antes, 8.0)


if __name__ == "__main__":
    unittest.main()
