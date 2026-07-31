"""Fase 15 — coherencia analítica (anti doble conteo / histórico).

Ejecutar:

    py -m unittest tests.test_analitica_fase15_coherencia -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.services import analitica_consumo_service as analitica


class TestFase15Coherencia(unittest.TestCase):
    def test_explicacion_anti_doble(self) -> None:
        texto = analitica.TEXTO_EXPLICACION_CALCULO
        self.assertIn("anti doble conteo", texto.casefold().replace("anti-doble", "anti doble"))
        self.assertIn("receta", texto.casefold())
        self.assertIn("escalado", texto.casefold())

    def test_detalle_vs_total_coherente(self) -> None:
        lineas = [
            SimpleNamespace(coste=3.5),
            SimpleNamespace(coste=1.5),
        ]
        self.assertTrue(analitica.coherencia_detalle_vs_coste_total(lineas, 5.0))
        self.assertFalse(analitica.coherencia_detalle_vs_coste_total(lineas, 6.0))
        self.assertFalse(analitica.coherencia_detalle_vs_coste_total([], 5.0))

    def test_excluyentes_no_suman_receta_aparte(self) -> None:
        """coste_general = suma de coste_total de registros; no usa eventos receta."""
        hoy = date.today()
        data = SimpleNamespace(
            desayunos=[
                SimpleNamespace(
                    fecha=hoy,
                    coste_total=10.0,
                    anulado=False,
                    lineas_detalle=[],  # histórico: total por coste_total
                )
            ],
            registros_servicio=[
                SimpleNamespace(
                    fecha=hoy,
                    tipo_servicio="comida",
                    coste_total=7.0,
                    anulado=False,
                    lineas_detalle=[SimpleNamespace(coste=7.0)],
                ),
                SimpleNamespace(
                    fecha=hoy,
                    tipo_servicio="cena",
                    coste_total=3.0,
                    anulado=False,
                    lineas_detalle=[],
                ),
                SimpleNamespace(
                    fecha=hoy,
                    tipo_servicio="bebidas",
                    coste_total=2.0,
                    anulado=True,
                    lineas_detalle=[SimpleNamespace(coste=2.0)],
                ),
            ],
        )
        costes = analitica.coste_servicios_excluyentes(hoy, hoy, data=data)
        self.assertEqual(costes.desayuno_total, 10.0)
        self.assertEqual(costes.comida_total, 7.0)
        self.assertEqual(costes.cena_total, 3.0)
        self.assertEqual(costes.bebidas_independientes, 0.0)  # anulado
        self.assertEqual(costes.coste_general, 20.0)

        hist = analitica.resumen_historico_incompleto(hoy, hoy, data=data)
        self.assertEqual(hist["n_sin_detalle"], 2)  # desayuno + cena
        self.assertEqual(hist["coste_sin_detalle"], 13.0)
        self.assertTrue(hist["hay_aviso"])


if __name__ == "__main__":
    unittest.main()
