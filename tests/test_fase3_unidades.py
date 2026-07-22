"""Pruebas de la Fase 3: conversión de unidades para ingredientes de receta.

Nota: el gramo se abrevia "gr" (no "g") para mantener la misma abreviatura
que ya usa el resto de la aplicación (`UnidadProducto.GR.value == "gr"`).

Ejecutar desde la raíz del proyecto con:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import AppData, IngredienteReceta, LoteStock, Producto, Receta, UnidadProducto
from app.core.services import desayuno_service, receta_service
from app.core.services.desayuno_service import (
    LineaCestaIngrediente,
    calcular_coste_linea,
    cantidad_texto_linea_receta,
    etiqueta_linea_receta,
    stock_disponible,
)
from app.core.services.unidad_service import (
    cantidad_para_mostrar,
    cantidad_y_unidad_mostrar,
    convertir_a_unidad_producto,
    escalar_presentacion,
    unidades_seleccionables,
)


class TestConversionesUnidad(unittest.TestCase):
    def test_gr_a_kg(self) -> None:
        self.assertEqual(convertir_a_unidad_producto(10, "gr", UnidadProducto.KG), 0.01)

    def test_kg_a_gr(self) -> None:
        self.assertEqual(cantidad_para_mostrar(0.01, UnidadProducto.KG, "gr"), 10.0)

    def test_mg_a_kg(self) -> None:
        self.assertEqual(convertir_a_unidad_producto(500, "mg", UnidadProducto.KG), 0.0005)

    def test_ml_a_l(self) -> None:
        self.assertEqual(convertir_a_unidad_producto(150, "ml", UnidadProducto.L), 0.15)

    def test_l_a_ml(self) -> None:
        self.assertEqual(cantidad_para_mostrar(0.15, UnidadProducto.L, "ml"), 150.0)

    def test_cl_a_l(self) -> None:
        self.assertEqual(convertir_a_unidad_producto(25, "cl", UnidadProducto.L), 0.25)

    def test_l_a_cl_mostrar(self) -> None:
        self.assertEqual(cantidad_para_mostrar(0.25, UnidadProducto.L, "cl"), 25.0)

    def test_unidad_discreta_no_se_convierte(self) -> None:
        self.assertEqual(convertir_a_unidad_producto(5, "Ud", UnidadProducto.UD), 5.0)

    def test_unidad_igual_a_nativa_no_cambia(self) -> None:
        self.assertEqual(convertir_a_unidad_producto(2.5, "Kg", UnidadProducto.KG), 2.5)

    def test_conversion_incompatible_no_se_altera_silenciosamente(self) -> None:
        # kg -> L no es una conversión válida: al no coincidir grupos, se
        # devuelve la cantidad sin alterar (nunca debería ofrecerse en la UI).
        self.assertEqual(convertir_a_unidad_producto(5, "L", UnidadProducto.KG), 5.0)

    def test_precision_visual_sin_ruido_de_coma_flotante(self) -> None:
        # 3 x 0.1 en floats puros puede arrastrar ruido (0.30000000000000004).
        cantidad_nativa = 0.1 + 0.1 + 0.1
        mostrado = cantidad_para_mostrar(cantidad_nativa, UnidadProducto.KG, "gr")
        self.assertEqual(mostrado, 300.0)

    def test_escalar_presentacion(self) -> None:
        self.assertEqual(escalar_presentacion(10, 3, "gr"), 30.0)


class TestUnidadesSeleccionables(unittest.TestCase):
    def test_masa_ofrece_solo_unidades_de_masa(self) -> None:
        opciones = unidades_seleccionables(UnidadProducto.KG)
        self.assertEqual(set(opciones), {"mg", "gr", "Kg"})

    def test_volumen_ofrece_solo_unidades_de_volumen(self) -> None:
        opciones = unidades_seleccionables(UnidadProducto.L)
        self.assertEqual(set(opciones), {"ml", "cl", "L"})

    def test_masa_y_volumen_son_disjuntas(self) -> None:
        masa = set(unidades_seleccionables(UnidadProducto.KG))
        volumen = set(unidades_seleccionables(UnidadProducto.L))
        self.assertEqual(masa & volumen, set())

    def test_unidad_discreta_solo_se_ofrece_a_si_misma(self) -> None:
        self.assertEqual(unidades_seleccionables(UnidadProducto.UD), ["Ud"])

    def test_otro_solo_se_ofrece_a_si_mismo(self) -> None:
        self.assertEqual(unidades_seleccionables(UnidadProducto.OTRO), ["Otro"])


class TestCantidadYUnidadMostrar(unittest.TestCase):
    def test_con_presentacion_diferenciada_se_respeta(self) -> None:
        cantidad, unidad = cantidad_y_unidad_mostrar(0.01, UnidadProducto.KG, 10.0, "gr")
        self.assertEqual((cantidad, unidad), (10.0, "gr"))

    def test_sin_presentacion_grande_usa_unidad_nativa(self) -> None:
        # Cantidades >= 1 en kg se mantienen en la unidad de inventario.
        cantidad, unidad = cantidad_y_unidad_mostrar(2.45, UnidadProducto.KG, None, None)
        self.assertEqual((cantidad, unidad), (2.45, "Kg"))

    def test_sin_presentacion_pequena_usa_unidad_legible(self) -> None:
        # 0,001 kg se muestra como 1 gr cuando no hay presentación guardada.
        cantidad, unidad = cantidad_y_unidad_mostrar(0.001, UnidadProducto.KG, None, None)
        self.assertEqual((cantidad, unidad), (1.0, "gr"))


class TestRecetaServiceUnidades(unittest.TestCase):
    def setUp(self) -> None:
        self.data = AppData(productos=[Producto("p01", "Queso", UnidadProducto.KG)])
        self._patcher = patch("app.core.services.receta_service.get_data", return_value=self.data)
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()

    def test_resumen_muestra_unidad_de_presentacion(self) -> None:
        receta = Receta("r01", "Tostada con queso", [
            IngredienteReceta("p01", 0.01, cantidad_presentacion=10.0, unidad_presentacion="gr"),
        ])
        self.assertEqual(receta_service.resumen_ingredientes(receta), "Queso 10 gr")

    def test_resumen_sin_presentacion_usa_unidad_nativa(self) -> None:
        receta = Receta("r01", "Tostada con queso", [IngredienteReceta("p01", 2.45)])
        self.assertEqual(receta_service.resumen_ingredientes(receta), "Queso 2.45 Kg")

    def test_resumen_sin_presentacion_pequena_usa_unidad_legible(self) -> None:
        receta = Receta("r01", "Tostada con queso", [IngredienteReceta("p01", 0.001)])
        self.assertEqual(receta_service.resumen_ingredientes(receta), "Queso 1 gr")


class TestEtiquetaLineaReceta(unittest.TestCase):
    def test_ingrediente_base_con_presentacion(self) -> None:
        ing = LineaCestaIngrediente(
            "lin_1", "p01", "Queso", "Kg", 0.01,
            es_base_receta=True, cantidad_mostrar=10.0, unidad_mostrar="gr",
        )
        self.assertEqual(etiqueta_linea_receta(ing), "Queso — 10 gr")

    def test_ingrediente_base_sin_presentacion_usa_unidad_legible(self) -> None:
        ing = LineaCestaIngrediente("lin_1", "p01", "Queso", "Kg", 0.001, es_base_receta=True)
        self.assertEqual(etiqueta_linea_receta(ing), "Queso — 1 gr")
        self.assertEqual(cantidad_texto_linea_receta(ing), "1")

    def test_extra_con_presentacion_mantiene_prefijo(self) -> None:
        ing = LineaCestaIngrediente(
            "lin_1", "p01", "Queso", "Kg", 0.02,
            es_base_receta=False, es_extra=True, cantidad_mostrar=20.0, unidad_mostrar="gr",
        )
        self.assertEqual(etiqueta_linea_receta(ing), "c/ extra Queso — 20 gr")

    def test_omision_con_presentacion_mantiene_prefijo(self) -> None:
        ing = LineaCestaIngrediente(
            "lin_1", "p01", "Queso", "Kg", -0.01,
            es_base_receta=True, es_omision=True, cantidad_mostrar=-10.0, unidad_mostrar="gr",
        )
        self.assertEqual(etiqueta_linea_receta(ing), "s/ Queso — 10 gr")


class TestCestaConUnidadDePresentacion(unittest.TestCase):
    """`anadir_receta_a_cesta` debe mostrar la unidad elegida en la receta,
    pero calcular coste y stock siempre en la unidad nativa del producto."""

    def setUp(self) -> None:
        self.data = AppData(
            productos=[Producto("p01", "Queso", UnidadProducto.KG)],
            lotes=[LoteStock("l01", "p01", precio_total=10.0, cantidad=1.0, cantidad_restante=1.0)],
            recetas=[Receta("r01", "Tostada con queso", [
                IngredienteReceta("p01", 0.01, cantidad_presentacion=10.0, unidad_presentacion="gr"),
            ])],
        )
        self._patcher = patch("app.core.services.desayuno_service.get_data", return_value=self.data)
        self._patcher_cesta = patch("app.core.services.cesta_service.get_data", return_value=self.data)
        self._patcher.start()
        self._patcher_cesta.start()
        self._session_patcher = patch("streamlit.session_state", {})
        self._session_patcher.start()

    def tearDown(self) -> None:
        self._session_patcher.stop()
        self._patcher_cesta.stop()
        self._patcher.stop()

    def test_anadir_receta_legacy_muestra_gramos_no_kilos(self) -> None:
        """Receta antigua sin unidad_presentacion: 0,001 kg → 1 gr en pantalla."""
        legado = self.data.recetas[0].ingredientes[0]
        legado.cantidad = 0.001
        legado.cantidad_presentacion = None
        legado.unidad_presentacion = None
        resultado = desayuno_service.anadir_receta_a_cesta("r01", 1.0)
        self.assertTrue(resultado.ok)
        ingrediente = desayuno_service.get_cesta_recetas()[0].ingredientes[0]
        self.assertEqual(ingrediente.cantidad, 0.001)
        self.assertEqual(etiqueta_linea_receta(ingrediente), "Queso — 1 gr")

    def test_anadir_receta_muestra_gramos_no_kilos(self) -> None:
        resultado = desayuno_service.anadir_receta_a_cesta("r01", 1.0)
        self.assertTrue(resultado.ok)

        grupos = desayuno_service.get_cesta_recetas()
        self.assertEqual(len(grupos), 1)
        ingrediente = grupos[0].ingredientes[0]

        self.assertEqual(ingrediente.cantidad, 0.01)  # nativa (kg) intacta para cálculos
        self.assertEqual(etiqueta_linea_receta(ingrediente), "Queso — 10 gr")

    def test_porciones_escalan_la_presentacion_proporcionalmente(self) -> None:
        desayuno_service.anadir_receta_a_cesta("r01", 1.0)
        grupo = desayuno_service.get_cesta_recetas()[0]

        desayuno_service.modificar_porciones_grupo(grupo.grupo_id, 3.0)
        ingrediente = desayuno_service.get_cesta_recetas()[0].ingredientes[0]

        self.assertEqual(ingrediente.cantidad, 0.03)
        self.assertEqual(etiqueta_linea_receta(ingrediente), "Queso — 30 gr")

    def test_coste_se_calcula_en_unidad_nativa(self) -> None:
        desayuno_service.anadir_receta_a_cesta("r01", 1.0)
        # Lote: 10 € por 1 kg -> 10 €/kg. Ingrediente: 0.01 kg -> 0.10 €.
        self.assertEqual(desayuno_service.coste_total_cesta(), 0.10)

    def test_stock_disponible_se_valida_en_unidad_nativa(self) -> None:
        # 0.01 kg de un lote con 1 kg restante: hay stock de sobra.
        self.assertEqual(stock_disponible(self.data, "p01"), 1.0)
        self.assertEqual(calcular_coste_linea(self.data, "p01", 0.01), 0.10)


if __name__ == "__main__":
    unittest.main()
