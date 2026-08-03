"""Fase 7B.3 — stock por ubicación derivado del ledger.

Ejecutar:

    py -m unittest tests.test_fase7b3_ubicaciones -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    ConfiguracionHotel,
    DireccionMovimiento,
    LoteStock,
    MovimientoInventario,
    Producto,
    TipoMovimiento,
    Ubicacion,
    UnidadProducto,
)
from app.core.services import movimiento_service as mov
from app.core.services.ubicacion_stock_service import (
    SIN_UBICACION_HISTORICA,
    CoberturaUbicacion,
    saldo_en_ubicacion,
    saldos_por_ubicacion_lote,
)
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _data() -> AppData:
    return AppData(
        productos=[
            Producto(
                "p01",
                "Leche",
                UnidadProducto.L,
                ubicacion_ids=["ubi01", "ubi02"],
            )
        ],
        lotes=[
            LoteStock(
                "lot01",
                "p01",
                20.0,
                10.0,
                10.0,
                fecha_compra=date(2026, 1, 1),
            )
        ],
        ubicaciones=[
            Ubicacion("ubi01", "Cámara", True),
            Ubicacion("ubi02", "Barra", True),
        ],
        configuracion=ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-01-01T00:00:00",
            ledger_balance_mode="shadow",
        ),
    )


class TestFase7B3Ubicaciones(unittest.TestCase):
    def test_01_entrada_localizada(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        r = mov.espejo_entrada_lote(
            producto_id="p01",
            lote_id="lot01",
            cantidad=10.0,
            fecha=date(2026, 1, 1),
            precio_total=20.0,
            ubicacion_destino_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        self.assertTrue(r.ok)
        self.assertEqual(r.movimiento.ubicacion_destino_id, "ubi01")
        self.assertAlmostEqual(saldo_en_ubicacion(data, "lot01", "ubi01"), 10.0)
        info = saldos_por_ubicacion_lote(data, "lot01")
        self.assertEqual(info.cobertura, CoberturaUbicacion.COBERTURA_COMPLETA)
        self.assertTrue(info.suma_cuadra_con_ledger)

    def test_02_consumo_y_merma_localizados(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        mov.espejo_entrada_lote(
            producto_id="p01",
            lote_id="lot01",
            cantidad=10.0,
            fecha=date(2026, 1, 1),
            ubicacion_destino_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        mov.espejo_consumo_fragmento(
            producto_id="p01",
            lote_id="lot01",
            cantidad=2.0,
            fecha=date(2026, 1, 2),
            origen_tipo="desayuno",
            registro_id="d01",
            det_idx=0,
            frag_idx=0,
            ubicacion_origen_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        mov.espejo_merma_linea(
            producto_id="p01",
            lote_id="lot01",
            cantidad=1.0,
            fecha=date(2026, 1, 3),
            merma_id="me01",
            indice_linea=0,
            ubicacion_origen_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        self.assertAlmostEqual(saldo_en_ubicacion(data, "lot01", "ubi01"), 7.0)
        info = saldos_por_ubicacion_lote(data, "lot01")
        self.assertTrue(info.suma_cuadra_con_ledger)

    def test_03_ajuste_y_reversion(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        mov.espejo_entrada_lote(
            producto_id="p01",
            lote_id="lot01",
            cantidad=10.0,
            fecha=date(2026, 1, 1),
            ubicacion_destino_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        mov.espejo_ajuste_linea(
            producto_id="p01",
            lote_id="lot01",
            delta=-1.5,
            fecha=date(2026, 1, 2),
            ajuste_id="aj01",
            ubicacion_origen_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        self.assertAlmostEqual(saldo_en_ubicacion(data, "lot01", "ubi01"), 8.5)
        mov.espejo_ajuste_linea(
            producto_id="p01",
            lote_id="lot01",
            delta=1.5,
            fecha=date(2026, 1, 3),
            ajuste_id="aj02",
            ubicacion_destino_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        self.assertAlmostEqual(saldo_en_ubicacion(data, "lot01", "ubi01"), 10.0)

    def test_04_historico_sin_ubicacion(self) -> None:
        data = _data()
        data.movimientos.append(
            MovimientoInventario(
                "m1",
                "p01",
                "lot01",
                TipoMovimiento.ENTRADA_COMPRA,
                DireccionMovimiento.ENTRADA,
                10.0,
                date(2025, 1, 1),
                None,
                "lote",
                "lot01",
                creado_en=datetime(2025, 1, 1),
            )
        )
        info = saldos_por_ubicacion_lote(data, "lot01")
        self.assertEqual(
            info.cobertura, CoberturaUbicacion.SIN_UBICACION_HISTORICA
        )
        self.assertIn(SIN_UBICACION_HISTORICA, info.por_ubicacion)
        # No se inventa ubi de catálogo
        self.assertNotIn("ubi01", info.por_ubicacion)

    def test_05_suma_ubicaciones_igual_ledger(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        mov.espejo_entrada_lote(
            producto_id="p01",
            lote_id="lot01",
            cantidad=10.0,
            fecha=date(2026, 1, 1),
            ubicacion_destino_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        # Traslado se probará en 7B.4; aquí consumo parcial
        mov.espejo_consumo_fragmento(
            producto_id="p01",
            lote_id="lot01",
            cantidad=3.0,
            fecha=date(2026, 1, 2),
            origen_tipo="desayuno",
            registro_id="d01",
            det_idx=0,
            frag_idx=0,
            ubicacion_origen_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        info = saldos_por_ubicacion_lote(data, "lot01")
        self.assertAlmostEqual(info.saldo_total_ubicaciones, info.saldo_ledger_lote)
        self.assertTrue(info.suma_cuadra_con_ledger)

    def test_06_roundtrip_campos_ubicacion(self) -> None:
        data = _data()
        data.movimientos.append(
            MovimientoInventario(
                "m1",
                "p01",
                "lot01",
                TipoMovimiento.ENTRADA_COMPRA,
                DireccionMovimiento.ENTRADA,
                10.0,
                date(2026, 1, 1),
                None,
                "lote",
                "lot01",
                ubicacion_destino_id="ubi01",
            )
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.movimientos[0].ubicacion_destino_id, "ubi01")
        self.assertIsNone(back.movimientos[0].ubicacion_origen_id)

    def test_07_json_antiguo_sin_ubicacion_en_movimiento(self) -> None:
        payload = {
            "movimientos": [
                {
                    "id": "m1",
                    "producto_id": "p01",
                    "lote_id": "lot01",
                    "tipo": "entrada_compra",
                    "direccion": "entrada",
                    "cantidad": 1,
                    "fecha": "2026-01-01",
                    "origen_tipo": "lote",
                    "origen_id": "lot01",
                }
            ]
        }
        data = dict_to_appdata(payload)
        self.assertIsNone(data.movimientos[0].ubicacion_origen_id)
        self.assertIsNone(data.movimientos[0].ubicacion_destino_id)

    def test_08_entrada_no_cambia_stock_total_por_asignar_ubi(self) -> None:
        data = _data()
        antes = data.lotes[0].cantidad_restante
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        mov.espejo_entrada_lote(
            producto_id="p01",
            lote_id="lot01",
            cantidad=10.0,
            fecha=date(2026, 1, 1),
            ubicacion_destino_id="ubi01",
            ctx=ctx,
            commit=False,
        )
        self.assertEqual(data.lotes[0].cantidad_restante, antes)


if __name__ == "__main__":
    unittest.main()
