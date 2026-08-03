"""Fase 4A — catálogos: lectura de productos vía AppContext.

Comportamiento visible de `mapa_productos` / `DataRepository.get_producto` sin cambios.

Ejecutar:

    py -m unittest tests.test_fase4a_catalogos -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import AppData, Producto, UnidadProducto
from app.core.repositories.data_repository import DataRepository
from app.core.services.stock_service import mapa_bebidas, mapa_productos


def _datos() -> AppData:
    return AppData(
        productos=[
            Producto("p02", "Leche", UnidadProducto.L, es_bebida=False),
            Producto("p01", "Agua", UnidadProducto.L, es_bebida=True),
        ],
    )


class TestFase4ACatalogos(unittest.TestCase):
    def test_mapa_productos_legacy_orden_y_filtro(self) -> None:
        data = _datos()
        # Orden de inserción en data.productos (sin reordenar por nombre)
        self.assertEqual(
            list(mapa_productos(data).keys()),
            ["Leche", "Agua"],
        )
        self.assertEqual(mapa_productos(data, es_bebida=True), {"Agua": "p01"})
        self.assertEqual(mapa_productos(data, es_bebida=False), {"Leche": "p02"})
        self.assertEqual(mapa_bebidas(data), {"Agua": "p01"})

    def test_get_producto_via_adaptador(self) -> None:
        data = _datos()
        repo = DataRepository(data)
        self.assertEqual(repo.get_producto("p01").nombre, "Agua")
        self.assertIsNone(repo.get_producto("x"))


if __name__ == "__main__":
    unittest.main()
