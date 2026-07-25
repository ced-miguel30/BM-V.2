"""Simulador de recetas solo lectura (Fase 7)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    CategoriaReceta,
    IngredienteReceta,
    LoteStock,
    Producto,
    Receta,
    UnidadProducto,
)
from app.core.services import receta_service
from app.data.serializers import appdata_to_dict, dict_to_appdata
from datetime import date


def _datos() -> AppData:
    return AppData(
        productos=[
            Producto("p1", "Harina", UnidadProducto.KG),
            Producto("p2", "Huevo", UnidadProducto.UD),
        ],
        lotes=[
            LoteStock("l1", "p1", 10.0, 5.0, 5.0, date(2026, 7, 1)),
            LoteStock("l2", "p2", 2.0, 20.0, 20.0, date(2026, 7, 1)),
        ],
        recetas=[
            Receta(
                "r1",
                "Tortilla",
                [
                    IngredienteReceta("p1", 0.1),
                    IngredienteReceta("p2", 2.0),
                ],
                CategoriaReceta.DESAYUNO,
                servicios_disponibles=["desayuno"],
                porciones_estandar=10.0,
            ),
            Receta(
                "r2",
                "Sin rendimiento",
                [IngredienteReceta("p1", 0.2)],
                CategoriaReceta.COMIDA,
                porciones_estandar=None,
            ),
        ],
    )


class TestSimuladorReceta(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos()

    def test_factor_25_sobre_10(self) -> None:
        with mock.patch("app.core.services.receta_service.get_data", return_value=self.data):
            r = receta_service.simular_receta("r1", 25.0)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(r.factor, 2.5)
        self.assertEqual(r.porciones_estandar, 10.0)
        self.assertEqual(r.porciones_simuladas, 25.0)
        harina = next(ln for ln in r.lineas if ln.producto_id == "p1")
        self.assertAlmostEqual(harina.cantidad_nativa, 0.25, places=4)
        huevo = next(ln for ln in r.lineas if ln.producto_id == "p2")
        self.assertAlmostEqual(huevo.cantidad_nativa, 5.0, places=4)
        # No muta stock
        self.assertEqual(self.data.lotes[0].cantidad_restante, 5.0)

    def test_sin_estandar_bloquea(self) -> None:
        with mock.patch("app.core.services.receta_service.get_data", return_value=self.data):
            r = receta_service.simular_receta("r2", 10.0)
        self.assertFalse(r.ok)
        self.assertIn("Dato no disponible", r.mensaje)

    def test_json_antiguo_sin_campo(self) -> None:
        payload = {
            "productos": [],
            "lotes": [],
            "recetas": [
                {
                    "id": "r9",
                    "nombre": "Antigua",
                    "categoria": "desayuno",
                    "ingredientes": [],
                }
            ],
            "desayunos": [],
            "mermas": [],
            "alertas": [],
            "usuarios": [],
            "actividades": [],
        }
        data = dict_to_appdata(payload)
        self.assertIsNone(data.recetas[0].porciones_estandar)
        restored = dict_to_appdata(appdata_to_dict(data))
        self.assertIsNone(restored.recetas[0].porciones_estandar)


if __name__ == "__main__":
    unittest.main()
