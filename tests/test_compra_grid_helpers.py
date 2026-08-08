"""Tests rejilla multi-línea y conciliación multi-albarán (UI helpers).

    python -m unittest tests.test_compra_grid_helpers -v
"""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BM_TEST_ISOLATION"] = "1"

from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.auth.session import clear_test_session, set_test_session
from app.core.models import (
    AppData,
    Documento,
    EstadoDocumento,
    LineaDocumento,
    Producto,
    Proveedor,
    TipoDocumento,
    UnidadProducto,
)
from app.core.services import compra_registro_service as compra
from app.ui import compra_grid_helpers as grid
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _prod(pid: str = "p1", nombre: str = "Pan") -> Producto:
    return Producto(pid, nombre, UnidadProducto.KG)


def _data() -> AppData:
    return AppData(
        productos=[_prod("p1", "Pan"), _prod("p2", "Aceite")],
        proveedores=[
            Proveedor(id="prov1", nombre_fiscal="Prov SA", codigo="P1", activo=True)
        ],
    )


class TestBidirPrecios(unittest.TestCase):
    def test_total_desde_unitario(self) -> None:
        row = grid.empty_row()
        row["cantidad"] = 10
        row["precio_unitario"] = 2.5
        out = grid.sincronizar_precios_fila(row, campo_editado="precio_unitario")
        self.assertAlmostEqual(out["precio_total"], 25.0, places=2)

    def test_unitario_desde_total(self) -> None:
        row = grid.empty_row()
        row["cantidad"] = 4
        row["precio_total"] = 20
        out = grid.sincronizar_precios_fila(row, campo_editado="precio_total")
        self.assertAlmostEqual(out["precio_unitario"], 5.0, places=4)

    def test_cambio_cantidad_recalcula_total(self) -> None:
        prev = {"cantidad": 2, "precio_unitario": 3, "precio_total": 6, grid.META_KEY: "k1"}
        row = dict(prev)
        row["cantidad"] = 5
        out = grid.sincronizar_precios_fila(row, prev=prev)
        self.assertAlmostEqual(out["precio_total"], 15.0, places=2)

    def test_qty_cero_no_destruye_precios(self) -> None:
        row = grid.empty_row()
        row["cantidad"] = 0
        row["precio_unitario"] = 9
        row["precio_total"] = 99
        out = grid.sincronizar_precios_fila(row, campo_editado="precio_unitario")
        self.assertEqual(out["precio_unitario"], 9)
        self.assertEqual(out["precio_total"], 99)


class TestTotalesGrid(unittest.TestCase):
    def test_dos_igic(self) -> None:
        rows = [
            {
                **grid.empty_row(),
                "producto": "Pan",
                "cantidad": 10,
                "precio_unitario": 1,
                "precio_total": 10,
                "igic_pct": 7,
                grid.META_PROD_ID: "p1",
            },
            {
                **grid.empty_row(),
                "producto": "Aceite",
                "cantidad": 2,
                "precio_unitario": 5,
                "precio_total": 10,
                "igic_pct": 3,
                grid.META_PROD_ID: "p2",
            },
        ]
        res = grid.calcular_totales_grid(rows)
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.base_imponible, Decimal("20.00"))
        # 10*7% = 0.70 ; 10*3% = 0.30
        self.assertEqual(res.impuesto_total, Decimal("1.00"))
        self.assertEqual(res.total_documento, Decimal("21.00"))
        self.assertEqual(len(res.desglose_impuestos), 2)
        info = grid.totales_a_dict(res)
        self.assertEqual(info["base_imponible"], "20,00")
        self.assertEqual(len(info["desglose"]), 2)


