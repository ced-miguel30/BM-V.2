"""Fase 7A.1 — ledger de movimientos (modelo, persistencia, servicio espejo).

Ejecutar:

    py -m unittest tests.test_fase7a1_ledger_modelo -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import date, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application import espacios as esp
from app.core.application.context import AppContext, build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    Categoria,
    Departamento,
    DireccionMovimiento,
    LoteStock,
    MovimientoInventario,
    Producto,
    Subcategoria,
    TipoArticulo,
    TipoMovimiento,
    Ubicacion,
    UnidadProducto,
)
from app.core.services import movimiento_service as mov
from app.core.services.diagnostico_service import generar_diagnostico
from app.core.services.inventory_batch_service import descontar_lotes
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui.theme import APP_VERSION


def _base_data() -> AppData:
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
            LoteStock(
                "lot01",
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
    )


def _ctx(data: AppData) -> AppContext:
    return build_app_context(uow=InMemoryUnitOfWork(data))


class TestFase7A1LedgerModelo(unittest.TestCase):
    def test_01_json_antiguo_sin_movimientos(self) -> None:
        payload = {
            "meta": {},
            "productos": [{"id": "p1", "nombre": "Pan", "unidad": "Ud"}],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(data.movimientos, [])

    def test_02_roundtrip_lista_vacia(self) -> None:
        data = AppData()
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(back.movimientos, [])
        self.assertIn("movimientos", appdata_to_dict(data))

    def test_03_roundtrip_entrada(self) -> None:
        data = _base_data()
        data.movimientos.append(
            MovimientoInventario(
                id="mov01",
                producto_id="p01",
                lote_id="lot01",
                tipo=TipoMovimiento.ENTRADA_COMPRA,
                direccion=DireccionMovimiento.ENTRADA,
                cantidad=5.0,
                fecha=date(2026, 1, 1),
                hora=time(9, 0),
                origen_tipo="compra",
                origen_id="lot01",
                idempotency_key="compra:lot01::lot01:entrada_compra",
                coste_unitario_snapshot=2.0,
                coste_total_snapshot=10.0,
            )
        )
        back = dict_to_appdata(appdata_to_dict(data))
        m = back.movimientos[0]
        self.assertEqual(m.tipo, TipoMovimiento.ENTRADA_COMPRA)
        self.assertEqual(m.direccion, DireccionMovimiento.ENTRADA)
        self.assertEqual(m.cantidad, 5.0)
        self.assertEqual(m.hora, time(9, 0))
        self.assertEqual(m.coste_total_snapshot, 10.0)

    def test_04_roundtrip_salida(self) -> None:
        data = _base_data()
        data.movimientos.append(
            MovimientoInventario(
                id="mov01",
                producto_id="p01",
                lote_id="lot01",
                tipo=TipoMovimiento.CONSUMO,
                direccion=DireccionMovimiento.SALIDA,
                cantidad=1.5,
                fecha=date(2026, 1, 2),
                hora=None,
                origen_tipo="registro_servicio",
                origen_id="reg01",
                origen_linea_id="det01",
            )
        )
        back = dict_to_appdata(appdata_to_dict(data))
        m = back.movimientos[0]
        self.assertEqual(m.tipo, TipoMovimiento.CONSUMO)
        self.assertEqual(m.direccion, DireccionMovimiento.SALIDA)
        self.assertIsNone(m.hora)
        self.assertEqual(m.origen_linea_id, "det01")

    def test_05_cantidad_cero_rechazada(self) -> None:
        data = _base_data()
        err = mov.validar_movimiento(
            data,
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=0,
            origen_tipo="test",
            origen_id="t1",
        )
        self.assertTrue(any("mayor que cero" in e for e in err))

    def test_06_cantidad_negativa_rechazada(self) -> None:
        data = _base_data()
        err = mov.validar_movimiento(
            data,
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=-1,
            origen_tipo="test",
            origen_id="t1",
        )
        self.assertTrue(any("mayor que cero" in e for e in err))

    def test_07_producto_inexistente(self) -> None:
        data = _base_data()
        err = mov.validar_movimiento(
            data,
            producto_id="px",
            lote_id="lot01",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=1,
            origen_tipo="test",
            origen_id="t1",
        )
        self.assertTrue(any("producto inexistente" in e for e in err))

    def test_08_lote_inexistente(self) -> None:
        data = _base_data()
        err = mov.validar_movimiento(
            data,
            producto_id="p01",
            lote_id="lx",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=1,
            origen_tipo="test",
            origen_id="t1",
        )
        self.assertTrue(any("lote inexistente" in e for e in err))

    def test_09_lote_otro_producto(self) -> None:
        data = _base_data()
        data.productos.append(Producto("p02", "Pan", UnidadProducto.UD))
        err = mov.validar_movimiento(
            data,
            producto_id="p02",
            lote_id="lot01",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=1,
            origen_tipo="test",
            origen_id="t1",
        )
        self.assertTrue(any("pertenece a producto" in e for e in err))

    def _assert_dir(
        self, tipo: TipoMovimiento, direccion: DireccionMovimiento, ok: bool
    ) -> None:
        data = _base_data()
        err = mov.validar_movimiento(
            data,
            producto_id="p01",
            lote_id="lot01",
            tipo=tipo,
            direccion=direccion,
            cantidad=1,
            origen_tipo="test",
            origen_id="t1",
        )
        tiene = any("exige dirección" in e for e in err)
        if ok:
            self.assertFalse(tiene, err)
        else:
            self.assertTrue(tiene, err)

    def test_10_entrada_compra_exige_entrada(self) -> None:
        self._assert_dir(
            TipoMovimiento.ENTRADA_COMPRA, DireccionMovimiento.ENTRADA, True
        )
        self._assert_dir(
            TipoMovimiento.ENTRADA_COMPRA, DireccionMovimiento.SALIDA, False
        )

    def test_11_consumo_exige_salida(self) -> None:
        self._assert_dir(TipoMovimiento.CONSUMO, DireccionMovimiento.SALIDA, True)
        self._assert_dir(TipoMovimiento.CONSUMO, DireccionMovimiento.ENTRADA, False)

    def test_12_merma_exige_salida(self) -> None:
        self._assert_dir(TipoMovimiento.MERMA, DireccionMovimiento.SALIDA, True)
        self._assert_dir(TipoMovimiento.MERMA, DireccionMovimiento.ENTRADA, False)

    def test_13_ajuste_entrada_exige_entrada(self) -> None:
        self._assert_dir(
            TipoMovimiento.AJUSTE_ENTRADA, DireccionMovimiento.ENTRADA, True
        )
        self._assert_dir(
            TipoMovimiento.AJUSTE_ENTRADA, DireccionMovimiento.SALIDA, False
        )

    def test_14_ajuste_salida_exige_salida(self) -> None:
        self._assert_dir(
            TipoMovimiento.AJUSTE_SALIDA, DireccionMovimiento.SALIDA, True
        )
        self._assert_dir(
            TipoMovimiento.AJUSTE_SALIDA, DireccionMovimiento.ENTRADA, False
        )

    def test_15_reversion_consumo_exige_entrada(self) -> None:
        self._assert_dir(
            TipoMovimiento.REVERSION_CONSUMO, DireccionMovimiento.ENTRADA, True
        )
        self._assert_dir(
            TipoMovimiento.REVERSION_CONSUMO, DireccionMovimiento.SALIDA, False
        )

    def test_16_reversion_entrada_exige_salida(self) -> None:
        self._assert_dir(
            TipoMovimiento.REVERSION_ENTRADA, DireccionMovimiento.SALIDA, True
        )
        self._assert_dir(
            TipoMovimiento.REVERSION_ENTRADA, DireccionMovimiento.ENTRADA, False
        )

    def test_17_origen_vacio_rechazado(self) -> None:
        data = _base_data()
        err = mov.validar_movimiento(
            data,
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=1,
            origen_tipo="",
            origen_id="",
        )
        self.assertTrue(any("origen_tipo" in e for e in err))
        self.assertTrue(any("origen_id" in e for e in err))

    def test_18_id_duplicado_detectado(self) -> None:
        data = _base_data()
        data.movimientos.append(
            MovimientoInventario(
                id="mov01",
                producto_id="p01",
                lote_id="lot01",
                tipo=TipoMovimiento.CONSUMO,
                direccion=DireccionMovimiento.SALIDA,
                cantidad=1,
                fecha=date.today(),
                hora=None,
                origen_tipo="test",
                origen_id="a",
            )
        )
        resumen = generar_diagnostico(data)
        # Crear segundo con mismo id vía append y diagnosticar
        data.movimientos.append(
            MovimientoInventario(
                id="mov01",
                producto_id="p01",
                lote_id="lot01",
                tipo=TipoMovimiento.MERMA,
                direccion=DireccionMovimiento.SALIDA,
                cantidad=1,
                fecha=date.today(),
                hora=None,
                origen_tipo="test",
                origen_id="b",
            )
        )
        resumen = generar_diagnostico(data)
        self.assertTrue(
            any("id duplicado" in i for i in resumen.incidencias_movimientos)
        )

    def test_19_idempotency_key_duplicada(self) -> None:
        data = _base_data()
        r1 = mov.crear_movimiento(
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=1,
            fecha=date.today(),
            origen_tipo="registro_servicio",
            origen_id="reg001",
            origen_linea_id="detalle003",
            ctx=_ctx(data),
            commit=True,
        )
        self.assertTrue(r1.ok)
        r2 = mov.crear_movimiento(
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=1,
            fecha=date.today(),
            origen_tipo="registro_servicio",
            origen_id="reg001",
            origen_linea_id="detalle003",
            ctx=_ctx(data),
            commit=True,
        )
        self.assertFalse(r2.ok)
        self.assertTrue(r2.duplicado)
        self.assertEqual(r2.movimiento.id, r1.movimiento.id)

    def test_20_idempotency_key_estable(self) -> None:
        k1 = mov.construir_idempotency_key(
            "registro_servicio",
            "reg001",
            "detalle003",
            "lot004",
            TipoMovimiento.CONSUMO,
        )
        k2 = mov.construir_idempotency_key(
            "registro_servicio",
            "reg001",
            "detalle003",
            "lot004",
            "consumo",
        )
        self.assertEqual(k1, "registro_servicio:reg001:detalle003:lot004:consumo")
        self.assertEqual(k1, k2)

    def test_21_busqueda_por_producto(self) -> None:
        data = _base_data()
        mov.crear_movimiento(
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=1,
            fecha=date.today(),
            origen_tipo="test",
            origen_id="t1",
            ctx=_ctx(data),
        )
        self.assertEqual(len(mov.buscar_por_producto(data, "p01")), 1)
        self.assertEqual(mov.buscar_por_producto(data, "p99"), [])

    def test_22_busqueda_por_lote(self) -> None:
        data = _base_data()
        mov.crear_movimiento(
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.MERMA,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=0.5,
            fecha=date.today(),
            origen_tipo="merma",
            origen_id="m1",
            ctx=_ctx(data),
        )
        self.assertEqual(len(mov.buscar_por_lote(data, "lot01")), 1)

    def test_23_busqueda_por_origen(self) -> None:
        data = _base_data()
        mov.crear_movimiento(
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.AJUSTE_SALIDA,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=0.2,
            fecha=date.today(),
            origen_tipo="ajuste",
            origen_id="aj1",
            origen_linea_id="ln1",
            ctx=_ctx(data),
        )
        hallados = mov.buscar_por_origen(data, "ajuste", "aj1", "ln1")
        self.assertEqual(len(hallados), 1)

    def test_24_sin_edicion_ni_borrado_publico(self) -> None:
        publicos = set(mov.__all__)
        prohibidos = {
            "editar_movimiento",
            "actualizar_movimiento",
            "eliminar_movimiento",
            "borrar_movimiento",
            "update_movimiento",
            "delete_movimiento",
        }
        self.assertTrue(prohibidos.isdisjoint(publicos))
        for nombre in prohibidos:
            self.assertFalse(hasattr(mov, nombre))

    def test_25_reversion_original_inexistente(self) -> None:
        data = _base_data()
        err = mov.validar_movimiento(
            data,
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.REVERSION_CONSUMO,
            direccion=DireccionMovimiento.ENTRADA,
            cantidad=1,
            origen_tipo="anulacion",
            origen_id="a1",
            movimiento_revertido_id="mov999",
        )
        self.assertTrue(any("inexistente" in e for e in err))

    def test_26_autoreferencia_rechazada(self) -> None:
        data = _base_data()
        err = mov.validar_movimiento(
            data,
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.REVERSION_CONSUMO,
            direccion=DireccionMovimiento.ENTRADA,
            cantidad=1,
            origen_tipo="anulacion",
            origen_id="a1",
            movimiento_id="mov01",
            movimiento_revertido_id="mov01",
        )
        self.assertTrue(any("autorreferenciarse" in e for e in err))

    def test_27_diagnostico_no_modifica(self) -> None:
        data = _base_data()
        antes = copy.deepcopy(appdata_to_dict(data))
        generar_diagnostico(data)
        despues = appdata_to_dict(data)
        self.assertEqual(antes, despues)

    def test_28_reconciliacion_no_modifica_lotes(self) -> None:
        data = _base_data()
        restante = data.lotes[0].cantidad_restante
        comps = mov.reconciliacion_informativa(data)
        self.assertEqual(data.lotes[0].cantidad_restante, restante)
        self.assertTrue(all(c.nota == mov.NOTA_LEDGER_PARCIAL for c in comps))

    def test_29_crear_movimiento_no_cambia_stock(self) -> None:
        data = _base_data()
        stock_antes = sum(l.cantidad_restante for l in data.lotes)
        r = mov.crear_movimiento(
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.ENTRADA_COMPRA,
            direccion=DireccionMovimiento.ENTRADA,
            cantidad=99,
            fecha=date.today(),
            origen_tipo="test_aislada",
            origen_id="iso1",
            ctx=_ctx(data),
        )
        self.assertTrue(r.ok)
        stock_despues = sum(l.cantidad_restante for l in data.lotes)
        self.assertEqual(stock_antes, stock_despues)
        self.assertEqual(stock_despues, 5.0)

    def test_30_fifo_no_cambia(self) -> None:
        data = _base_data()
        data.lotes.append(
            LoteStock(
                "lot02",
                "p01",
                precio_total=6.0,
                cantidad=3.0,
                cantidad_restante=3.0,
                fecha_compra=date(2026, 1, 2),
            )
        )
        copia = copy.deepcopy(data)
        res_a = descontar_lotes(copia, "p01", 2.0)
        # Movimiento ledger aislado en data original no debe alterar FIFO
        mov.crear_movimiento(
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=2.0,
            fecha=date.today(),
            origen_tipo="test_fifo",
            origen_id="f1",
            ctx=_ctx(data),
        )
        res_b = descontar_lotes(data, "p01", 2.0)
        self.assertEqual(
            [(m.lote_id, m.cantidad) for m in res_a.movimientos],
            [(m.lote_id, m.cantidad) for m in res_b.movimientos],
        )
        self.assertEqual(res_a.movimientos[0].lote_id, "lot01")

    def test_31_campos_6a_6b_6c_intactos(self) -> None:
        data = _base_data()
        mov.crear_movimiento(
            producto_id="p01",
            lote_id="lot01",
            tipo=TipoMovimiento.AJUSTE_ENTRADA,
            direccion=DireccionMovimiento.ENTRADA,
            cantidad=0.1,
            fecha=date.today(),
            origen_tipo="test",
            origen_id="x",
            ctx=_ctx(data),
        )
        back = dict_to_appdata(appdata_to_dict(data))
        p = back.productos[0]
        self.assertEqual(p.categoria_id, "cat01")
        self.assertEqual(p.subcategoria_id, "sub01")
        self.assertEqual(p.departamento_ids, ["dep01"])
        self.assertEqual(p.ubicacion_ids, ["ubi01"])
        self.assertEqual(p.tipo_articulo, TipoArticulo.CONSUMIBLE)
        self.assertEqual(p.categoria_inventario, "Lácteos")
        self.assertEqual(len(back.departamentos), 1)
        self.assertEqual(len(back.ubicaciones), 1)

    def test_32_espacios_f5_intactos(self) -> None:
        self.assertEqual(esp.ESPACIO_DEFAULT, esp.ESPACIO_GESTOR)
        self.assertIn(esp.ESPACIO_REGISTRO, esp.ESPACIOS_ORDEN)
        self.assertIn(esp.ESPACIO_INVENTARIO, esp.ESPACIOS_ORDEN)
        ops = esp.secciones_operativas(esp.ESPACIO_INVENTARIO)
        self.assertTrue(len(ops) >= 1)
        self.assertIn("Ledger", APP_VERSION)

    def test_33_tipo_desconocido_no_convertido(self) -> None:
        payload = {
            "meta": {},
            "movimientos": [
                {
                    "id": "mov01",
                    "producto_id": "p01",
                    "lote_id": "lot01",
                    "tipo": "traslado_futuro",
                    "direccion": "entrada",
                    "cantidad": 1,
                    "fecha": "2026-01-01",
                    "origen_tipo": "test",
                    "origen_id": "t",
                }
            ],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(data.movimientos[0].tipo, "traslado_futuro")
        self.assertNotIsInstance(data.movimientos[0].tipo, TipoMovimiento)
        resumen = generar_diagnostico(data)
        self.assertTrue(
            any("tipo desconocido" in i for i in resumen.incidencias_movimientos)
        )


if __name__ == "__main__":
    unittest.main()
