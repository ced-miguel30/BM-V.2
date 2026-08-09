"""Pruebas Fase 6 — navegación Registros (paso 3: único punto de entrada).

Ejecutar:

    py -m unittest tests.test_multi_fase6_navegacion -v
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import PAGES
from app.pages import desayuno, registros
from app.ui.theme import NAV_SECTIONS


class TestFase6NavegacionPaso3(unittest.TestCase):
    """Tras el paso 3, solo Registros queda en el menú como acceso a registros."""

    def test_nav_solo_registros_sin_entradas_sueltas(self) -> None:
        self.assertEqual(NAV_SECTIONS.get("Registros"), "registros")
        for etiqueta in ("Desayuno", "Comida", "Cena", "Bebidas"):
            self.assertNotIn(etiqueta, NAV_SECTIONS)

    def test_pages_solo_registros_sin_rutas_sueltas(self) -> None:
        self.assertIn("registros", PAGES)
        self.assertIs(PAGES["registros"], registros.render)
        for clave in ("desayuno", "comida", "cena", "bebidas"):
            self.assertNotIn(clave, PAGES)

    def test_registros_alcanza_desayuno_y_merma(self) -> None:
        self.assertEqual(
            list(registros._SUBTABS.keys()),
            ["Desayuno", "Comida", "Cena", "Bebidas", "Merma", "Caducidad", "Historial"],
        )
        self.assertTrue(callable(desayuno.render_registro_desayuno))
        self.assertTrue(callable(desayuno.render_registro_merma))
        self.assertIn("Desayuno", registros._SUBTABS)
        self.assertIn("Merma", registros._SUBTABS)

    def test_paginas_servicio_siguen_disponibles_para_embeber(self) -> None:
        from app.pages import bebidas, cena, comida

        for mod in (comida, cena, bebidas):
            self.assertTrue(callable(mod.render))
            self.assertIn("mostrar_cabecera", inspect.signature(mod.render).parameters)


if __name__ == "__main__":
    unittest.main()
