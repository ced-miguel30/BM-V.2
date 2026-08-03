"""Fase 1A — caracterización: anulación soft de mermas.

Solo prueba `anulacion_merma_service`. No mezcla diagnóstico ni registro/compra.

Ejecutar:

    py -m unittest tests.test_anulacion_merma_fase1a -v
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
    LineaMerma,
    LoteStock,
    MotivoMerma,
    Producto,
    RegistroMerma,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.services import anulacion_merma_service as anul


def _base() -> AppData:
    return AppData(
        productos=[Producto("p1", "Leche", UnidadProducto.L)],
        lotes=[
            LoteStock(
                "l1", "p1",
                precio_total=10.0,
                cantidad=5.0,
                cantidad_restante=3.0,
                fecha_compra=date(2026, 7, 1),
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestAnulacionMermaFase1A(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _base()
        self._patches = [
            mock.patch(
                "app.core.services.anulacion_merma_service.get_data",
                return_value=self.data,
            ),
            mock.patch("app.core.services.anulacion_merma_service.persist_data"),
            mock.patch("app.core.services.alert_service.sincronizar_alertas"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()

    def test_bloquea_sin_lote_id(self) -> None:
        merma = RegistroMerma(
            id="m01",
            fecha=date(2026, 7, 15),
            coste_total=2.0,
            lineas=[
                LineaMerma("p1", 1.0, 2.0, MotivoMerma.MERMA, lote_id=None),
            ],
        )
        self.data.mermas.append(merma)
        puede = anul.puede_anular_merma(self.data, merma)
        self.assertFalse(puede.ok)
        r = anul.anular_merma(self.data, "m01", "error")
        self.assertFalse(r.ok)
        self.assertFalse(merma.anulado)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 3.0)

    def test_reponne_al_lote_original(self) -> None:
        merma = RegistroMerma(
            id="m02",
            fecha=date(2026, 7, 16),
            coste_total=4.0,
            lineas=[
                LineaMerma(
                    "p1", 2.0, 4.0, MotivoMerma.EXPIRACION,
                    lote_id="l1",
                    tipo_servicio_snapshot="desayuno",
                ),
            ],
        )
        self.data.mermas.append(merma)
        r = anul.anular_merma(self.data, "m02", "caducidad mal registrada")
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(merma.anulado)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 5.0)
        self.assertEqual(self.data.lotes[0].cantidad, 5.0)

    def test_idempotente_ya_anulada(self) -> None:
        merma = RegistroMerma(
            id="m03",
            fecha=date(2026, 7, 17),
            coste_total=1.0,
            lineas=[LineaMerma("p1", 1.0, 1.0, MotivoMerma.MERMA, lote_id="l1")],
        )
        self.data.mermas.append(merma)
        self.assertTrue(anul.anular_merma(self.data, "m03", "uno").ok)
        r2 = anul.anular_merma(self.data, "m03", "dos")
        self.assertFalse(r2.ok)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 4.0)


if __name__ == "__main__":
    unittest.main()
