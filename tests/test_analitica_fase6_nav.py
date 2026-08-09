"""Pruebas Fase 6 (plan Dashboard/Análisis) — nav Análisis + Registros + deep-links.

Ejecutar:

    py -m unittest tests.test_analitica_fase6_nav -v
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import PAGES
from app.pages import analisis, dashboard, registros
from app.ui.theme import NAV_SECTIONS


class TestAnaliticaFase6Nav(unittest.TestCase):
    def test_analisis_tabs_sin_kpis(self) -> None:
        self.assertEqual(
            list(analisis._SUBTABS.keys()),
            ["Consumo", "Costes", "Merma", "BI"],
        )
        self.assertNotIn("KPIs", analisis._SUBTABS)

    def test_legacy_subtab_mapping(self) -> None:
        self.assertEqual(analisis._LEGACY_SUBTABS["Gestor consumo"], "Consumo")
        self.assertEqual(analisis._LEGACY_SUBTABS["Gestor costes"], "Costes")
        self.assertEqual(analisis._LEGACY_SUBTABS["Gestor merma"], "Merma")
        self.assertEqual(analisis._LEGACY_SUBTABS["KPIs"], "Consumo")
        self.assertEqual(analisis._LEGACY_SUBTABS["Business Intelligence"], "BI")

    def test_nav_menu_esperado(self) -> None:
        self.assertEqual(
            list(NAV_SECTIONS.keys()),
            ["Dashboard", "Registros", "Recetas", "Stock", "Análisis", "Configuración"],
        )
        self.assertEqual(NAV_SECTIONS["Análisis"], "analisis")
        self.assertEqual(NAV_SECTIONS["Registros"], "registros")
        self.assertEqual(NAV_SECTIONS["Configuración"], "settings")

    def test_registros_intactos(self) -> None:
        self.assertEqual(
            list(registros._SUBTABS.keys()),
            ["Desayuno", "Comida", "Cena", "Bebidas", "Merma", "Caducidad", "Historial"],
        )
        self.assertIn("registros", PAGES)
        self.assertIs(PAGES["registros"], registros.render)

    def test_ir_analisis_deep_link_consumo(self) -> None:
        fake_st = MagicMock()
        fake_st.session_state = {}
        with patch.object(dashboard, "st", fake_st):
            dashboard._ir_analisis("Consumo", consumo_pestana="Comida")
        self.assertEqual(fake_st.session_state["nav_section_pending"], "Análisis")
        self.assertNotIn("nav_section", fake_st.session_state)
        self.assertEqual(fake_st.session_state["analisis_subtab"], "Consumo")
        self.assertEqual(fake_st.session_state["consumo_pestana"], "Comida")
        fake_st.rerun.assert_called_once()

    def test_ir_analisis_deep_link_merma(self) -> None:
        fake_st = MagicMock()
        fake_st.session_state = {}
        with patch.object(dashboard, "st", fake_st):
            dashboard._ir_analisis("Merma", merma_pestana="Resumen")
        self.assertEqual(fake_st.session_state["nav_section_pending"], "Análisis")
        self.assertEqual(fake_st.session_state["analisis_subtab"], "Merma")
        self.assertEqual(fake_st.session_state["merma_pestana"], "Resumen")

    def test_tarjeta_firma_acepta_desglose(self) -> None:
        sig = inspect.signature(dashboard._tarjeta_categoria)
        self.assertIn("desglose", sig.parameters)


if __name__ == "__main__":
    unittest.main()
