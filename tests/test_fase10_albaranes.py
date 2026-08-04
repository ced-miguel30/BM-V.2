"""Fase 10 — albaranes → lotes + movimientos (atómico). Sin facturas.

Ejecutar:

    py -m unittest tests.test_fase10_albaranes -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    EstadoDocumento,
    Producto,
    TipoMovimiento,
    UnidadProducto,
)
from app.core.models.enums import DireccionMovimiento
from app.core.services import albaran_service as alb
from app.core.services import movimiento_service as mov
from app.core.services import proveedor_service as prv
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui.theme import APP_VERSION


def _ctx(data: AppData):
    return build_app_context(uow=InMemoryUnitOfWork(data))


def _base() -> AppData:
    data = AppData(
        productos=[Producto("p01", "Aceite", UnidadProducto.L)],
    )
    ctx = _ctx(data)
    prv.crear_proveedor("Proveedor Sur", codigo="PRV-S", nif_cif="B999", ctx=ctx)
    return data


class TestFase10Albaranes(unittest.TestCase):
    def test_01_json_antiguo_sin_documentos(self) -> None:
        data = dict_to_appdata({"productos": []})
        self.assertEqual(data.documentos, [])

    def test_02_borrador_y_linea(self) -> None:
        data = _base()
        ctx = _ctx(data)
        r = alb.crear_borrador_albaran(
            fecha_documento=date(2026, 7, 1),
            proveedor_id=data.proveedores[0].id,
            referencia_externa="ALB-77",
            ctx=ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(r.documento.estado, EstadoDocumento.BORRADOR)
        self.assertEqual(r.documento.referencia_externa, "ALB-77")
        self.assertNotEqual(r.documento.id, "ALB-77")

        r2 = alb.anadir_linea_albaran(
            r.documento.id,
            producto_id="p01",
            cantidad=10.0,
            precio_total=25.0,
            ctx=ctx,
        )
        self.assertTrue(r2.ok, r2.mensaje)
        self.assertEqual(len(r.documento.lineas), 1)

    def test_03_confirmacion_atomica_lotes_y_ledger(self) -> None:
        data = _base()
        ctx = _ctx(data)
        r = alb.crear_borrador_albaran(
            proveedor_id=data.proveedores[0].id,
            ctx=ctx,
        )
        alb.anadir_linea_albaran(
            r.documento.id,
            producto_id="p01",
            cantidad=4.0,
            precio_total=12.0,
            ctx=ctx,
        )
        conf = alb.confirmar_albaran(r.documento.id, ctx=ctx)
        self.assertTrue(conf.ok, conf.mensaje)
        self.assertEqual(conf.documento.estado, EstadoDocumento.CONFIRMADO)
        self.assertEqual(len(data.lotes), 1)
        lote = data.lotes[0]
        self.assertEqual(lote.cantidad_restante, 4.0)
        self.assertEqual(lote.marca_proveedor, "Proveedor Sur")
        self.assertEqual(conf.documento.lineas[0].lote_id, lote.id)

        entradas = [
            m
            for m in data.movimientos
            if (
                m.tipo.value if hasattr(m.tipo, "value") else m.tipo
            )
            == TipoMovimiento.ENTRADA_ALBARAN.value
        ]
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0].origen_tipo, "albaran")
        self.assertEqual(entradas[0].origen_id, conf.documento.id)
        cmp_ = mov.comparar_ledger_vs_lote(data, lote.id)
        self.assertIsNotNone(cmp_)
        self.assertAlmostEqual(cmp_.diferencia, 0.0, places=6)

    def test_04_confirmacion_falla_sin_parcial(self) -> None:
        data = _base()
        ctx = _ctx(data)
        r = alb.crear_borrador_albaran(ctx=ctx)
        alb.anadir_linea_albaran(
            r.documento.id,
            producto_id="p01",
            cantidad=2.0,
            precio_total=5.0,
            ctx=ctx,
        )
        # Forzar fallo en la 2.ª línea: producto inexistente tras mutar
        alb.anadir_linea_albaran(
            r.documento.id,
            producto_id="p01",
            cantidad=1.0,
            precio_total=1.0,
            ctx=ctx,
        )
        r.documento.lineas[1].producto_id = "no_existe"

        conf = alb.confirmar_albaran(r.documento.id, ctx=ctx)
        self.assertFalse(conf.ok)
        self.assertEqual(len(data.lotes), 0)
        self.assertEqual(len(data.movimientos), 0)
        self.assertEqual(
            conf.documento.estado.value
            if hasattr(conf.documento.estado, "value")
            else conf.documento.estado,
            EstadoDocumento.BORRADOR.value,
        )
        self.assertIsNone(conf.documento.lineas[0].lote_id)

    def test_05_anular_confirmado_revierte(self) -> None:
        data = _base()
        ctx = _ctx(data)
        r = alb.crear_borrador_albaran(
            proveedor_id=data.proveedores[0].id, ctx=ctx
        )
        alb.anadir_linea_albaran(
            r.documento.id, producto_id="p01", cantidad=3.0, precio_total=9.0, ctx=ctx
        )
        alb.confirmar_albaran(r.documento.id, ctx=ctx)
        lote = data.lotes[0]
        an = alb.anular_albaran(r.documento.id, motivo="Error recepción", ctx=ctx)
        self.assertTrue(an.ok, an.mensaje)
        self.assertEqual(
            an.documento.estado.value
            if hasattr(an.documento.estado, "value")
            else an.documento.estado,
            EstadoDocumento.ANULADO.value,
        )
        self.assertEqual(lote.cantidad_restante, 0.0)
        self.assertTrue(lote.anulado)
        reversos = [
            m
            for m in data.movimientos
            if (
                m.tipo.value if hasattr(m.tipo, "value") else m.tipo
            )
            == TipoMovimiento.REVERSION_ENTRADA.value
        ]
        self.assertEqual(len(reversos), 1)
        self.assertEqual(reversos[0].origen_tipo, "anulacion_albaran")

    def test_06_anular_bloqueado_si_consumido(self) -> None:
        data = _base()
        ctx = _ctx(data)
        r = alb.crear_borrador_albaran(ctx=ctx)
        alb.anadir_linea_albaran(
            r.documento.id, producto_id="p01", cantidad=5.0, precio_total=10.0, ctx=ctx
        )
        alb.confirmar_albaran(r.documento.id, ctx=ctx)
        data.lotes[0].cantidad_restante = 2.0
        an = alb.anular_albaran(r.documento.id, ctx=ctx)
        self.assertFalse(an.ok)
        self.assertIn("parcialmente consumido", an.mensaje)
        self.assertEqual(
            r.documento.estado.value
            if hasattr(r.documento.estado, "value")
            else r.documento.estado,
            EstadoDocumento.CONFIRMADO.value,
        )
        self.assertEqual(data.lotes[0].cantidad_restante, 2.0)
        self.assertFalse(data.lotes[0].anulado)

    def test_07_roundtrip_documento(self) -> None:
        data = _base()
        ctx = _ctx(data)
        r = alb.crear_borrador_albaran(
            referencia_externa="EXT-1",
            proveedor_id=data.proveedores[0].id,
            ctx=ctx,
        )
        alb.anadir_linea_albaran(
            r.documento.id, producto_id="p01", cantidad=1.5, precio_total=3.0, ctx=ctx
        )
        alb.confirmar_albaran(r.documento.id, ctx=ctx)
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(len(back.documentos), 1)
        d = back.documentos[0]
        self.assertEqual(
            d.estado.value if hasattr(d.estado, "value") else d.estado,
            EstadoDocumento.CONFIRMADO.value,
        )
        self.assertEqual(d.referencia_externa, "EXT-1")
        self.assertEqual(len(d.lineas), 1)
        self.assertIsNotNone(d.lineas[0].lote_id)
        self.assertIsNotNone(d.lineas[0].movimiento_id)

    def test_08_version_incluye_albaranes(self) -> None:
        self.assertIn("Albaranes", APP_VERSION)

    def test_09_direccion_entrada_albaran(self) -> None:
        from app.core.models.enums import DIRECCION_POR_TIPO_MOVIMIENTO

        self.assertEqual(
            DIRECCION_POR_TIPO_MOVIMIENTO[TipoMovimiento.ENTRADA_ALBARAN],
            DireccionMovimiento.ENTRADA,
        )


if __name__ == "__main__":
    unittest.main()
