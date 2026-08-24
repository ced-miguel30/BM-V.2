"""Tests Flet — Terminal Inventario economato (auth, recepción, maestros)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import clear_test_session, iniciar_terminal_inventario, set_test_session
from app.core.models import EstadoDocumento, TipoDocumento
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.inventory_document_viewmodels import EconomatoPanelVM
from app.presentation.flet.inventory_viewmodels import ESPACIOS, ESPACIOS_OPS
from app.presentation.flet.presenters.terminal_inventario_presenter import (
    TerminalInventarioPresenter,
)


class _Harness(unittest.TestCase):
    def setUp(self) -> None:
        reset_container()
        clear_test_session()
        self._tmpdir = tempfile.TemporaryDirectory()
        src = Path(DEMO_FILE).read_bytes()
        self._demo = Path(self._tmpdir.name) / "datos_hotel.json"
        self._demo.write_bytes(src)
        set_demo_file_override(self._demo)
        configure_for_flet()
        set_test_session(iniciar_terminal_inventario())

    def tearDown(self) -> None:
        clear_test_session()
        set_demo_file_override(None)
        reset_container()
        self._tmpdir.cleanup()

    def _p(self) -> TerminalInventarioPresenter:
        p = TerminalInventarioPresenter()
        p.entrar()
        return p


class TestEconomatoAuthEspacios(_Harness):
    def test_espacios_incluyen_economato(self) -> None:
        self.assertIn("recepcion", ESPACIOS)
        self.assertIn("maestros", ESPACIOS)
        self.assertIn("documentos", ESPACIOS)
        self.assertIn("historial", ESPACIOS)
        self.assertTrue(ESPACIOS_OPS.isdisjoint({"recepcion", "maestros"}))

    def test_recepcion_expone_economato_con_economia(self) -> None:
        p = self._p()
        s = p.seleccionar_espacio("recepcion")
        self.assertIsInstance(s.economato, EconomatoPanelVM)
        self.assertEqual(s.espacio_activo, "recepcion")
        # Campos económicos viven en el slice documental, no en ops
        self.assertTrue(hasattr(s.economato, "compra_lineas"))


class TestEconomatoRecepcion(_Harness):
    def _ensure_prov_prod(self):
        from app.core.services import proveedor_service
        data = get_container().app_data_store.get()
        prov = next((x for x in (data.proveedores or []) if getattr(x, "activo", True)), None)
        if prov is None:
            r = proveedor_service.crear_proveedor("Prov Eco Test", codigo="PECO1")
            self.assertTrue(r.ok, r.mensaje)
            data = get_container().app_data_store.get()
            prov = next(x for x in data.proveedores if x.codigo == "PECO1")
        prod = next((x for x in (data.productos or []) if getattr(x, "activo", True)), None)
        self.assertIsNotNone(prod, "Demo sin productos")
        return prov, prod

    def test_añadir_linea_y_totales(self) -> None:
        p = self._p()
        prov, prod = self._ensure_prov_prod()
        p.set_compra_cabecera(proveedor_id=prov.id, referencia="TEST-ALB-1")
        s = p.añadir_linea_compra(
            prod.id, cantidad="2", precio_unitario="10", igic_pct="7"
        )
        self.assertTrue(s.feedback.ok)
        self.assertEqual(len(s.economato.compra_lineas), 1)
        self.assertIsNotNone(s.economato.compra_totales)
        self.assertNotEqual(s.economato.compra_totales.total, "0,00")

    def test_guardar_borrador(self) -> None:
        p = self._p()
        prov, prod = self._ensure_prov_prod()
        p.set_compra_cabecera(proveedor_id=prov.id, referencia="BORR-ECO-1")
        p.añadir_linea_compra(prod.id, cantidad="1", precio_unitario="5", igic_pct="7")
        s = p.guardar_borrador_compra()
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertTrue(s.economato.compra_documento_id)
        data2 = get_container().app_data_store.get()
        doc = next(
            (d for d in data2.documentos if d.id == s.economato.compra_documento_id),
            None,
        )
        self.assertIsNotNone(doc)
        estado = doc.estado.value if hasattr(doc.estado, "value") else str(doc.estado)
        self.assertEqual(estado, EstadoDocumento.BORRADOR.value)


class TestEconomatoMaestros(_Harness):
    def test_crear_departamento(self) -> None:
        p = self._p()
        s = p.crear_departamento_maestro("Cocina Test Eco")
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        nombres = [d.nombre for d in s.economato.departamentos]
        self.assertIn("Cocina Test Eco", nombres)

    def test_crear_ubicacion_con_tipo(self) -> None:
        p = self._p()
        s = p.crear_ubicacion_maestro("Camara Eco", "CAM-ECO", "camara")
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        ubi = next(
            (u for u in s.economato.ubicaciones_maestro if u.codigo == "CAM-ECO"),
            None,
        )
        self.assertIsNotNone(ubi)
        self.assertEqual(ubi.tipo, "camara")


class TestEconomatoDocumentosHistorial(_Harness):
    def test_documentos_y_historial_cargan(self) -> None:
        p = self._p()
        s = p.seleccionar_espacio("documentos")
        self.assertIsNotNone(s.economato)
        s2 = p.seleccionar_espacio("historial")
        self.assertIsNotNone(s2.economato)
        nombre, csv_txt = p.exportar_historial_csv()
        self.assertTrue(nombre.endswith(".csv"))
        self.assertIn("fecha", csv_txt.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
