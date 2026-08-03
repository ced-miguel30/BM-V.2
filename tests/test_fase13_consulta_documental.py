"""Fase 13 — búsqueda y exportación documental.

Ejecutar:

    py -m unittest tests.test_fase13_consulta_documental -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import AppData, Producto, UnidadProducto
from app.core.services import albaran_service as alb
from app.core.services import documento_consulta_service as docq
from app.core.services import factura_service as fac
from app.core.services import proveedor_service as prv
from app.ui.theme import APP_VERSION


def _ctx(data: AppData):
    return build_app_context(uow=InMemoryUnitOfWork(data))


def _seed() -> AppData:
    data = AppData(productos=[Producto("p01", "Aceite", UnidadProducto.L)])
    ctx = _ctx(data)
    prv.crear_proveedor("Norte SA", nif_cif="B1", ctx=ctx)
    r = alb.crear_borrador_albaran(
        proveedor_id=data.proveedores[0].id,
        referencia_externa="ALB-99",
        fecha_documento=date(2026, 7, 10),
        ctx=ctx,
    )
    alb.anadir_linea_albaran(
        r.documento.id, producto_id="p01", cantidad=2.0, precio_total=6.0, ctx=ctx
    )
    alb.confirmar_albaran(r.documento.id, ctx=ctx)

    f = fac.crear_borrador_factura(
        proveedor_id=data.proveedores[0].id,
        referencia_externa="FAC-1",
        fecha_documento=date(2026, 7, 15),
        ctx=ctx,
    )
    fac.anadir_linea_factura(
        f.documento.id,
        producto_id="p01",
        cantidad=2.0,
        precio_total=6.5,
        documento_origen_id=r.documento.id,
        linea_origen_id=r.documento.lineas[0].id,
        ctx=ctx,
    )
    fac.confirmar_factura(f.documento.id, ctx=ctx)
    return data


class TestFase13ConsultaDocumental(unittest.TestCase):
    def test_01_filtro_tipo_y_texto(self) -> None:
        data = _seed()
        alb_only = docq.buscar_documentos(
            docq.FiltroDocumentos(tipo="albaran"), data=data
        )
        self.assertEqual(len(alb_only), 1)
        self.assertEqual(alb_only[0].tipo.value if hasattr(alb_only[0].tipo, "value") else alb_only[0].tipo, "albaran")

        por_ref = docq.buscar_documentos(
            docq.FiltroDocumentos(texto="FAC-1"), data=data
        )
        self.assertEqual(len(por_ref), 1)
        self.assertEqual(por_ref[0].referencia_externa, "FAC-1")

        por_prod = docq.buscar_documentos(
            docq.FiltroDocumentos(texto="Aceite"), data=data
        )
        self.assertGreaterEqual(len(por_prod), 1)

    def test_02_filtro_fechas(self) -> None:
        data = _seed()
        julio_fin = docq.buscar_documentos(
            docq.FiltroDocumentos(
                fecha_desde=date(2026, 7, 12),
                fecha_hasta=date(2026, 7, 31),
            ),
            data=data,
        )
        self.assertEqual(len(julio_fin), 1)
        self.assertEqual(julio_fin[0].referencia_externa, "FAC-1")

    def test_03_csv_incluye_lineas(self) -> None:
        data = _seed()
        docs = docq.buscar_documentos(data=data)
        bruto = docq.construir_csv_documentos(docs)
        texto = bruto.decode("utf-8-sig")
        self.assertIn("documento_id", texto)
        self.assertIn("ALB-99", texto)
        self.assertIn("FAC-1", texto)
        self.assertIn("Aceite", texto)

    def test_04_exportar_guarda_archivo(self) -> None:
        data = _seed()
        ctx = _ctx(data)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            with patch.object(docq, "EXPORTS_DIR", dest):
                r = docq.exportar_documentos_csv(ctx=ctx)
            self.assertTrue(r.ok, r.mensaje)
            self.assertIsNotNone(r.ruta)
            assert r.ruta is not None
            self.assertTrue(r.ruta.is_file())
            self.assertGreater(r.filas, 0)
            self.assertTrue(any(a.accion == "Exportar documentos" for a in data.actividades))

    def test_05_resumen(self) -> None:
        data = _seed()
        docs = docq.buscar_documentos(
            docq.FiltroDocumentos(tipo="factura"), data=data
        )
        res = docq.resumen_documento(docs[0])
        self.assertEqual(res["tipo"], "factura")
        self.assertEqual(res["lineas"], 1)
        self.assertEqual(res["importe"], 6.5)

    def test_06_version(self) -> None:
        self.assertIn("Documentos", APP_VERSION)


if __name__ == "__main__":
    unittest.main()
