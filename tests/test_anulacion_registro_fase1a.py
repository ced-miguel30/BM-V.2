"""Fase 1A — caracterización: anulación soft de registros (desayuno/servicio).

Solo prueba `anulacion_registro_service`. No mezcla diagnóstico ni merma/compra.

Ejecutar:

    py -m unittest tests.test_anulacion_registro_fase1a -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    LineaDetalleOrigen,
    LoteStock,
    Producto,
    RegistroDesayuno,
    RegistroServicio,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import OrigenConsumo
from app.core.models.registro_servicio import ConsumoLoteDetalle
from app.core.services import anulacion_registro_service as anul


def _base() -> AppData:
    return AppData(
        productos=[Producto("p1", "Harina", UnidadProducto.KG)],
        lotes=[
            LoteStock(
                "l1", "p1",
                precio_total=20.0,
                cantidad=10.0,
                cantidad_restante=7.0,
                fecha_compra=date(2026, 7, 1),
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


def _desayuno_con_traza() -> RegistroDesayuno:
    return RegistroDesayuno(
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
    )


def _desayuno_sin_traza() -> RegistroDesayuno:
    return RegistroDesayuno(
        id="d_hist",
        fecha=date(2026, 1, 1),
        coste_total=5.0,
        registrado_por="Ana",
        lineas_detalle=[],
    )


class TestAnulacionRegistroFase1A(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _base()
        self._patches = [
            mock.patch(
                "app.core.services.anulacion_registro_service.get_data",
                return_value=self.data,
            ),
            mock.patch("app.core.services.anulacion_registro_service.persist_data"),
            mock.patch("app.core.services.alert_service.sincronizar_alertas"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()

    def test_bloquea_sin_trazabilidad_historica(self) -> None:
        reg = _desayuno_sin_traza()
        self.data.desayunos.append(reg)
        puede = anul.puede_anular_registro(self.data, reg)
        self.assertFalse(puede.ok)
        self.assertTrue(any("trazabilidad" in m.lower() for m in puede.motivos_bloqueo))
        r = anul.anular_desayuno("d_hist", "error")
        self.assertFalse(r.ok)
        self.assertFalse(reg.anulado)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 7.0)

    def test_reponne_exactamente_consumos_lote(self) -> None:
        reg = _desayuno_con_traza()
        self.data.desayunos.append(reg)
        lote = self.data.lotes[0]
        self.assertEqual(lote.cantidad_restante, 7.0)

        r = anul.anular_desayuno("d01", "carga duplicada", "ticket-1")
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(reg.anulado)
        self.assertEqual(reg.motivo_anulacion, "carga duplicada")
        self.assertEqual(reg.referencia_anulacion, "ticket-1")
        self.assertEqual(lote.cantidad_restante, 10.0)
        self.assertEqual(lote.cantidad, 10.0)  # compra intacta

    def test_idempotente_ya_anulado(self) -> None:
        reg = _desayuno_con_traza()
        self.data.desayunos.append(reg)
        self.assertTrue(anul.anular_desayuno("d01", "uno").ok)
        r2 = anul.anular_desayuno("d01", "dos")
        self.assertFalse(r2.ok)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 10.0)

    def test_motivo_obligatorio(self) -> None:
        reg = _desayuno_con_traza()
        self.data.desayunos.append(reg)
        r = anul.anular_desayuno("d01", "   ")
        self.assertFalse(r.ok)
        self.assertFalse(reg.anulado)

    def test_servicio_comida_con_traza(self) -> None:
        reg = RegistroServicio(
            id="co01",
            tipo_servicio="comida",
            fecha=date(2026, 7, 21),
            coste_total=4.0,
            registrado_por="Ana",
            lineas_detalle=[
                LineaDetalleOrigen(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p1",
                    cantidad=2.0,
                    coste=4.0,
                    tipo_servicio="comida",
                    consumos_lote=[ConsumoLoteDetalle("l1", "p1", 2.0, 4.0)],
                ),
            ],
        )
        self.data.registros_servicio.append(reg)
        self.data.lotes[0].cantidad_restante = 5.0
        r = anul.anular_servicio("co01", "equivocación")
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(reg.anulado)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 7.0)


if __name__ == "__main__":
    unittest.main()
