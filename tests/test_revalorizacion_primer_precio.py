"""D60 — revalorización al primer precio de compra.

Ejecutar:

    py -m unittest tests.test_revalorizacion_primer_precio -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.models import (
    AppData,
    LineaDesayuno,
    LoteStock,
    Producto,
    Proveedor,
    RegistroDesayuno,
    TipoDocumento,
    TipoMovimiento,
    UnidadProducto,
)
from app.core.models.enums import DireccionMovimiento, OrigenConsumo, TipoServicio
from app.core.models.registro_servicio import ConsumoLoteDetalle, LineaDetalleOrigen
from app.core.services import compra_registro_service as compra
from app.core.services import movimiento_service as mov_svc
from app.core.services.persistencia_appdata import (
    read_appdata_json,
    transactional_update_appdata,
)
from app.core.services.revalorizacion_primer_precio_service import (
    producto_tiene_lote_de_compra,
    revalorizar_producto_primer_precio,
)


def _seed_base(data: AppData) -> None:
    data.productos.append(
        Producto("p1", "Cafe", UnidadProducto.KG, codigo="CAFE-01")
    )
    data.proveedores.append(
        Proveedor(id="prv1", nombre_fiscal="Norte", codigo="PRV-N")
    )
    # Lote provisional (import / sin documento): 0,50 €/kg
    data.lotes.append(
        LoteStock("lprov", "p1", 5.0, 10.0, 8.0, date(2026, 7, 1))
    )


def _desayuno_consumo(data: AppData, *, qty: float = 2.0, coste_unit: float = 0.5) -> None:
    """Consumo histórico @ coste provisional."""
    from app.core.models import MovimientoInventario

    coste = round(qty * coste_unit, 2)
    frag = ConsumoLoteDetalle("lprov", "p1", qty, coste)
    det = LineaDetalleOrigen(
        origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
        producto_id="p1",
        cantidad=qty,
        coste=coste,
        registro_origen_id="d01",
        tipo_servicio=TipoServicio.DESAYUNO.value,
        consumos_lote=[frag],
    )
    data.desayunos.append(
        RegistroDesayuno(
            "d01",
            date(2026, 8, 1),
            [LineaDesayuno("p1", qty, coste)],
            coste,
            "test",
            10,
            lineas_detalle=[det],
        )
    )
    data.movimientos.append(
        MovimientoInventario(
            id="mcons01",
            producto_id="p1",
            lote_id="lprov",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=qty,
            fecha=date(2026, 8, 1),
            hora=None,
            origen_tipo=mov_svc.ORIGEN_TIPO_DESAYUNO,
            origen_id="d01",
            origen_linea_id=mov_svc.origen_linea_id_consumo(0, 0),
            coste_unitario_snapshot=coste_unit,
            coste_total_snapshot=coste,
        )
    )


def _confirmar_albaran(path: Path, *, precio: str, qty: str = "5", ref: str = "ALB-1") -> str:
    def seed(data: AppData) -> AppData:
        compra.guardar_borrador(
            data,
            tipo=TipoDocumento.ALBARAN.value,
            proveedor_id="prv1",
            referencia_externa=ref,
            lineas=[
                {
                    "producto_id": "p1",
                    "client_line_key": f"k-{ref}",
                    "cantidad_compra": qty,
                    "unidad_compra": "Kg",
                    "precio_unitario_compra": precio,
                    "impuesto_porcentaje": "0",
                }
            ],
        )
        return data

    transactional_update_appdata(path, seed)
    data = read_appdata_json(path)
    doc = next(d for d in data.documentos if d.referencia_externa == ref)
    h = compra.construir_hash_documento(doc)
    res = compra.confirmar_compra(
        doc.id,
        confirmacion_id=str(uuid.uuid4()),
        contenido_hash=h,
        json_path=path,
    )
    assert res.ok, res.mensaje
    return doc.id


class TestRevalorizacionPrimerPrecio(unittest.TestCase):
    def test_sin_lote_compra_provisional(self) -> None:
        data = AppData()
        _seed_base(data)
        self.assertFalse(producto_tiene_lote_de_compra(data, "p1"))

    def test_primer_albaran_revaloriza_desayuno_y_lote_provisional(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_base(data)
                _desayuno_consumo(data, qty=2.0, coste_unit=0.5)
                return data

            transactional_update_appdata(path, seed)
            before = read_appdata_json(path)
            self.assertAlmostEqual(before.desayunos[0].coste_total, 1.0, places=2)
            self.assertAlmostEqual(before.lotes[0].precio_total, 5.0, places=2)

            # Primer albarán: 4 €/kg (5 kg × 4 = 20)
            _confirmar_albaran(path, precio="4", qty="5", ref="ALB-P1")

            after = read_appdata_json(path)
            des = next(d for d in after.desayunos if d.id == "d01")
            self.assertAlmostEqual(des.coste_total, 8.0, places=2)  # 2 × 4
            self.assertAlmostEqual(des.lineas[0].coste, 8.0, places=2)
            self.assertAlmostEqual(des.lineas_detalle[0].coste, 8.0, places=2)
            self.assertAlmostEqual(des.lineas_detalle[0].consumos_lote[0].coste, 8.0, places=2)

            prov = next(l for l in after.lotes if l.id == "lprov")
            self.assertAlmostEqual(prov.precio_total, 40.0, places=2)  # 10 × 4

            compra_lotes = [l for l in after.lotes if l.documento_origen_id]
            self.assertEqual(len(compra_lotes), 1)
            self.assertAlmostEqual(compra_lotes[0].precio_total, 20.0, places=2)

            mov = mov_svc.buscar_movimiento_consumo_fragmento(after, "d01", 0, 0)
            self.assertIsNotNone(mov)
            self.assertAlmostEqual(float(mov.coste_total_snapshot or 0), 8.0, places=2)

            acts = [
                a
                for a in after.actividades
                if a.accion == "Revalorización primer precio"
            ]
            self.assertTrue(acts)

    def test_segundo_albaran_no_toca_historico(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_base(data)
                _desayuno_consumo(data, qty=2.0, coste_unit=0.5)
                return data

            transactional_update_appdata(path, seed)
            _confirmar_albaran(path, precio="4", qty="5", ref="ALB-1")
            mid = read_appdata_json(path)
            coste_hist = mid.desayunos[0].coste_total
            n_reval = sum(
                1 for a in mid.actividades if a.accion == "Revalorización primer precio"
            )

            _confirmar_albaran(path, precio="9", qty="3", ref="ALB-2")
            after = read_appdata_json(path)
            self.assertAlmostEqual(after.desayunos[0].coste_total, coste_hist, places=2)
            n_reval2 = sum(
                1 for a in after.actividades if a.accion == "Revalorización primer precio"
            )
            self.assertEqual(n_reval2, n_reval)
            compra_lotes = [l for l in after.lotes if l.documento_origen_id]
            self.assertEqual(len(compra_lotes), 2)

    def test_factura_conciliacion_no_crea_stock_ni_revaloriza_de_nuevo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_base(data)
                _desayuno_consumo(data, qty=2.0, coste_unit=0.5)
                return data

            transactional_update_appdata(path, seed)
            _confirmar_albaran(path, precio="4", qty="5", ref="ALB-C")
            after_alb = read_appdata_json(path)
            ln_alb = next(
                d for d in after_alb.documentos if d.referencia_externa == "ALB-C"
            ).lineas[0]
            coste_hist = after_alb.desayunos[0].coste_total
            n_lotes = len(after_alb.lotes)
            n_reval = sum(
                1
                for a in after_alb.actividades
                if a.accion == "Revalorización primer precio"
            )

            def seed_fac(data: AppData) -> AppData:
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.FACTURA.value,
                    proveedor_id="prv1",
                    referencia_externa="FAC-C",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "kf",
                            "cantidad_compra": "5",
                            "unidad_compra": "Kg",
                            "precio_unitario_compra": "99",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed_fac)
            data = read_appdata_json(path)
            fac = next(d for d in data.documentos if d.referencia_externa == "FAC-C")
            props = [
                {
                    "linea_factura_client_key": "kf",
                    "linea_albaran_id": ln_alb.id,
                    "cantidad_conciliada": "5",
                }
            ]
            h = compra.construir_hash_documento(fac, props)
            res = compra.confirmar_compra(
                fac.id,
                confirmacion_id=str(uuid.uuid4()),
                contenido_hash=h,
                json_path=path,
                conciliaciones_propuestas=props,
            )
            self.assertTrue(res.ok, res.mensaje)
            after = read_appdata_json(path)
            self.assertEqual(len(after.lotes), n_lotes)
            self.assertAlmostEqual(after.desayunos[0].coste_total, coste_hist, places=2)
            n_reval2 = sum(
                1
                for a in after.actividades
                if a.accion == "Revalorización primer precio"
            )
            self.assertEqual(n_reval2, n_reval)

    def test_servicio_directo_revaloriza(self) -> None:
        data = AppData()
        _seed_base(data)
        _desayuno_consumo(data, qty=1.0, coste_unit=0.5)
        self.assertAlmostEqual(data.desayunos[0].coste_total, 0.5, places=2)
        r = revalorizar_producto_primer_precio(
            data, "p1", Decimal("3.5"), doc_id="docX", actor="test"
        )
        self.assertEqual(r.registros_desayuno, 1)
        self.assertAlmostEqual(data.desayunos[0].coste_total, 3.5, places=2)
        self.assertAlmostEqual(data.lotes[0].precio_total, 35.0, places=2)


if __name__ == "__main__":
    unittest.main()
