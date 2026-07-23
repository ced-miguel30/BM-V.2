"""Pruebas Fase 5 — gestor de merma (ámbitos bebida / general; sin servicio).

Ejecutar:

    py -m unittest tests.test_analitica_fase5_merma -v
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
    LineaMerma,
    MotivoMerma,
    Producto,
    RegistroMerma,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import RolUsuario
from app.core.repositories.data_repository import DataRepository
from app.core.services import merma_analisis_service as merma_an


def _data() -> AppData:
    d0 = date(2026, 7, 10)
    return AppData(
        productos=[
            Producto("p1", "Pan", UnidadProducto.KG),
            Producto("p2", "Café", UnidadProducto.L, es_bebida=True),
            Producto("p3", "Leche", UnidadProducto.L, es_bebida=True),
        ],
        usuarios=[Usuario("u1", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u1",
        mermas=[
            RegistroMerma(
                "m1", d0,
                [
                    LineaMerma("p1", 1.0, 4.0, MotivoMerma.MERMA),
                    LineaMerma("p2", 0.5, 3.0, MotivoMerma.EXPIRACION),
                    LineaMerma("p3", 1.0, 2.0, MotivoMerma.PRODUCTO_MALO),
                ],
                coste_total=9.0,
                registrado_por="Ana",
            ),
            RegistroMerma(
                "m2", date(2026, 7, 12),
                [LineaMerma("p1", 0.5, 1.0, MotivoMerma.MERMA)],
                coste_total=1.0,
                registrado_por="Ana",
            ),
        ],
    )


class TestFase5Merma(unittest.TestCase):
    def test_resumen_separa_merma_y_expiracion(self) -> None:
        data = _data()
        repo = DataRepository(data)
        with patch(
            "app.core.services.merma_analisis_service.get_repository",
            return_value=repo,
        ):
            res = merma_an.resumen_merma(date(2026, 7, 1), date(2026, 7, 31), data=data)
        self.assertEqual(res["total"], 10.0)
        self.assertEqual(res["expiracion"], 3.0)
        self.assertEqual(res["merma"], 7.0)  # 4+2+1
        self.assertEqual(res["bebida_coste"], 5.0)  # café 3 + leche 2
        self.assertEqual(res["general_coste"], 5.0)  # pan 4+1

    def test_ambito_bebida_no_incluye_pan(self) -> None:
        data = _data()
        repo = DataRepository(data)
        with patch(
            "app.core.services.merma_analisis_service.get_repository",
            return_value=repo,
        ):
            filas = merma_an.ranking_productos_merma(
                date(2026, 7, 1), date(2026, 7, 31),
                data=data, ambito=merma_an.AMBITO_BEBIDA,
            )
        nombres = {f["nombre"] for f in filas}
        self.assertIn("Café", nombres)
        self.assertIn("Leche", nombres)
        self.assertNotIn("Pan", nombres)

    def test_menos_solo_uso_positivo_ascendente(self) -> None:
        data = _data()
        repo = DataRepository(data)
        with patch(
            "app.core.services.merma_analisis_service.get_repository",
            return_value=repo,
        ):
            filas = merma_an.ranking_productos_merma(
                date(2026, 7, 1), date(2026, 7, 31),
                data=data, ambito=merma_an.AMBITO_TODO, ascendente=True,
            )
        self.assertTrue(all(f["usos"] > 0 for f in filas))
        costes = [f["coste"] for f in filas]
        self.assertEqual(costes, sorted(costes))

    def test_mensaje_servicio_sin_vinculo(self) -> None:
        self.assertIn("Desayuno", merma_an.MSG_SERVICIO_SIN_VINCULO)
        self.assertIn("deshabilitadas", merma_an.MSG_SERVICIO_SIN_VINCULO)
