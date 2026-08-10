"""Tests Flet — Terminal Inventario (auth, operaciones, economía, smoke)."""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from dataclasses import fields
from datetime import date
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import clear_test_session
from app.core.models import EstadoAlerta, MotivoAjuste, MotivoMerma
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.inventory_viewmodels import (
    AlertaVM,
    AjustePreviewVM,
    InventarioScreenVM,
    LoteCaducidadVM,
    MermaLineaVM,
)
from app.presentation.flet.presenters.terminal_inventario_presenter import (
    TerminalInventarioPresenter,
)
from app.presentation.flet.viewmodels import CAMPOS_ECONOMICOS_PROHIBIDOS
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import write_browser_fixture

ROOT = Path(__file__).resolve().parent.parent
FLET_ROOT = ROOT / "app" / "presentation" / "flet"


class _InvHarness(unittest.TestCase):
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

    def _p(self) -> TerminalInventarioPresenter:
        p = TerminalInventarioPresenter()
        p.entrar()
        return p


class TestInventarioAuthNav(_InvHarness):
    def test_entrada_autorizada(self) -> None:
        s = self._p().screen()
        self.assertTrue(s.session.authenticated)
        self.assertEqual(s.session.actor_id, "terminal_inventario")
        self.assertEqual(len(s.espacios), 4)

    def test_entrada_denegada(self) -> None:
        p = TerminalInventarioPresenter()
        s = p.denegar_demo("recepcion")
        self.assertFalse(s.session.authenticated)
        self.assertFalse(s.feedback.ok)

    def test_navegacion_cuatro_espacios(self) -> None:
        p = self._p()
        for eid in ("alertas", "caducidad", "merma", "ajustes"):
            s = p.seleccionar_espacio(eid)
            self.assertEqual(s.espacio_activo, eid)


class TestInventarioOperaciones(_InvHarness):
    def test_alertas_y_cambio_estado(self) -> None:
        p = self._p()
        p.seleccionar_espacio("alertas")
        s = p.screen()
        # Puede haber 0 alertas; forzar sync y opcionalmente crear manual
        from app.core.services import alert_service

        r = alert_service.crear_alerta_manual("Alerta UI", "Prueba inventario", "bp_pan")
        self.assertTrue(r.ok, r.mensaje)
        alert_service.sincronizar_alertas()
        s = p.seleccionar_espacio("alertas")
        self.assertTrue(s.alertas)
        aid = s.alertas[0].id
        s = p.marcar_alerta(aid, EstadoAlerta.REVISADA.value)
        self.assertTrue(s.feedback.ok)

    def test_caducidad_a_merma_y_confirmacion(self) -> None:
        p = self._p()
        p.seleccionar_espacio("caducidad")
        s = p.screen()
        # Fixture tiene lote caducado bl_exp
        vencidos = [l for l in s.lotes_caducidad if l.lote_id == "bl_exp"]
        self.assertTrue(vencidos)
        lot = vencidos[0]
        s = p.enviar_caducidad_a_merma(lot.lote_id, min(1.0, lot.cantidad_restante))
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertFalse(s.cesta_merma_vacia)
        before = len(get_container().app_data_store.get().mermas)
        pan0 = next(l for l in get_container().app_data_store.get().lotes if l.id == "bl_exp").cantidad_restante
        s = p.confirmar_merma(fecha=date.today())
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        after = get_container().app_data_store.get()
        self.assertGreaterEqual(len(after.mermas), before + 1)
        pan1 = next(l for l in after.lotes if l.id == "bl_exp").cantidad_restante
        self.assertLess(pan1, pan0)
        self.assertTrue(s.cesta_merma_vacia)

    def test_merma_error_recuperable_conserva_cesta(self) -> None:
        p = self._p()
        p.seleccionar_espacio("merma")
        s = p.anadir_merma("bl_agua", 1.0, MotivoMerma.MERMA.value)
        self.assertTrue(s.feedback.ok)
        # Vaciar stock del lote tras añadir → fallo al confirmar
        data = get_container().app_data_store.get()
        for lote in data.lotes:
            if lote.id == "bl_agua":
                lote.cantidad_restante = 0.0
        get_container().app_data_store.persist(data)
        s = p.confirmar_merma(fecha=date.today())
        self.assertFalse(s.feedback.ok)
        self.assertFalse(s.cesta_merma_vacia)

    def test_ajuste_preview_confirm_actor_stock(self) -> None:
        p = self._p()
        p.seleccionar_espacio("ajustes")
        agua = next(l for l in p.screen().lotes_ajuste if l.lote_id == "bl_agua")
        antes = agua.restante
        s = p.previsualizar_ajuste(agua.lote_id, antes - 2, MotivoAjuste.RECONTEO_FISICO.value)
        self.assertIsNotNone(s.ajuste_preview)
        self.assertEqual(s.ajuste_preview.delta, -2.0)
        # Sin precio en preview VM
        names = {f.name for f in fields(s.ajuste_preview)}
        self.assertNotIn("precio_total", names)
        s = p.confirmar_ajuste(fecha=date.today())
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        data = get_container().app_data_store.get()
        self.assertTrue(data.ajustes)
        self.assertEqual(data.ajustes[-1].registrado_por, "Inventario")
        agua1 = next(l for l in data.lotes if l.id == "bl_agua").cantidad_restante
        self.assertAlmostEqual(agua1, antes - 2, places=4)
        self.assertGreaterEqual(len(data.movimientos), 1)

    def test_doble_confirmacion_ajuste_no_duplica(self) -> None:
        p = self._p()
        p.seleccionar_espacio("ajustes")
        agua = next(l for l in p.screen().lotes_ajuste if l.lote_id == "bl_agua")
        p.previsualizar_ajuste(agua.lote_id, agua.restante - 1, MotivoAjuste.OTRO.value)
        p.confirmar_ajuste(fecha=date.today())
        n = len(get_container().app_data_store.get().ajustes)
        s = p.confirmar_ajuste(fecha=date.today())
        self.assertFalse(s.feedback.ok)
        self.assertEqual(len(get_container().app_data_store.get().ajustes), n)

    def test_persistencia_tras_recrear(self) -> None:
        p = self._p()
        p.seleccionar_espacio("ajustes")
        agua = next(l for l in p.screen().lotes_ajuste if l.lote_id == "bl_leche")
        p.previsualizar_ajuste(agua.lote_id, agua.restante - 0.5, MotivoAjuste.ERROR_REGISTRO.value)
        p.confirmar_ajuste(fecha=date.today())
        n = len(get_container().app_data_store.get().ajustes)
        reset_container()
        clear_test_session()
        configure_for_flet(data_path=self.json_path)
        self.assertEqual(len(get_container().app_data_store.get().ajustes), n)