class TestPayloadYConc(unittest.TestCase):
    def test_filas_a_payload_multi(self) -> None:
        data = _data()
        mapa = {
            f"{p.nombre} [{getattr(p, 'codigo', None) or '—'}] ({p.id})": p
            for p in data.productos
        }
        # Usar labels exactas
        labels = list(mapa.keys())
        rows = [
            {
                **grid.empty_row(),
                "producto": labels[0],
                "cantidad": 1,
                "precio_unitario": 2,
                "unidad": "Kg",
            },
            {
                **grid.empty_row(),
                "producto": labels[1],
                "cantidad": 3,
                "precio_unitario": 1.5,
                "unidad": "Kg",
                grid.META_ALB_LN: "ln_alb_1",
                grid.META_ALB_DOC: "alb1",
            },
        ]
        payload = grid.filas_a_payload_lineas(rows, mapa_prod_por_label=mapa)
        self.assertEqual(len(payload), 2)
        self.assertIsNone(payload[0].get("factor_conversion") or None)
        # factor_conversion key is None
        self.assertTrue(
            payload[0]["factor_conversion"] is None
            or payload[0].get("factor_conversion") is None
        )
        self.assertEqual(payload[1]["linea_origen_id"], "ln_alb_1")
        conc = grid.filas_a_conciliaciones(rows)
        self.assertEqual(len(conc), 1)
        self.assertEqual(conc[0]["linea_albaran_id"], "ln_alb_1")


class TestMultiAlbaran(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.data = _data()
        # Albarán confirmado con 2 líneas
        alb = Documento(
            id="alb1",
            tipo=TipoDocumento.ALBARAN,
            estado=EstadoDocumento.CONFIRMADO,
            fecha_documento=date(2026, 7, 1),
            proveedor_id="prov1",
            referencia_externa="A-100",
            total_documento=Decimal("30.00"),
            lineas=[
                LineaDocumento(
                    id="aln1",
                    producto_id="p1",
                    cantidad=10,
                    precio_total=20,
                    cantidad_compra=Decimal("10"),
                    precio_unitario_compra=Decimal("2"),
                    unidad_compra="Kg",
                    producto_nombre_snapshot="Pan",
                ),
                LineaDocumento(
                    id="aln2",
                    producto_id="p2",
                    cantidad=2,
                    precio_total=10,
                    cantidad_compra=Decimal("2"),
                    precio_unitario_compra=Decimal("5"),
                    unidad_compra="Kg",
                    producto_nombre_snapshot="Aceite",
                ),
            ],
        )
        self.data.documentos.append(alb)

    def test_albaranes_conciliables(self) -> None:
        albs = grid.albaranes_conciliables(self.data, proveedor_id="prov1")
        self.assertEqual(len(albs), 1)
        self.assertEqual(albs[0].id, "alb1")

    def test_expandir_y_agrupar(self) -> None:
        labels = {p.id: p.nombre for p in self.data.productos}
        prods = {p.id: p for p in self.data.productos}
        rows = grid.expandir_albaranes_a_filas(
            self.data,
            self.data.documentos[:1],
            mapa_label_por_id=labels,
            mapa_prod_por_id=prods,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][grid.META_ALB_LN], "aln1")
        grupos = grid.agrupar_filas_por_albaran(
            rows, mapa_alb={"alb1": self.data.documentos[0]}
        )
        self.assertEqual(len(grupos), 1)
        self.assertIn("Pan", grupos[0]["productos"])
        self.assertIn("Aceite", grupos[0]["productos"])

    def test_linea_ya_en_factura_excluida(self) -> None:
        fac = Documento(
            id="fac1",
            tipo=TipoDocumento.FACTURA,
            estado=EstadoDocumento.CONFIRMADO,
            fecha_documento=date(2026, 7, 2),
            proveedor_id="prov1",
            lineas=[
                LineaDocumento(
                    id="fl1",
                    producto_id="p1",
                    cantidad=10,
                    precio_total=20,
                    linea_origen_id="aln1",
                    documento_origen_id="alb1",
                )
            ],
        )
        self.data.documentos.append(fac)
        libres = grid.lineas_libres_albaran(self.data, self.data.documentos[0])
        ids = [ln.id for ln in libres]
        self.assertNotIn("aln1", ids)
        self.assertIn("aln2", ids)


