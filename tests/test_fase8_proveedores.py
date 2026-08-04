"""Fase 8 — proveedores, impuestos y relación producto–proveedor.

Ejecutar:

    py -m unittest tests.test_fase8_proveedores -v
"""

from __future__ import annotations

import copy
import sys
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
from app.core.models import AppData, LoteStock, Producto, UnidadProducto
from app.core.services import proveedor_service as prv
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui.theme import APP_VERSION


def _ctx(data: AppData):
    return build_app_context(uow=InMemoryUnitOfWork(data))


class TestFase8Proveedores(unittest.TestCase):
    def test_01_json_antiguo_sin_claves(self) -> None:
        data = dict_to_appdata({"productos": []})
        self.assertEqual(data.proveedores, [])
        self.assertEqual(data.impuestos, [])
        self.assertEqual(data.relaciones_producto_proveedor, [])

    def test_02_crear_proveedor_y_roundtrip(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        with patch.object(prv, "_ctx", return_value=ctx):
            r = prv.crear_proveedor(
                "Distribuciones Norte SA",
                codigo="NORTE-01",
                nif_cif="B12345678",
                nombre_comercial="Norte",
                ctx=ctx,
            )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(data.proveedores), 1)
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.proveedores[0].nif_cif, "B12345678")
        self.assertEqual(back.proveedores[0].nombre_comercial, "Norte")

    def test_03_no_duplicar_nombre_ni_nif(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        prv.crear_proveedor("Alpha", codigo="A-01", nif_cif="A1", ctx=ctx)
        r2 = prv.crear_proveedor("alpha", codigo="A-02", ctx=ctx)
        self.assertFalse(r2.ok)
        r3 = prv.crear_proveedor("Beta", codigo="B-01", nif_cif="A1", ctx=ctx)
        self.assertFalse(r3.ok)

    def test_04_impuesto_decimal(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        r = prv.crear_impuesto("IVA general", "21.00", ctx=ctx)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(data.impuestos[0].porcentaje, Decimal("21.0000"))
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.impuestos[0].porcentaje, Decimal("21.0000"))

    def test_05_cambiar_porcentaje_no_toca_lotes(self) -> None:
        data = AppData(
            lotes=[
                LoteStock(
                    "l1",
                    "p1",
                    10.0,
                    5.0,
                    5.0,
                    fecha_compra=date(2026, 1, 1),
                    marca_proveedor="Texto histórico",
                )
            ]
        )
        ctx = _ctx(data)
        prv.crear_impuesto("IVA", "10", ctx=ctx)
        antes = copy.deepcopy(appdata_to_dict(data)["lotes"])
        prv.editar_impuesto(data.impuestos[0].id, porcentaje="21", ctx=ctx)
        self.assertEqual(appdata_to_dict(data)["lotes"], antes)
        self.assertEqual(data.lotes[0].marca_proveedor, "Texto histórico")

    def test_06_vincular_con_snapshot(self) -> None:
        data = AppData(
            productos=[Producto("p01", "Leche", UnidadProducto.L)],
        )
        ctx = _ctx(data)
        prv.crear_proveedor(
            "Fiscal Viejo",
            codigo="FV-01",
            nombre_comercial="Comercial X",
            nif_cif="X1",
            ctx=ctx,
        )
        r = prv.vincular_producto_proveedor(
            "p01", data.proveedores[0].id, codigo_proveedor="SKU-1", preferente=True, ctx=ctx
        )
        self.assertTrue(r.ok, r.mensaje)
        rel = data.relaciones_producto_proveedor[0]
        self.assertEqual(rel.proveedor_nombre_snapshot, "Comercial X")
        self.assertEqual(rel.nif_cif_snapshot, "X1")
        # Editar proveedor no reescribe snapshot
        prv.editar_proveedor(
            data.proveedores[0].id, nombre_comercial="Comercial Y", ctx=ctx
        )
        self.assertEqual(rel.proveedor_nombre_snapshot, "Comercial X")

    def test_07_preferente_unico_por_producto(self) -> None:
        data = AppData(productos=[Producto("p01", "Pan", UnidadProducto.UD)])
        ctx = _ctx(data)
        prv.crear_proveedor("Prov A", codigo="PA", ctx=ctx)
        prv.crear_proveedor("Prov B", codigo="PB", ctx=ctx)
        a, b = data.proveedores[0].id, data.proveedores[1].id
        prv.vincular_producto_proveedor("p01", a, preferente=True, ctx=ctx)
        prv.vincular_producto_proveedor("p01", b, preferente=True, ctx=ctx)
        prefs = [r for r in data.relaciones_producto_proveedor if r.preferente]
        self.assertEqual(len(prefs), 1)
        self.assertEqual(prefs[0].proveedor_id, b)

    def test_08_soft_delete(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        prv.crear_proveedor("Zeta", codigo="Z1", ctx=ctx)
        pid = data.proveedores[0].id
        self.assertTrue(prv.desactivar_proveedor(pid, ctx=ctx).ok)
        self.assertFalse(data.proveedores[0].activo)
        self.assertTrue(prv.reactivar_proveedor(pid, ctx=ctx).ok)

    def test_09_version_ui(self) -> None:
        self.assertIn("Proveedor", APP_VERSION)

    def test_10_editar_proveedor_no_reescribe_marca_lote(self) -> None:
        data = AppData(
            lotes=[
                LoteStock(
                    "l1",
                    "p1",
                    1.0,
                    1.0,
                    1.0,
                    marca_proveedor="Marca libre antigua",
                )
            ]
        )
        ctx = _ctx(data)
        prv.crear_proveedor("Nuevo Maestro", codigo="NM-01", ctx=ctx)
        marca = data.lotes[0].marca_proveedor
        prv.editar_proveedor(data.proveedores[0].id, nombre_fiscal="Otro Nombre SA", ctx=ctx)
        self.assertEqual(data.lotes[0].marca_proveedor, marca)


if __name__ == "__main__":
    unittest.main()
