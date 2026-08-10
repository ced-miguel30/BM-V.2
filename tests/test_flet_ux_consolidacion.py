"""Regresión UX Flet — buscador Restaurante y feedback merma Inventario."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path
os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, reset_container
from app.core.auth.session import clear_test_session
from app.core.models import MotivoMerma
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.app_shell import TerminalRestauranteShell
from app.presentation.flet.mappers import (
    MermaLineaOperativa,
    map_merma_registro_feedback,
)
from app.presentation.flet.presenters.terminal_inventario_presenter import (
    TerminalInventarioPresenter,
)
from app.presentation.flet.presenters.terminal_restaurante_presenter import (
    TerminalRestaurantePresenter,
)
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import write_browser_fixture

_ECON = re.compile(
    r"(€|euro|euros|\bcoste\b|\bprecio\b|\bmargen\b|\bimporte\b|\bvaloraci[oó]n\b)",
    re.I,
)


class _FakePage:
    def __init__(self) -> None:
        self.width = 900
        self.title = ""
        self.theme_mode = None
        self.padding = 0
        self.bgcolor = None
        self.on_resize = None
        self._added = []

    def add(self, *controls) -> None:
        self._added.extend(controls)

    def update(self) -> None:
        return None


class _UxHarness(unittest.TestCase):
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


class TestBuscadorRestauranteUX(_UxHarness):
    def _shell(self) -> TerminalRestauranteShell:
        page = _FakePage()
        shell = TerminalRestauranteShell(page)
        shell.presenter.entrar()
        shell.presenter.seleccionar_servicio("desayuno")
        shell.refresh()
        return shell

    def test_entrada_progresiva_conserva_campo_y_filtra(self) -> None:
        shell = self._shell()
        search_id = id(shell._search_field)
        catalog_id = id(shell._catalog_results)
        for fragment in ("P", "Po", "Por", "Porr"):
            shell._on_search(fragment)
            self.assertEqual(id(shell._search_field), search_id)
            self.assertEqual(id(shell._catalog_results), catalog_id)
            self.assertEqual(shell._last_refresh_kind, "catalog")
            self.assertEqual(shell.presenter.screen().busqueda, fragment)
            nombres = [i.nombre.lower() for i in shell.presenter.screen().catalogo]
            self.assertTrue(any("porridge" in n for n in nombres), nombres)

    def test_conserva_servicio_y_cesta(self) -> None:
        shell = self._shell()
        shell.presenter.anadir_producto_directo("bp_zumo", 1.0)
        shell.refresh()
        n_lineas = len(shell.presenter.screen().cesta.lineas)
        search_id = id(shell._search_field)
        shell._on_search("Zumo")
        screen = shell.presenter.screen()
        self.assertEqual(screen.servicio_activo, "desayuno")
        self.assertEqual(len(screen.cesta.lineas), n_lineas)
        self.assertEqual(id(shell._search_field), search_id)
        self.assertFalse(any(i.tipo == "receta" and "porridge" in i.nombre.lower() for i in screen.catalogo))

    def test_vacio_sin_resultados_y_limpieza(self) -> None:
        shell = self._shell()
        shell._on_search("ZZZ_NO_MATCH_€")
        self.assertEqual(shell.presenter.screen().catalogo, ())
        # Estado vacío de UI: columna con un control de texto
        self.assertEqual(len(shell._catalog_results.controls), 1)
        shell._on_search("")
        self.assertEqual(shell.presenter.screen().busqueda, "")
        self.assertGreater(len(shell.presenter.screen().catalogo), 0)

    def test_case_insensitive_y_especiales(self) -> None:
        shell = self._shell()
        shell._on_search("porridge")
        n1 = {i.id for i in shell.presenter.screen().catalogo}
        shell._on_search("PORRIDGE")
        n2 = {i.id for i in shell.presenter.screen().catalogo}
        self.assertEqual(n1, n2)
        self.assertIn("br_porridge", n1)

    def test_no_doble_add_por_busqueda(self) -> None:
        shell = self._shell()
        shell.presenter.anadir_receta("br_porridge", 4.0)
        shell.refresh()
        n = len(shell.presenter.screen().cesta.lineas)
        shell._on_search("Por")
        shell._on_search("Porr")
        self.assertEqual(len(shell.presenter.screen().cesta.lineas), n)


class TestFeedbackMermaUX(_UxHarness):
    def test_mapper_exito_tipado_sin_economia(self) -> None:
        fb = map_merma_registro_feedback(
            ok=True,
            lineas=(
                MermaLineaOperativa(
                    nombre="Pan UI",
                    cantidad=1.0,
                    unidad="Ud",
                    lote_id="bl_pan",
                    motivo="Merma",
                    servicio="Almacén / General",
                ),
            ),
        )
        self.assertTrue(fb.ok)
        self.assertIn("Pan UI", fb.mensaje)
        self.assertIn("1", fb.mensaje)
        self.assertIn("Ud", fb.mensaje)
        self.assertIn("bl_pan", fb.mensaje)
        self.assertIn("Merma", fb.mensaje)
        self.assertIsNone(_ECON.search(fb.mensaje))

    def test_mapper_error_validacion_y_denegado(self) -> None:
        fb = map_merma_registro_feedback(
            ok=False, mensaje_backend="La cantidad debe ser mayor que 0."
        )
        self.assertFalse(fb.ok)
        self.assertIn("cantidad", fb.mensaje.lower())
        fb2 = map_merma_registro_feedback(
            ok=False, mensaje_backend="No autorizado para esta operación."
        )
        self.assertEqual(fb2.codigo, "DENEGADO")
        fb3 = map_merma_registro_feedback(
            ok=False, mensaje_backend="La cesta está vacía."
        )
        self.assertEqual(fb3.codigo, "CESTA_VACIA")

    def test_mapper_idempotente(self) -> None:
        fb = map_merma_registro_feedback(
            ok=False, mensaje_backend="Ya registrado", codigo="IDEMPOTENTE"
        )
        self.assertEqual(fb.codigo, "IDEMPOTENTE")

    def test_presenter_exito_operativo(self) -> None:
        p = TerminalInventarioPresenter()
        p.entrar()
        p.seleccionar_espacio("merma")
        p.seleccionar_responsable("brm1")
        p.anadir_merma("bl_pan", 1.0, MotivoMerma.MERMA.value)
        s = p.confirmar_merma(fecha=date.today())
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        msg = s.feedback.mensaje
        self.assertIn("Pan", msg)
        self.assertIn("bl_pan", msg)
        self.assertIn("Cocina UI", msg)
        self.assertIsNone(s.responsable_seleccionado)
        self.assertIsNone(_ECON.search(msg))
        self.assertNotIn("Consulte el módulo de costes", msg)

    def test_presenter_no_expone_excepcion_ni_ruta(self) -> None:
        fb = map_merma_registro_feedback(
            ok=False,
            mensaje_backend=r"Error C:\Users\x\file.py line 10 traceback",
        )
        # sanitize no añade rutas; el mensaje de error de validación genérico se limpia si tiene €
        self.assertNotIn("traceback", fb.mensaje.lower())


class TestUxRegresionBasica(_UxHarness):
    def test_composicion_y_permisos_ambos(self) -> None:
        pr = TerminalRestaurantePresenter()
        pr.entrar()
        self.assertTrue(pr.screen().session.authenticated)
        reset_container()
        clear_test_session()
        configure_for_flet(data_path=self.json_path)
        pi = TerminalInventarioPresenter()
        pi.entrar()
        self.assertEqual(pi.screen().session.actor_id, "terminal_inventario")
        fb = pi.intentar_consulta_economica()
        self.assertFalse(fb.ok)


if __name__ == "__main__":
    unittest.main()
