"""Fase 4G — anulaciones vía AppContext.

Ejecutar:

    py -m unittest tests.test_fase4g_anulaciones -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.actor import Actor
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
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
from app.core.services import anulacion_merma_service as anul_m
from app.core.services import anulacion_registro_service as anul_r


def _ctx(data: AppData):
    return build_app_context(
        uow=InMemoryUnitOfWork(data),
        clock=FixedClock(datetime(2026, 7, 30, 15, 30, 0)),
        actor=Actor(id="u01", nombre="Ana", rol="Admin"),
    )


class TestFase4GAnulaciones(unittest.TestCase):
    def setUp(self) -> None:
        self._alert = mock.patch(
            "app.core.services.alert_service.sincronizar_alertas",
        )
        self._alert.start()

    def tearDown(self) -> None:
        self._alert.stop()

    def test_anular_registro_via_contexto_reloj_actor(self) -> None:
        data = AppData(
            productos=[Producto("p1", "Harina", UnidadProducto.KG)],
            lotes=[
                LoteStock("l1", "p1", 20.0, 10.0, 7.0, fecha_compra=date(2026, 7, 1)),
            ],
            desayunos=[
                RegistroDesayuno(
                    id="d01",
                    fecha=date(2026, 7, 20),
                    coste_total=6.0,
                    registrado_por="Ana",
                    lineas_detalle=[
                        LineaDetalleOrigen(
                            origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                            producto_id="p1",
                            cantidad=3.0,
                            coste=6.0,
                            tipo_servicio="desayuno",
                            consumos_lote=[
                                ConsumoLoteDetalle("l1", "p1", 3.0, 6.0),
                            ],
                        ),
                    ],
                ),
            ],
            usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
            usuario_actual_id="u01",
        )
        ctx = _ctx(data)
        r = anul_r.anular_registro(
            None, "d01", anul_r.TIPO_DESAYUNO, "error carga", ctx=ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(data.desayunos[0].anulado)
        self.assertEqual(data.desayunos[0].fecha_anulacion, date(2026, 7, 30))
        self.assertEqual(data.desayunos[0].anulado_por, "Ana")
        self.assertAlmostEqual(data.lotes[0].cantidad_restante, 10.0, places=4)
        self.assertEqual(data.actividades[0].accion, "Anulación registro")

    def test_anular_merma_via_contexto(self) -> None:
        data = AppData(
            productos=[Producto("p1", "Pan", UnidadProducto.UD)],
            lotes=[
                LoteStock("l1", "p1", 5.0, 10.0, 8.0, fecha_compra=date(2026, 7, 1)),
            ],
            mermas=[
                RegistroMerma(
                    id="m01",
                    fecha=date(2026, 7, 20),
                    lineas=[
                        LineaMerma(
                            "p1", 2.0, 1.0, MotivoMerma.EXPIRACION,
                            None, "l1", "general", "manana", "rm01", "Ana",
                            "Pan", "Ud",
                        ),
                    ],
                    coste_total=1.0,
                    registrado_por="Ana",
                ),
            ],
            usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
            usuario_actual_id="u01",
        )
        ctx = _ctx(data)
        r = anul_m.anular_merma(None, "m01", "devolución", ctx=ctx)
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(data.mermas[0].anulado)
        self.assertEqual(data.mermas[0].anulado_por, "Ana")
        self.assertAlmostEqual(data.lotes[0].cantidad_restante, 10.0, places=4)


if __name__ == "__main__":
    unittest.main()
