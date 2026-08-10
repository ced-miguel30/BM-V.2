"""Regresión P1 — responsable obligatorio en Merma Flet + listado Admin visible."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import clear_test_session
from app.core.models import MotivoMerma
from app.core.services import merma_service
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
)
from app.presentation.flet.presenters.terminal_inventario_presenter import (
    TerminalInventarioPresenter,
)
from app.presentation.flet.views import admin_shell_view, inventario_shell_view
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import (
    LOGIN_DIR,
    PASS_DIR,
    write_browser_fixture,
)

_ECON = re.compile(
    r"(€|euro|euros|\bcoste\b|\bprecio\b|\bmargen\b|\bimporte\b|\bvaloraci[oó]n\b)",
    re.I,
)


class _Harness(unittest.TestCase):
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


class TestResponsableMermaObligatorio(_Harness):
    def _inv(self) -> TerminalInventarioPresenter:
        p = TerminalInventarioPresenter()
        p.entrar()
        p.seleccionar_espacio("merma")
        return p

    def test_selector_inicial_vacio_y_placeholder_ui(self) -> None:
        p = self._inv()
        self.assertIsNone(p.screen().responsable_seleccionado)
        # Construcción UI: hint correcto y sin value autofill
        from app.presentation.flet.inventory_viewmodels import InventarioScreenVM
        from app.presentation.flet.viewmodels import SessionVM

        # Usa screen real
        screen = p.screen()
        built = []

        def capture_sel(v):
            built.append(v)

        dd = inventario_shell_view._responsable_dropdown(screen, capture_sel)
        self.assertEqual(dd.hint_text, "Selecciona un responsable")
        self.assertIsNone(dd.value)

    def test_sin_responsable_rechaza_sin_tocar_stock(self) -> None:
        p = self._inv()
        data = get_container().app_data_store.get()
        stock0 = next(l for l in data.lotes if l.id == "bl_pan").cantidad_restante
        n_mov = len(getattr(data, "movimientos", []) or [])
        n_mermas = len(data.mermas)
        s = p.anadir_merma("bl_pan", 1.0, MotivoMerma.MERMA.value)
        self.assertFalse(s.feedback.ok)
        self.assertEqual(s.feedback.codigo, "VALIDACION")
        self.assertIn("responsable", s.feedback.mensaje.lower())
        data2 = get_container().app_data_store.get()
        self.assertEqual(
            next(l for l in data2.lotes if l.id == "bl_pan").cantidad_restante, stock0
        )
        self.assertEqual(len(getattr(data2, "movimientos", []) or []), n_mov)
        self.assertEqual(len(data2.mermas), n_mermas)
        self.assertTrue(s.cesta_merma_vacia)

    def test_seleccion_valida_resumen_y_limpia_tras_exito(self) -> None:
        p = self._inv()
        p.seleccionar_responsable("brm1")
        self.assertEqual(p.screen().responsable_seleccionado, "brm1")
        s = p.anadir_merma("bl_pan", 1.0, MotivoMerma.MERMA.value)
        self.assertTrue(s.feedback.ok)
        self.assertEqual(s.cesta_merma[0].responsable, "Cocina UI")
        s = p.confirmar_merma(fecha=date.today())
        self.assertTrue(s.feedback.ok, s.feedback.mensaje)
        self.assertIn("Cocina UI", s.feedback.mensaje)
        self.assertIsNone(s.responsable_seleccionado)
        self.assertIsNone(_ECON.search(s.feedback.mensaje))

    def test_cambio_pestana_limpia_seleccion(self) -> None:
        p = self._inv()
        p.seleccionar_responsable("brm1")
        p.seleccionar_espacio("alertas")
        p.seleccionar_espacio("merma")
        self.assertIsNone(p.screen().responsable_seleccionado)

    def test_desactivado_antes_de_confirmar_rechaza(self) -> None:
        p = self._inv()
        p.seleccionar_responsable("brm1")
        p.anadir_merma("bl_pan", 1.0, MotivoMerma.MERMA.value)
        # Login admin desactiva
        clear_test_session()
        admin = TerminalAdministracionPresenter()
        admin.login(LOGIN_DIR, PASS_DIR)
        admin.proponer_desactivacion("brm1")
        admin.confirmar_pendiente()
        clear_test_session()
        # Misma composition + cesta en memoria del container
        p2 = TerminalInventarioPresenter()
        p2.entrar()
        p2.seleccionar_espacio("merma")
        # Cesta todavía con líneas del basket store compartido
        self.assertFalse(p2.screen().cesta_merma_vacia)
        stock0 = next(
            l for l in get_container().app_data_store.get().lotes if l.id == "bl_pan"
        ).cantidad_restante
        n_mov = len(getattr(get_container().app_data_store.get(), "movimientos", []) or [])
        s = p2.confirmar_merma(fecha=date.today())
        self.assertFalse(s.feedback.ok)
        self.assertIn("inactivo", s.feedback.mensaje.lower())
        data = get_container().app_data_store.get()
        self.assertEqual(
            next(l for l in data.lotes if l.id == "bl_pan").cantidad_restante, stock0
        )
        self.assertEqual(len(getattr(data, "movimientos", []) or []), n_mov)

    def test_catalogo_sin_activos_y_sin_autofill_tras_refresco(self) -> None:
        clear_test_session()
        admin = TerminalAdministracionPresenter()
        admin.login(LOGIN_DIR, PASS_DIR)
        admin.proponer_desactivacion("brm1")
        admin.confirmar_pendiente()
        clear_test_session()
        p = TerminalInventarioPresenter()
        p.entrar()
        p.seleccionar_espacio("merma")
        self.assertEqual(p.screen().responsables_merma, ())
        self.assertIsNone(p.screen().responsable_seleccionado)
        p.seleccionar_responsable("brm1")
        self.assertIsNone(p.screen().responsable_seleccionado)

    def test_idempotencia_confirmacion(self) -> None:
        p = self._inv()
        p.seleccionar_responsable("brm1")
        p.anadir_merma("bl_pan", 1.0, MotivoMerma.MERMA.value)
        s1 = p.confirmar_merma(fecha=date.today())
        self.assertTrue(s1.feedback.ok)
        n = len(get_container().app_data_store.get().mermas)
        s2 = p.confirmar_merma(fecha=date.today())
        self.assertFalse(s2.feedback.ok)  # cesta vacía
        self.assertEqual(len(get_container().app_data_store.get().mermas), n)


class TestAdminListadoVisible(_Harness):
    def test_listado_y_vacio_y_mutaciones(self) -> None:
        p = TerminalAdministracionPresenter()
        p.login(LOGIN_DIR, PASS_DIR)
        s = p.screen()
        self.assertGreaterEqual(len(s.responsables), 1)
        # UI construible con filas
        from app.presentation.flet.app_shell_administracion import TerminalAdministracionShell

        class _Fake:
            width = 900
            title = ""
            theme_mode = None
            padding = 0
            bgcolor = None
            on_resize = None

            def add(self, *a):
                return None

            def update(self):
                return None

        shell = TerminalAdministracionShell(_Fake(), presenter=p)
        shell.refresh()
        # vacío forzado
        p.set_filtro("ZZZ_NADA")
        self.assertEqual(p.screen().responsables, ())
        p.set_filtro("")
        p.proponer_creacion("Visible ADM")
        p.confirmar_pendiente()
        names = [r.nombre for r in p.screen().responsables]
        self.assertIn("Visible ADM", names)
        rid = next(r.id for r in p.screen().responsables if r.nombre == "Visible ADM")
        p.proponer_renombre(rid, "Visible REN")
        p.confirmar_pendiente()
        self.assertIn("Visible REN", [r.nombre for r in p.screen().responsables])
        p.proponer_desactivacion(rid)
        p.confirmar_pendiente()
        row = next(r for r in p.screen().responsables if r.id == rid)
        self.assertFalse(row.activo)
        p.proponer_reactivacion(rid)
        p.confirmar_pendiente()
        self.assertTrue(next(r for r in p.screen().responsables if r.id == rid).activo)


if __name__ == "__main__":
    unittest.main()
