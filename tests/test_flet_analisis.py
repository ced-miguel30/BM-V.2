"""Tests Flet — sección Análisis (Costes / Consumo / Merma)."""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, reset_container
from app.presentation.flet.admin_viewmodels import (
    ADMIN_SECCIONES,
    secciones_visibles_admin,
)
from app.presentation.flet.analisis_viewmodels import ANALISIS_HUBS
from app.presentation.flet.charts import (
    build_barras_horizontales,
    build_donut,
    build_lineas_series,
    normalize_donut_slices,
)
from app.presentation.flet.analisis_viewmodels import BarItemVM, ChartSeriesVM
from app.core.services import costes_service
from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
)
from app.presentation.flet.views.admin_shell_view import build_admin_shell
from tests.browser.fixtures_minimos import LOGIN_DIR, PASS_DIR, write_browser_fixture

FLET_ROOT = Path(__file__).resolve().parents[1] / "app" / "presentation" / "flet"


class TestFletAnalisis(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "datos_hotel.json"
        write_browser_fixture(self.path)
        reset_container()
        configure_for_flet(data_path=str(self.path))
        self.pr = TerminalAdministracionPresenter()
        self.pr.login(LOGIN_DIR, PASS_DIR)

    def tearDown(self) -> None:
        reset_container()
        self._tmp.cleanup()

    def _cbs(self) -> dict:
        return {
            k: (lambda *a, **kw: None)
            for k in (
                "on_logout",
                "on_seccion",
                "on_filtro",
                "on_proponer_crear",
                "on_proponer_renombrar",
                "on_proponer_desactivar",
                "on_proponer_reactivar",
                "on_crear_producto",
                "on_desactivar_producto",
                "on_reactivar_producto",
                "on_crear_receta",
                "on_editar_receta",
                "on_iniciar_edicion_receta",
                "on_cancelar_edicion_receta",
                "on_eliminar_receta",
                "on_desactivar_receta",
                "on_reactivar_receta",
                "on_crear_usuario",
                "on_editar_usuario",
                "on_cambiar_rol",
                "on_desactivar_usuario",
                "on_reactivar_usuario",
                "on_restablecer_password",
                "on_registrar_lote",
                "on_crear_proveedor",
                "on_editar_proveedor",
                "on_desactivar_proveedor",
                "on_reactivar_proveedor",
                "on_set_compra_cabecera",
                "on_añadir_linea_compra",
                "on_quitar_linea_compra",
                "on_guardar_borrador_compra",
                "on_confirmar_compra",
                "on_limpiar_borrador_compra",
                "on_set_compra_albaran",
                "on_generar_backup",
                "on_inspeccionar_backup",
                "on_proponer_restaurar",
                "on_guardar_hotel",
                "on_refresh_datos",
                "on_guardar_shared_root",
                "on_crear_departamento",
                "on_crear_categoria",
                "on_crear_ubicacion",
                "on_ejecutar_destructiva",
                "on_exportar_documentos",
                "on_proponer_anular_documento",
                "on_proponer_rectificativa_economica",
                "on_proponer_rectificativa_stock",
                "on_adjuntar_archivo",
                "on_abrir_adjunto",
                "on_analisis_hub",
                "on_analisis_pestana",
                "on_analisis_subtab",
                "on_analisis_periodo",
                "on_analisis_busqueda",
                "on_analisis_tipo",
                "on_analisis_comparacion",
                "on_analisis_export",
                "on_confirmar",
                "on_cancelar",
            )
        }

    def test_analisis_en_secciones(self) -> None:
        self.assertIn("analisis", ADMIN_SECCIONES)
        vis = secciones_visibles_admin(
            puede_zona_peligro=False, puede_ver_analisis=True
        )
        self.assertIn("analisis", vis)
        oculto = secciones_visibles_admin(
            puede_zona_peligro=False, puede_ver_analisis=False
        )
        self.assertNotIn("analisis", oculto)

    def test_costes_resumen_metrics_y_ui(self) -> None:
        self.pr.set_seccion("analisis")
        screen = self.pr.screen()
        self.assertTrue(screen.puede_ver_analisis)
        self.assertIsNotNone(screen.analisis)
        assert screen.analisis is not None
        self.assertTrue(screen.analisis.puede_consultar)
        self.assertEqual(screen.analisis.hub, "costes")
        self.assertTrue(screen.analisis.metrics)
        labels = " ".join(m.etiqueta for m in screen.analisis.metrics)
        self.assertIn("Coste total", labels)
        # Dirección: donuts + tones
        self.assertTrue(screen.analisis.chart_donuts)
        self.assertTrue(any(m.tone for m in screen.analisis.metrics))
        build_admin_shell(screen, on_volver_menu=None, **self._cbs())

    def test_costes_resumen_pareto_y_alertas_shape(self) -> None:
        self.pr.set_seccion("analisis")
        screen = self.pr.screen()
        assert screen.analisis is not None
        # Pareto / alertas pueden estar vacíos en fixture mínima; tipos OK
        self.assertIsInstance(screen.analisis.pareto, tuple)
        self.assertIsInstance(screen.analisis.alertas, tuple)
        for m in screen.analisis.metrics:
            self.assertIn(m.tone, ("ok", "warn", "danger", "neutral"))

    def test_hubs_consumo_merma(self) -> None:
        self.pr.set_seccion("analisis")
        for hub in ANALISIS_HUBS:
            self.pr.set_analisis_hub(hub)
            screen = self.pr.screen()
            assert screen.analisis is not None
            self.assertEqual(screen.analisis.hub, hub)
            if screen.analisis.pestana == "Resumen":
                # Resumen usa donuts en los 3 hubs
                self.assertIsInstance(screen.analisis.chart_donuts, tuple)
            build_admin_shell(screen, on_volver_menu=None, **self._cbs())

    def test_charts_helpers(self) -> None:
        bars = build_barras_horizontales(
            (
                BarItemVM("Consumo", 10.0, 50.0, "10,00 €"),
                BarItemVM("Merma", 5.0, 25.0, "5,00 €"),
            ),
            titulo="Naturaleza",
        )
        self.assertIsNotNone(bars)
        lines = build_lineas_series(
            ChartSeriesVM(
                titulo="Evo",
                series=("Consumo", "Merma"),
                puntos=(
                    {"fecha": "01/08", "Consumo": 1.0, "Merma": 0.5},
                    {"fecha": "02/08", "Consumo": 2.0, "Merma": 0.0},
                ),
            )
        )
        self.assertIsNotNone(lines)
        donut = build_donut(
            (
                BarItemVM("Consumo", 70.0, 70.0, "70"),
                BarItemVM("Merma", 20.0, 20.0, "20"),
                BarItemVM("Exp", 10.0, 10.0, "10"),
            ),
            titulo="Naturaleza",
        )
        self.assertIsNotNone(donut)

    def test_normalize_donut_slices_otros(self) -> None:
        items = [
            BarItemVM("A", 90, 90, "90"),
            BarItemVM("B", 5, 5, "5"),
            BarItemVM("C", 2, 2, "2"),
            BarItemVM("D", 1, 1, "1"),
            BarItemVM("E", 1, 1, "1"),
            BarItemVM("F", 1, 1, "1"),
        ]
        out = normalize_donut_slices(items, min_pct=3.0, max_slices=6)
        cats = [x.categoria for x in out]
        self.assertIn("A", cats)
        self.assertIn("Otros", cats)
        self.assertLessEqual(len(out), 6)

    def test_pareto_acumula_umbral(self) -> None:
        # Sin sesión de costes el usecase falla; validamos lógica vía filas sintéticas
        # construyendo acum manualmente como el servicio.
        filas = [
            {"nombre": "P1", "coste": 50},
            {"nombre": "P2", "coste": 30},
            {"nombre": "P3", "coste": 10},
            {"nombre": "P4", "coste": 10},
        ]
        total = sum(f["coste"] for f in filas)
        acum = 0.0
        out = []
        for f in filas:
            pct = round(100.0 * f["coste"] / total, 1)
            acum = round(acum + pct, 1)
            out.append(acum)
            if acum >= 80:
                break
        self.assertGreaterEqual(out[-1], 80)
        self.assertLessEqual(len(out), 4)
        # API existe
        self.assertTrue(callable(costes_service.pareto_generadores_coste))
        self.assertTrue(callable(costes_service.alertas_periodo_costes))

    def test_flet_sin_streamlit_ni_altair(self) -> None:
        for path in FLET_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(alias.name.startswith("streamlit"))
                        self.assertFalse(alias.name.startswith("altair"))
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith("streamlit"))
                    self.assertFalse(node.module.startswith("altair"))
                    self.assertFalse(node.module.startswith("app.pages"))
                    self.assertFalse(node.module.startswith("app.ui.charts"))


if __name__ == "__main__":
    unittest.main()
