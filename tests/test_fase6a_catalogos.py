"""Fase 6A — catálogos departamentos / categorías / subcategorías.

Ejecutar:

    py -m unittest tests.test_fase6a_catalogos -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.context import AppContext, build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    Categoria,
    Departamento,
    Producto,
    Subcategoria,
    UnidadProducto,
)
from app.core.services import catalogo_service as cat
from app.core.services.diagnostico_service import generar_diagnostico
from app.core.application import espacios as esp
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _ctx(data: AppData) -> AppContext:
    return build_app_context(uow=InMemoryUnitOfWork(data))


class TestFase6ACatalogos(unittest.TestCase):
    def test_01_json_antiguo_sin_catalogos(self) -> None:
        payload = {
            "meta": {},
            "productos": [
                {
                    "id": "p1",
                    "nombre": "Pan",
                    "unidad": "Ud",
                    "categoria_inventario": "Panadería",
                }
            ],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(data.departamentos, [])
        self.assertEqual(data.categorias, [])
        self.assertEqual(data.subcategorias, [])
        self.assertIsNone(data.productos[0].categoria_id)
        self.assertIsNone(data.productos[0].subcategoria_id)
        self.assertEqual(data.productos[0].departamento_ids, [])
        self.assertEqual(data.productos[0].categoria_inventario, "Panadería")

    def test_02_roundtrip_catalogos(self) -> None:
        data = AppData(
            departamentos=[Departamento("dep01", "Cocina", True)],
            categorias=[Categoria("cat01", "Lácteos", True)],
            subcategorias=[Subcategoria("sub01", "Leches", "cat01", True)],
        )
        payload = appdata_to_dict(data)
        back = dict_to_appdata(payload)
        self.assertEqual(len(back.departamentos), 1)
        self.assertEqual(back.departamentos[0].nombre, "Cocina")
        self.assertEqual(back.categorias[0].id, "cat01")
        self.assertEqual(back.subcategorias[0].categoria_id, "cat01")

    def test_03_roundtrip_producto_con_referencias(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1",
                    "Leche",
                    UnidadProducto.L,
                    categoria_inventario="Lácteos",
                    categoria_id="cat01",
                    subcategoria_id="sub01",
                    departamento_ids=["dep01", "dep02"],
                )
            ],
            departamentos=[
                Departamento("dep01", "Cocina"),
                Departamento("dep02", "Bar"),
            ],
            categorias=[Categoria("cat01", "Lácteos")],
            subcategorias=[Subcategoria("sub01", "Leches", "cat01")],
        )
        back = dict_to_appdata(appdata_to_dict(data))
        p = back.productos[0]
        self.assertEqual(p.categoria_id, "cat01")
        self.assertEqual(p.subcategoria_id, "sub01")
        self.assertEqual(p.departamento_ids, ["dep01", "dep02"])

    def test_04_conserva_categoria_inventario(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1",
                    "Tomate",
                    UnidadProducto.KG,
                    categoria_inventario="Verduras",
                    categoria_id="cat01",
                )
            ],
            categorias=[Categoria("cat01", "Frescos")],
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.productos[0].categoria_inventario, "Verduras")
        self.assertEqual(back.productos[0].categoria_id, "cat01")

    def test_05_categoria_duplicada(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        self.assertTrue(cat.crear_categoria("Lácteos", ctx=ctx).ok)
        r = cat.crear_categoria("  LÁCTEOS  ", ctx=ctx)
        self.assertFalse(r.ok)

    def test_06_departamento_duplicado(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        self.assertTrue(cat.crear_departamento("Cocina", ctx=ctx).ok)
        self.assertFalse(cat.crear_departamento("  cocina  ", ctx=ctx).ok)

    def test_07_subcategoria_duplicada_misma_categoria(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        cat.crear_categoria("A", ctx=ctx)
        cid = data.categorias[0].id
        self.assertTrue(cat.crear_subcategoria("X", cid, ctx=ctx).ok)
        self.assertFalse(cat.crear_subcategoria("x", cid, ctx=ctx).ok)

    def test_08_misma_subcategoria_en_categorias_distintas(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        cat.crear_categoria("A", ctx=ctx)
        cat.crear_categoria("B", ctx=ctx)
        a, b = data.categorias[0].id, data.categorias[1].id
        self.assertTrue(cat.crear_subcategoria("Común", a, ctx=ctx).ok)
        self.assertTrue(cat.crear_subcategoria("Común", b, ctx=ctx).ok)

    def test_09_crear_subcategoria_sin_categoria(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        r = cat.crear_subcategoria("X", "", ctx=ctx)
        self.assertFalse(r.ok)
        r2 = cat.crear_subcategoria("X", "cat_inexistente", ctx=ctx)
        self.assertFalse(r2.ok)

    def test_10_categoria_inexistente_en_producto(self) -> None:
        data = AppData()
        r = cat.validar_referencias_producto(
            data, categoria_id="cat_x", subcategoria_id=None, departamento_ids=[],
        )
        self.assertFalse(r.ok)

    def test_11_subcategoria_inexistente(self) -> None:
        data = AppData(categorias=[Categoria("cat01", "A")])
        r = cat.validar_referencias_producto(
            data,
            categoria_id="cat01",
            subcategoria_id="sub_x",
            departamento_ids=[],
        )
        self.assertFalse(r.ok)

    def test_12_subcategoria_de_categoria_diferente(self) -> None:
        data = AppData(
            categorias=[Categoria("cat01", "A"), Categoria("cat02", "B")],
            subcategorias=[Subcategoria("sub01", "X", "cat02")],
        )
        r = cat.validar_referencias_producto(
            data,
            categoria_id="cat01",
            subcategoria_id="sub01",
            departamento_ids=[],
        )
        self.assertFalse(r.ok)

    def test_13_departamento_inexistente(self) -> None:
        data = AppData()
        r = cat.validar_referencias_producto(
            data, categoria_id=None, subcategoria_id=None, departamento_ids=["dep_x"],
        )
        self.assertFalse(r.ok)

    def test_14_ids_departamento_duplicados(self) -> None:
        data = AppData(departamentos=[Departamento("dep01", "Cocina")])
        r = cat.validar_referencias_producto(
            data,
            categoria_id=None,
            subcategoria_id=None,
            departamento_ids=["dep01", "dep01"],
        )
        self.assertFalse(r.ok)

    def test_15_desactivar_sin_eliminar(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        cat.crear_departamento("Bar", ctx=ctx)
        did = data.departamentos[0].id
        self.assertTrue(cat.desactivar_departamento(did, ctx=ctx).ok)
        self.assertEqual(len(data.departamentos), 1)
        self.assertFalse(data.departamentos[0].activo)

    def test_16_categoria_inactiva_no_en_nuevas_asignaciones(self) -> None:
        data = AppData(
            categorias=[
                Categoria("cat01", "Activa", True),
                Categoria("cat02", "Inactiva", False),
            ]
        )
        opts = cat.opciones_categoria_asignacion(data)
        self.assertEqual([c.id for c in opts], ["cat01"])

    def test_17_subcategoria_de_categoria_inactiva_no_disponible(self) -> None:
        data = AppData(
            categorias=[Categoria("cat01", "Inactiva", False)],
            subcategorias=[Subcategoria("sub01", "X", "cat01", True)],
        )
        opts = cat.opciones_subcategoria_asignacion(data, "cat01")
        self.assertEqual(opts, [])

    def test_18_producto_conserva_referencia_inactiva(self) -> None:
        data = AppData(
            categorias=[Categoria("cat01", "Vieja", False)],
            productos=[
                Producto("p1", "Pan", UnidadProducto.UD, categoria_id="cat01"),
            ],
        )
        opts = cat.opciones_categoria_asignacion(data, conservar_id="cat01")
        self.assertEqual({c.id for c in opts}, {"cat01"})
        r = cat.validar_referencias_producto(
            data,
            categoria_id="cat01",
            subcategoria_id=None,
            departamento_ids=[],
            categoria_id_anterior="cat01",
        )
        self.assertTrue(r.ok)

    def test_19_renombrar_conserva_id(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        cat.crear_categoria("Antes", ctx=ctx)
        cid = data.categorias[0].id
        self.assertTrue(cat.renombrar_categoria(cid, "Después", ctx=ctx).ok)
        self.assertEqual(data.categorias[0].id, cid)
        self.assertEqual(data.categorias[0].nombre, "Después")

    def test_20_referencia_huerfana_carga_y_diagnostica(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1",
                    "Orphan",
                    UnidadProducto.UD,
                    categoria_id="cat_fantasma",
                    subcategoria_id="sub_fantasma",
                    departamento_ids=["dep_fantasma"],
                )
            ]
        )
        # Carga / roundtrip conserva IDs
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.productos[0].categoria_id, "cat_fantasma")
        self.assertEqual(
            cat.etiqueta_categoria(back, "cat_fantasma"),
            cat.ETIQUETA_REF_NO_ENCONTRADA,
        )
        resumen = generar_diagnostico(back)
        joined = " ".join(resumen.incidencias_catalogo)
        self.assertIn("categoría inexistente", joined)
        self.assertIn("subcategoría inexistente", joined)
        self.assertIn("departamento inexistente", joined)

    def test_21_matriz_espacios_f5_sin_cambios(self) -> None:
        self.assertEqual(
            esp.SECCIONES_POR_ESPACIO[esp.ESPACIO_REGISTRO],
            (esp.SECCION_REGISTROS,),
        )
        self.assertEqual(
            esp.SECCIONES_POR_ESPACIO[esp.ESPACIO_GESTOR],
            (esp.SECCION_DASHBOARD, esp.SECCION_ANALISIS),
        )
        self.assertEqual(
            esp.SECCIONES_POR_ESPACIO[esp.ESPACIO_INVENTARIO],
            (esp.SECCION_STOCK, esp.SECCION_RECETAS),
        )
        self.assertEqual(esp.SECCIONES_GLOBALES, (esp.SECCION_CONFIGURACION,))

    def test_22_ninguna_prueba_toca_fifo(self) -> None:
        svc_path = ROOT / "app" / "core" / "services" / "catalogo_service.py"
        src = svc_path.read_text(encoding="utf-8")
        self.assertNotIn("inventory_batch_service", src)
        self.assertNotIn("aplicar_descuento", src)
        self.assertNotIn("consumos_lote", src)
        self.assertNotIn("get_data()", src.split("class _CompatSessionUow")[0])


if __name__ == "__main__":
    unittest.main()
