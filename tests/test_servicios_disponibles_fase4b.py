"""Filtros servicios_disponibles (Fase 4B): lista vacía ≠ todos."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    CategoriaReceta,
    Producto,
    Receta,
    UnidadProducto,
)
from app.core.services import desayuno_service, merma_service, receta_service
from app.core.services.servicio_registro_service import ServicioRegistro
from app.core.services.stock_service import disponible_en_servicio


class TestDisponibleEnServicio(unittest.TestCase):
    def test_lista_vacia_no_es_todos(self) -> None:
        self.assertFalse(disponible_en_servicio([], "desayuno"))
        self.assertFalse(disponible_en_servicio(None, "comida"))

    def test_servicio_incluido(self) -> None:
        self.assertTrue(disponible_en_servicio(["desayuno", "cena"], "desayuno"))
        self.assertFalse(disponible_en_servicio(["desayuno"], "comida"))

    def test_general_sin_filtro_por_defecto(self) -> None:
        self.assertTrue(disponible_en_servicio([], "general"))
        self.assertTrue(disponible_en_servicio(["desayuno"], "general"))
        self.assertFalse(
            disponible_en_servicio([], "general", permitir_general_sin_filtro=False),
        )


class TestFiltrosCatalogo(unittest.TestCase):
    def setUp(self) -> None:
        self.prod_desayuno = Producto(
            id="p1",
            nombre="Pan desayuno",
            unidad=UnidadProducto.UD,
            es_bebida=False,
            servicios_disponibles=["desayuno"],
        )
        self.prod_comida = Producto(
            id="p2",
            nombre="Arroz comida",
            unidad=UnidadProducto.KG,
            es_bebida=False,
            servicios_disponibles=["comida"],
        )
        self.prod_vacio = Producto(
            id="p3",
            nombre="Sin configurar",
            unidad=UnidadProducto.UD,
            es_bebida=False,
            servicios_disponibles=[],
        )
        self.prod_dual = Producto(
            id="p4",
            nombre="Huevos dual",
            unidad=UnidadProducto.UD,
            es_bebida=False,
            servicios_disponibles=["desayuno", "comida"],
        )
        self.data = MagicMock()
        self.data.productos = [
            self.prod_desayuno,
            self.prod_comida,
            self.prod_vacio,
            self.prod_dual,
        ]
        self.data.lotes = []

    def test_desayuno_catalogo_excluye_vacio_y_comida(self) -> None:
        with mock.patch(
            "app.core.services.desayuno_service.get_data", return_value=self.data,
        ), mock.patch(
            "app.core.services.desayuno_service.stock_disponible", return_value=1.0,
        ):
            ids = {p["id"] for p in desayuno_service.productos_catalogo("", servicio="desayuno")}
        self.assertEqual(ids, {"p1", "p4"})

    def test_servicio_registro_filtra(self) -> None:
        with mock.patch(
            "app.core.services.servicio_registro_service.get_data", return_value=self.data,
        ), mock.patch(
            "app.core.services.servicio_registro_service.stock_disponible", return_value=1.0,
        ):
            svc = ServicioRegistro(
                "comida",
                "test_comida",
                [CategoriaReceta.COMIDA],
            )
            ids = {p["id"] for p in svc.productos_catalogo("")}
        self.assertEqual(ids, {"p2", "p4"})

    def test_merma_general_incluye_vacios(self) -> None:
        lote = MagicMock()
        lote.producto_id = "p3"
        lote.cantidad_restante = 2.0
        self.data.lotes = [lote]
        with mock.patch(
            "app.core.services.merma_service.get_data", return_value=self.data,
        ):
            ids_gen = {p["id"] for p in merma_service.productos_con_stock("", servicio="general")}
            ids_des = {p["id"] for p in merma_service.productos_con_stock("", servicio="desayuno")}
        self.assertIn("p3", ids_gen)
        self.assertNotIn("p3", ids_des)

    def test_listar_recetas_servicio(self) -> None:
        recetas = [
            Receta(
                id="r1", nombre="Tostada", categoria=CategoriaReceta.DESAYUNO,
                ingredientes=[], servicios_disponibles=["desayuno"],
            ),
            Receta(
                id="r2", nombre="Sopa", categoria=CategoriaReceta.COMIDA,
                ingredientes=[], servicios_disponibles=["comida"],
            ),
            Receta(
                id="r3", nombre="Sin svc", categoria=CategoriaReceta.DESAYUNO,
                ingredientes=[], servicios_disponibles=[],
            ),
        ]
        data = MagicMock()
        data.recetas = recetas
        with mock.patch(
            "app.core.services.receta_service.get_data", return_value=data,
        ):
            nombres = [r.nombre for r in receta_service.listar_recetas(servicio_disponible="desayuno")]
        self.assertEqual(nombres, ["Tostada"])


if __name__ == "__main__":
    unittest.main()
