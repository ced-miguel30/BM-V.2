"""Bloque A3+A4+A5+A9 — money, totales documentales, observaciones, códigos.

Ejecutar:

    python -m unittest tests.test_a3_a4_a5_a9_bloque -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    Documento,
    EstadoDocumento,
    LineaDocumento,
    Producto,
    Proveedor,
    TipoDocumento,
    Ubicacion,
    UnidadProducto,
)
from app.core.services import catalogo_service as cat
from app.core.services import proveedor_service as prv
from app.core.services.documento_totales import recalcular_totales_documento
from app.core.services.money import (
    EntradaLineaCalculo,
    calcular_documento,
    calcular_linea,
    money_round,
    normalizar_codigo_funcional,
    precio_unitario_neto,
)
from app.core.services.stock_service import crear_producto
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _ctx(data: AppData):
    return build_app_context(uow=InMemoryUnitOfWork(data))


class TestA3Money(unittest.TestCase):
    def test_caso_canonico_2_cajas_no_960(self) -> None:
        r = calcular_linea(
            cantidad_compra=2,
            precio_unitario_compra="20",
            factor_conversion=24,
            impuesto_porcentaje="7",
        )
        self.assertEqual(r.base_antes_descuentos, Decimal("40.00"))
        self.assertEqual(r.cantidad_inventario, Decimal("48"))
        self.assertEqual(r.cuota_impuesto, Decimal("2.80"))
        self.assertEqual(r.total_linea, Decimal("42.80"))
        self.assertNotEqual(r.base_antes_descuentos, Decimal("960.00"))
        self.assertEqual(r.coste_inventariable_linea, Decimal("40.00"))
        self.assertEqual(r.coste_unitario_inventario, Decimal("40") / Decimal("48"))
        # Incorrecto sería 42.80/48
        self.assertNotEqual(
            r.coste_unitario_inventario, Decimal("42.80") / Decimal("48")
        )

    def test_precio_incluye_igic_sin_round_previo(self) -> None:
        neto = precio_unitario_neto(
            "21.40", precio_incluye_igic=True, impuesto_porcentaje="7"
        )
        # 21.40 / 1.07 — alta precisión
        self.assertGreater(neto, Decimal("19.9"))
        r = calcular_linea(
            cantidad_compra=2,
            precio_unitario_compra="21.40",
            factor_conversion=24,
            precio_incluye_igic=True,
            impuesto_porcentaje="7",
        )
        self.assertEqual(r.base_antes_descuentos, money_round(2 * neto))

    def test_descuento_linea_pct_luego_importe(self) -> None:
        r = calcular_linea(
            cantidad_compra=10,
            precio_unitario_compra="10",
            descuento_linea_porcentaje="10",
            descuento_linea_importe="5",
            impuesto_porcentaje=0,
        )
        # base 100 → -10% = 90 → -5 = 85
        self.assertEqual(r.base_antes_descuentos, Decimal("100.00"))
        self.assertEqual(r.base_tras_descuento_linea, Decimal("85.00"))
        self.assertEqual(r.base_imponible_final, Decimal("85.00"))

    def test_descuento_importe_excede_error(self) -> None:
        with self.assertRaises(ValueError):
            calcular_linea(
                cantidad_compra=1,
                precio_unitario_compra="10",
                descuento_linea_importe="11",
            )

    def test_ultimo_centimo_cabecera(self) -> None:
        entradas = [
            EntradaLineaCalculo(
                cantidad_compra=1,
                precio_unitario_compra="10",
                impuesto_porcentaje=0,
                linea_id="a",
            ),
            EntradaLineaCalculo(
                cantidad_compra=1,
                precio_unitario_compra="10",
                impuesto_porcentaje=0,
                linea_id="b",
            ),
            EntradaLineaCalculo(
                cantidad_compra=1,
                precio_unitario_compra="10",
                impuesto_porcentaje=0,
                linea_id="c",
            ),
        ]
        # 1.00 sobre 30 → 0.33 + 0.33 + 0.34
        doc = calcular_documento(entradas, descuento_cabecera_importe="1.00")
        asignados = [ln.descuento_cabecera_asignado for ln in doc.lineas]
        self.assertEqual(sum(asignados), Decimal("1.00"))
        self.assertEqual(asignados[-1], Decimal("0.34"))
        self.assertEqual(doc.base_imponible, Decimal("29.00"))
        self.assertEqual(doc.descuento_total, Decimal("1.00"))

    def test_cabecera_sin_bases_error(self) -> None:
        entradas = [
            EntradaLineaCalculo(
                cantidad_compra=0,
                precio_unitario_compra="10",
                linea_id="z",
            )
        ]
        with self.assertRaises(ValueError):
            calcular_documento(entradas, descuento_cabecera_importe="1")

    def test_round_half_up(self) -> None:
        self.assertEqual(money_round(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(money_round(Decimal("1.004")), Decimal("1.00"))


class TestA4TotalesDocumento(unittest.TestCase):
    def test_recalcular_y_roundtrip_json(self) -> None:
        doc = Documento(
            id="d1",
            tipo=TipoDocumento.ALBARAN,
            estado=EstadoDocumento.BORRADOR,
            fecha_documento=date(2026, 7, 1),
            descuento_cabecera_importe=Decimal("1.00"),
            moneda="EUR",
            lineas=[
                LineaDocumento(
                    id="ln1",
                    producto_id="p1",
                    cantidad=0,
                    precio_total=0,
                    cantidad_compra=Decimal("2"),
                    precio_unitario_compra=Decimal("20"),
                    factor_conversion=Decimal("24"),
                    impuesto_porcentaje_snapshot=Decimal("7"),
                ),
                LineaDocumento(
                    id="ln2",
                    producto_id="p2",
                    cantidad=0,
                    precio_total=0,
                    cantidad_compra=Decimal("1"),
                    precio_unitario_compra=Decimal("10"),
                    factor_conversion=Decimal("1"),
                    impuesto_porcentaje_snapshot=Decimal("7"),
                ),
            ],
        )
        res = recalcular_totales_documento(doc)
        self.assertIsNotNone(res)
        self.assertEqual(doc.lineas[0].cantidad_inventario, Decimal("48"))
        self.assertEqual(doc.lineas[0].base_antes_descuento, Decimal("40.00"))
        self.assertIsNotNone(doc.total_documento)
        self.assertTrue(doc.desglose_impuestos)

        data = AppData(documentos=[doc])
        back = dict_to_appdata(appdata_to_dict(data))
        d2 = back.documentos[0]
        self.assertEqual(d2.moneda, "EUR")
        self.assertEqual(d2.lineas[0].cantidad_compra, Decimal("2"))
        self.assertEqual(d2.total_documento, doc.total_documento)
        self.assertEqual(len(d2.desglose_impuestos), len(doc.desglose_impuestos))

    def test_legacy_sin_campos_compra_no_recalcula(self) -> None:
        doc = Documento(
            id="d2",
            tipo=TipoDocumento.FACTURA,
            estado=EstadoDocumento.CONFIRMADO,
            fecha_documento=date(2026, 1, 1),
            lineas=[
                LineaDocumento(id="l", producto_id="p", cantidad=5.0, precio_total=50.0),
            ],
        )
        self.assertIsNone(recalcular_totales_documento(doc))
        self.assertIsNone(doc.total_documento)

    def test_compat_json_sin_campos_a4(self) -> None:
        payload = {
            "documentos": [
                {
                    "id": "d-old",
                    "tipo": "albaran",
                    "estado": "borrador",
                    "fecha_documento": "2026-01-02",
                    "lineas": [
                        {
                            "id": "l1",
                            "producto_id": "p1",
                            "cantidad": 3,
                            "precio_total": 12.5,
                        }
                    ],
                }
            ]
        }
        data = dict_to_appdata(payload)
        ln = data.documentos[0].lineas[0]
        self.assertIsNone(ln.cantidad_compra)
        self.assertEqual(ln.cantidad, 3.0)
        self.assertIsNone(data.documentos[0].total_documento)


class TestA5Observaciones(unittest.TestCase):
    def test_observaciones_crear_editar_roundtrip(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        r = prv.crear_proveedor(
            "Obs SA",
            codigo="OBS-01",
            observaciones="Entregar por muelle B",
            ctx=ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(data.proveedores[0].observaciones, "Entregar por muelle B")
        prv.editar_proveedor(
            data.proveedores[0].id,
            observaciones="Actualizado",
            ctx=ctx,
        )
        self.assertEqual(data.proveedores[0].observaciones, "Actualizado")
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.proveedores[0].observaciones, "Actualizado")

    def test_legacy_sin_observaciones(self) -> None:
        data = dict_to_appdata(
            {
                "proveedores": [
                    {
                        "id": "prv1",
                        "nombre_fiscal": "Viejo",
                        "activo": True,
                    }
                ]
            }
        )
        self.assertIsNone(data.proveedores[0].observaciones)
        self.assertIsNone(data.proveedores[0].codigo)


class TestA9Codigos(unittest.TestCase):
    def test_normalizar_codigo(self) -> None:
        self.assertEqual(normalizar_codigo_funcional("  ab  1 "), "AB 1")
        self.assertIsNone(normalizar_codigo_funcional("   "))
        self.assertIsNone(normalizar_codigo_funcional(None))

    def test_alta_sin_codigo_rechazada(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        r = prv.crear_proveedor("X", codigo="  ", ctx=ctx)
        self.assertFalse(r.ok)
        self.assertEqual(data.proveedores, [])

        r2 = cat.crear_ubicacion("Cámara", codigo="", ctx=ctx)
        self.assertFalse(r2.ok)

        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            r3 = crear_producto(
                "Pan", "Ud", None, codigo="", tipo_articulo="consumible"
            )
        self.assertFalse(r3.ok)

    def test_editar_codigo_permite_mismo_registro(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        self.assertTrue(
            prv.crear_proveedor("Solo", codigo="SOLO-1", ctx=ctx).ok
        )
        pid = data.proveedores[0].id
        r = prv.editar_proveedor(pid, codigo="solo-1", ctx=ctx)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(data.proveedores[0].codigo, "SOLO-1")

    def test_serializer_omite_codigo_none(self) -> None:
        data = AppData(
            productos=[Producto("p1", "X", UnidadProducto.UD)],
            proveedores=[Proveedor(id="prv1", nombre_fiscal="P")],
            ubicaciones=[Ubicacion("ubi1", "U", True)],
        )
        payload = appdata_to_dict(data)
        self.assertNotIn("codigo", payload["productos"][0])
        self.assertNotIn("codigo", payload["proveedores"][0])
        self.assertNotIn("codigo", payload["ubicaciones"][0])

    def test_unicidad_codigo_entre_no_nulos(self) -> None:
        data = AppData(
            productos=[Producto("p0", "Hist", UnidadProducto.UD, codigo=None)],
            proveedores=[Proveedor(id="prv0", nombre_fiscal="H", codigo=None)],
            ubicaciones=[Ubicacion("ubi0", "H", True, codigo=None)],
        )
        ctx = _ctx(data)
        self.assertTrue(
            prv.crear_proveedor("Nuevo", codigo="DUP", ctx=ctx).ok
        )
        self.assertFalse(
            prv.crear_proveedor("Otro", codigo="dup", ctx=ctx).ok
        )
        self.assertTrue(cat.crear_ubicacion("A", codigo="U1", ctx=ctx).ok)
        self.assertFalse(cat.crear_ubicacion("B", codigo="u1", ctx=ctx).ok)

        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            self.assertTrue(
                crear_producto(
                    "P1", "Ud", None, codigo="SKU-1", tipo_articulo="consumible"
                ).ok
            )
            self.assertFalse(
                crear_producto(
                    "P2", "Ud", None, codigo="sku-1", tipo_articulo="consumible"
                ).ok
            )
        # Históricos None siguen admitidos en carga
        self.assertIsNone(data.productos[0].codigo)

    def test_no_autogen_legacy_y_persist_aislado(self) -> None:
        data = AppData(
            productos=[Producto("p1", "SinCódigo", UnidadProducto.UD)],
        )
        self.assertIsNone(data.productos[0].codigo)
        payload = appdata_to_dict(data)
        self.assertIsNone(payload["productos"][0].get("codigo"))
        loaded = dict_to_appdata(payload)
        self.assertIsNone(loaded.productos[0].codigo)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            path.write_text(
                __import__("json").dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            loaded2 = dict_to_appdata(
                __import__("json").loads(path.read_text(encoding="utf-8"))
            )
            self.assertIsNone(loaded2.productos[0].codigo)
            # No tocar demo: escritura solo en TemporaryDirectory
            self.assertTrue(path.exists())



if __name__ == "__main__":
    unittest.main()
