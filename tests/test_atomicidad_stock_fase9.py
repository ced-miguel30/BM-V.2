"""Atomicidad de stock (Fase 9): fallo sin mutaciones parciales; sin ignorar_stock."""

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
    MotivoMerma,
    Producto,
    Receta,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.services import desayuno_service, merma_service
from app.core.services.inventory_batch_service import (
    aplicar_descuento_atomico,
    descontar_lotes,
    planificar_descuento,
    snapshot_cantidades_restantes,
    stock_disponible,
)


def _datos_receta_corta() -> AppData:
    """Receta 2 ingredientes; solo hay stock del primero."""
    return AppData(
        productos=[
            Producto("p1", "Harina", UnidadProducto.KG),
            Producto("p2", "Huevo", UnidadProducto.UD),
        ],
        lotes=[
            LoteStock("l1", "p1", 10.0, 5.0, 5.0, date(2026, 7, 1)),
            LoteStock("l2", "p2", 2.0, 1.0, 1.0, date(2026, 7, 1)),  # solo 1 ud
        ],
        recetas=[
            Receta(
                "r1",
                "Tortilla",
                [
                    IngredienteReceta("p1", 0.1),
                    IngredienteReceta("p2", 2.0),  # pide 2, solo hay 1
                ],
                CategoriaReceta.DESAYUNO,
                servicios_disponibles=["desayuno"],
                porciones_estandar=1.0,
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestPlanificarYDescontar(unittest.TestCase):
    def test_plan_detecta_deficit(self) -> None:
        data = _datos_receta_corta()
        plan = planificar_descuento(
            data,
            {"p1": 0.1, "p2": 2.0},
            nombres={"p1": "Harina", "p2": "Huevo"},
            unidades={"p1": "Kg", "p2": "Ud"},
        )
        self.assertFalse(plan.ok)
        self.assertTrue(any("Huevo" in d for d in plan.deficits))
        huevo = next(ln for ln in plan.lineas if ln.producto_id == "p2")
        self.assertFalse(huevo.ok)
        self.assertLess(huevo.resultante, 0)

    def test_descontar_sin_stock_no_muta(self) -> None:
        data = _datos_receta_corta()
        snap = snapshot_cantidades_restantes(data)
        with self.assertRaises(ValueError):
            descontar_lotes(data, "p2", 2.0, permitir_negativo=False)
        self.assertEqual(snapshot_cantidades_restantes(data), snap)

    def test_aplicar_atomico_falla_sin_tocar(self) -> None:
        data = _datos_receta_corta()
        snap = snapshot_cantidades_restantes(data)
        with self.assertRaises(ValueError):
            aplicar_descuento_atomico(data, {"p1": 0.1, "p2": 2.0})
        self.assertEqual(snapshot_cantidades_restantes(data), snap)
        self.assertEqual(stock_disponible(data, "p1"), 5.0)


class TestRegistroDesayunoAtomico(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos_receta_corta()
        self._patches = [
            mock.patch("app.core.services.desayuno_service.get_data", return_value=self.data),
            mock.patch("app.core.services.cesta_service.get_data", return_value=self.data),
            mock.patch("app.core.services.desayuno_service.persist_data"),
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

    def test_receta_corta_permite_stock_negativo(self) -> None:
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("r1", 1.0).ok)
        r = desayuno_service.registrar_desayuno(date(2026, 7, 21), 5)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.desayunos), 1)
        self.assertLess(stock_disponible(self.data, "p2"), 0)

    def test_ignorar_stock_tambien_permite_negativo(self) -> None:
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("r1", 1.0).ok)
        r = desayuno_service.registrar_desayuno(
            date(2026, 7, 21), 5, ignorar_stock=True,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertLess(stock_disponible(self.data, "p2"), 0)

    def test_registro_valido_ok(self) -> None:
        self.data.lotes[1].cantidad_restante = 10.0
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("r1", 1.0).ok)
        r = desayuno_service.registrar_desayuno(date(2026, 7, 21), 5)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.desayunos), 1)
        self.assertAlmostEqual(stock_disponible(self.data, "p1"), 4.9, places=4)
        self.assertAlmostEqual(stock_disponible(self.data, "p2"), 8.0, places=4)


class TestMermaAtomica(unittest.TestCase):
    def setUp(self) -> None:
        from app.core.models import ResponsableMerma

        self.data = AppData(
            productos=[Producto("p1", "Pan", UnidadProducto.UD)],
            lotes=[
                LoteStock("l1", "p1", 5.0, 3.0, 3.0, date(2026, 7, 1)),
            ],
            usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
            usuario_actual_id="u01",
            responsables_merma=[ResponsableMerma("resp1", "Cocina", True)],
        )
        self._session: dict = {}
        self._patches = [
            mock.patch("app.core.services.merma_service.get_data", return_value=self.data),
            mock.patch("app.core.services.merma_service.persist_data"),
            mock.patch("streamlit.session_state", self._session),
        ]
        for p in self._patches:
            p.start()
        from tests.streamlit_store_harness import cleanup_container, use_patched_streamlit_stores

        use_patched_streamlit_stores()
        self.addCleanup(cleanup_container)

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()

    def test_exceso_bloqueado_sin_mutar(self) -> None:
        from app.core.services.merma_service import LineaCestaMerma

        self._session[merma_service.CESTA_MERMA_KEY] = [
            LineaCestaMerma(
                lote_id="l1",
                producto_id="p1",
                nombre="Pan",
                unidad="Ud",
                fecha_compra_txt="01/07/2026",
                cantidad=5.0,  # > 3 disponibles
                motivo=MotivoMerma.EXPIRACION.value,
                tipo_servicio_snapshot="desayuno",
                turno_snapshot="manana",
                responsable_id="resp1",
                responsable_nombre="Cocina",
                comentario="",
            ),
        ]
        snap = snapshot_cantidades_restantes(self.data)
        r = merma_service.registrar_merma(date(2026, 7, 21))
        self.assertFalse(r.ok)
        self.assertIn("insuficiente", r.mensaje.lower())
        self.assertEqual(snapshot_cantidades_restantes(self.data), snap)
        self.assertEqual(len(self.data.mermas), 0)


if __name__ == "__main__":
    unittest.main()
