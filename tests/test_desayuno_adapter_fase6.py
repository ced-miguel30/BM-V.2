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
            "leches_rapidas",
            "bebidas_frias_rapidas",
        ]
        for nombre in metodos:
            self.assertTrue(callable(getattr(desayuno_registro, nombre)), nombre)

    def test_bebidas_frias_una_ud(self) -> None:
        from app.core.services.desayuno_service import _BEBIDAS_FRIAS_RAPIDAS_DESAYUNO

        self.assertGreaterEqual(len(_BEBIDAS_FRIAS_RAPIDAS_DESAYUNO), 14)
        labels = {e.label for e in _BEBIDAS_FRIAS_RAPIDAS_DESAYUNO}
        self.assertIn("Agua sin gas PET", labels)
        self.assertIn("Agua sin gas cristal", labels)
        self.assertIn("Soda", labels)
        self.assertIn("Coca-Cola lata", labels)
        self.assertIn("Sprite 1,5 L", labels)
        for e in _BEBIDAS_FRIAS_RAPIDAS_DESAYUNO:
            self.assertEqual(e.cantidad, 1.0, e.label)
            self.assertEqual(e.unidad_mostrar, "Ud", e.label)


if __name__ == "__main__":
    unittest.main()
