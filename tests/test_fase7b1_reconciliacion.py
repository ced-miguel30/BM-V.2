"""Fase 7B.1 — reconciliación reforzada y frontera de activación.

Ejecutar:

    py -m unittest tests.test_fase7b1_reconciliacion -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    ConfiguracionHotel,
    DireccionMovimiento,
    LoteStock,
    MovimientoInventario,
    Producto,
    TipoMovimiento,
    UnidadProducto,
)
from app.core.services.ledger_config import (
    asegurar_frontera_activacion,
    frontera_activacion,
)
from app.core.services.ledger_reconciliacion_service import (
    EstadoCoberturaLedger,
    reconciliacion_reforzada,
    reconciliar_lote,
)
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _prod() -> Producto:
    return Producto("p01", "Leche", UnidadProducto.L)


def _lote(
    lid: str = "lot01",
    *,
    cantidad: float = 10.0,
    restante: float = 10.0,
) -> LoteStock:
    return LoteStock(
        lid,
        "p01",
        precio_total=20.0,
        cantidad=cantidad,
        cantidad_restante=restante,
        fecha_compra=date(2025, 1, 1),
    )


class TestFase7B1Reconciliacion(unittest.TestCase):
    def test_01_historico_sin_ledger(self) -> None:
        data = AppData(productos=[_prod()], lotes=[_lote(restante=7.0)])
        data.configuracion = ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-01-01T00:00:00",
        )
        r = reconciliar_lote(data, "lot01")
        assert r is not None
        self.assertEqual(r.cobertura, EstadoCoberturaLedger.HISTORICO_SIN_LEDGER)
        self.assertAlmostEqual(r.diferencia, -7.0)

    def test_02_cobertura_completa(self) -> None:
        data = AppData(productos=[_prod()], lotes=[_lote(cantidad=10, restante=6)])
        data.configuracion = ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-01-01T00:00:00",
        )
        data.movimientos = [
            MovimientoInventario(
                "m1",
                "p01",
                "lot01",
                TipoMovimiento.ENTRADA_COMPRA,
                DireccionMovimiento.ENTRADA,
                10.0,
                date(2026, 2, 1),
                None,
                "lote",
                "lot01",
                creado_en=datetime(2026, 2, 1, 10, 0, 0),
            ),
            MovimientoInventario(
                "m2",
                "p01",
                "lot01",
                TipoMovimiento.CONSUMO,
                DireccionMovimiento.SALIDA,
                4.0,
                date(2026, 2, 2),
                None,
                "desayuno",
                "d01",
                creado_en=datetime(2026, 2, 2, 10, 0, 0),
            ),
        ]
        r = reconciliar_lote(data, "lot01")
        assert r is not None
        self.assertEqual(r.cobertura, EstadoCoberturaLedger.COBERTURA_COMPLETA)
        self.assertAlmostEqual(r.diferencia, 0.0, places=4)

    def test_03_cobertura_parcial(self) -> None:
        data = AppData(productos=[_prod()], lotes=[_lote(cantidad=10, restante=5)])
        data.configuracion = ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-06-01T00:00:00",
        )
        # Solo un consumo post-parcial: entradas no cubren original; saldo no cuadra
        # sin movimientos post → parcial (no inconsistencia post).
        data.movimientos = [
            MovimientoInventario(
                "m1",
                "p01",
                "lot01",
                TipoMovimiento.CONSUMO,
                DireccionMovimiento.SALIDA,
                2.0,
                date(2026, 3, 1),
                None,
                "desayuno",
                "d01",
                creado_en=datetime(2026, 3, 1, 10, 0, 0),  # antes de frontera
            ),
        ]
        r = reconciliar_lote(data, "lot01")
        assert r is not None
        self.assertEqual(r.cobertura, EstadoCoberturaLedger.COBERTURA_PARCIAL)

    def test_04_inconsistencia_posterior(self) -> None:
        data = AppData(productos=[_prod()], lotes=[_lote(cantidad=10, restante=10)])
        data.configuracion = ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-01-01T00:00:00",
        )
        data.movimientos = [
            MovimientoInventario(
                "m1",
                "p01",
                "lot01",
                TipoMovimiento.ENTRADA_COMPRA,
                DireccionMovimiento.ENTRADA,
                10.0,
                date(2026, 2, 1),
                None,
                "lote",
                "lot01",
                creado_en=datetime(2026, 2, 1, 10, 0, 0),
            ),
            MovimientoInventario(
                "m2",
                "p01",
                "lot01",
                TipoMovimiento.CONSUMO,
                DireccionMovimiento.SALIDA,
                3.0,
                date(2026, 2, 2),
                None,
                "desayuno",
                "d01",
                creado_en=datetime(2026, 2, 2, 10, 0, 0),
            ),
        ]
        # restante sigue en 10 pero ledger dice 7 → inconsistencia post
        r = reconciliar_lote(data, "lot01")
        assert r is not None
        self.assertEqual(
            r.cobertura, EstadoCoberturaLedger.INCONSISTENCIA_POSTERIOR_ACTIVACION
        )

    def test_05_no_modifica_datos(self) -> None:
        data = AppData(productos=[_prod()], lotes=[_lote(restante=4.0)])
        data.configuracion = ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-01-01T00:00:00",
        )
        antes = copy.deepcopy(appdata_to_dict(data))
        reconciliacion_reforzada(data, fijar_frontera_si_falta=False)
        self.assertEqual(appdata_to_dict(data), antes)

    def test_06_frontera_persistida_no_reinfiere(self) -> None:
        data = AppData(productos=[_prod()], lotes=[_lote()])
        data.configuracion = ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-01-15T12:00:00",
        )
        data.movimientos = [
            MovimientoInventario(
                "m1",
                "p01",
                "lot01",
                TipoMovimiento.ENTRADA_COMPRA,
                DireccionMovimiento.ENTRADA,
                10.0,
                date(2026, 3, 1),
                None,
                "lote",
                "lot01",
                creado_en=datetime(2020, 1, 1, 0, 0, 0),
            ),
        ]
        f1, _ = asegurar_frontera_activacion(data)
        f2, _ = asegurar_frontera_activacion(data)
        self.assertEqual(f1, datetime(2026, 1, 15, 12, 0, 0))
        self.assertEqual(f2, f1)
        self.assertEqual(
            data.configuracion.ledger_activation_iso, "2026-01-15T12:00:00"
        )

    def test_07_frontera_derivada_una_vez_desde_movimientos(self) -> None:
        data = AppData(
            productos=[_prod()],
            lotes=[_lote()],
            configuracion=ConfiguracionHotel("H", "EUR"),
        )
        data.movimientos = [
            MovimientoInventario(
                "m1",
                "p01",
                "lot01",
                TipoMovimiento.ENTRADA_COMPRA,
                DireccionMovimiento.ENTRADA,
                10.0,
                date(2026, 4, 1),
                None,
                "lote",
                "lot01",
                creado_en=datetime(2026, 4, 1, 8, 30, 0),
            ),
        ]
        f, fuente = asegurar_frontera_activacion(data)
        self.assertEqual(f, datetime(2026, 4, 1, 8, 30, 0))
        self.assertIn("derived", fuente)
        iso = data.configuracion.ledger_activation_iso
        # segunda llamada no cambia
        asegurar_frontera_activacion(data)
        self.assertEqual(data.configuracion.ledger_activation_iso, iso)

    def test_08_roundtrip_config_ledger(self) -> None:
        data = AppData(
            configuracion=ConfiguracionHotel(
                "Hotel X",
                "EUR",
                ledger_activation_iso="2026-05-01T00:00:00",
                ledger_balance_mode="shadow",
                ledger_schema_version=7,
            )
        )
        back = dict_to_appdata(appdata_to_dict(data))
        assert back.configuracion is not None
        self.assertEqual(
            back.configuracion.ledger_activation_iso, "2026-05-01T00:00:00"
        )
        self.assertEqual(back.configuracion.ledger_balance_mode, "shadow")

    def test_09_json_antiguo_sin_campos_ledger(self) -> None:
        payload = {
            "configuracion": {
                "nombre_establecimiento": "Viejo",
                "moneda": "EUR",
                "simbolo_moneda": "€",
                "logo_path": None,
            }
        }
        data = dict_to_appdata(payload)
        assert data.configuracion is not None
        self.assertIsNone(data.configuracion.ledger_activation_iso)
        self.assertEqual(data.configuracion.ledger_balance_mode, "shadow")

    def test_10_sin_movimientos_vacio(self) -> None:
        data = AppData(
            productos=[_prod()],
            lotes=[_lote(cantidad=0.0, restante=0.0)],
            configuracion=ConfiguracionHotel(
                "H", "EUR", ledger_activation_iso="2026-01-01T00:00:00"
            ),
        )
        r = reconciliar_lote(data, "lot01")
        assert r is not None
        self.assertEqual(r.cobertura, EstadoCoberturaLedger.SIN_MOVIMIENTOS)


if __name__ == "__main__":
    unittest.main()
