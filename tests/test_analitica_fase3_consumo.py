"""Pruebas Fase 3 — gestor de consumo multi-categoría.

Ejecutar:

    py -m unittest tests.test_analitica_fase3_consumo -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    LineaDetalleOrigen,
    OrigenConsumo,
    Producto,
    RegistroDesayuno,
    RegistroRecetaDesayuno,
    RegistroServicio,
    TipoServicio,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import RolUsuario
from app.core.models.registro_servicio import RegistroRecetaServicio
from app.core.services import analitica_consumo_service as analitica
from app.core.services import consumo_service
from app.core.storage.session_store import get_data
from unittest.mock import patch


def _data() -> AppData:
    return AppData(
        productos=[
            Producto("p_pan", "Pan", UnidadProducto.KG),
            Producto("p_cafe", "Café", UnidadProducto.L, es_bebida=True),
        ],
        usuarios=[Usuario("u1", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u1",
        desayunos=[
            RegistroDesayuno(
                "d1", date(2026, 7, 10), coste_total=10.0, registrado_por="Ana",
                registros_recetas=[
                    RegistroRecetaDesayuno(
                        "r1", "Tostada", 2.0, categoria_receta_snapshot="desayuno",
                    ),
                ],
                lineas_detalle=[
                    LineaDetalleOrigen(
                        OrigenConsumo.INGREDIENTE_RECETA.value, "p_pan", 0.2, 7.0,
                        receta_origen_id="r1", tipo_servicio="desayuno",
                        es_bebida_snapshot=False, categoria_receta_snapshot="desayuno",
                    ),
                    LineaDetalleOrigen(
                        OrigenConsumo.PRODUCTO_DIRECTO.value, "p_cafe", 0.1, 3.0,
                        tipo_servicio="desayuno", es_bebida_snapshot=True,
                    ),
                ],
            ),
        ],
        registros_servicio=[
            RegistroServicio(
                "b1", TipoServicio.BEBIDAS.value, date(2026, 7, 10),
                coste_total=5.0, registrado_por="Ana",
                lineas_detalle=[
                    LineaDetalleOrigen(
                        OrigenConsumo.PRODUCTO_DIRECTO.value, "p_cafe", 0.2, 5.0,
                        tipo_servicio="bebidas", es_bebida_snapshot=True,
                    ),
                ],
            ),
        ],
    )


class TestFase3Consumo(unittest.TestCase):
    def test_resumen_y_separacion_bebidas(self) -> None:
        data = _data()
        res = analitica.resumen_consumo(date(2026, 7, 1), date(2026, 7, 31), data=data)
        self.assertEqual(res["coste_consumo"], 15.0)
        self.assertEqual(res["n_registros"], 2)
        self.assertEqual(
            analitica.coste_bucket_bebida(
                analitica.BUCKET_BEBIDA_EN_DESAYUNO, date(2026, 7, 1), date(2026, 7, 31), data=data,
            ),
            3.0,
        )
        self.assertEqual(
            analitica.coste_bucket_bebida(
                analitica.BUCKET_BEBIDA_INDEPENDIENTE, date(2026, 7, 1), date(2026, 7, 31), data=data,
            ),
            5.0,
        )

    def test_ranking_recetas_con_coste_desde_productos(self) -> None:
        data = _data()
        rec = analitica.ranking_recetas(
            date(2026, 7, 1), date(2026, 7, 31),
            data=data, tipo_servicio="desayuno",
        )
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["porciones"], 2.0)
        self.assertEqual(rec[0]["coste"], 7.0)  # solo pan, no café directo

    def test_menos_solo_consumo_positivo(self) -> None:
        data = _data()
        menos = analitica.ranking_productos(
            date(2026, 7, 1), date(2026, 7, 31),
            data=data, ascendente=True, solo_consumo_bebida=False,
        )
        self.assertTrue(all(r["usos"] > 0 for r in menos))
        self.assertEqual(menos[0]["producto_id"], "p_pan")

    def test_export_incluye_registros_servicio(self) -> None:
        data = _data()
        with patch("app.core.services.consumo_service.get_data", return_value=data):
            regs = consumo_service.registros_exportables(
                date(2026, 7, 1), datetime(2026, 7, 31, 23, 59, 59),
            )
        tipos = {r.tipo for r in regs}
        self.assertIn("Consumo", tipos)
        self.assertTrue(any("bebidas" in t for t in tipos))
