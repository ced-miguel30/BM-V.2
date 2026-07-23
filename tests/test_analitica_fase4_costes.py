"""Pruebas Fase 4 — gestor de costes (naturaleza × servicio).

Ejecutar:

    py -m unittest tests.test_analitica_fase4_costes -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    LineaDetalleOrigen,
    LineaMerma,
    MotivoMerma,
    OrigenConsumo,
    Producto,
    RegistroDesayuno,
    RegistroMerma,
    RegistroServicio,
    TipoServicio,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import RolUsuario
from app.core.repositories.data_repository import DataRepository
from app.core.services import costes_service


def _data() -> AppData:
    d0 = date(2026, 7, 10)
    return AppData(
        productos=[
            Producto("p1", "Pan", UnidadProducto.KG),
            Producto("p2", "Café", UnidadProducto.L, es_bebida=True),
        ],
        usuarios=[Usuario("u1", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u1",
        desayunos=[
            RegistroDesayuno(
                "d1", d0, coste_total=10.0, registrado_por="Ana", num_huespedes=10,
                lineas_detalle=[
                    LineaDetalleOrigen(
                        OrigenConsumo.PRODUCTO_DIRECTO.value, "p1", 0.1, 7.0,
                        tipo_servicio="desayuno", es_bebida_snapshot=False,
                    ),
                    LineaDetalleOrigen(
                        OrigenConsumo.PRODUCTO_DIRECTO.value, "p2", 0.1, 3.0,
                        tipo_servicio="desayuno", es_bebida_snapshot=True,
                    ),
                ],
            ),
        ],
        registros_servicio=[
            RegistroServicio("c1", TipoServicio.COMIDA.value, d0, coste_total=20.0),
            RegistroServicio("b1", TipoServicio.BEBIDAS.value, d0, coste_total=5.0),
        ],
        mermas=[
            RegistroMerma(
                "m1", d0,
                [
                    LineaMerma("p1", 1.0, 2.0, MotivoMerma.MERMA),
                    LineaMerma("p1", 1.0, 4.0, MotivoMerma.EXPIRACION),
                ],
                coste_total=6.0,
                registrado_por="Ana",
            ),
        ],
    )


class TestFase4Costes(unittest.TestCase):
    def test_consumo_multi_servicio_en_naturaleza(self) -> None:
        data = _data()
        repo = DataRepository(data)
        with patch("app.core.services.costes_service.get_repository", return_value=repo):
            nat = costes_service._costes_naturaleza(date(2026, 7, 1), date(2026, 7, 31))
        self.assertEqual(nat["Consumo"], 35.0)  # 10+20+5
        self.assertEqual(nat["Merma"], 2.0)
        self.assertEqual(nat["Expiración"], 4.0)

    def test_servicios_excluyentes_y_desglose(self) -> None:
        data = _data()
        repo = DataRepository(data)
        with patch("app.core.services.costes_service.get_repository", return_value=repo):
            serv = costes_service.costes_consumo_por_servicio(date(2026, 7, 1), date(2026, 7, 31))
            des = costes_service.desglose_costes_desayuno(date(2026, 7, 1), date(2026, 7, 31))
        self.assertEqual(serv["Desayuno"], 10.0)
        self.assertEqual(serv["Comida"], 20.0)
        self.assertEqual(serv["Bebidas"], 5.0)
        self.assertEqual(serv["Total"], 35.0)
        self.assertEqual(des["Desayuno"], 7.0)
        self.assertEqual(des["Bebidas en desayuno"], 3.0)
        self.assertEqual(des["Desayuno total"], 10.0)

    def test_export_incluye_xlsx(self) -> None:
        data = _data()
        repo = DataRepository(data)
        with patch("app.core.services.costes_service.get_repository", return_value=repo):
            raw = costes_service.exportar_costes_excel(
                date(2026, 7, 1), date(2026, 7, 15),
                date(2026, 6, 1), date(2026, 6, 15),
                ["Consumo", "Merma", "Expiración"],
            )
        self.assertTrue(raw.startswith(b"PK"))
