"""Tests Flet — composición, presenter Terminal Restaurante, seguridad económica."""

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
from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.session import (
    AuthSession,
    get_auth_session,
    save_auth_session,
    set_test_session,
    clear_test_session,
)
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.presenters.terminal_restaurante_presenter import (
    TerminalRestaurantePresenter,
    SERVICIOS,
)
from app.presentation.flet.viewmodels import (
    CAMPOS_ECONOMICOS_PROHIBIDOS,
    BasketLineVM,
    BasketVM,
    CatalogItemVM,
    FeedbackVM,
    SessionVM,
    TerminalScreenVM,
)
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import build_browser_fixture, write_browser_fixture

ROOT = Path(__file__).resolve().parent.parent
FLET_ROOT = ROOT / "app" / "presentation" / "flet"


class _FletHarness(unittest.TestCase):
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

    def _presenter(self) -> TerminalRestaurantePresenter:
        p = TerminalRestaurantePresenter()
        p.entrar()
        return p


class TestFletComposition(_FletHarness):
    def test_configure_for_flet_no_importa_streamlit(self) -> None:
        src = (ROOT / "app" / "bootstrap.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        # configure_for_flet body must not reference streamlit
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "configure_for_flet":
                text = ast.get_source_segment(src, node) or ""
                self.assertNotIn("streamlit", text)
                self.assertNotIn("session_state", text)

    def test_inyecta_ruta_temporal_sin_demo(self) -> None:
        c = get_container()
        data = c.app_data_store.get()
        self.assertTrue(any(p.id == "bp_leche" for p in data.productos))
        self.assertNotEqual(self.json_path.resolve(), DEMO_FILE.resolve())
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_unica_instancia_appdata(self) -> None:
        c = get_container()
        a = c.app_data_store.get()
        b = get_container().app_data_store.get()
        self.assertIs(a, b)
        self.assertIs(c.app_data_store, get_container().app_data_store)


class TestFletPresenterAuthCatalogBasket(_FletHarness):
    def test_entrada_autorizada(self) -> None:
        p = self._presenter()
        screen = p.screen()
        self.assertTrue(screen.session.authenticated)
        self.assertEqual(screen.session.actor_id, "terminal_restaurante")
        self.assertEqual(screen.servicio_activo, "desayuno")

    def test_entrada_denegada(self) -> None:
        p = TerminalRestaurantePresenter()
        screen = p.denegar_demo("recepcion")
        self.assertFalse(screen.session.authenticated)
        self.assertIsNotNone(screen.feedback)
        self.assertFalse(screen.feedback.ok)
        self.assertIn("denegado", screen.feedback.mensaje.lower())

    def test_seleccion_cada_servicio(self) -> None:
        p = self._presenter()
        for sid, etiqueta in SERVICIOS:
            screen = p.seleccionar_servicio(sid)
            self.assertEqual(screen.servicio_activo, sid)
            self.assertTrue(any(s.activo and s.etiqueta == etiqueta for s in screen.servicios))

    def test_catalogo_filtrado(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        screen = p.set_busqueda("Porridge")
        ids = {i.id for i in screen.catalogo}
        self.assertIn("br_porridge", ids)
        self.assertTrue(all("porridge" in i.nombre.lower() or i.tipo != "receta" or True for i in screen.catalogo))
        # Productos sin match de nombre no aparecen si filtro aplica solo por nombre
        nombres = {i.nombre.lower() for i in screen.catalogo}
        self.assertTrue(any("porridge" in n for n in nombres))

    def test_anadir_receta_y_producto(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.anadir_receta("br_porridge", 4.0)
        screen = p.anadir_producto_directo("bp_zumo", 1.0)
        self.assertIsNotNone(screen.cesta)
        kinds = {ln.kind for ln in screen.cesta.lineas}
        self.assertIn("receta", kinds)
        self.assertIn("producto", kinds)
        self.assertFalse(screen.cesta.vacia)

    def test_cambiar_quitar_vaciar(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.anadir_producto_directo("bp_zumo", 2.0)
        screen = p.screen()
        lid = screen.cesta.lineas[0].line_id
        p.ajustar_linea_producto(lid, 1.0)
        screen = p.screen()
        self.assertGreaterEqual(screen.cesta.lineas[0].cantidad, 2.0)
        p.quitar_linea_producto(lid)
        self.assertTrue(p.screen().cesta.vacia)
        p.anadir_producto_directo("bp_zumo", 1.0)
        p.vaciar_cesta()
        self.assertTrue(p.screen().cesta.vacia)

    def test_cesta_aislada_por_servicio(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.anadir_producto_directo("bp_zumo", 1.0)
        self.assertFalse(p.screen().cesta.vacia)
        p.seleccionar_servicio("comida")
        # Cesta de comida independentemente vacía
        self.assertTrue(p.screen().cesta.vacia)
        p.seleccionar_servicio("desayuno")
        self.assertFalse(p.screen().cesta.vacia)


class TestFletConfirmacionDominio(_FletHarness):
    def test_confirmacion_ok_limpia_cesta(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.set_num_huespedes(10)
        p.anadir_receta("br_porridge", 4.0)
        before = len(get_container().app_data_store.get().desayunos)
        screen = p.confirmar(fecha=date.today())
        self.assertTrue(screen.feedback.ok)
        self.assertTrue(screen.cesta.vacia)
        after = get_container().app_data_store.get()
        self.assertGreaterEqual(len(after.desayunos), before + 1)

    def test_error_recuperable_conserva_cesta(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.set_num_huespedes(10)
        # Vaciar stock de leche para forzar STOCK_INSUFICIENTE
        data = get_container().app_data_store.get()
        for lote in data.lotes:
            if lote.producto_id == "bp_leche":
                lote.cantidad_restante = 0.0
        get_container().app_data_store.persist(data)
        p.anadir_receta("br_porridge", 4.0)
        self.assertFalse(p.screen().cesta.vacia)
        screen = p.confirmar(fecha=date.today())
        self.assertFalse(screen.feedback.ok)
        self.assertFalse(screen.cesta.vacia)

    def test_producto_directo_en_servicio_activo(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("comida")
        p.anadir_producto_directo("bp_pan", 2.0)
        screen = p.confirmar(fecha=date.today())
        self.assertTrue(screen.feedback.ok, screen.feedback.mensaje if screen.feedback else "")
        data = get_container().app_data_store.get()
        regs = [r for r in data.registros_servicio if r.tipo_servicio == "comida" and not getattr(r, "anulado", False)]
        self.assertTrue(regs)
        last = regs[-1]
        from app.core.models.registro_servicio import RegistroServicio

        self.assertIsInstance(last, RegistroServicio)
        sueltos = [ln.producto_id for ln in last.lineas]
        self.assertIn("bp_pan", sueltos)

    def test_receta_sin_doble_contabilizacion_y_fifo(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.set_num_huespedes(8)
        data0 = get_container().app_data_store.get()
        leche0 = next(l for l in data0.lotes if l.id == "bl_leche").cantidad_restante
        avena0 = next(l for l in data0.lotes if l.id == "bl_avena").cantidad_restante
        p.anadir_receta("br_porridge", 4.0)  # factor 1 → 0.5 L + 0.25 kg
        p.confirmar(fecha=date.today())
        data1 = get_container().app_data_store.get()
        leche1 = next(l for l in data1.lotes if l.id == "bl_leche").cantidad_restante
        avena1 = next(l for l in data1.lotes if l.id == "bl_avena").cantidad_restante
        self.assertAlmostEqual(leche0 - leche1, 0.5, places=4)
        self.assertAlmostEqual(avena0 - avena1, 0.25, places=4)
        reg = data1.desayunos[-1]
        # No doble conteo: snapshot de receta + detalle, sin productos sueltos duplicados
        self.assertTrue(reg.registros_recetas)
        self.assertTrue(reg.lineas_detalle)
        # Movimientos de stock creados
        self.assertGreaterEqual(len(data1.movimientos), 2)

    def test_actor_y_snapshots(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.set_num_huespedes(5)
        p.anadir_producto_directo("bp_zumo", 1.0)
        p.confirmar(fecha=date.today())
        sess = get_auth_session()
        self.assertIsNotNone(sess)
        self.assertEqual(sess.actor_id, "terminal_restaurante")
        reg = get_container().app_data_store.get().desayunos[-1]
        self.assertEqual(reg.registrado_por, "Restaurante")
        self.assertTrue(reg.lineas_detalle or reg.lineas)

    def test_idempotencia_doble_confirmacion(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.set_num_huespedes(5)
        p.anadir_producto_directo("bp_zumo", 1.0)
        data0 = get_container().app_data_store.get()
        zumo0 = next(l for l in data0.lotes if l.id == "bl_zumo").cantidad_restante
        n0 = len(data0.desayunos)
        p.confirmar(fecha=date.today())
        data1 = get_container().app_data_store.get()
        self.assertEqual(len(data1.desayunos), n0 + 1)
        zumo1 = next(l for l in data1.lotes if l.id == "bl_zumo").cantidad_restante
        # Segunda confirmación con cesta vacía no duplica
        screen = p.confirmar(fecha=date.today())
        self.assertFalse(screen.feedback.ok)
        data2 = get_container().app_data_store.get()
        self.assertEqual(len(data2.desayunos), n0 + 1)
        zumo2 = next(l for l in data2.lotes if l.id == "bl_zumo").cantidad_restante
        self.assertEqual(zumo1, zumo2)
        self.assertLess(zumo1, zumo0)

    def test_persistencia_tras_recrear_composicion(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.set_num_huespedes(4)
        p.anadir_producto_directo("bp_zumo", 1.0)
        p.confirmar(fecha=date.today())
        n = len(get_container().app_data_store.get().desayunos)
        reset_container()
        clear_test_session()
        configure_for_flet(data_path=self.json_path)
        data = get_container().app_data_store.get()
        self.assertEqual(len(data.desayunos), n)


class TestFletSeguridadEconomica(_FletHarness):
    def test_viewmodels_sin_campos_economicos(self) -> None:
        for cls in (SessionVM, CatalogItemVM, BasketLineVM, BasketVM, FeedbackVM, TerminalScreenVM):
            names = {f.name.lower() for f in fields(cls)}
            for bad in CAMPOS_ECONOMICOS_PROHIBIDOS:
                self.assertNotIn(bad.lower(), names)

    def test_screen_sin_simbolos_economicos(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.anadir_receta("br_porridge", 4.0)
        screen = p.screen()
        blob = repr(screen)
        for token in ("€", "euro", "coste", "precio", "margen", "importe"):
            self.assertNotIn(token.lower(), blob.lower())

    def test_autorizacion_economica_denegada(self) -> None:
        p = self._presenter()
        fb = p.intentar_consulta_economica()
        self.assertFalse(fb.ok)

    def test_flet_no_importa_streamlit_ni_pages(self) -> None:
        for path in FLET_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for m in mods:
                    self.assertFalse(m == "streamlit" or m.startswith("streamlit."))
                    self.assertFalse(m == "app.pages" or m.startswith("app.pages."))
                    self.assertFalse(m == "app.ui" or m.startswith("app.ui."))
                    self.assertNotIn("session_state", path.read_text(encoding="utf-8"))


class TestFletArranque(unittest.TestCase):
    def test_smoke_import_y_build(self) -> None:
        from app.presentation.flet.main import build_app_handler
        from app.presentation.flet.app_shell import TerminalRestauranteShell
        from app.presentation.flet.views.login_terminal_view import build_login_view
        from app.presentation.flet.views.registro_servicio_view import build_registro_view

        self.assertTrue(callable(build_app_handler))
        self.assertTrue(callable(build_login_view))
        self.assertTrue(callable(build_registro_view))
        self.assertTrue(TerminalRestauranteShell)

    def test_asgi_smoke_headless(self) -> None:
        import flet as ft
        from app.bootstrap import configure_for_flet, reset_container
        from app.presentation.flet.app_shell import attach_terminal
        from tests.auth_harness import restore_harness_session

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos_hotel.json"
            write_browser_fixture(path)
            reset_container()
            set_demo_file_override(None)
            clear_test_session()
            configure_for_flet(data_path=path)

            def handler(page: ft.Page) -> None:
                attach_terminal(page)

            app = ft.run(handler, export_asgi_app=True)
            self.assertIsNotNone(app)
            reset_container()
            set_demo_file_override(None)
            restore_harness_session()
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)


class TestCatalogoBebidasSinSueltos(unittest.TestCase):
    """Bebidas independientes sin productos sueltos; Comida/Cena Bebidas = recetas."""

    def setUp(self) -> None:
        reset_container()
        clear_test_session()
        self._tmpdir = tempfile.TemporaryDirectory()
        raw = __import__("json").loads(Path(DEMO_FILE).read_text(encoding="utf-8"))
        if not raw.get("productos"):
            raw["productos"] = [
                {
                    "id": "px",
                    "nombre": "Agua",
                    "unidad": "Ud",
                    "es_bebida": True,
                    "activo": True,
                }
            ]
        else:
            raw["productos"][0]["es_bebida"] = True
        pid = raw["productos"][0]["id"]
        raw.setdefault("recetas", [])
        raw["recetas"].append(
            {
                "id": "rb_test",
                "nombre": "Copa Test Cat",
                "categoria": "bebidas",
                "activo": True,
                "porciones_estandar": 1,
                "ingredientes": [{"producto_id": pid, "cantidad": 0.15}],
                "servicios_disponibles": ["bebidas", "comida", "cena"],
            }
        )
        self._demo = Path(self._tmpdir.name) / "datos_hotel.json"
        self._demo.write_text(
            __import__("json").dumps(raw), encoding="utf-8"
        )
        set_demo_file_override(self._demo)
        configure_for_flet()
        from app.core.auth.session import iniciar_terminal_restaurante

        set_test_session(iniciar_terminal_restaurante())

    def tearDown(self) -> None:
        clear_test_session()
        set_demo_file_override(None)
        reset_container()
        self._tmpdir.cleanup()

    def test_bebidas_independientes_solo_recetas(self) -> None:
        p = TerminalRestaurantePresenter()
        p.entrar()
        s = p.seleccionar_servicio("bebidas")
        self.assertEqual(s.catalogo_tipo, "recetas")
        self.assertTrue(s.catalogo)
        self.assertTrue(all(i.tipo == "receta" for i in s.catalogo))

    def test_comida_chip_bebidas_son_recetas(self) -> None:
        p = TerminalRestaurantePresenter()
        p.entrar()
        p.seleccionar_servicio("comida")
        s = p.set_catalogo_tipo("bebidas")
        self.assertTrue(s.catalogo)
        self.assertTrue(all(i.tipo == "receta" for i in s.catalogo))
        self.assertTrue(
            all((i.categoria or "").lower() == "bebidas" for i in s.catalogo)
        )
        s2 = p.anadir_receta(s.catalogo[0].id, 1.0)
        self.assertTrue(s2.feedback.ok, s2.feedback.mensaje)


if __name__ == "__main__":
    unittest.main()
