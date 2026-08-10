"""Escalado real de recetas en cesta/registro (Fase 8). Misma regla que el simulador."""

from __future__ import annotations

import sys
import unittest
from datetime import date
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
    Usuario,
    RolUsuario,
)
from app.core.services import desayuno_service, receta_service
from app.core.services.inventory_batch_service import stock_disponible


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
                CategoriaReceta.DESAYUNO,
                servicios_disponibles=["desayuno"],
                porciones_estandar=None,
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestEscaladoRecetaFase8(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos()
        self._patches = [
            mock.patch("app.core.services.desayuno_service.get_data", return_value=self.data),
            mock.patch(
                "app.core.services.desayuno_service.persist_data",
                side_effect=lambda d=None: d if d is not None else self.data,
            ),
            mock.patch("app.core.services.cesta_service.get_data", return_value=self.data),
            mock.patch("app.core.services.receta_service.get_data", return_value=self.data),
            mock.patch("streamlit.session_state", {}),
        ]
        for p in self._patches:
            p.start()
        from tests.streamlit_store_harness import cleanup_container, fresh_memory_container

        fresh_memory_container()
        self.addCleanup(cleanup_container)

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()

    def test_cesta_factor_igual_que_simulador(self) -> None:
        sim = receta_service.simular_receta("r1", 25.0)
        self.assertTrue(sim.ok, sim.mensaje)

        r = desayuno_service.anadir_receta_a_cesta("r1", 25.0)
        self.assertTrue(r.ok, r.mensaje)
        grupo = desayuno_service.get_cesta_recetas()[0]
        self.assertEqual(grupo.porciones_estandar, 10.0)
        self.assertEqual(grupo.factor_aplicado, 2.5)
        self.assertEqual(grupo.porciones, 25.0)

        harina = next(i for i in grupo.ingredientes if i.producto_id == "p1")
        huevo = next(i for i in grupo.ingredientes if i.producto_id == "p2")
        self.assertAlmostEqual(harina.cantidad, 0.25, places=4)
        self.assertAlmostEqual(huevo.cantidad, 5.0, places=4)

        sim_h = next(ln for ln in sim.lineas if ln.producto_id == "p1")
        sim_u = next(ln for ln in sim.lineas if ln.producto_id == "p2")
        self.assertAlmostEqual(harina.cantidad, sim_h.cantidad_nativa, places=4)
        self.assertAlmostEqual(huevo.cantidad, sim_u.cantidad_nativa, places=4)

    def test_registro_descuenta_stock_como_simulador(self) -> None:
        sim = receta_service.simular_receta("r1", 25.0)
        self.assertTrue(sim.ok)

        stock_h0 = stock_disponible(self.data, "p1")
        stock_u0 = stock_disponible(self.data, "p2")

        self.assertTrue(desayuno_service.anadir_receta_a_cesta("r1", 25.0).ok)
        resultado = desayuno_service.registrar_desayuno(date(2026, 7, 21), 10)
        self.assertTrue(resultado.ok, resultado.mensaje)

        sim_h = next(ln for ln in sim.lineas if ln.producto_id == "p1")
        sim_u = next(ln for ln in sim.lineas if ln.producto_id == "p2")
        self.assertAlmostEqual(
            stock_disponible(self.data, "p1"),
            stock_h0 - sim_h.cantidad_nativa,
            places=4,
        )
        self.assertAlmostEqual(
            stock_disponible(self.data, "p2"),
            stock_u0 - sim_u.cantidad_nativa,
            places=4,
        )

        reg = self.data.desayunos[-1]
        self.assertEqual(len(reg.registros_recetas), 1)
        rr = reg.registros_recetas[0]
        self.assertEqual(rr.porciones_estandar_snapshot, 10.0)
        self.assertEqual(rr.factor_aplicado, 2.5)
        self.assertEqual(rr.porciones, 25.0)

    def test_sin_estandar_bloquea_cesta(self) -> None:
        r = desayuno_service.anadir_receta_a_cesta("r2", 10.0)
        self.assertFalse(r.ok)
        self.assertIn("porciones estándar", r.mensaje.lower())


if __name__ == "__main__":
    unittest.main()
