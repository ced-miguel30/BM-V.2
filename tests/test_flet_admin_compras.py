"""Tests Flet — Administración proveedores y compras."""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import clear_test_session
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.admin_viewmodels import (
    ADMIN_SECCIONES,
    CompraLineaVM,
    ProveedorAdminVM,
    assert_admin_sin_economia,
    assert_compra_linea_permite_precio_unitario,
)
from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
)
from app.presentation.flet.viewmodels import CAMPOS_ECONOMICOS_PROHIBIDOS
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import LOGIN_DIR, PASS_DIR, write_browser_fixture

ROOT = Path(__file__).resolve().parent.parent
FLET_ROOT = ROOT / "app" / "presentation" / "flet"
ADMIN_VIEW = FLET_ROOT / "views" / "admin_shell_view.py"


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name.split(".")[0])
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
            out.add(node.module)
    return out


class _ComprasHarness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.json_path = Path(self._tmp.name) / "datos_hotel.json"
        write_browser_fixture(self.json_path)
        reset_container()
        clear_test_session()
        set_demo_file_override(None)
        configure_for_flet(data_path=self.json_path)
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        reset_container()
        clear_test_session()
        set_demo_file_override(None)
        restore_harness_session()
        self._tmp.cleanup()
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def _login_dir(self) -> TerminalAdministracionPresenter:
        p = TerminalAdministracionPresenter()
        s = p.login(LOGIN_DIR, PASS_DIR)
        self.assertTrue(s.session.authenticated, s.feedback.mensaje if s.feedback else "")
        return p


class TestAdminProveedores(_ComprasHarness):
    def test_crear_proveedor(self) -> None:
        p = self._login_dir()
        n0 = len(p.screen().proveedores)
        s = p.crear_proveedor(
            "Proveedor Admin Nuevo",
            "PRV-ADM-01",
            nombre_comercial="Prov Adm",
            nif_cif="B12345678",
        )
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertEqual(len(s.proveedores), n0 + 1)
        self.assertTrue(any(x.codigo == "PRV-ADM-01" for x in s.proveedores))
        self.assertIn("proveedores", ADMIN_SECCIONES)


class TestAdminCompras(_ComprasHarness):
    def test_confirmar_compra_incrementa_stock_lote(self) -> None:
        p = self._login_dir()
        s = p.crear_proveedor("Prov Compra Test", "PRV-CMP-01")
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        prov = next(x for x in s.proveedores if x.codigo == "PRV-CMP-01")
        prod = next(x for x in s.productos if x.activo and x.nombre == "Pan UI")

        data0 = get_container().app_data_store.get()
        lotes0 = [l for l in data0.lotes if l.producto_id == prod.id]
        stock0 = sum(float(l.cantidad_restante) for l in lotes0)
        n_lotes0 = len(lotes0)

        p.set_compra_cabecera(prov.id, "ALB-FLET-1")
        p.añadir_linea_compra(prod.id, 3.0, 1.5)
        self.assertEqual(len(p.screen().compra_lineas), 1)

        s = p.confirmar_compra_borrador()
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertEqual(len(s.compra_lineas), 0)

        data1 = get_container().app_data_store.get()
        lotes1 = [l for l in data1.lotes if l.producto_id == prod.id]
        stock1 = sum(float(l.cantidad_restante) for l in lotes1)
        self.assertEqual(len(lotes1), n_lotes0 + 1)
        self.assertAlmostEqual(stock1, stock0 + 3.0, places=4)
        docs = [d for d in (data1.documentos or []) if getattr(d, "referencia_externa", None) == "ALB-FLET-1"]
        self.assertEqual(len(docs), 1)
        estado = docs[0].estado.value if hasattr(docs[0].estado, "value") else str(docs[0].estado)
        self.assertEqual(estado, "confirmado")

    def test_update_linea_y_busqueda_por_codigo(self) -> None:
        p = self._login_dir()
        s = p.crear_proveedor("Prov Edit Linea", "PRV-EDIT-01")
        self.assertTrue(s.feedback and s.feedback.ok)
        prov = next(x for x in s.proveedores if x.codigo == "PRV-EDIT-01")
        prod = next(x for x in s.productos if x.activo and x.nombre == "Pan UI")
        p.set_compra_cabecera(prov.id, "ALB-EDIT-1")
        p.añadir_linea_compra(prod.id, 2.0, 1.0)
        self.assertEqual(len(p.screen().compra_lineas), 1)

        s = p.update_linea_compra(0, cantidad=5.0, precio_unitario=2.25)
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        ln = s.compra_lineas[0]
        self.assertAlmostEqual(ln.cantidad, 5.0)
        self.assertAlmostEqual(ln.precio_unitario, 2.25)

        # búsqueda por nombre único
        s = p.añadir_linea_compra_por_busqueda("Pan UI", 1.0, 0.5)
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertEqual(len(s.compra_lineas), 2)

        # código exacto si existe
        if prod.codigo:
            n0 = len(p.screen().compra_lineas)
            s = p.añadir_linea_compra_por_busqueda(prod.codigo, 1.0, 0.5)
            self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
            self.assertEqual(len(s.compra_lineas), n0 + 1)

        s = p.añadir_linea_compra_por_busqueda("zzz-no-existe", 1.0, 1.0)
        self.assertTrue(s.feedback and not s.feedback.ok)


class TestAdminArquitecturaCompras(_ComprasHarness):
    def test_compra_vm_economia_permitida(self) -> None:
        assert_compra_linea_permite_precio_unitario()
        assert_admin_sin_economia(ProveedorAdminVM)
        self.assertIn("precio_unitario", {f.name for f in fields(CompraLineaVM)})
        for f in fields(ProveedorAdminVM):
            self.assertNotIn(f.name.lower(), CAMPOS_ECONOMICOS_PROHIBIDOS)

    def test_admin_view_sin_servicios(self) -> None:
        imports = _imports_of(ADMIN_VIEW)
        text = ADMIN_VIEW.read_text(encoding="utf-8")
        self.assertNotIn("AppData", text)
        self.assertFalse(any(i.startswith("app.core.services") for i in imports))
        self.assertFalse(any(i.startswith("app.core.repositories") for i in imports))
        self.assertNotIn("json", imports)
        self.assertNotIn("streamlit", imports)
        self.assertIn("compras", ADMIN_SECCIONES)
        self.assertIn("proveedores", ADMIN_SECCIONES)


if __name__ == "__main__":
    unittest.main()