class TestBidirValidacionCierre(unittest.TestCase):
    """Casos obligatorios del recálculo bidireccional (helpers puros)."""

    def _sync(self, row, *, campo=None, prev=None):
        return grid.sincronizar_precios_fila(
            row, campo_editado=campo, prev=prev
        )

    def test_01_unitario_a_total(self) -> None:
        row = {**grid.empty_row(), "cantidad": 2, "precio_unitario": 5, "precio_total": 0}
        out = self._sync(row, campo="precio_unitario")
        self.assertEqual(out["precio_total"], 10.0)

    def test_02_total_a_unitario(self) -> None:
        row = {**grid.empty_row(), "cantidad": 2, "precio_total": 14, "precio_unitario": 0}
        out = self._sync(row, campo="precio_total")
        self.assertEqual(out["precio_unitario"], 7.0)

    def test_03_unitario_coma_decimal(self) -> None:
        row = {
            **grid.empty_row(),
            "cantidad": 3,
            "precio_unitario": "4,50",
            "precio_total": 0,
        }
        out = self._sync(row, campo="precio_unitario")
        self.assertEqual(out["precio_total"], 13.5)

    def test_04_total_precision_money_round(self) -> None:
        row = {**grid.empty_row(), "cantidad": 3, "precio_total": 10, "precio_unitario": 0}
        out = self._sync(row, campo="precio_total")
        self.assertEqual(out["precio_unitario"], 3.33)
        self.assertIsInstance(
            __import__("decimal").Decimal(str(out["precio_unitario"])),
            Decimal,
        )

    def test_05_06_cantidad_cero_o_vacia_no_divide(self) -> None:
        for qty in (0, "", None):
            row = {
                **grid.empty_row(),
                "cantidad": qty,
                "precio_unitario": 9,
                "precio_total": 99,
            }
            out = self._sync(row, campo="precio_unitario")
            self.assertEqual(out["precio_unitario"], 9)
            self.assertEqual(out["precio_total"], 99)
            self.assertFalse(
                __import__("math").isinf(out["precio_unitario"])
                or __import__("math").isnan(out["precio_unitario"])
            )

    def test_07_08_vaciar_precio_no_destruye_pareja(self) -> None:
        row = {**grid.empty_row(), "cantidad": 2, "precio_unitario": "", "precio_total": 10}
        out = self._sync(row, campo="precio_unitario")
        self.assertEqual(out["precio_total"], 10)
        row2 = {**grid.empty_row(), "cantidad": 2, "precio_unitario": 5, "precio_total": ""}
        out2 = self._sync(row2, campo="precio_total")
        self.assertEqual(out2["precio_unitario"], 5)

    def test_10_11_12_edicion_repetida_y_alternancia(self) -> None:
        row = {**grid.empty_row(), "cantidad": 2, "precio_unitario": 5, "precio_total": 0}
        row = self._sync(row, campo="precio_unitario")
        self.assertEqual(row["precio_total"], 10.0)
        row = self._sync(
            {**row, "precio_unitario": 6},
            prev=row,
        )
        self.assertEqual(row["precio_total"], 12.0)
        prev = dict(row)
        row = self._sync({**row, "precio_total": 14}, prev=prev)
        self.assertEqual(row["precio_unitario"], 7.0)
        prev = dict(row)
        row = self._sync({**row, "precio_unitario": 8}, prev=prev)
        self.assertEqual(row["precio_total"], 16.0)
        # Ausencia de bucle: re-sync estable
        for _ in range(5):
            nxt = self._sync(row, prev=row)
            self.assertFalse(grid.filas_precios_distintas([row], [nxt]))
            row = nxt

    def test_13_una_linea_no_altera_otra(self) -> None:
        a = {
            **grid.empty_row(),
            grid.META_KEY: "a",
            "cantidad": 2,
            "precio_unitario": 5,
            "precio_total": 10,
        }
        b = {
            **grid.empty_row(),
            grid.META_KEY: "b",
            "cantidad": 1,
            "precio_unitario": 3,
            "precio_total": 3,
        }
        prev = [dict(a), dict(b)]
        a2 = dict(a)
        a2["precio_unitario"] = 8
        out = grid.sincronizar_precios_filas([a2, dict(b)], prev)
        self.assertEqual(out[0]["precio_total"], 16.0)
        self.assertEqual(out[1]["precio_unitario"], 3)
        self.assertEqual(out[1]["precio_total"], 3)

    def test_14_cambio_cantidad_conserva_unitario(self) -> None:
        prev = {
            **grid.empty_row(),
            "cantidad": 2,
            "precio_unitario": 7,
            "precio_total": 14,
        }
        row = dict(prev)
        row["cantidad"] = 4
        out = self._sync(row, prev=prev)
        self.assertEqual(out["precio_unitario"], 7)
        self.assertEqual(out["precio_total"], 28.0)

    def test_15_impuestos_totales_documento(self) -> None:
        rows = [
            {
                **grid.empty_row(),
                "producto": "Pan",
                grid.META_PROD_ID: "p1",
                "cantidad": 2,
                "precio_unitario": 5,
                "precio_total": 10,
                "igic_pct": 7,
            },
            {
                **grid.empty_row(),
                "producto": "Aceite",
                grid.META_PROD_ID: "p2",
                "cantidad": 2,
                "precio_unitario": 7,
                "precio_total": 14,
                "igic_pct": 7,
                "dto_eur": 0,
            },
        ]
        # Sync unitario en línea 0 no debe cambiar impuestos de forma incorrecta
        prev = [dict(rows[0]), dict(rows[1])]
        rows[0] = self._sync(
            {**rows[0], "precio_unitario": 5}, campo="precio_unitario"
        )
        res = grid.calcular_totales_grid(rows)
        assert res is not None
        self.assertEqual(res.base_imponible, Decimal("24.00"))
        self.assertEqual(res.impuesto_total, Decimal("1.68"))
        self.assertEqual(res.total_documento, Decimal("25.68"))
        _ = prev  # isolation of lines already covered in test_13


