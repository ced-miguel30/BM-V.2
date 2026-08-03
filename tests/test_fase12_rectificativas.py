"""Fase 12 — rectificativas documentales (sin edición silenciosa).

Ejecutar:

    py -m unittest tests.test_fase12_rectificativas -v
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
    TipoDocumento,
    TipoMovimiento,
    UnidadProducto,
)
from app.core.services import albaran_service as alb
from app.core.services import factura_service as fac
from app.core.services import proveedor_service as prv
from app.core.services import rectificativa_service as rect
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui.theme import APP_VERSION


def _ctx(data: AppData):
    return build_app_context(uow=InMemoryUnitOfWork(data))


def _base() -> AppData:
    data = AppData(productos=[Producto("p01", "Aceite", UnidadProducto.L)])
    ctx = _ctx(data)
    prv.crear_proveedor("Proveedor Sur", nif_cif="B999", ctx=ctx)
    return data


def _albaran_confirmado(data: AppData, ctx):
    r = alb.crear_borrador_albaran(
        proveedor_id=data.proveedores[0].id, ctx=ctx
    )
    alb.anadir_linea_albaran(
        r.documento.id, producto_id="p01", cantidad=5.0, precio_total=15.0, ctx=ctx
    )
    conf = alb.confirmar_albaran(r.documento.id, ctx=ctx)
    assert conf.ok, conf.mensaje
    return conf.documento


class TestFase12Rectificativas(unittest.TestCase):
    def test_01_enums(self) -> None:
        self.assertEqual(TipoDocumento.RECTIFICATIVA.value, "rectificativa")
        self.assertEqual(EstadoDocumento.RECTIFICADO.value, "rectificado")

    def test_02_rectificar_albaran_revierte_stock(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        lote = data.lotes[0]
        self.assertEqual(lote.cantidad_restante, 5.0)

        br = rect.crear_borrador_rectificativa(
            alb_doc.id, motivo="Error de recepción", ctx=ctx
        )
        self.assertTrue(br.ok, br.mensaje)
        self.assertEqual(br.documento.documento_rectificado_id, alb_doc.id)
        self.assertEqual(len(br.documento.lineas), 1)

        conf = rect.confirmar_rectificativa(br.documento.id, ctx=ctx)
        self.assertTrue(conf.ok, conf.mensaje)
        self.assertEqual(
            alb_doc.estado.value
            if hasattr(alb_doc.estado, "value")
            else alb_doc.estado,
            EstadoDocumento.RECTIFICADO.value,
        )
        self.assertIsNotNone(alb_doc.rectificado_en)
        self.assertEqual(lote.cantidad_restante, 0.0)
        self.assertTrue(lote.anulado)
        reversos = [
            m
            for m in data.movimientos
            if (m.tipo.value if hasattr(m.tipo, "value") else m.tipo)
            == TipoMovimiento.REVERSION_ENTRADA.value
            and m.origen_tipo == "rectificativa"
        ]
        self.assertEqual(len(reversos), 1)

    def test_03_bloquea_si_lote_consumido(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        data.lotes[0].cantidad_restante = 2.0
        br = rect.crear_borrador_rectificativa(
            alb_doc.id, motivo="Corrección", ctx=ctx
        )
        conf = rect.confirmar_rectificativa(br.documento.id, ctx=ctx)
        self.assertFalse(conf.ok)
        self.assertIn("parcialmente consumido", conf.mensaje)
        self.assertEqual(
            alb_doc.estado.value
            if hasattr(alb_doc.estado, "value")
            else alb_doc.estado,
            EstadoDocumento.CONFIRMADO.value,
        )

    def test_04_no_segunda_rectificativa(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        br = rect.crear_borrador_rectificativa(alb_doc.id, motivo="A", ctx=ctx)
        self.assertTrue(rect.confirmar_rectificativa(br.documento.id, ctx=ctx).ok)
        bad = rect.crear_borrador_rectificativa(alb_doc.id, motivo="B", ctx=ctx)
        self.assertFalse(bad.ok)

    def test_05_no_anular_original_rectificado(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        br = rect.crear_borrador_rectificativa(alb_doc.id, motivo="X", ctx=ctx)
        rect.confirmar_rectificativa(br.documento.id, ctx=ctx)
        an = alb.anular_albaran(alb_doc.id, ctx=ctx)
        self.assertFalse(an.ok)
        self.assertIn("rectificado", an.mensaje.lower())

    def test_06_factura_conciliacion_solo_metadatos(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        n_lotes = len(data.lotes)
        fr = fac.crear_borrador_factura(ctx=ctx)
        fac.anadir_linea_factura(
            fr.documento.id,
            producto_id="p01",
            cantidad=5.0,
            precio_total=15.0,
            documento_origen_id=alb_doc.id,
            linea_origen_id=alb_doc.lineas[0].id,
            ctx=ctx,
        )
        self.assertTrue(fac.confirmar_factura(fr.documento.id, ctx=ctx).ok)

        # Rectificar la factura (conciliación): no crea reverso de stock del albarán
        restante_antes = data.lotes[0].cantidad_restante
        br = rect.crear_borrador_rectificativa(
            fr.documento.id, motivo="Precio mal", ctx=ctx
        )
        conf = rect.confirmar_rectificativa(br.documento.id, ctx=ctx)
        self.assertTrue(conf.ok, conf.mensaje)
        self.assertEqual(len(data.lotes), n_lotes)
        self.assertEqual(data.lotes[0].cantidad_restante, restante_antes)
        self.assertEqual(
            fr.documento.estado.value
            if hasattr(fr.documento.estado, "value")
            else fr.documento.estado,
            EstadoDocumento.RECTIFICADO.value,
        )

    def test_07_motivo_obligatorio(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        bad = rect.crear_borrador_rectificativa(alb_doc.id, motivo="  ", ctx=ctx)
        self.assertFalse(bad.ok)

    def test_08_confirmada_no_anulable(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        br = rect.crear_borrador_rectificativa(alb_doc.id, motivo="Y", ctx=ctx)
        rect.confirmar_rectificativa(br.documento.id, ctx=ctx)
        an = rect.anular_rectificativa(br.documento.id, ctx=ctx)
        self.assertFalse(an.ok)
        self.assertIn("append-only", an.mensaje)

    def test_09_roundtrip(self) -> None:
        data = _base()
        ctx = _ctx(data)
        alb_doc = _albaran_confirmado(data, ctx)
        br = rect.crear_borrador_rectificativa(
            alb_doc.id, motivo="RT", referencia_externa="RECT-1", ctx=ctx
        )
        rect.confirmar_rectificativa(br.documento.id, ctx=ctx)
        back = dict_to_appdata(appdata_to_dict(data))
        rects = [
            d
            for d in back.documentos
            if (d.tipo.value if hasattr(d.tipo, "value") else d.tipo)
            == "rectificativa"
        ]
        self.assertEqual(len(rects), 1)
        self.assertEqual(rects[0].documento_rectificado_id, alb_doc.id)
        self.assertEqual(rects[0].motivo_rectificacion, "RT")
        orig = next(d for d in back.documentos if d.id == alb_doc.id)
        self.assertEqual(
            orig.estado.value if hasattr(orig.estado, "value") else orig.estado,
            EstadoDocumento.RECTIFICADO.value,
        )

    def test_10_version(self) -> None:
        self.assertIn("Rectificativas", APP_VERSION)


if __name__ == "__main__":
    unittest.main()
