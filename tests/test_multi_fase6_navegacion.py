"""Pruebas Fase 6 — navegación Registros (paso 1: coexistencia).

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


class TestFase6NavegacionPaso1(unittest.TestCase):
    """Durante el paso 1, Registros y las rutas antiguas coexisten."""

    def test_nav_incluye_registros_y_desayuno(self) -> None:
        self.assertEqual(NAV_SECTIONS.get("Registros"), "registros")
        self.assertEqual(NAV_SECTIONS.get("Desayuno"), "desayuno")
        self.assertEqual(NAV_SECTIONS.get("Comida"), "comida")
        self.assertEqual(NAV_SECTIONS.get("Cena"), "cena")
        self.assertEqual(NAV_SECTIONS.get("Bebidas"), "bebidas")

    def test_pages_incluye_registros_y_rutas_antiguas(self) -> None:
        self.assertIn("registros", PAGES)
        self.assertIn("desayuno", PAGES)
        self.assertIn("comida", PAGES)
        self.assertIn("cena", PAGES)
        self.assertIn("bebidas", PAGES)
        self.assertIs(PAGES["registros"], registros.render)
        self.assertIs(PAGES["desayuno"], desayuno.render)

    def test_registros_expone_subtabs_esperadas(self) -> None:
        self.assertEqual(
            list(registros._SUBTABS.keys()),
            ["Desayuno", "Comida", "Cena", "Bebidas", "Merma"],
        )

    def test_desayuno_expone_renderizadores_sin_cabecera(self) -> None:
        self.assertTrue(callable(desayuno.render_registro_desayuno))
        self.assertTrue(callable(desayuno.render_registro_merma))

    def test_paginas_servicio_aceptan_mostrar_cabecera(self) -> None:
        from app.pages import bebidas, cena, comida

        for mod in (comida, cena, bebidas):
            params = inspect.signature(mod.render).parameters
            self.assertIn("mostrar_cabecera", params)


if __name__ == "__main__":
    unittest.main()
