"""Pruebas Fase 1 — categorías de recetas.

Ejecutar desde la raíz del proyecto:

    py -m unittest tests.test_multi_fase1_categorias -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    CategoriaReceta,
    IngredienteReceta,
    Producto,
    Receta,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import RolUsuario
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.core.services import receta_service


def _producto(pid: str = "p01", nombre: str = "Pan") -> Producto:
    return Producto(pid, nombre, UnidadProducto.KG)


def _datos_base() -> AppData:
    return AppData(
        productos=[_producto()],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestCrearRecetaPorCategoria(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos_base()
        self.patcher = patch("app.core.services.receta_service.get_data", return_value=self.data)
        self.patcher_persist = patch("app.core.services.receta_service.persist_data")
        self.patcher.start()
        self.patcher_persist.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.patcher_persist.stop()

    def _ingredientes(self) -> list[IngredienteReceta]:
        return [IngredienteReceta("p01", 0.1)]

    def test_crear_desayuno(self) -> None:
        resultado = receta_service.crear_receta("Tostada", self._ingredientes(), CategoriaReceta.DESAYUNO, porciones_estandar=1)
        self.assertTrue(resultado.ok)
        self.assertEqual(self.data.recetas[0].categoria, CategoriaReceta.DESAYUNO)

    def test_crear_comida(self) -> None:
        resultado = receta_service.crear_receta("Ensalada", self._ingredientes(), CategoriaReceta.COMIDA, porciones_estandar=1)
        self.assertTrue(resultado.ok)
        self.assertEqual(self.data.recetas[0].categoria, CategoriaReceta.COMIDA)

    def test_crear_cena(self) -> None:
        resultado = receta_service.crear_receta("Sopa", self._ingredientes(), CategoriaReceta.CENA, porciones_estandar=1)
        self.assertTrue(resultado.ok)
        self.assertEqual(self.data.recetas[0].categoria, CategoriaReceta.CENA)

    def test_crear_bebidas(self) -> None:
        resultado = receta_service.crear_receta("Café latte", self._ingredientes(), CategoriaReceta.BEBIDAS, porciones_estandar=1)
        self.assertTrue(resultado.ok)
        self.assertEqual(self.data.recetas[0].categoria, CategoriaReceta.BEBIDAS)

    def test_crear_sin_categoria_usa_desayuno(self) -> None:
        resultado = receta_service.crear_receta("Antigua", self._ingredientes(), porciones_estandar=1)
        self.assertTrue(resultado.ok)
        self.assertEqual(self.data.recetas[0].categoria, CategoriaReceta.DESAYUNO)

    def test_rechazar_categoria_invalida(self) -> None:
        resultado = receta_service.crear_receta("X", self._ingredientes(), "brunch", porciones_estandar=1)
        self.assertFalse(resultado.ok)
        self.assertIn("no válida", resultado.mensaje.lower())
        self.assertEqual(len(self.data.recetas), 0)


class TestEditarCategoria(unittest.TestCase):
    def setUp(self) -> None:
        self.ingredientes = [IngredienteReceta("p01", 0.05, 50.0, "gr")]
        self.data = _datos_base()
        self.data.recetas = [
            Receta(
                "r01",
                "Tostada",
                list(self.ingredientes),
                CategoriaReceta.DESAYUNO,
                porciones_estandar=1,
            ),
        ]
        self.patcher = patch("app.core.services.receta_service.get_data", return_value=self.data)
        self.patcher_persist = patch("app.core.services.receta_service.persist_data")
        self.patcher.start()
        self.patcher_persist.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.patcher_persist.stop()

    def test_editar_solo_categoria_mantiene_ingredientes(self) -> None:
        resultado = receta_service.editar_receta(
            "r01", "Tostada", list(self.ingredientes), CategoriaReceta.COMIDA,
            porciones_estandar=1,
        )
        self.assertTrue(resultado.ok)
        receta = self.data.recetas[0]
        self.assertEqual(receta.categoria, CategoriaReceta.COMIDA)
        self.assertEqual(receta.nombre, "Tostada")
        self.assertEqual(len(receta.ingredientes), 1)
        self.assertEqual(receta.ingredientes[0].cantidad, 0.05)
        self.assertEqual(receta.ingredientes[0].cantidad_presentacion, 50.0)
        self.assertEqual(receta.ingredientes[0].unidad_presentacion, "gr")
        self.assertEqual(len(self.data.actividades), 1)
        self.assertIn("categoría", self.data.actividades[0].detalle.lower())

    def test_editar_categoria_invalida(self) -> None:
        resultado = receta_service.editar_receta(
            "r01", "Tostada", list(self.ingredientes), "tapas",
            porciones_estandar=1,
        )
        self.assertFalse(resultado.ok)
        self.assertEqual(self.data.recetas[0].categoria, CategoriaReceta.DESAYUNO)


class TestCompatibilidadRecetaAntigua(unittest.TestCase):
    def test_cargar_receta_sin_categoria_asigna_desayuno(self) -> None:
        payload = {
            "productos": [],
            "lotes": [],
            "recetas": [
                {
                    "id": "r01",
                    "nombre": "Legacy",
                    "ingredientes": [
                        {"producto_id": "p01", "cantidad": 0.2},
                    ],
                },
            ],
            "desayunos": [],
            "mermas": [],
            "alertas": [],
            "actividades": [],
            "usuarios": [],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(len(data.recetas), 1)
        self.assertEqual(data.recetas[0].categoria, CategoriaReceta.DESAYUNO)
        self.assertEqual(data.recetas[0].ingredientes[0].cantidad, 0.2)

    def test_serializar_incluye_categoria(self) -> None:
        data = AppData(recetas=[
            Receta("r01", "Sopa", [IngredienteReceta("p01", 0.1)], CategoriaReceta.CENA),
        ])
        payload = appdata_to_dict(data)
        self.assertEqual(payload["recetas"][0]["categoria"], "cena")

    def test_roundtrip_conserva_categoria_e_ingredientes(self) -> None:
        original = AppData(recetas=[
            Receta(
                "r01",
                "Café",
                [IngredienteReceta("p02", 0.05, 50.0, "ml")],
                CategoriaReceta.BEBIDAS,
            ),
        ])
        recuperado = dict_to_appdata(appdata_to_dict(original))
        receta = recuperado.recetas[0]
        self.assertEqual(receta.categoria, CategoriaReceta.BEBIDAS)
        self.assertEqual(receta.ingredientes[0].cantidad, 0.05)
        self.assertEqual(receta.ingredientes[0].unidad_presentacion, "ml")


class TestListarPorCategoria(unittest.TestCase):
    def setUp(self) -> None:
        self.data = AppData(recetas=[
            Receta("r01", "Tostada", [], CategoriaReceta.DESAYUNO),
            Receta("r02", "Pasta", [], CategoriaReceta.COMIDA),
            Receta("r03", "Zumo", [], CategoriaReceta.BEBIDAS),
            Receta("r04", "Café", [], CategoriaReceta.BEBIDAS),
        ])
        self.patcher = patch("app.core.services.receta_service.get_data", return_value=self.data)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_filtro_una_categoria(self) -> None:
        nombres = [r.nombre for r in receta_service.listar_recetas(categoria=CategoriaReceta.BEBIDAS)]
        self.assertEqual(nombres, ["Café", "Zumo"])

    def test_filtro_varias_categorias(self) -> None:
        nombres = [
            r.nombre
            for r in receta_service.listar_recetas(
                categorias=[CategoriaReceta.DESAYUNO, CategoriaReceta.BEBIDAS],
            )
        ]
        self.assertEqual(nombres, ["Café", "Tostada", "Zumo"])


if __name__ == "__main__":
    unittest.main()