class TestGuardarMultiLinea(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.data = _data()

    def test_guardar_varias_lineas(self) -> None:
        r = compra.guardar_borrador(
            self.data,
            tipo="albaran",
            proveedor_id="prov1",
            lineas=[
                {
                    "producto_id": "p1",
                    "client_line_key": "k1",
                    "cantidad_compra": "2",
                    "unidad_compra": "Kg",
                    "unidad_inventario": "Kg",
                    "precio_unitario_compra": "3",
                    "impuesto_porcentaje": "7",
                },
                {
                    "producto_id": "p2",
                    "client_line_key": "k2",
                    "cantidad_compra": "1",
                    "unidad_compra": "Kg",
                    "unidad_inventario": "Kg",
                    "precio_unitario_compra": "10",
                    "impuesto_porcentaje": "7",
                },
            ],
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(r.documento.lineas), 2)
        self.assertIsNotNone(r.documento.base_imponible)
        self.assertEqual(r.documento.base_imponible, Decimal("16.00"))

    def test_borrador_y_confirmacion_conservan_unitario_sync(self) -> None:
        """Valores tras sync unitario→total se persisten en borrador y confirmación."""
        import tempfile

        from app.core.services.persistencia_appdata import (
            read_appdata_json,
            transactional_update_appdata,
        )

        row = {
            **grid.empty_row(),
            grid.META_PROD_ID: "p1",
            "cantidad": 2,
            "precio_unitario": 5,
            "precio_total": 0,
            "unidad": "Kg",
            "igic_pct": 7,
        }
        synced = grid.sincronizar_precios_fila(row, campo_editado="precio_unitario")
        self.assertEqual(synced["precio_total"], 10.0)
        mapa = {
            f"{p.nombre} [{getattr(p, 'codigo', None) or '—'}] ({p.id})": p
            for p in self.data.productos
        }
        synced["producto"] = next(
            lbl for lbl, p in mapa.items() if p.id == "p1"
        )
        payload = grid.filas_a_payload_lineas([synced], mapa_prod_por_label=mapa)
        self.assertEqual(len(payload), 1)
        self.assertEqual(Decimal(payload[0]["precio_unitario_compra"]), Decimal("5"))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos_hotel.json"

            def seed(data: AppData) -> AppData:
                data.productos = list(self.data.productos)
                data.proveedores = list(self.data.proveedores)
                r = compra.guardar_borrador(
                    data, tipo="albaran", proveedor_id="prov1", lineas=payload
                )
                self.assertTrue(r.ok, r.mensaje)
                self.assertEqual(
                    Decimal(str(r.documento.lineas[0].precio_unitario_compra)),
                    Decimal("5"),
                )
                self.assertEqual(r.documento.base_imponible, Decimal("10.00"))
                return data

            transactional_update_appdata(path, seed)
            data = read_appdata_json(path)
            doc = data.documentos[0]
            h = compra.construir_hash_documento(doc)
            token = str(uuid.uuid4())
            c = compra.confirmar_compra(
                doc.id,
                confirmacion_id=token,
                contenido_hash=h,
                json_path=path,
            )
            self.assertTrue(c.ok, c.mensaje)
            after = read_appdata_json(path)
            conf = after.documentos[0]
            self.assertEqual(conf.estado.value, "confirmado")
            self.assertEqual(
                Decimal(str(conf.lineas[0].precio_unitario_compra)),
                Decimal("5"),
            )
            self.assertEqual(conf.base_imponible, Decimal("10.00"))


class TestFormatoEs(unittest.TestCase):
    def test_formatear_basico(self) -> None:
        self.assertEqual(grid.formatear_numero_es(10), "10,00")
        self.assertEqual(grid.formatear_numero_es(10000), "10.000,00")
        self.assertEqual(grid.formatear_numero_es(10000.5), "10.000,50")
        self.assertEqual(grid.formatear_numero_es(2.5, decimales=4), "2,5000")

    def test_parsear_es(self) -> None:
        self.assertEqual(grid.parsear_numero_es("10,00"), 10.0)
        self.assertEqual(grid.parsear_numero_es("10.000"), 10000.0)
        self.assertEqual(grid.parsear_numero_es("10.000,50"), 10000.5)
        self.assertAlmostEqual(grid.parsear_numero_es("1.234,56"), 1234.56)

    def test_parsear_en_y_float(self) -> None:
        self.assertEqual(grid.parsear_numero_es("10.5"), 10.5)
        self.assertEqual(grid.parsear_numero_es(10.5), 10.5)
        self.assertEqual(grid.parsear_numero_es(float("nan")), 0.0)
        self.assertEqual(grid.parsear_numero_es(""), 0.0)

    def test_celda_numero_acepta_es(self) -> None:
        self.assertEqual(grid.celda_numero("1.250,75"), 1250.75)

    def test_sync_tras_texto_es(self) -> None:
        row = grid.empty_row()
        row["cantidad"] = "4,0000"
        row["precio_unitario"] = "5,00"
        out = grid.sincronizar_precios_fila(row, campo_editado="precio_unitario")
        self.assertAlmostEqual(out["precio_total"], 20.0, places=2)

    def test_sync_total_a_unitario_es(self) -> None:
        row = grid.empty_row()
        row["cantidad"] = "4"
        row["precio_total"] = "20,00"
        out = grid.sincronizar_precios_fila(row, campo_editado="precio_total")
        self.assertAlmostEqual(out["precio_unitario"], 5.0, places=4)

    def test_filas_precios_distintas(self) -> None:
        a = [grid.empty_row()]
        a[0]["precio_unitario"] = 2
        a[0]["cantidad"] = 3
        a[0]["precio_total"] = 0
        b = grid.sincronizar_precios_filas(a)
        self.assertTrue(grid.filas_precios_distintas(a, b))
        self.assertFalse(grid.filas_precios_distintas(b, b))


class TestCeldaTexto(unittest.TestCase):
    def test_nan_float(self) -> None:
        self.assertEqual(grid.celda_texto(float("nan")), "")

    def test_none(self) -> None:
        self.assertEqual(grid.celda_texto(None), "")

    def test_str_nan(self) -> None:
        self.assertEqual(grid.celda_texto("nan"), "")
        self.assertEqual(grid.celda_texto("NaN"), "")

    def test_texto_normal(self) -> None:
        self.assertEqual(grid.celda_texto("  Pan  "), "Pan")

    def test_numero_a_str(self) -> None:
        self.assertEqual(grid.celda_texto(12), "12")

    def test_celda_numero_nan(self) -> None:
        self.assertEqual(grid.celda_numero(float("nan")), 0.0)
        self.assertEqual(grid.celda_numero(float("nan"), 7.0), 7.0)
        self.assertEqual(grid.celda_numero(None, 3.0), 3.0)


class TestFilasNanYVacias(unittest.TestCase):
    def test_add_n_filas_nan_no_lanza(self) -> None:
        """Simula Add row ×N: celdas llegan como float('nan')."""
        nan = float("nan")
        rows = []
        for _ in range(5):
            rows.append(
                {
                    "producto": nan,
                    "cantidad": nan,
                    "unidad": nan,
                    "precio_unitario": nan,
                    "precio_total": nan,
                    "dto_pct": nan,
                    "dto_eur": nan,
                    "igic_pct": nan,
                    "incluye_igic": False,
                    grid.META_KEY: str(uuid.uuid4()),
                    grid.META_ALB_LN: nan,
                    grid.META_ALB_DOC: nan,
                    grid.META_PROD_ID: nan,
                }
            )
        purged = grid.purgar_filas_sin_producto(rows, None)
        self.assertEqual(len(purged), 5)
        synced = grid.sincronizar_precios_filas(purged, None)
        self.assertEqual(len(synced), 5)
        payload = grid.filas_a_payload_lineas(synced, mapa_prod_por_label={})
        self.assertEqual(payload, [])
        self.assertIsNone(grid.calcular_totales_grid(synced))
        # No debe llamar .strip() sobre float
        for r in synced:
            self.assertEqual(grid.celda_texto(r.get("producto")), "")
            self.assertFalse(grid.fila_tiene_producto(r))


class TestPurgarFilas(unittest.TestCase):
    def test_vaciar_producto_elimina_fila(self) -> None:
        prev = [
            {
                **grid.empty_row(),
                grid.META_KEY: "k1",
                "producto": "Pan [—] (p1)",
                grid.META_PROD_ID: "p1",
                "cantidad": 2,
            },
            {**grid.empty_row(), grid.META_KEY: "k2"},
        ]
        ahora = [
            {**prev[0], "producto": "", grid.META_PROD_ID: ""},
            dict(prev[1]),
        ]
        out = grid.purgar_filas_sin_producto(ahora, prev)
        keys = [r[grid.META_KEY] for r in out if grid.fila_tiene_producto(r)]
        self.assertNotIn("k1", keys)
        self.assertEqual(sum(1 for r in out if not grid.fila_tiene_producto(r)), 1)

    def test_conserva_plantilla_vacia(self) -> None:
        prev = [{**grid.empty_row(), grid.META_KEY: "empty"}]
        ahora = [dict(prev[0])]
        out = grid.purgar_filas_sin_producto(ahora, prev)
        self.assertEqual(len(out), 1)
        self.assertFalse(grid.fila_tiene_producto(out[0]))

    def test_siempre_una_vacia_al_final(self) -> None:
        prev = [
            {
                **grid.empty_row(),
                grid.META_KEY: "k1",
                "producto": "Pan",
                grid.META_PROD_ID: "p1",
            }
        ]
        ahora = [dict(prev[0])]
        out = grid.purgar_filas_sin_producto(ahora, prev)
        self.assertTrue(grid.fila_tiene_producto(out[0]))
        self.assertFalse(grid.fila_tiene_producto(out[-1]))
        self.assertEqual(len(out), 2)

    def test_conserva_varias_filas_vacias(self) -> None:
        """Add row ×2: no colapsar plantillas vacías mientras se rellenan."""
        prev = [
            {**grid.empty_row(), grid.META_KEY: "a"},
            {**grid.empty_row(), grid.META_KEY: "b"},
        ]
        out = grid.purgar_filas_sin_producto(prev, prev)
        self.assertEqual(len(out), 2)
        self.assertTrue(all(not grid.fila_tiene_producto(r) for r in out))


if __name__ == "__main__":
    unittest.main()
