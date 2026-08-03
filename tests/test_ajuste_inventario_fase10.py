"""Ajustes de inventario (Fase 10 + 4C AppContext).

Trazabilidad mínima, compras intactas, atomicidad; operaciones vía contexto.
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
    LoteStock,
    MotivoAjuste,
    Producto,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.services import ajuste_service
from app.core.services.diagnostico_service import generar_diagnostico
from app.core.services.inventory_batch_service import snapshot_cantidades_restantes
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _datos() -> AppData:
    return AppData(
        productos=[Producto("p1", "Harina", UnidadProducto.KG)],
        lotes=[
            LoteStock(
                "l1", "p1",
                precio_total=20.0,
                cantidad=10.0,
                cantidad_restante=7.5,
                fecha_compra=date(2026, 7, 1),
                marca_proveedor="Molino SA",
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


def _ctx(data: AppData):
    return build_app_context(
        uow=InMemoryUnitOfWork(data),
        clock=FixedClock(datetime(2026, 7, 30, 12, 0, 0)),
        actor=Actor(id="u01", nombre="Ana", rol="Admin"),
    )


class TestAjusteInventario(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos()
        self.ctx = _ctx(self.data)

    def test_aplica_y_deja_compra_intacta(self) -> None:
        lote = self.data.lotes[0]
        r = ajuste_service.aplicar_ajuste(
            date(2026, 7, 22),
            "l1",
            6.0,
            MotivoAjuste.RECONTEO_FISICO.value,
            "cámara",
            ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(lote.cantidad_restante, 6.0)
        self.assertEqual(lote.cantidad, 10.0)
        self.assertEqual(lote.precio_total, 20.0)
        self.assertEqual(lote.fecha_compra, date(2026, 7, 1))
        self.assertEqual(lote.marca_proveedor, "Molino SA")
        self.assertEqual(len(self.data.ajustes), 1)
        ln = self.data.ajustes[0].lineas[0]
        self.assertEqual(ln.cantidad_antes, 7.5)
        self.assertEqual(ln.cantidad_despues, 6.0)
        self.assertEqual(ln.motivo, MotivoAjuste.RECONTEO_FISICO)
        self.assertEqual(self.data.ajustes[0].registrado_por, "Ana")
        self.assertTrue(self.data.actividades)
        self.assertEqual(self.data.actividades[0].accion, "Ajuste inventario")

    def test_misma_cantidad_bloquea(self) -> None:
        snap = snapshot_cantidades_restantes(self.data)
        r = ajuste_service.aplicar_ajuste(
            date(2026, 7, 22), "l1", 7.5, MotivoAjuste.ERROR_REGISTRO.value,
            ctx=self.ctx,
        )
        self.assertFalse(r.ok)
        self.assertEqual(snapshot_cantidades_restantes(self.data), snap)
        self.assertEqual(len(self.data.ajustes), 0)

    def test_negativo_bloqueado(self) -> None:
        snap = snapshot_cantidades_restantes(self.data)
        r = ajuste_service.aplicar_ajuste(
            date(2026, 7, 22), "l1", -1.0, MotivoAjuste.OTRO.value,
            ctx=self.ctx,
        )
        self.assertFalse(r.ok)
        self.assertEqual(snapshot_cantidades_restantes(self.data), snap)

    def test_fecha_futura_bloqueada(self) -> None:
        r = ajuste_service.aplicar_ajuste(
            date(2026, 8, 1), "l1", 6.0, MotivoAjuste.OTRO.value, ctx=self.ctx,
        )
        self.assertFalse(r.ok)
        self.assertIn("futur", r.mensaje.lower())

    def test_json_antiguo_sin_ajustes(self) -> None:
        payload = {
            "productos": [],
            "lotes": [],
            "recetas": [],
            "desayunos": [],
            "mermas": [],
            "alertas": [],
            "usuarios": [],
            "actividades": [],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(data.ajustes, [])

    def test_roundtrip_ajuste(self) -> None:
        self.assertTrue(
            ajuste_service.aplicar_ajuste(
                date(2026, 7, 22),
                "l1",
                8.0,
                MotivoAjuste.ERROR_REGISTRO.value,
                ctx=self.ctx,
            ).ok
        )
        restored = dict_to_appdata(appdata_to_dict(self.data))
        self.assertEqual(len(restored.ajustes), 1)
        self.assertEqual(restored.ajustes[0].lineas[0].cantidad_despues, 8.0)
        self.assertEqual(restored.lotes[0].precio_total, 20.0)
        self.assertEqual(restored.lotes[0].cantidad, 10.0)

    def test_diagnostico_cuenta_ajustes(self) -> None:
        self.assertTrue(
            ajuste_service.aplicar_ajuste(
                date(2026, 7, 22),
                "l1",
                5.0,
                MotivoAjuste.RECONTEO_FISICO.value,
                ctx=self.ctx,
            ).ok
        )
        resumen = generar_diagnostico(self.data)
        self.assertEqual(resumen.num_ajustes, 1)
        self.assertEqual(resumen.num_lineas_ajuste, 1)

    def test_lotes_ajustables_via_contexto(self) -> None:
        items = ajuste_service.lotes_ajustables(ctx=self.ctx)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "l1")


if __name__ == "__main__":
    unittest.main()
