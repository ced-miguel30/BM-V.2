"""Tests Flet Admin — cierre Streamlit-free (dashboard, catálogos, servidor, etc.)."""

from __future__ import annotations

import os
import tempfile
import unittest
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
    AdminScreenVM,
    assert_admin_sin_economia,
)
from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
)
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import (
    LOGIN_ADM,
    LOGIN_DIR,
    PASS_ADM,
    PASS_DIR,
    write_browser_fixture,
)

ROOT = Path(__file__).resolve().parent.parent


class _CierreHarness(unittest.TestCase):
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

    def _login_adm(self) -> TerminalAdministracionPresenter:
        p = TerminalAdministracionPresenter()
        s = p.login(LOGIN_ADM, PASS_ADM)
        self.assertTrue(s.session.authenticated, s.feedback.mensaje if s.feedback else "")
        return p


class TestAdminCierreDashboard(_CierreHarness):
    def test_dashboard_screen_con_auth(self) -> None:
        p = self._login_dir()
        s = p.screen()
        self.assertEqual(s.seccion, "inicio")
        self.assertTrue(s.periodo)
        self.assertIsInstance(s.consumo_count, int)
        self.assertIsInstance(s.merma_count, int)
        self.assertIsInstance(s.stock_bajo, int)
        self.assertIsInstance(s.caducidades, int)
        self.assertTrue(s.alerta_registro)
        self.assertIsInstance(s.revision, int)
        self.assertTrue(s.data_path_label)
        self.assertIn("inicio", ADMIN_SECCIONES)
        self.assertIsInstance(s.dashboard_error, str)
        self.assertIsInstance(s.stock_bajo_nombres, tuple)
        self.assertIsInstance(s.productos_total, int)
        self.assertIsNotNone(s.dashboard)
        self.assertTrue(s.dashboard.saludo)
        self.assertTrue(s.dashboard.periodo_label)
        if s.dashboard.puede_ver_economia:
            self.assertGreaterEqual(len(s.dashboard.metrics), 1)

    def test_dashboard_panel_ui(self) -> None:
        from app.presentation.flet.views.admin_shell_view import _panel_inicio

        p = self._login_dir()
        s = p.screen()
        ctrl = _panel_inicio(
            s, on_seccion=lambda _x: None, on_refresh_datos=lambda: None
        )
        self.assertIsNotNone(ctrl)

    def test_productos_paginacion(self) -> None:
        from app.presentation.flet.admin_viewmodels import PRODUCTOS_PAGE_SIZE

        p = self._login_dir()
        p.set_seccion("productos")
        s = p.screen()
        self.assertLessEqual(len(s.productos), PRODUCTOS_PAGE_SIZE)
        self.assertGreaterEqual(s.productos_total, len(s.productos))
        s2 = p.set_productos_page(1)
        self.assertEqual(s2.productos_page, 1 if s.productos_total > PRODUCTOS_PAGE_SIZE else 0)

    def test_nav_groups_cubren_secciones(self) -> None:
        from app.presentation.flet.admin_viewmodels import ADMIN_NAV_GROUPS

        flat = [s for _, secs in ADMIN_NAV_GROUPS for s in secs]
        for sec in ADMIN_SECCIONES:
            self.assertIn(sec, flat)

    def test_refresh_if_stale_no_crash(self) -> None:
        p = self._login_dir()
        s = p.refresh_datos()
        self.assertTrue(s.session.authenticated)
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        get_container().app_data_store.refresh_if_stale()


class TestAdminCierreCatalogos(_CierreHarness):
    def test_crear_departamento(self) -> None:
        p = self._login_dir()
        p.set_seccion("catalogos")
        n0 = len([d for d in p.screen().departamentos if d.activo])
        s = p.crear_departamento_catalogo("Dep Cierre Test")
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        activos = [d for d in s.departamentos if d.activo]
        self.assertEqual(len(activos), n0 + 1)
        self.assertTrue(any(d.nombre == "Dep Cierre Test" for d in activos))

    def test_crear_ubicacion(self) -> None:
        p = self._login_dir()
        s = p.crear_ubicacion_catalogo("Ubi Cierre", "UBI-CIERRE-1")
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertTrue(
            any(u.nombre == "Ubi Cierre" and u.activo for u in s.ubicaciones)
        )


