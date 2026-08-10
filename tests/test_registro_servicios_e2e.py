"""E2E operativo: Tortilla + Café + Zumo en Desayuno (almacenamiento temporal)."""

from __future__ import annotations

import math
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.auth.session import clear_test_session, set_test_session
from app.core.models import (
    AppData,
    CategoriaReceta,
    IngredienteReceta,
    LoteStock,
    OrigenConsumo,
    Producto,
    Receta,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.services import desayuno_service
from app.core.services.cesta_service import validar_cantidad_operativa
from app.core.services.inventory_batch_service import stock_disponible
from app.core.services.registro_estado_service import estado_registro_dia
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _datos_tortilla_cafe() -> AppData:
    return AppData(
        productos=[
            Producto(
                "ph", "Huevo", UnidadProducto.UD,
                servicios_disponibles=["desayuno"], codigo="HUEVO",
            ),
            Producto(
                "pcaf", "Café", UnidadProducto.KG,
                servicios_disponibles=["desayuno"], codigo="CAFE",
            ),
            Producto(
                "pl", "Leche", UnidadProducto.L,
                servicios_disponibles=["desayuno"], codigo="LECHE",
            ),
            Producto(
                "pz", "Zumo", UnidadProducto.UD,
                es_bebida=True,
                servicios_disponibles=["desayuno", "bebidas"],
                codigo="ZUMO",
            ),
        ],
        lotes=[
            # 0,20 €/ud → 20 ud * 0,20 = 4,0 €
            LoteStock("lh", "ph", 4.0, 20.0, 20.0, date(2026, 7, 1)),
            # 20 €/kg
            LoteStock("lc", "pcaf", 40.0, 2.0, 2.0, date(2026, 7, 1)),
            # 1 €/L
            LoteStock("ll", "pl", 10.0, 10.0, 10.0, date(2026, 7, 1)),
            # 1 €/ud
            LoteStock("lz", "pz", 30.0, 30.0, 30.0, date(2026, 7, 1)),
        ],
        recetas=[
            Receta(
                "rt",
                "Tortilla",
                [IngredienteReceta("ph", 2.0)],  # 2 huevos por ración
                CategoriaReceta.DESAYUNO,
                servicios_disponibles=["desayuno"],
                porciones_estandar=1.0,
            ),
            Receta(
                "rc",
                "Café",
                [
                    IngredienteReceta("pcaf", 0.01),  # 10 g
                    IngredienteReceta("pl", 0.15),
                ],
                CategoriaReceta.DESAYUNO,
                servicios_disponibles=["desayuno"],
                porciones_estandar=1.0,
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestE2ETortillaCafeZumo(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.demo_before = DEMO_FILE.read_bytes()
        self.data = _datos_tortilla_cafe()
        self._session: dict = {}
        self._patches = [
            mock.patch("app.core.services.desayuno_service.get_data", return_value=self.data),
            mock.patch(
                "app.core.services.desayuno_service.persist_data",
                side_effect=lambda d=None: d if d is not None else self.data,
            ),
            mock.patch("app.core.services.cesta_service.get_data", return_value=self.data),
            mock.patch("streamlit.session_state", self._session),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        from tests.streamlit_store_harness import cleanup_container, fresh_memory_container

        fresh_memory_container()
        self.addCleanup(cleanup_container)

    def tearDown(self) -> None:
        self.assertEqual(DEMO_FILE.read_bytes(), self.demo_before)
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_validar_cantidad_helper(self) -> None:
        self.assertIsNotNone(validar_cantidad_operativa(0))
        self.assertIsNotNone(validar_cantidad_operativa(-1))
        self.assertIsNotNone(validar_cantidad_operativa(float("nan")))
        self.assertIsNotNone(validar_cantidad_operativa(float("inf")))
        self.assertIsNone(validar_cantidad_operativa(1.5))

    def test_e2e_completo_reconciliado(self) -> None:
        # Tortilla 5 raciones → 10 huevos → 2,00 €
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("rt", 5.0).ok)
        # Café 4 raciones → 0,04 kg + 0,60 L → 0,80 + 0,60 = 1,40 €
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("rc", 4.0).ok)
        # Zumo 3 (bebida dentro de desayuno)
        self.assertTrue(desayuno_service.anadir_a_cesta("pz", 3.0).ok)

        grupos = desayuno_service.get_cesta_recetas()
        self.assertEqual(len(grupos), 2)
        cost_est = desayuno_service.coste_total_cesta()
        self.assertAlmostEqual(cost_est, 2.0 + 1.40 + 3.0, places=2)

        r = desayuno_service.registrar_desayuno(
            date(2026, 7, 21),
            12,
            clave_idempotencia="tok-tortilla",
            observaciones="Servicio sala 1",
        )
        self.assertTrue(r.ok, r.mensaje)
        reg = self.data.desayunos[0]
        self.assertEqual(reg.observaciones, "Servicio sala 1")
        self.assertAlmostEqual(reg.coste_total, 6.40, places=2)

        self.assertAlmostEqual(stock_disponible(self.data, "ph"), 10.0, places=4)
        self.assertAlmostEqual(stock_disponible(self.data, "pcaf"), 1.96, places=4)
        self.assertAlmostEqual(stock_disponible(self.data, "pl"), 9.4, places=4)
        self.assertAlmostEqual(stock_disponible(self.data, "pz"), 27.0, places=4)

        # Familias: recetas (snapshots) + producto directo bebida
        self.assertEqual(len(reg.registros_recetas), 2)
        nombres = {rr.nombre_receta for rr in reg.registros_recetas}
        self.assertEqual(nombres, {"Tortilla", "Café"})

        deta_zumo = [d for d in reg.lineas_detalle if d.producto_id == "pz"]
        self.assertEqual(len(deta_zumo), 1)
        self.assertEqual(deta_zumo[0].origen, OrigenConsumo.PRODUCTO_DIRECTO.value)
        self.assertEqual(deta_zumo[0].tipo_servicio, "desayuno")
        self.assertTrue(deta_zumo[0].es_bebida_snapshot)

        ings = [
            d for d in reg.lineas_detalle
            if d.origen == OrigenConsumo.INGREDIENTE_RECETA.value
        ]
        self.assertGreaterEqual(len(ings), 3)  # huevos + café + leche

        # Coste de lineas agregadas = coste_total (sin doble conteo económico)
        self.assertAlmostEqual(
            round(sum(l.coste for l in reg.lineas), 2),
            reg.coste_total,
            places=2,
        )

        # Estado diario
        est = estado_registro_dia(
            self.data, tipo_servicio="desayuno", fecha=date(2026, 7, 21),
        )
        self.assertEqual(est.registros_activos, 1)
        self.assertIn("1 registro", est.etiqueta)

        # Idempotencia
        self.assertTrue(desayuno_service.anadir_a_cesta("pz", 1.0).ok)
        r2 = desayuno_service.registrar_desayuno(
            date(2026, 7, 21), 12, clave_idempotencia="tok-tortilla",
        )
        self.assertEqual(r2.codigo, "IDEMPOTENTE")
        self.assertEqual(len(self.data.desayunos), 1)
        self.assertAlmostEqual(stock_disponible(self.data, "pz"), 27.0, places=4)

    def test_quitar_muestra_nombre(self) -> None:
        self.assertTrue(desayuno_service.anadir_a_cesta("pz", 2.0).ok)
        lid = desayuno_service.get_cesta()[0].linea_id
        nombre = desayuno_service.quitar_linea_suelta(lid)
        self.assertEqual(nombre, "Zumo")
        self.assertTrue(desayuno_service.cesta_vacia())


class TestCompatHistoricoSinSnapshots(unittest.TestCase):
    def test_estado_dia_vacio(self) -> None:
        data = AppData()
        est = estado_registro_dia(data, tipo_servicio="desayuno", fecha=date(2026, 1, 1))
        self.assertEqual(est.registros_activos, 0)
        self.assertIn("Sin registro", est.etiqueta)


if __name__ == "__main__":
    unittest.main()
