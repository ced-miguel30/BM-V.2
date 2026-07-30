"""Pruebas Fase 2 — motor común de registro de servicio.

Ejecutar:

    py -m unittest tests.test_multi_fase2_motor -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    CategoriaReceta,
    IngredienteReceta,
    LoteStock,
    OrigenConsumo,
    Producto,
    Receta,
    RegistroDesayuno,
    TipoServicio,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import RolUsuario
from app.core.services import inventory_batch_service, servicio_registro_service
from app.core.services.cesta_service import crear_motor_cesta
from app.core.services.detalle_origen_service import construir_lineas_detalle
from app.core.services.inventory_batch_service import (
    calcular_coste_linea,
    descontar_lotes,
    lotes_ordenados_consumo,
    stock_disponible,
)
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _datos_stock() -> AppData:
    return AppData(
        productos=[
            Producto("p01", "Pan", UnidadProducto.KG),
            Producto("p02", "Leche", UnidadProducto.L, es_bebida=True),
            Producto("p03", "Huevo", UnidadProducto.UD),
        ],
        lotes=[
            LoteStock("l01", "p01", precio_total=10.0, cantidad=1.0, cantidad_restante=1.0,
                      fecha_compra=date(2026, 1, 1)),
            LoteStock("l02", "p01", precio_total=30.0, cantidad=1.0, cantidad_restante=1.0,
                      fecha_compra=date(2026, 2, 1)),
            LoteStock("l03", "p02", precio_total=2.0, cantidad=1.0, cantidad_restante=1.0,
                      fecha_compra=date(2026, 1, 15)),
        ],
        recetas=[
            Receta("r01", "Tostada", [IngredienteReceta("p01", 0.1)], CategoriaReceta.DESAYUNO, porciones_estandar=1.0),
            Receta("r02", "Pasta", [IngredienteReceta("p01", 0.2)], CategoriaReceta.COMIDA, porciones_estandar=1.0),
            Receta("r03", "Café latte", [IngredienteReceta("p02", 0.2)], CategoriaReceta.BEBIDAS, porciones_estandar=1.0),
            Receta("r04", "Sopa", [IngredienteReceta("p01", 0.15)], CategoriaReceta.CENA, porciones_estandar=1.0),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestInventoryBatchFifo(unittest.TestCase):
    def test_orden_fifo_por_fecha_compra(self) -> None:
        data = _datos_stock()
        orden = [l.id for l in lotes_ordenados_consumo(data, "p01")]
        self.assertEqual(orden, ["l01", "l02"])

    def test_descuenta_primero_el_lote_mas_antiguo(self) -> None:
        data = _datos_stock()
        coste = descontar_lotes(data, "p01", 0.5).coste
        # 0.5 de l01 a 10€/ud → 5.0
        self.assertEqual(coste, 5.0)
        self.assertEqual(data.lotes[0].cantidad_restante, 0.5)
        self.assertEqual(data.lotes[1].cantidad_restante, 1.0)

    def test_coste_cruza_dos_lotes_fifo(self) -> None:
        data = _datos_stock()
        coste = calcular_coste_linea(data, "p01", 1.5)
        # 1.0 * 10 + 0.5 * 30 = 25
        self.assertEqual(coste, 25.0)

    def test_stock_disponible(self) -> None:
        data = _datos_stock()
        self.assertEqual(stock_disponible(data, "p01"), 2.0)


class TestCestaPrefijosAislados(unittest.TestCase):
    def test_dos_prefijos_no_se_contaminan(self) -> None:
        cesta_a = crear_motor_cesta("comida")
        cesta_b = crear_motor_cesta("cena")

        state: dict = {}

        class FakeSession(dict):
            def __setitem__(self, key, value):
                state[key] = value
                super().__setitem__(key, value)

            def get(self, key, default=None):
                return state.get(key, default)

            def __contains__(self, key):
                return key in state

        fake_st = MagicMock()
        fake_st.session_state = FakeSession()

        with patch.dict("sys.modules", {"streamlit": fake_st}):
            # Re-bind session_state used inside MotorCesta methods
            import streamlit as st
            st.session_state = fake_st.session_state

            with patch("app.core.services.cesta_service.get_data", return_value=_datos_stock()):
                r1 = cesta_a.anadir_a_cesta("p01", 1.0)
                r2 = cesta_b.anadir_a_cesta("p02", 2.0)
                self.assertTrue(r1.ok)
                self.assertTrue(r2.ok)
                self.assertEqual(len(cesta_a.get_cesta()), 1)
                self.assertEqual(len(cesta_b.get_cesta()), 1)
                self.assertEqual(cesta_a.get_cesta()[0].producto_id, "p01")
                self.assertEqual(cesta_b.get_cesta()[0].producto_id, "p02")
                self.assertIn("bm_cesta_comida", state)
                self.assertIn("bm_cesta_cena", state)
                self.assertNotEqual(state["bm_cesta_comida"], state["bm_cesta_cena"])


class TestAllowListRecetas(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos_stock()
        self.servicio = servicio_registro_service.crear_servicio(
            "comida", "comida",
            [CategoriaReceta.COMIDA, CategoriaReceta.BEBIDAS],
        )
        self.patcher = patch(
            "app.core.services.servicio_registro_service.get_data",
            return_value=self.data,
        )
        self.patcher_cesta = patch(
            "app.core.services.cesta_service.get_data",
            return_value=self.data,
        )
        self.patcher.start()
        self.patcher_cesta.start()

        state: dict = {}

        class FakeSession(dict):
            def __setitem__(self, key, value):
                state[key] = value
                super().__setitem__(key, value)

            def get(self, key, default=None):
                return state.get(key, default)

            def __contains__(self, key):
                return key in state

        self.state = state
        fake_st = MagicMock()
        fake_st.session_state = FakeSession()
        self.st_patch = patch.dict("sys.modules", {"streamlit": fake_st})
        self.st_patch.start()
        import streamlit as st
        st.session_state = fake_st.session_state

    def tearDown(self) -> None:
        self.patcher.stop()
        self.patcher_cesta.stop()
        self.st_patch.stop()

    def test_bebidas_permitida_en_comida(self) -> None:
        r = self.servicio.anadir_receta_a_cesta("r03", 1.0)
        self.assertTrue(r.ok)

    def test_comida_permitida(self) -> None:
        r = self.servicio.anadir_receta_a_cesta("r02", 1.0)
        self.assertTrue(r.ok)

    def test_cena_rechazada_en_comida(self) -> None:
        r = self.servicio.anadir_receta_a_cesta("r04", 1.0)
        self.assertFalse(r.ok)
        self.assertIn("no está permitida", r.mensaje)


class TestLineasDetalleOrigen(unittest.TestCase):
    def test_mismo_producto_directo_e_ingrediente_no_se_fusionan(self) -> None:
        from app.core.services.cesta_service import GrupoRecetaCesta, LineaCesta, LineaCestaIngrediente

        data = _datos_stock()
        cesta = [LineaCesta("lin1", "p01", "Pan", "Kg", 0.05)]
        grupos = [GrupoRecetaCesta(
            "g1", "r01", "Tostada", 1.0,
            [LineaCestaIngrediente("lin2", "p01", "Pan", "Kg", 0.1, es_base_receta=True)],
        )]
        detalle = construir_lineas_detalle(
            cesta, grupos,
            tipo_servicio="desayuno",
            registro_id="d01",
            data=data,
        )
        self.assertEqual(len(detalle), 2)
        origenes = {d.origen for d in detalle}
        self.assertEqual(origenes, {
            OrigenConsumo.PRODUCTO_DIRECTO.value,
            OrigenConsumo.INGREDIENTE_RECETA.value,
        })
        self.assertTrue(all(d.tipo_servicio == "desayuno" for d in detalle))
        self.assertTrue(all(d.registro_origen_id == "d01" for d in detalle))
        ing = next(d for d in detalle if d.origen == OrigenConsumo.INGREDIENTE_RECETA.value)
        self.assertEqual(ing.receta_origen_id, "r01")
        self.assertEqual(ing.categoria_receta, "desayuno")


class TestRegistroServicioRoundtrip(unittest.TestCase):
    def test_serializar_deserializar_registro_servicio(self) -> None:
        data = _datos_stock()
        self.servicio_patch_get = patch(
            "app.core.services.servicio_registro_service.get_data", return_value=data,
        )
        self.servicio_patch_persist = patch(
            "app.core.services.servicio_registro_service.persist_data",
        )
        self.cesta_patch = patch(
            "app.core.services.cesta_service.get_data", return_value=data,
        )
        self.alert_patch = patch(
            "app.core.services.alert_service.sincronizar_alertas",
        )
        self.servicio_patch_get.start()
        self.servicio_patch_persist.start()
        self.cesta_patch.start()
        self.alert_patch.start()

        state: dict = {}

        class FakeSession(dict):
            def __setitem__(self, key, value):
                state[key] = value
                super().__setitem__(key, value)

            def get(self, key, default=None):
                return state.get(key, default)

            def __contains__(self, key):
                return key in state

        fake_st = MagicMock()
        fake_st.session_state = FakeSession()
        st_patch = patch.dict("sys.modules", {"streamlit": fake_st})
        st_patch.start()
        import streamlit as st
        st.session_state = fake_st.session_state

        try:
            servicio = servicio_registro_service.crear_servicio(
                "comida", "comida",
                [CategoriaReceta.COMIDA, CategoriaReceta.BEBIDAS],
            )
            self.assertTrue(servicio.anadir_receta_a_cesta("r02", 1.0).ok)
            self.assertTrue(servicio.anadir_a_cesta("p02", 0.1).ok)  # leche con stock
            resultado = servicio.registrar(date(2026, 7, 20), ignorar_stock=False)
            self.assertTrue(resultado.ok, resultado.mensaje)
            self.assertEqual(len(data.registros_servicio), 1)
            reg = data.registros_servicio[0]
            self.assertEqual(reg.tipo_servicio, TipoServicio.COMIDA.value)
            self.assertTrue(len(reg.lineas_detalle) >= 2)

            payload = appdata_to_dict(data)
            recuperado = dict_to_appdata(payload)
            self.assertEqual(len(recuperado.registros_servicio), 1)
            r2 = recuperado.registros_servicio[0]
            self.assertEqual(r2.tipo_servicio, "comida")
            self.assertEqual(len(r2.lineas_detalle), len(reg.lineas_detalle))
            self.assertEqual(r2.lineas_detalle[0].origen, reg.lineas_detalle[0].origen)
        finally:
            self.servicio_patch_get.stop()
            self.servicio_patch_persist.stop()
            self.cesta_patch.stop()
            self.alert_patch.stop()
            st_patch.stop()

    def test_desayuno_antiguo_sin_lineas_detalle_carga(self) -> None:
        payload = {
            "productos": [],
            "lotes": [],
            "recetas": [],
            "desayunos": [
                {
                    "id": "d01",
                    "fecha": "2026-07-01",
                    "lineas": [
                        {"producto_id": "p01", "cantidad": 0.1, "coste": 1.0},
                    ],
                    "coste_total": 1.0,
                },
            ],
            "mermas": [],
            "alertas": [],
            "actividades": [],
            "usuarios": [],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(len(data.desayunos), 1)
        self.assertEqual(data.desayunos[0].lineas_detalle, [])
        self.assertEqual(data.registros_servicio, [])


class TestBebidasSoloProductosBebida(unittest.TestCase):
    def test_rechaza_producto_no_bebida(self) -> None:
        data = _datos_stock()
        servicio = servicio_registro_service.crear_servicio(
            "bebidas", "bebidas",
            [CategoriaReceta.BEBIDAS],
            solo_bebidas_sueltas=True,
        )
        with patch("app.core.services.servicio_registro_service.get_data", return_value=data):
            with patch("app.core.services.cesta_service.get_data", return_value=data):
                r = servicio.anadir_a_cesta("p01", 1.0)
                self.assertFalse(r.ok)
                self.assertIn("bebida", r.mensaje.lower())


if __name__ == "__main__":
    unittest.main()
