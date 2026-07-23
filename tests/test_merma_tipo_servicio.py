"""Pruebas merma por tipo_servicio_snapshot (persistencia, cesta, análisis).

Ejecutar:

    py -m unittest tests.test_merma_tipo_servicio -v
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
    LoteStock,
    MotivoMerma,
    OrigenServicioMerma,
    Producto,
    RegistroMerma,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import RolUsuario
from app.core.repositories.data_repository import DataRepository
from app.core.services import merma_analisis_service as merma_an
from app.core.services import merma_service
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _catalogo() -> AppData:
    return AppData(
        productos=[
            Producto("p_cafe", "Café", UnidadProducto.L, es_bebida=True),
            Producto("p_pan", "Pan", UnidadProducto.KG, es_bebida=False),
        ],
        lotes=[
            LoteStock("l_cafe", "p_cafe", 20.0, 10.0, 10.0, date(2026, 7, 1)),
            LoteStock("l_pan", "p_pan", 10.0, 5.0, 5.0, date(2026, 7, 1)),
        ],
        usuarios=[Usuario("u1", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u1",
    )


class TestFase1Persistencia(unittest.TestCase):
    def test_json_antiguo_sin_snapshot_carga_none(self) -> None:
        payload = {
            "productos": [],
            "lotes": [],
            "recetas": [],
            "desayunos": [],
            "mermas": [
                {
                    "id": "m1",
                    "fecha": "2026-07-10",
                    "lineas": [
                        {
                            "producto_id": "p1",
                            "cantidad": 1.0,
                            "coste": 2.0,
                            "motivo": "Merma",
                        }
                    ],
                    "coste_total": 2.0,
                    "registrado_por": "Ana",
                }
            ],
            "alertas": [],
            "usuarios": [],
            "actividades": [],
        }
        data = dict_to_appdata(payload)
        self.assertIsNone(data.mermas[0].lineas[0].tipo_servicio_snapshot)

    def test_roundtrip_con_snapshot(self) -> None:
        data = _catalogo()
        data.mermas.append(RegistroMerma(
            "m1", date(2026, 7, 10),
            [LineaMerma(
                "p_cafe", 0.5, 1.0, MotivoMerma.MERMA,
                lote_id="l_cafe",
                tipo_servicio_snapshot=OrigenServicioMerma.DESAYUNO.value,
            )],
            coste_total=1.0,
            registrado_por="Ana",
        ))
        restored = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(
            restored.mermas[0].lineas[0].tipo_servicio_snapshot,
            "desayuno",
        )


class TestFase2CestaYRegistro(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _catalogo()
        self.cesta: list = []

    def _ctx(self):
        return patch.multiple(
            merma_service,
            get_data=lambda: self.data,
            persist_data=lambda d: None,
            get_cesta_merma=lambda: self.cesta,
            limpiar_cesta_merma=lambda: self.cesta.clear(),
        )

    def test_cafe_desayuno_y_comida(self) -> None:
        with self._ctx(), patch("app.core.services.alert_service.sincronizar_alertas"):
            r1 = merma_service.anadir_a_cesta_merma(
                "l_cafe", 0.2, MotivoMerma.MERMA.value, "desayuno",
            )
            r2 = merma_service.anadir_a_cesta_merma(
                "l_cafe", 0.3, MotivoMerma.MERMA.value, "comida",
            )
            self.assertTrue(r1.ok)
            self.assertTrue(r2.ok)
            self.assertEqual(len(self.cesta), 2)
            servicios = {l.tipo_servicio_snapshot for l in self.cesta}
            self.assertEqual(servicios, {"desayuno", "comida"})

    def test_mismo_lote_motivo_servicios_distintos_no_fusionan(self) -> None:
        with self._ctx():
            merma_service.anadir_a_cesta_merma(
                "l_cafe", 0.1, MotivoMerma.MERMA.value, "desayuno",
            )
            merma_service.anadir_a_cesta_merma(
                "l_cafe", 0.1, MotivoMerma.MERMA.value, "cena",
            )
            self.assertEqual(len(self.cesta), 2)

    def test_pan_cena_y_bebida_general(self) -> None:
        with self._ctx():
            r_pan = merma_service.anadir_a_cesta_merma(
                "l_pan", 0.5, MotivoMerma.MERMA.value, "cena",
            )
            r_gen = merma_service.anadir_a_cesta_merma(
                "l_cafe", 0.2, MotivoMerma.PRODUCTO_MALO.value, "general",
            )
            self.assertTrue(r_pan.ok)
            self.assertTrue(r_gen.ok)

    def test_rechaza_sin_servicio(self) -> None:
        with self._ctx():
            r = merma_service.anadir_a_cesta_merma(
                "l_cafe", 0.1, MotivoMerma.MERMA.value, None,
            )
            self.assertFalse(r.ok)
            r2 = merma_service.anadir_a_cesta_merma(
                "l_cafe", 0.1, MotivoMerma.MERMA.value, "otro",
            )
            self.assertFalse(r2.ok)
            self.assertEqual(len(self.cesta), 0)

    def test_registrar_descuenta_stock_y_guarda_snapshot(self) -> None:
        with self._ctx(), patch("app.core.services.alert_service.sincronizar_alertas"):
            merma_service.anadir_a_cesta_merma(
                "l_cafe", 1.0, MotivoMerma.MERMA.value, "desayuno",
            )
            restante_antes = self.data.lotes[0].cantidad_restante
            ok = merma_service.registrar_merma(date(2026, 7, 15))
            self.assertTrue(ok.ok)
            self.assertEqual(self.data.lotes[0].cantidad_restante, restante_antes - 1.0)
            self.assertEqual(len(self.data.mermas), 1)
            self.assertEqual(
                self.data.mermas[0].lineas[0].tipo_servicio_snapshot, "desayuno",
            )
            self.assertEqual(len(self.cesta), 0)


class TestFase3Analisis(unittest.TestCase):
    def _data_mixto(self) -> AppData:
        data = _catalogo()
        d0 = date(2026, 7, 10)
        data.mermas.extend([
            RegistroMerma(
                "m1", d0,
                [
                    LineaMerma(
                        "p_cafe", 0.2, 3.0, MotivoMerma.MERMA,
                        lote_id="l_cafe",
                        tipo_servicio_snapshot="desayuno",
                    ),
                    LineaMerma(
                        "p_cafe", 0.3, 4.0, MotivoMerma.MERMA,
                        lote_id="l_cafe",
                        tipo_servicio_snapshot="comida",
                    ),
                    LineaMerma(
                        "p_pan", 1.0, 5.0, MotivoMerma.MERMA,
                        lote_id="l_pan",
                        tipo_servicio_snapshot="cena",
                    ),
                    LineaMerma(
                        "p_cafe", 0.1, 2.0, MotivoMerma.PRODUCTO_MALO,
                        lote_id="l_cafe",
                        tipo_servicio_snapshot="general",
                    ),
                    # Histórico sin snapshot
                    LineaMerma(
                        "p_pan", 0.5, 1.5, MotivoMerma.EXPIRACION,
                        lote_id="l_pan",
                        tipo_servicio_snapshot=None,
                    ),
                ],
                coste_total=15.5,
                registrado_por="Ana",
            ),
        ])
        return data

    def test_filtro_por_servicio(self) -> None:
        data = self._data_mixto()
        repo = DataRepository(data)
        with patch("app.core.services.merma_analisis_service.get_repository", return_value=repo):
            des = merma_an.iter_lineas_merma(
                date(2026, 7, 1), date(2026, 7, 31), data=data, ambito="desayuno",
            )
            self.assertEqual(len(des), 1)
            self.assertEqual(des[0].coste, 3.0)
            hist = merma_an.iter_lineas_merma(
                date(2026, 7, 1), date(2026, 7, 31),
                data=data, ambito=merma_an.BUCKET_SIN_DESGLOSE,
            )
            self.assertEqual(len(hist), 1)
            self.assertEqual(hist[0].coste, 1.5)

    def test_suma_categorias_igual_total(self) -> None:
        data = self._data_mixto()
        repo = DataRepository(data)
        with patch("app.core.services.merma_analisis_service.get_repository", return_value=repo):
            res = merma_an.resumen_merma(date(2026, 7, 1), date(2026, 7, 31), data=data)
            self.assertEqual(res["total"], 15.5)
            self.assertEqual(res["suma_grupos"], 15.5)
            self.assertEqual(sum(res["por_grupo"].values()), 15.5)

    def test_cambiar_es_bebida_no_mueve_bucket(self) -> None:
        data = self._data_mixto()
        # Café deja de ser bebida en catálogo vivo
        cafe = next(p for p in data.productos if p.id == "p_cafe")
        cafe.es_bebida = False
        repo = DataRepository(data)
        with patch("app.core.services.merma_analisis_service.get_repository", return_value=repo):
            des = merma_an.iter_lineas_merma(
                date(2026, 7, 1), date(2026, 7, 31), data=data, ambito="desayuno",
            )
            self.assertEqual(len(des), 1)
            self.assertEqual(des[0].producto_id, "p_cafe")
            # No debe ir a "general" por es_bebida=False
            gen = merma_an.iter_lineas_merma(
                date(2026, 7, 1), date(2026, 7, 31), data=data, ambito="general",
            )
            self.assertEqual(len(gen), 1)
            self.assertEqual(gen[0].coste, 2.0)


class TestHelpersUI(unittest.TestCase):
    def test_valor_servicio_desde_ui(self) -> None:
        self.assertIsNone(
            merma_service.valor_servicio_desde_ui(merma_service.PLACEHOLDER_SERVICIO)
        )
        self.assertEqual(merma_service.valor_servicio_desde_ui("Desayuno"), "desayuno")
        self.assertEqual(
            merma_service.valor_servicio_desde_ui("Almacén / General"), "general",
        )


if __name__ == "__main__":
    unittest.main()