class TestAdminCierreActividad(_CierreHarness):
    def test_actividad_lista(self) -> None:
        p = self._login_dir()
        p.set_seccion("actividad")
        s = p.screen()
        self.assertIsInstance(s.actividades, tuple)
        self.assertLessEqual(len(s.actividades), 50)
        for a in s.actividades:
            self.assertTrue(hasattr(a, "fecha"))
            self.assertTrue(hasattr(a, "usuario"))
            self.assertTrue(hasattr(a, "accion"))
            self.assertTrue(hasattr(a, "detalle"))


class TestAdminCierreServidor(_CierreHarness):
    def test_shared_root_vacio_rechazado(self) -> None:
        p = self._login_dir()
        s = p.guardar_shared_root("")
        self.assertTrue(s.feedback)
        self.assertFalse(s.feedback.ok)
        self.assertIn("ruta", s.feedback.mensaje.lower())

    def test_shared_root_espacios_rechazado(self) -> None:
        p = self._login_dir()
        s = p.guardar_shared_root("   ")
        self.assertTrue(s.feedback)
        self.assertFalse(s.feedback.ok)


class TestAdminCierreZonaPeligro(_CierreHarness):
    def test_denegado_sin_permiso_adm(self) -> None:
        p = self._login_adm()
        s = p.screen()
        self.assertFalse(s.puede_zona_peligro)
        s2 = p.ejecutar_op_destructiva(
            "restablecer_mock",
            "BORRAR TODOS LOS DATOS",
            True,
        )
        self.assertTrue(s2.feedback)
        self.assertFalse(s2.feedback.ok)
        self.assertIn("dirección", s2.feedback.mensaje.lower())

    def test_dir_ve_ops(self) -> None:
        p = self._login_dir()
        s = p.screen()
        self.assertTrue(s.puede_zona_peligro)
        self.assertTrue(any(o.id == "restablecer_mock" for o in s.ops_destructivas))


class TestAdminCierreSecciones(_CierreHarness):
    def test_secciones_incluyen_cierre(self) -> None:
        for key in (
            "catalogos",
            "actividad",
            "servidor",
            "zona_peligro",
            "documentos",
        ):
            self.assertIn(key, ADMIN_SECCIONES)
        assert_admin_sin_economia(AdminScreenVM)


class TestAdminDocumentosWorkflow(_CierreHarness):
    def _seed_compra_confirmada(self, p: TerminalAdministracionPresenter) -> str:
        s = p.screen()
        prov = next((x for x in s.proveedores if x.activo), None)
        prod = next((x for x in s.productos if x.activo), None)
        self.assertIsNotNone(prov)
        self.assertIsNotNone(prod)
        assert prov is not None and prod is not None
        p.set_compra_tipo("albaran")
        p.set_compra_cabecera(prov.id, "ALB-FLET-DOC", "albaran")
        p.añadir_linea_compra(prod.id, 2.0, 1.5)
        s = p.confirmar_compra_borrador()
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        docs = p.set_seccion("documentos").documentos
        self.assertTrue(docs)
        return docs[0].id

    def test_factura_tipo_en_borrador(self) -> None:
        p = self._login_dir()
        s = p.screen()
        prov = next(x for x in s.proveedores if x.activo)
        prod = next(x for x in s.productos if x.activo)
        p.set_compra_tipo("factura")
        p.set_compra_cabecera(prov.id, "FAC-1", "factura")
        p.añadir_linea_compra(prod.id, 1.0, 3.0)
        s = p.guardar_borrador_compra()
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertEqual(s.compra_tipo, "factura")
        self.assertTrue(s.compra_documento_id)

    def test_adjunto_y_rectificativa_economica(self) -> None:
        p = self._login_dir()
        doc_id = self._seed_compra_confirmada(p)
        contenido = b"%PDF-1.4 fake adjunto " + os.urandom(16)
        s = p.adjuntar_archivo_documento(doc_id, "albaran.pdf", contenido)
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertTrue(any(a.documento_id == doc_id for a in s.archivos))

        s = p.proponer_rectificativa_economica(doc_id, "Ajuste documental Flet")
        self.assertTrue(s.pending and s.pending.kind == "rectificativa_economica")
        s = p.confirmar_pendiente()
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")


if __name__ == "__main__":
    unittest.main()
