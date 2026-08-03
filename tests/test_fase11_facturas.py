"""Fase 11 — facturas + conciliación (sin stock en conciliación).

Ejecutar:

    py -m unittest tests.test_fase11_facturas -v
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
from app.core.services import factura_service as fac
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
    prv.crear_proveedor("Proveedor Sur", nif_cif="B999", ctx=ctx)
    return data


def _albaran_confirmado(data: AppData, ctx, *, qty: float = 4.0, precio: float = 12.0):
    r = alb.crear_borrador_albaran(
        proveedor_id=data.proveedores[0].id, ctx=ctx
    )
    alb.anadir_linea_albaran(
        r.documento.id,
        producto_id="p01",
        cantidad=qty,
        precio_total=precio,
        ctx=ctx,
    )
    conf = alb.confirmar_albaran(r.documento.id, ctx=ctx)
    assert conf.ok, conf.mensaje
    return conf.documento


class TestFase11Facturas(unittest.TestCase):
    def test_01_tipo_factura_en_enum(self) -> None:
        from app.core.models import TipoDocumento

        self.assertEqual(TipoDocumento.FACTURA.value, "factura")

    def test_02_conciliacion_no_incrementa_stock(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        n_lotes = len(data.lotes)
        n_mov = len(data.movimientos)

        fr = fac.crear_borrador_factura(
            proveedor_id=data.proveedores[0].id,
            referencia_externa="FAC-1",
            ctx=ctx,
        )
        self.assertTrue(fr.ok, fr.mensaje)
        ln_alb = alb_doc.lineas[0]
        add = fac.anadir_linea_factura(
            fr.documento.id,
            producto_id="p01",
            cantidad=4.0,
            precio_total=12.5,
            documento_origen_id=alb_doc.id,
            linea_origen_id=ln_alb.id,
            ctx=ctx,
        )
        self.assertTrue(add.ok, add.mensaje)
        conf = fac.confirmar_factura(fr.documento.id, ctx=ctx)
        self.assertTrue(conf.ok, conf.mensaje)
        self.assertEqual(len(data.lotes), n_lotes)
        self.assertEqual(len(data.movimientos), n_mov)
        self.assertIsNone(conf.documento.lineas[0].lote_id)
        self.assertIsNone(conf.documento.lineas[0].movimiento_id)
        self.assertEqual(conf.documento.lineas[0].linea_origen_id, ln_alb.id)

    def test_03_no_doble_conciliacion(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        ln_id = alb_doc.lineas[0].id
        f1 = fac.crear_borrador_factura(ctx=ctx)
        fac.anadir_linea_factura(
            f1.documento.id,
            producto_id="p01",
            cantidad=4.0,
            precio_total=10.0,
            documento_origen_id=alb_doc.id,
            linea_origen_id=ln_id,
            ctx=ctx,
        )
        self.assertTrue(fac.confirmar_factura(f1.documento.id, ctx=ctx).ok)

        f2 = fac.crear_borrador_factura(ctx=ctx)
        bad = fac.anadir_linea_factura(
            f2.documento.id,
            producto_id="p01",
            cantidad=4.0,
            precio_total=10.0,
            documento_origen_id=alb_doc.id,
            linea_origen_id=ln_id,
            ctx=ctx,
        )
        self.assertFalse(bad.ok)
        self.assertIn("ya conciliada", bad.mensaje)

    def test_04_factura_directa_crea_lote(self) -> None:
        data = _base()
        ctx = _ctx(data)
        fr = fac.crear_borrador_factura(
            proveedor_id=data.proveedores[0].id, ctx=ctx
        )
        fac.anadir_linea_factura(
            fr.documento.id,
            producto_id="p01",
            cantidad=2.0,
            precio_total=8.0,
            ctx=ctx,
        )
        conf = fac.confirmar_factura(fr.documento.id, ctx=ctx)
        self.assertTrue(conf.ok, conf.mensaje)
        self.assertEqual(len(data.lotes), 1)
        self.assertEqual(data.lotes[0].cantidad_restante, 2.0)
        entradas = [
            m
            for m in data.movimientos
            if (m.tipo.value if hasattr(m.tipo, "value") else m.tipo)
            == TipoMovimiento.ENTRADA_FACTURA.value
        ]
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0].origen_tipo, "factura")

    def test_05_anular_conciliacion_libera_enlace(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        ln_id = alb_doc.lineas[0].id
        fr = fac.crear_borrador_factura(ctx=ctx)
        fac.anadir_linea_factura(
            fr.documento.id,
            producto_id="p01",
            cantidad=4.0,
            precio_total=12.0,
            documento_origen_id=alb_doc.id,
            linea_origen_id=ln_id,
            ctx=ctx,
        )
        fac.confirmar_factura(fr.documento.id, ctx=ctx)
        an = fac.anular_factura(fr.documento.id, motivo="Error", ctx=ctx)
        self.assertTrue(an.ok, an.mensaje)
        self.assertEqual(
            an.documento.estado.value
            if hasattr(an.documento.estado, "value")
            else an.documento.estado,
            EstadoDocumento.ANULADO.value,
        )
        # Tras anular, se puede volver a conciliar
        f2 = fac.crear_borrador_factura(ctx=ctx)
        ok = fac.anadir_linea_factura(
            f2.documento.id,
            producto_id="p01",
            cantidad=4.0,
            precio_total=12.0,
            documento_origen_id=alb_doc.id,
            linea_origen_id=ln_id,
            ctx=ctx,
        )
        self.assertTrue(ok.ok, ok.mensaje)

    def test_06_anular_directa_revierte(self) -> None:
        data = _base()
        ctx = _ctx(data)
        fr = fac.crear_borrador_factura(ctx=ctx)
        fac.anadir_linea_factura(
            fr.documento.id, producto_id="p01", cantidad=3.0, precio_total=9.0, ctx=ctx
        )
        fac.confirmar_factura(fr.documento.id, ctx=ctx)
        lote = data.lotes[0]
        an = fac.anular_factura(fr.documento.id, ctx=ctx)
        self.assertTrue(an.ok, an.mensaje)
        self.assertEqual(lote.cantidad_restante, 0.0)
        self.assertTrue(lote.anulado)

    def test_07_roundtrip(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        fr = fac.crear_borrador_factura(referencia_externa="EXT-F", ctx=ctx)
        fac.anadir_linea_factura(
            fr.documento.id,
            producto_id="p01",
            cantidad=1.0,
            precio_total=2.0,
            documento_origen_id=alb_doc.id,
            linea_origen_id=alb_doc.lineas[0].id,
            ctx=ctx,
        )
        fac.confirmar_factura(fr.documento.id, ctx=ctx)
        back = dict_to_appdata(appdata_to_dict(data))
        facts = [
            d
            for d in back.documentos
            if (d.tipo.value if hasattr(d.tipo, "value") else d.tipo) == "factura"
        ]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].referencia_externa, "EXT-F")
        self.assertEqual(facts[0].lineas[0].linea_origen_id, alb_doc.lineas[0].id)

    def test_08_version(self) -> None:
        self.assertIn("Facturas", APP_VERSION)

    def test_09_direccion_entrada_factura(self) -> None:
        from app.core.models.enums import DIRECCION_POR_TIPO_MOVIMIENTO

        self.assertEqual(
            DIRECCION_POR_TIPO_MOVIMIENTO[TipoMovimiento.ENTRADA_FACTURA],
            DireccionMovimiento.ENTRADA,
        )

    def test_10_id_tecnico_distinto_de_referencia(self) -> None:
        data = _base()
        ctx = _ctx(data)
        fr = fac.crear_borrador_factura(referencia_externa="FAC-99", ctx=ctx)
        self.assertNotEqual(fr.documento.id, "FAC-99")


if __name__ == "__main__":
    unittest.main()
