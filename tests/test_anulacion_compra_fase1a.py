"""Fase 1A — caracterización: anulación restringida de compras/lotes.

Solo prueba `anulacion_compra_service`. No mezcla diagnóstico ni registro/merma.

Ejecutar:

    py -m unittest tests.test_anulacion_compra_fase1a -v
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
    LineaAjuste,
    LineaDetalleOrigen,
    LoteStock,
    MotivoAjuste,
    Producto,
    RegistroAjuste,
    RegistroDesayuno,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import OrigenConsumo
from app.core.models.registro_servicio import ConsumoLoteDetalle
from app.core.services import anulacion_compra_service as anul


def _base(*, restante: float = 10.0) -> AppData:
    return AppData(
        productos=[Producto("p1", "Azúcar", UnidadProducto.KG)],
        lotes=[
            LoteStock(
                "l1", "p1",
                precio_total=15.0,
                cantidad=10.0,
                cantidad_restante=restante,
                fecha_compra=date(2026, 7, 1),
                marca_proveedor="Dulce SA",
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestAnulacionCompraFase1A(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _base()
        self._patches = [
            mock.patch(
                "app.core.services.anulacion_compra_service.get_data",
                return_value=self.data,
            ),
            mock.patch("app.core.services.anulacion_compra_service.persist_data"),
            mock.patch("app.core.services.alert_service.sincronizar_alertas"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()

    def test_anula_lote_intacto(self) -> None:
        lote = self.data.lotes[0]
        r = anul.anular_compra(self.data, "l1", "compra duplicada")
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(lote.anulado)
        self.assertEqual(lote.cantidad_restante, 0.0)
        self.assertEqual(lote.cantidad, 10.0)
        self.assertEqual(lote.precio_total, 15.0)
        self.assertEqual(lote.marca_proveedor, "Dulce SA")

    def test_bloquea_lote_consumido(self) -> None:
        self.data = _base(restante=6.0)
        self._patches[0].stop()
        self._patches[0] = mock.patch(
            "app.core.services.anulacion_compra_service.get_data",
            return_value=self.data,
        )
        self._patches[0].start()

        lote = self.data.lotes[0]
        puede = anul.puede_anular_compra(self.data, lote)
        self.assertFalse(puede.ok)
        r = anul.anular_compra(self.data, "l1", "intento")
        self.assertFalse(r.ok)
        self.assertFalse(lote.anulado)
        self.assertEqual(lote.cantidad_restante, 6.0)

    def test_bloquea_si_desayuno_activo_referencia_lote(self) -> None:
        self.data.desayunos.append(
            RegistroDesayuno(
                id="d01",
                fecha=date(2026, 7, 20),
                coste_total=2.0,
                lineas_detalle=[
                    LineaDetalleOrigen(
                        origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                        producto_id="p1",
                        cantidad=1.0,
                        coste=2.0,
                        consumos_lote=[ConsumoLoteDetalle("l1", "p1", 1.0, 2.0)],
                    ),
                ],
            )
        )
        # Restante == cantidad, pero hay dependencia activa
        self.data.lotes[0].cantidad_restante = 10.0
        puede = anul.puede_anular_compra(self.data, self.data.lotes[0])
        self.assertFalse(puede.ok)
        self.assertTrue(any("desayuno" in m.lower() for m in puede.motivos_bloqueo))

    def test_bloquea_si_ajuste_referencia_lote(self) -> None:
        self.data.ajustes.append(
            RegistroAjuste(
                id="aj01",
                fecha=date(2026, 7, 18),
                lineas=[
                    LineaAjuste(
                        producto_id="p1",
                        lote_id="l1",
                        cantidad_antes=10.0,
                        cantidad_despues=10.0,
                        motivo=MotivoAjuste.RECONTEO_FISICO,
                    ),
                ],
            )
        )
        puede = anul.puede_anular_compra(self.data, self.data.lotes[0])
        self.assertFalse(puede.ok)
        self.assertTrue(any("ajuste" in m.lower() for m in puede.motivos_bloqueo))


if __name__ == "__main__":
    unittest.main()
