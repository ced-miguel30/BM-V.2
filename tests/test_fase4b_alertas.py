"""Fase 4B — alertas vía AppContext (reloj, UoW, auditoría).

Ejecutar:

    py -m unittest tests.test_fase4b_alertas -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.actor import Actor
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    EstadoAlerta,
    LoteStock,
    Producto,
    RegistroDesayuno,
    TipoAlerta,
    UnidadProducto,
    Usuario,
)
from app.core.services.alert_service import (
    alertas_operativas_abiertas,
    cambiar_estado_alerta,
    crear_alerta_manual,
    sincronizar_alertas,
)


def _ctx(data: AppData, *, dia: date = date(2026, 7, 30)):
    return build_app_context(
        uow=InMemoryUnitOfWork(data),
        clock=FixedClock(datetime(dia.year, dia.month, dia.day, 10, 0, 0)),
        actor=Actor(id="u01", nombre="Tester", rol="Owner"),
    )


class TestFase4BAlertas(unittest.TestCase):
    def test_sincroniza_stock_bajo_y_expirado(self) -> None:
        data = AppData(
            usuarios=[Usuario("u01", "Tester", "Owner")],
            usuario_actual_id="u01",
            productos=[
                Producto("p01", "Leche", UnidadProducto.L, stock_minimo=20.0),
            ],
            lotes=[
                LoteStock(
                    "l01",
                    "p01",
                    10.0,
                    5.0,
                    5.0,
                    fecha_compra=date(2026, 7, 1),
                    fecha_expiracion=date(2026, 7, 20),
                ),
            ],
            desayunos=[
                RegistroDesayuno("d01", date(2026, 7, 30), coste_total=0.0, registrado_por="Tester"),
            ],
        )
        ctx = _ctx(data)
        out = sincronizar_alertas(ctx)
        tipos = {a.tipo for a in out.alertas}
        self.assertIn(TipoAlerta.STOCK_BAJO, tipos)
        self.assertIn(TipoAlerta.EXPIRADO, tipos)
        self.assertNotIn(TipoAlerta.DESAYUNO_NO_REGISTRADO, tipos)

    def test_manual_y_cierre_idempotente_firma(self) -> None:
        data = AppData(
            usuarios=[Usuario("u01", "Tester", "Owner")],
            usuario_actual_id="u01",
            productos=[Producto("p01", "Pan", UnidadProducto.UD)],
        )
        ctx = _ctx(data)
        r = crear_alerta_manual("Aviso", "Revisar cámara", producto_id="p01", ctx=ctx)
        self.assertTrue(r.ok)
        self.assertEqual(len(data.alertas), 1)
        self.assertEqual(data.actividades[0].accion, "Alerta manual")

        alerta_id = data.alertas[0].id
        r2 = cambiar_estado_alerta(alerta_id, EstadoAlerta.RESUELTA.value, ctx=ctx)
        self.assertTrue(r2.ok)
        self.assertFalse(data.alertas[0].activa)
        self.assertEqual(len(alertas_operativas_abiertas(data)), 0)

    def test_ignorar_auto_añade_descartada(self) -> None:
        data = AppData(
            usuarios=[Usuario("u01", "Tester", "Owner")],
            usuario_actual_id="u01",
            productos=[Producto("p01", "Huevos", UnidadProducto.UD, stock_minimo=10.0)],
            lotes=[
                LoteStock("l01", "p01", 5.0, 2.0, 2.0, fecha_compra=date(2026, 7, 1)),
            ],
            desayunos=[
                RegistroDesayuno("d01", date(2026, 7, 30), coste_total=0.0, registrado_por="Tester"),
            ],
        )
        ctx = _ctx(data)
        sincronizar_alertas(ctx)
        auto = next(a for a in data.alertas if a.tipo == TipoAlerta.STOCK_BAJO)
        cambiar_estado_alerta(auto.id, EstadoAlerta.IGNORADA.value, ctx=ctx)
        self.assertTrue(any("stock_bajo" in f for f in data.alertas_descartadas))
        sincronizar_alertas(ctx)
        tipos = {a.tipo for a in data.alertas}
        self.assertNotIn(TipoAlerta.STOCK_BAJO, tipos)


if __name__ == "__main__":
    unittest.main()
