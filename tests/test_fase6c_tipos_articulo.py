"""Fase 6C — tipos de artículo (consumible / reutilizable).

Ejecutar:

    py -m unittest tests.test_fase6c_tipos_articulo -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application import espacios as esp
from app.core.models import (
    AppData,
    Categoria,
    Departamento,
    LoteStock,
    Producto,
    Subcategoria,
    TipoArticulo,
    Ubicacion,
    UnidadProducto,
)
from app.core.services import catalogo_service as cat
from app.core.services.diagnostico_service import generar_diagnostico
from app.core.services.stock_service import crear_producto, editar_producto_catalogo
from app.data.serializers import appdata_to_dict, dict_to_appdata


class TestFase6CTiposArticulo(unittest.TestCase):
    def test_01_json_antiguo_sin_tipo(self) -> None:
        payload = {
            "meta": {},
            "productos": [{"id": "p1", "nombre": "Pan", "unidad": "Ud"}],
        }
        data = dict_to_appdata(payload)
        self.assertIsNone(data.productos[0].tipo_articulo)

    def test_02_historico_carga_none(self) -> None:
        data = AppData(productos=[Producto("p1", "Pan", UnidadProducto.UD)])
        self.assertIsNone(data.productos[0].tipo_articulo)
        self.assertEqual(cat.etiqueta_tipo_articulo(None), "Sin clasificar")

    def test_03_roundtrip_consumible(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1", "Leche", UnidadProducto.L,
                    tipo_articulo=TipoArticulo.CONSUMIBLE,
                )
            ]
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.productos[0].tipo_articulo, TipoArticulo.CONSUMIBLE)

    def test_04_roundtrip_reutilizable(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1", "Copa", UnidadProducto.UD,
                    tipo_articulo=TipoArticulo.REUTILIZABLE,
                )
            ]
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.productos[0].tipo_articulo, TipoArticulo.REUTILIZABLE)

    def test_05_roundtrip_none(self) -> None:
        data = AppData(
            productos=[Producto("p1", "X", UnidadProducto.UD, tipo_articulo=None)]
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertIsNone(back.productos[0].tipo_articulo)

    def test_06_valor_desconocido_no_bloquea_carga(self) -> None:
        payload = {
            "meta": {},
            "productos": [
                {
                    "id": "p1",
                    "nombre": "Raro",
                    "unidad": "Ud",
                    "tipo_articulo": "activo_futuro",
                }
            ],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(data.productos[0].tipo_articulo, "activo_futuro")
        self.assertNotEqual(data.productos[0].tipo_articulo, TipoArticulo.CONSUMIBLE)

    def test_07_diagnostico_valor_desconocido(self) -> None:
        data = AppData(
            productos=[
                Producto("p1", "Raro", UnidadProducto.UD, tipo_articulo="xyz"),
            ]
        )
        resumen = generar_diagnostico(data)
        self.assertTrue(
            any("desconocido" in i for i in resumen.incidencias_catalogo)
        )

    def test_08_diagnostico_sin_clasificar(self) -> None:
        data = AppData(
            productos=[Producto("p1", "Pan", UnidadProducto.UD, tipo_articulo=None)]
        )
        resumen = generar_diagnostico(data)
        self.assertTrue(
            any("sin clasificar" in i for i in resumen.incidencias_catalogo)
        )

    def test_09_nuevo_sin_tipo_rechazado(self) -> None:
        data = AppData()
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            r = crear_producto("Nuevo", "Ud", None, tipo_articulo=None)
        self.assertFalse(r.ok)
        self.assertEqual(data.productos, [])

    def test_10_nuevo_consumible_valido(self) -> None:
        data = AppData()
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            r = crear_producto(
                "Leche", "L", None, tipo_articulo=TipoArticulo.CONSUMIBLE.value,
            )
        self.assertTrue(r.ok)
        self.assertEqual(data.productos[0].tipo_articulo, TipoArticulo.CONSUMIBLE)

    def test_11_nuevo_reutilizable_valido(self) -> None:
        data = AppData()
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            r = crear_producto(
                "Copa", "Ud", None, tipo_articulo=TipoArticulo.REUTILIZABLE.value,
            )
        self.assertTrue(r.ok)
        self.assertEqual(data.productos[0].tipo_articulo, TipoArticulo.REUTILIZABLE)

    def test_12_historico_sin_tipo_puede_editar_otro_campo(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1",
                    "Pan",
                    UnidadProducto.UD,
                    categoria_inventario="Panadería",
                    tipo_articulo=None,
                )
            ]
        )
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            r = editar_producto_catalogo(
                "p1",
                servicios_disponibles=["desayuno"],
                categoria_inventario="Panadería",
                tipo_articulo=None,
            )
        self.assertTrue(r.ok)
        self.assertIsNone(data.productos[0].tipo_articulo)
        self.assertEqual(data.productos[0].servicios_disponibles, ["desayuno"])

    def test_13_clasificar_historico_conserva_resto(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1",
                    "Agua",
                    UnidadProducto.L,
                    es_bebida=True,
                    categoria_inventario="Bebidas",
                    categoria_id="cat01",
                    departamento_ids=["dep01"],
                    ubicacion_ids=["ubi01"],
                    tipo_articulo=None,
                )
            ],
            categorias=[Categoria("cat01", "Bebidas")],
            departamentos=[Departamento("dep01", "Bar")],
            ubicaciones=[Ubicacion("ubi01", "Cámara")],
        )
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            r = editar_producto_catalogo(
                "p1",
                servicios_disponibles=[],
                categoria_inventario="Bebidas",
                categoria_id="cat01",
                departamento_ids=["dep01"],
                ubicacion_ids=["ubi01"],
                tipo_articulo=TipoArticulo.CONSUMIBLE.value,
            )
        self.assertTrue(r.ok)
        p = data.productos[0]
        self.assertEqual(p.tipo_articulo, TipoArticulo.CONSUMIBLE)
        self.assertTrue(p.es_bebida)
        self.assertEqual(p.categoria_inventario, "Bebidas")
        self.assertEqual(p.categoria_id, "cat01")
        self.assertEqual(p.departamento_ids, ["dep01"])
        self.assertEqual(p.ubicacion_ids, ["ubi01"])

    def test_14_es_bebida_sin_cambios(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "b1", "Cola", UnidadProducto.L,
                    es_bebida=True, tipo_articulo=TipoArticulo.CONSUMIBLE,
                )
            ]
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertTrue(back.productos[0].es_bebida)

    def test_15_categoria_inventario_intacta(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1", "Tomate", UnidadProducto.KG,
                    categoria_inventario="Verduras",
                    tipo_articulo=TipoArticulo.CONSUMIBLE,
                )
            ]
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.productos[0].categoria_inventario, "Verduras")

    def test_16_campos_6a_intactos(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1",
                    "X",
                    UnidadProducto.UD,
                    categoria_id="cat01",
                    subcategoria_id="sub01",
                    departamento_ids=["dep01"],
                    tipo_articulo=TipoArticulo.CONSUMIBLE,
                )
            ],
            categorias=[Categoria("cat01", "A")],
            subcategorias=[Subcategoria("sub01", "B", "cat01")],
            departamentos=[Departamento("dep01", "Cocina")],
        )
        back = dict_to_appdata(appdata_to_dict(data))
        p = back.productos[0]
        self.assertEqual(p.categoria_id, "cat01")
        self.assertEqual(p.subcategoria_id, "sub01")
        self.assertEqual(p.departamento_ids, ["dep01"])

    def test_17_ubicaciones_6b_intactas(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1", "X", UnidadProducto.UD,
                    ubicacion_ids=["ubi01"],
                    tipo_articulo=TipoArticulo.REUTILIZABLE,
                )
            ],
            ubicaciones=[Ubicacion("ubi01", "Economato")],
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.productos[0].ubicacion_ids, ["ubi01"])
        self.assertEqual(back.ubicaciones[0].nombre, "Economato")

    def test_18_cambiar_tipo_no_modifica_stock(self) -> None:
        data = AppData(
            productos=[
                Producto("p1", "Pan", UnidadProducto.UD, tipo_articulo=None),
            ],
            lotes=[
                LoteStock("l1", "p1", 10.0, 5.0, 4.0, None, None, None, None),
            ],
        )
        antes = data.lotes[0].cantidad_restante
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            editar_producto_catalogo(
                "p1",
                tipo_articulo=TipoArticulo.CONSUMIBLE.value,
            )
        self.assertEqual(data.lotes[0].cantidad_restante, antes)

    def test_19_cambiar_tipo_no_modifica_lotes(self) -> None:
        data = AppData(
            productos=[
                Producto(
                    "p1", "Pan", UnidadProducto.UD,
                    tipo_articulo=TipoArticulo.CONSUMIBLE,
                ),
            ],
            lotes=[
                LoteStock("l1", "p1", 10.0, 5.0, 5.0, None, None, None, None),
            ],
        )
        n = len(data.lotes)
        lote_id = data.lotes[0].id
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            editar_producto_catalogo(
                "p1",
                tipo_articulo=TipoArticulo.REUTILIZABLE.value,
            )
        self.assertEqual(len(data.lotes), n)
        self.assertEqual(data.lotes[0].id, lote_id)

    def test_20_cambiar_tipo_no_altera_fifo_modulo(self) -> None:
        path = ROOT / "app" / "core" / "services" / "catalogo_service.py"
        src = path.read_text(encoding="utf-8")
        self.assertNotIn("inventory_batch_service", src)
        self.assertNotIn("aplicar_descuento", src)

    def test_21_cambiar_tipo_no_crea_movimientos(self) -> None:
        data = AppData(
            productos=[
                Producto("p1", "X", UnidadProducto.UD, tipo_articulo=None),
            ]
        )
        antes = appdata_to_dict(data)
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            editar_producto_catalogo(
                "p1", tipo_articulo=TipoArticulo.CONSUMIBLE.value,
            )
        despues = appdata_to_dict(data)
        self.assertEqual(despues.get("movimientos", []), [])
        self.assertEqual(len(despues.get("lotes", [])), len(antes.get("lotes", [])))
        self.assertEqual(despues.get("recuentos", []), [])

    def test_22_matriz_espacios_f5_intacta(self) -> None:
        self.assertEqual(esp.ESPACIO_DEFAULT, esp.ESPACIO_GESTOR)
        self.assertEqual(
            esp.SECCIONES_POR_ESPACIO[esp.ESPACIO_INVENTARIO],
            (esp.SECCION_STOCK, esp.SECCION_RECETAS),
        )

    def test_diagnostico_no_modifica(self) -> None:
        data = AppData(
            productos=[Producto("p1", "X", UnidadProducto.UD, tipo_articulo=None)]
        )
        snap = copy.deepcopy(appdata_to_dict(data))
        generar_diagnostico(data)
        self.assertEqual(appdata_to_dict(data), snap)


if __name__ == "__main__":
    unittest.main()
