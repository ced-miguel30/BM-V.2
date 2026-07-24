"""Pruebas de paso/formato por unidad (Fase 3 estabilización)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import UnidadProducto
from app.core.services.unidad_service import (
    decimales_unidad,
    ejemplos_formato_unidades,
    formatear_cantidad,
    formato_number_input,
    normalizar_cantidad,
    paso_unidad,
)


class TestPasoUnidad(unittest.TestCase):
    def test_pasos_orientacion_plan(self) -> None:
        self.assertEqual(paso_unidad(UnidadProducto.UD), 1.0)
        self.assertEqual(paso_unidad(UnidadProducto.KG), 0.01)
        self.assertEqual(paso_unidad(UnidadProducto.GR), 1.0)
        self.assertEqual(paso_unidad(UnidadProducto.L), 0.01)
        self.assertEqual(paso_unidad("ml"), 10.0)
        self.assertEqual(paso_unidad("paquete"), 1.0)
        self.assertEqual(paso_unidad("botella"), 1.0)

    def test_normalizar_rechaza_negativos_y_permite_002_kg(self) -> None:
        self.assertEqual(normalizar_cantidad(-1.5, UnidadProducto.UD), 0.0)
        self.assertEqual(normalizar_cantidad(0.02, UnidadProducto.KG), 0.02)
        self.assertEqual(normalizar_cantidad(1.234, UnidadProducto.KG), 1.23)

    def test_formato_number_input(self) -> None:
        self.assertEqual(formato_number_input(UnidadProducto.UD), "%.0f")
        self.assertEqual(formato_number_input(UnidadProducto.KG), "%.2f")
        self.assertEqual(decimales_unidad("ml"), 0)

    def test_ejemplos_tabla_diagnostico(self) -> None:
        filas = ejemplos_formato_unidades()
        self.assertGreaterEqual(len(filas), 5)
        self.assertIn("Paso", filas[0])
        self.assertEqual(formatear_cantidad(0.02, UnidadProducto.KG), "0.02")


if __name__ == "__main__":
    unittest.main()