class TestInventarioSeguridad(_InvHarness):
    def test_viewmodels_sin_economia(self) -> None:
        for cls in (AlertaVM, LoteCaducidadVM, MermaLineaVM, AjustePreviewVM, InventarioScreenVM):
            names = {f.name.lower() for f in fields(cls)}
            for bad in CAMPOS_ECONOMICOS_PROHIBIDOS:
                self.assertNotIn(bad.lower(), names)

    def test_screen_sin_simbolos(self) -> None:
        p = self._p()
        p.seleccionar_espacio("ajustes")
        blob = repr(p.screen()).lower()
        for token in ("€", "euro", "coste", "precio", "margen", "importe"):
            self.assertNotIn(token, blob)

    def test_economia_denegada(self) -> None:
        p = self._p()
        fb = p.intentar_consulta_economica()
        self.assertFalse(fb.ok)

    def test_flet_inventario_sin_streamlit_pages(self) -> None:
        inv_files = [
            FLET_ROOT / "presenters" / "terminal_inventario_presenter.py",
            FLET_ROOT / "app_shell_inventario.py",
            FLET_ROOT / "main_inventario.py",
            FLET_ROOT / "inventory_viewmodels.py",
            FLET_ROOT / "views" / "inventario_shell_view.py",
        ]
        for path in inv_files:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            self.assertNotIn("session_state", text)
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for m in mods:
                    self.assertFalse(m == "streamlit" or m.startswith("streamlit."))
                    self.assertFalse(m.startswith("app.pages"))
                    # No acoplar vistas restaurante ↔ inventario
                    if "inventario" in path.name or "inventory" in path.name:
                        self.assertFalse(
                            "terminal_restaurante" in m
                            or m.endswith("registro_servicio_view")
                            or m.endswith("login_terminal_view")
                        )


class TestInventarioArranque(unittest.TestCase):
    def test_smoke_import_build(self) -> None:
        from app.presentation.flet.main_inventario import build_app_handler
        from app.presentation.flet.app_shell_inventario import TerminalInventarioShell

        self.assertTrue(callable(build_app_handler()))
        self.assertTrue(TerminalInventarioShell)

    def test_asgi_smoke(self) -> None:
        import flet as ft
        from app.presentation.flet.app_shell_inventario import attach_terminal_inventario

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos_hotel.json"
            write_browser_fixture(path)
            reset_container()
            set_demo_file_override(None)
            clear_test_session()
            configure_for_flet(data_path=path)

            def handler(page: ft.Page) -> None:
                attach_terminal_inventario(page)

            app = ft.run(handler, export_asgi_app=True)
            self.assertIsNotNone(app)
            reset_container()
            set_demo_file_override(None)
            restore_harness_session()
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)


if __name__ == "__main__":
    unittest.main()
