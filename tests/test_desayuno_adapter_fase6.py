"""Adaptador desayuno para UI compartida (Fase 6)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services.desayuno_service import DesayunoRegistroAdapter, desayuno_registro


class TestDesayunoAdapter(unittest.TestCase):
    def test_singleton_y_tipo(self) -> None:
        self.assertIsInstance(desayuno_registro, DesayunoRegistroAdapter)
        self.assertEqual(desayuno_registro.tipo_servicio, "desayuno")
        self.assertEqual(desayuno_registro.etiqueta, "Desayuno")

    def test_api_duck_typed(self) -> None:
        metodos = [
            "productos_catalogo",
            "get_cesta",
            "get_cesta_recetas",
            "get_mods_pendientes",
            "limpiar_cesta",
            "anadir_a_cesta",
            "anadir_receta_a_cesta",
            "registrar",
            "historial_ordenado",
            "configuracion_exportacion",
            "registros_exportables",
            "coste_total_cesta",
        ]
        for nombre in metodos:
            self.assertTrue(callable(getattr(desayuno_registro, nombre)), nombre)


if __name__ == "__main__":
    unittest.main()
