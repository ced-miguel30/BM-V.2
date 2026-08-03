"""Fase 1B — pruebas del módulo de diagnóstico de invariantes (solo lectura).

Separado de los tests de anulación (Fase 1A). No ejecuta anulaciones.

Ejecutar:

    py -m unittest tests.test_diagnostico_invariantes_fase1b -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    LineaDetalleOrigen,
    LineaMerma,
    LoteStock,
    MotivoMerma,
    Producto,
    RegistroDesayuno,
    RegistroMerma,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import OrigenConsumo
from app.core.models.registro_servicio import ConsumoLoteDetalle
from app.core.services.diagnostico_invariantes import evaluar_invariantes_json
from app.core.services.diagnostico_service import generar_diagnostico


class TestDiagnosticoInvariantesFase1B(unittest.TestCase):
    def test_conteos_anulados_y_sin_traza(self) -> None:
        data = AppData(
            productos=[Producto("p1", "Harina", UnidadProducto.KG)],
            lotes=[
                LoteStock(
                    "l1", "p1", precio_total=10.0, cantidad=5.0,
                    cantidad_restante=0.0, fecha_compra=date(2026, 7, 1),
                    anulado=True, motivo_anulacion="dup",
                ),
                LoteStock(
                    "l2", "p1", precio_total=10.0, cantidad=5.0,
                    cantidad_restante=5.0, fecha_compra=date(2026, 7, 2),
                ),
            ],
            desayunos=[
                RegistroDesayuno(
                    id="d_ok",
                    fecha=date(2026, 7, 20),
                    coste_total=2.0,
                    lineas_detalle=[
                        LineaDetalleOrigen(
                            origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                            producto_id="p1",
                            cantidad=1.0,
                            coste=2.0,
                            consumos_lote=[ConsumoLoteDetalle("l2", "p1", 1.0, 2.0)],
                        ),
                    ],
                ),
                RegistroDesayuno(
                    id="d_hist",
                    fecha=date(2026, 1, 1),
                    coste_total=3.0,
                    lineas_detalle=[],
                ),
                RegistroDesayuno(
                    id="d_anul",
                    fecha=date(2026, 7, 10),
                    coste_total=1.0,
                    anulado=True,
                    motivo_anulacion="error",
                ),
            ],
            mermas=[
                RegistroMerma(
                    id="m1",
                    fecha=date(2026, 7, 11),
                    lineas=[LineaMerma("p1", 1.0, 1.0, MotivoMerma.MERMA, lote_id=None)],
                ),
            ],
            usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
            usuario_actual_id="u01",
        )

        inv = evaluar_invariantes_json(data)
        self.assertEqual(inv.num_compras_anuladas, 1)
        self.assertEqual(inv.num_registros_anulados, 1)
        self.assertEqual(inv.num_registros_activos_con_traza, 1)
        self.assertGreaterEqual(inv.num_registros_activos_sin_traza, 1)
        self.assertEqual(inv.num_mermas_activas_sin_lote, 1)
        self.assertTrue(any("sin lote_id" in x for x in inv.incidencias_invariantes))

        # Integración con diagnóstico general (sigue sin mutar).
        resumen = generar_diagnostico(data)
        self.assertEqual(resumen.num_compras_anuladas, 1)
        self.assertEqual(resumen.num_registros_anulados, 1)
        self.assertTrue(resumen.notas_invariantes)


if __name__ == "__main__":
    unittest.main()
