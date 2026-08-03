"""Fase 7A.2 — dual-write espejo: entrada de lote + ajustes ±.

Ejecutar:

    py -m unittest tests.test_fase7a2_dual_write_entrada_ajuste -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.actor import Actor
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    Categoria,
    Departamento,
    DireccionMovimiento,
    LoteStock,
    MotivoAjuste,
    Producto,
    RolUsuario,
    Subcategoria,
    TipoArticulo,
    TipoMovimiento,
    Ubicacion,
    UnidadProducto,
    Usuario,
)
from app.core.services import ajuste_service
from app.core.services import movimiento_service as mov
from app.core.services.diagnostico_service import generar_diagnostico
from app.core.services.inventory_batch_service import descontar_lotes
from app.core.services.stock_service import registrar_lote
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui.theme import APP_VERSION


def _data_base() -> AppData:
    return AppData(
        productos=[
            Producto(
                "p01",
                "Leche",
                UnidadProducto.L,
                categoria_id="cat01",
                subcategoria_id="sub01",
                departamento_ids=["dep01"],
                ubicacion_ids=["ubi01"],
                tipo_articulo=TipoArticulo.CONSUMIBLE,
                categoria_inventario="Lácteos",
            )
        ],
        lotes=[
            # Histórico pre-ledger: sin movimiento asociado.
            LoteStock(
                "l01",
                "p01",
                precio_total=10.0,
                cantidad=5.0,
                cantidad_restante=5.0,
                fecha_compra=date(2026, 1, 1),
            )
        ],
        departamentos=[Departamento("dep01", "Cocina", True)],
        categorias=[Categoria("cat01", "Lácteos", True)],
        subcategorias=[Subcategoria("sub01", "Leches", "cat01", True)],
        ubicaciones=[Ubicacion("ubi01", "Cámara", True)],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


def _ctx(data: AppData):
    return build_app_context(
        uow=InMemoryUnitOfWork(data),
        clock=FixedClock(datetime(2026, 7, 30, 12, 0, 0)),
        actor=Actor(id="u01", nombre="Ana", rol="Admin"),
    )


class TestFase7A2DualWrite(unittest.TestCase):
    def test_01_registrar_lote_crea_entrada_compra(self) -> None:
        data = _data_base()
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            r = registrar_lote(
                "p01",
                precio_total=20.0,
                cantidad=4.0,
                fecha_compra=date(2026, 7, 1),
                marca_proveedor="Proveedor X",
            )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(data.lotes), 2)
        nuevo = data.lotes[-1]
        self.assertEqual(nuevo.cantidad_restante, 4.0)
        movs = mov.buscar_por_lote(data, nuevo.id)
        self.assertEqual(len(movs), 1)
        m = movs[0]
        self.assertEqual(m.tipo, TipoMovimiento.ENTRADA_COMPRA)
        self.assertEqual(m.direccion, DireccionMovimiento.ENTRADA)
        self.assertEqual(m.cantidad, 4.0)
        self.assertEqual(m.origen_tipo, mov.ORIGEN_TIPO_LOTE)
        self.assertEqual(m.origen_id, nuevo.id)
        self.assertEqual(m.coste_total_snapshot, 20.0)
        self.assertAlmostEqual(m.coste_unitario_snapshot or 0, 5.0)

    def test_02_registrar_lote_no_cambia_stock_historico(self) -> None:
        data = _data_base()
        resto_hist = data.lotes[0].cantidad_restante
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            registrar_lote("p01", 8.0, 2.0, fecha_compra=date(2026, 7, 2))
        self.assertEqual(data.lotes[0].cantidad_restante, resto_hist)
        self.assertEqual(mov.buscar_por_lote(data, "l01"), [])

    def test_03_ajuste_positivo_espejo_entrada(self) -> None:
        data = _data_base()
        ctx = _ctx(data)
        r = ajuste_service.aplicar_ajuste(
            date(2026, 7, 22),
            "l01",
            6.5,
            MotivoAjuste.RECONTEO_FISICO.value,
            ctx=ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(data.lotes[0].cantidad_restante, 6.5)
        self.assertEqual(data.lotes[0].cantidad, 5.0)  # compra intacta
        movs = [m for m in data.movimientos if m.tipo == TipoMovimiento.AJUSTE_ENTRADA]
        self.assertEqual(len(movs), 1)
        self.assertEqual(movs[0].direccion, DireccionMovimiento.ENTRADA)
        self.assertEqual(movs[0].cantidad, 1.5)
        self.assertEqual(movs[0].origen_tipo, mov.ORIGEN_TIPO_AJUSTE)
        self.assertEqual(movs[0].origen_id, data.ajustes[0].id)

    def test_04_ajuste_negativo_espejo_salida(self) -> None:
        data = _data_base()
        ctx = _ctx(data)
        r = ajuste_service.aplicar_ajuste(
            date(2026, 7, 22),
            "l01",
            3.0,
            MotivoAjuste.RECONTEO_FISICO.value,
            ctx=ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(data.lotes[0].cantidad_restante, 3.0)
        movs = [m for m in data.movimientos if m.tipo == TipoMovimiento.AJUSTE_SALIDA]
        self.assertEqual(len(movs), 1)
        self.assertEqual(movs[0].direccion, DireccionMovimiento.SALIDA)
        self.assertEqual(movs[0].cantidad, 2.0)

    def test_05_idempotencia_entrada_lote(self) -> None:
        data = _data_base()
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            registrar_lote("p01", 10.0, 2.0, fecha_compra=date(2026, 7, 3))
        lote_id = data.lotes[-1].id
        r2 = mov.espejo_entrada_lote(
            producto_id="p01",
            lote_id=lote_id,
            cantidad=2.0,
            fecha=date(2026, 7, 3),
            precio_total=10.0,
            ctx=_ctx(data),
            commit=False,
        )
        self.assertTrue(r2.duplicado)
        self.assertEqual(
            len(mov.buscar_por_lote(data, lote_id)),
            1,
        )

    def test_06_historico_sin_movimiento_no_es_error_critico(self) -> None:
        data = _data_base()
        resumen = generar_diagnostico(data)
        self.assertEqual(resumen.num_movimientos, 0)
        # Ausencia histórica no debe listarse como error de producto/lote huérfano
        self.assertFalse(
            any("producto inexistente" in i for i in resumen.incidencias_movimientos)
        )

    def test_07_reconciliacion_lote_nuevo_coincide(self) -> None:
        data = AppData(
            productos=[Producto("p01", "Leche", UnidadProducto.L)],
            usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
            usuario_actual_id="u01",
        )
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            registrar_lote("p01", 12.0, 3.0, fecha_compra=date(2026, 7, 4))
        lote = data.lotes[0]
        comp = mov.comparar_ledger_vs_lote(data, lote.id)
        assert comp is not None
        self.assertEqual(comp.saldo_teorico_ledger, lote.cantidad_restante)
        self.assertEqual(comp.diferencia, 0.0)
        self.assertEqual(comp.nota, mov.NOTA_LEDGER_PARCIAL)

    def test_08_fifo_intacta_tras_dual_write(self) -> None:
        data = _data_base()
        data.lotes.append(
            LoteStock(
                "l02",
                "p01",
                precio_total=6.0,
                cantidad=3.0,
                cantidad_restante=3.0,
                fecha_compra=date(2026, 1, 2),
            )
        )
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            registrar_lote("p01", 4.0, 1.0, fecha_compra=date(2026, 7, 5))
        copia = copy.deepcopy(data)
        # Quitar movimientos en copia para aislar FIFO
        copia.movimientos = []
        res_a = descontar_lotes(copia, "p01", 2.0)
        res_b = descontar_lotes(data, "p01", 2.0)
        self.assertEqual(
            [(m.lote_id, m.cantidad) for m in res_a.movimientos],
            [(m.lote_id, m.cantidad) for m in res_b.movimientos],
        )
        self.assertEqual(res_b.movimientos[0].lote_id, "l01")

    def test_09_ajuste_no_crea_consumo_ni_merma(self) -> None:
        data = _data_base()
        ajuste_service.aplicar_ajuste(
            date(2026, 7, 22),
            "l01",
            4.0,
            MotivoAjuste.RECONTEO_FISICO.value,
            ctx=_ctx(data),
        )
        tipos = {_enum(m.tipo) for m in data.movimientos}
        self.assertNotIn(TipoMovimiento.CONSUMO.value, tipos)
        self.assertNotIn(TipoMovimiento.MERMA.value, tipos)

    def test_10_diagnostico_no_modifica(self) -> None:
        data = _data_base()
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            registrar_lote("p01", 5.0, 1.0, fecha_compra=date(2026, 7, 6))
        antes = copy.deepcopy(appdata_to_dict(data))
        generar_diagnostico(data)
        mov.reconciliacion_informativa(data)
        self.assertEqual(antes, appdata_to_dict(data))

    def test_11_campos_6a_6b_6c_intactos(self) -> None:
        data = _data_base()
        with patch("app.core.services.stock_service.get_data", return_value=data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            registrar_lote("p01", 5.0, 1.0, fecha_compra=date(2026, 7, 7))
        back = dict_to_appdata(appdata_to_dict(data))
        p = back.productos[0]
        self.assertEqual(p.categoria_id, "cat01")
        self.assertEqual(p.ubicacion_ids, ["ubi01"])
        self.assertEqual(p.tipo_articulo, TipoArticulo.CONSUMIBLE)

    def test_12_version_7a2(self) -> None:
        self.assertIn("Ledger", APP_VERSION)
        self.assertIn("7A.", APP_VERSION)

    def test_13_ajuste_fallo_espejo_revierte_stock(self) -> None:
        data = _data_base()
        ctx = _ctx(data)
        restante = data.lotes[0].cantidad_restante
        with patch(
            "app.core.services.movimiento_service.espejo_ajuste_linea",
            return_value=mov.ResultadoMovimiento(ok=False, mensaje="forzado"),
        ):
            with self.assertRaises(RuntimeError):
                ajuste_service.aplicar_ajuste(
                    date(2026, 7, 22),
                    "l01",
                    4.0,
                    MotivoAjuste.RECONTEO_FISICO.value,
                    ctx=ctx,
                )
        self.assertEqual(data.lotes[0].cantidad_restante, restante)
        self.assertEqual(data.ajustes, [])
        self.assertEqual(data.movimientos, [])


def _enum(val) -> str:
    return val.value if hasattr(val, "value") else str(val)


if __name__ == "__main__":
    unittest.main()
