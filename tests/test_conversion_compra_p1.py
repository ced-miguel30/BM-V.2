"""AUD-P1 — factor_compra en vínculo y preview alineada con confirmación."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.auth.session import clear_test_session, set_test_session
from app.core.models import AppData, IngredienteReceta, Producto, UnidadProducto
from app.core.services import compra_registro_service as compra
from app.core.services import proveedor_service as prv
from app.core.services import receta_service as rec
from app.core.services.conversion_compra import (
    ConversionDesconocidaError,
    resolver_factor_conversion,
    texto_equivalencia,
)
from app.core.services.persistencia_appdata import (
    read_appdata_json,
    transactional_update_appdata,
)
from app.core.services.stock_service import crear_producto
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui import compra_grid_helpers as grid
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _ctx(data: AppData):
    return build_app_context(uow=InMemoryUnitOfWork(data))


class TestVinculoFactorCompra(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.data = AppData(
            productos=[Producto("p1", "Aceite", UnidadProducto.L, codigo="ACE-01")]
        )
        self.ctx = _ctx(self.data)
        prv.crear_proveedor("Prov Aceite", codigo="PA-01", ctx=self.ctx)

    def test_01_crear_vinculo_factor_6(self) -> None:
        r = prv.vincular_producto_proveedor(
            "p1",
            self.data.proveedores[0].id,
            unidad_compra="Caja",
            factor_compra="6",
            ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        rel = self.data.relaciones_producto_proveedor[0]
        self.assertEqual(rel.unidad_compra, "Caja")
        self.assertEqual(rel.factor_compra, Decimal("6"))
        self.assertEqual(
            texto_equivalencia(rel.unidad_compra, rel.factor_compra, "L"),
            "1 Caja = 6 L",
        )

    def test_02_recuperar_y_editar_factor(self) -> None:
        prv.vincular_producto_proveedor(
            "p1",
            self.data.proveedores[0].id,
            unidad_compra="Caja",
            factor_compra=6,
            ctx=self.ctx,
        )
        rid = self.data.relaciones_producto_proveedor[0].id
        r = prv.actualizar_relacion_producto_proveedor(
            rid,
            unidad_compra="Caja",
            factor_compra="12",
            ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(
            self.data.relaciones_producto_proveedor[0].factor_compra, Decimal("12")
        )
        raw = appdata_to_dict(self.data)
        back = dict_to_appdata(raw)
        self.assertEqual(back.relaciones_producto_proveedor[0].factor_compra, Decimal("12"))
        self.assertEqual(back.relaciones_producto_proveedor[0].unidad_compra, "Caja")

    def test_03_rechaza_factor_cero(self) -> None:
        r = prv.vincular_producto_proveedor(
            "p1",
            self.data.proveedores[0].id,
            unidad_compra="Caja",
            factor_compra="0",
            ctx=self.ctx,
        )
        self.assertFalse(r.ok)
        self.assertIn("mayor que cero", r.mensaje.lower())

    def test_04_rechaza_factor_negativo(self) -> None:
        r = prv.vincular_producto_proveedor(
            "p1",
            self.data.proveedores[0].id,
            unidad_compra="Caja",
            factor_compra="-2",
            ctx=self.ctx,
        )
        self.assertFalse(r.ok)

    def test_04b_unidades_distintas_sin_factor_bloquea_vinculo(self) -> None:
        r = prv.vincular_producto_proveedor(
            "p1",
            self.data.proveedores[0].id,
            unidad_compra="Caja",
            factor_compra=None,
            ctx=self.ctx,
        )
        self.assertFalse(r.ok)
        self.assertIn("factor", r.mensaje.lower())


class TestResolverYPreview(unittest.TestCase):
    def test_05_unidades_iguales_sin_factor_explicito(self) -> None:
        f = resolver_factor_conversion(
            unidad_compra="L",
            unidad_inventario="L",
            factor_explicito=None,
            factor_catalogo=None,
        )
        self.assertEqual(f, Decimal("1"))

    def test_06_unidades_distintas_sin_factor_error(self) -> None:
        with self.assertRaises(ConversionDesconocidaError):
            resolver_factor_conversion(
                unidad_compra="Caja",
                unidad_inventario="L",
                factor_explicito=None,
                factor_catalogo=None,
            )

    def test_07_preview_2_cajas_factor_6(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        data = AppData(
            productos=[Producto("p1", "Aceite", UnidadProducto.L, codigo="ACE")],
        )
        ctx = _ctx(data)
        self.assertTrue(prv.crear_proveedor("Prov Preview", codigo="P1", ctx=ctx).ok)
        self.assertTrue(
            prv.vincular_producto_proveedor(
                "p1",
                data.proveedores[0].id,
                unidad_compra="Caja",
                factor_compra=6,
                ctx=ctx,
            ).ok
        )
        label = "Aceite"
        mapa = {label: data.productos[0]}
        rows = [
            {
                **grid.empty_row(),
                "producto": label,
                "cantidad": 2,
                "unidad": "Caja",
                "precio_unitario": 12,
                "igic_pct": 0,
                grid.META_PROD_ID: "p1",
            }
        ]
        entradas = grid.filas_a_entradas_calculo(
            rows,
            mapa_prod_por_label=mapa,
            data=data,
            proveedor_id=data.proveedores[0].id,
        )
        self.assertEqual(len(entradas), 1)
        self.assertEqual(Decimal(str(entradas[0].factor_conversion)), Decimal("6"))
        res = grid.calcular_totales_grid(
            rows,
            mapa_prod_por_label=mapa,
            data=data,
            proveedor_id=data.proveedores[0].id,
        )
        assert res is not None
        self.assertEqual(res.lineas[0].cantidad_inventario, Decimal("12"))
        self.assertEqual(res.lineas[0].coste_inventariable_linea, Decimal("24.00"))
        self.assertEqual(res.lineas[0].coste_unitario_inventario, Decimal("2"))

    def test_07b_preview_no_usa_factor_1_silencioso(self) -> None:
        """Falla si el preview volviera a hardcodear factor=1 (coste/ud sería 12)."""
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        data = AppData(
            productos=[Producto("p1", "Aceite", UnidadProducto.L, codigo="ACE")],
        )
        ctx = _ctx(data)
        self.assertTrue(prv.crear_proveedor("Prov Preview", codigo="P1", ctx=ctx).ok)
        self.assertTrue(
            prv.vincular_producto_proveedor(
                "p1",
                data.proveedores[0].id,
                unidad_compra="Caja",
                factor_compra=6,
                ctx=ctx,
            ).ok
        )
        label = "Aceite"
        mapa = {label: data.productos[0]}
        rows = [
            {
                **grid.empty_row(),
                "producto": label,
                "cantidad": 2,
                "unidad": "Caja",
                "precio_unitario": 12,
                "igic_pct": 0,
                grid.META_PROD_ID: "p1",
            }
        ]
        res = grid.calcular_totales_grid(
            rows,
            mapa_prod_por_label=mapa,
            data=data,
            proveedor_id=data.proveedores[0].id,
        )
        assert res is not None
        self.assertEqual(res.lineas[0].coste_unitario_inventario, Decimal("2"))
        self.assertNotEqual(res.lineas[0].coste_unitario_inventario, Decimal("12"))
        self.assertNotEqual(res.lineas[0].cantidad_inventario, Decimal("2"))


class TestConfirmacionYCoste(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.demo_before = DEMO_FILE.read_bytes()

    def tearDown(self) -> None:
        self.assertEqual(DEMO_FILE.read_bytes(), self.demo_before)
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_08_a_20_e2e_preview_confirm_idem_anular_receta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            snap: dict = {}

            def seed(data: AppData) -> AppData:
                with patch(
                    "app.core.services.stock_service.get_data", return_value=data
                ), patch(
                    "app.core.services.stock_service.persist_data",
                    side_effect=lambda d: d,
                ), patch(
                    "app.core.services.receta_service.get_data", return_value=data
                ), patch(
                    "app.core.services.receta_service.persist_data",
                    side_effect=lambda d: d,
                ):
                    ctx = _ctx(data)
                    assert crear_producto(
                        "Aceite L",
                        "L",
                        None,
                        codigo="ACEI-L",
                        tipo_articulo="consumible",
                    ).ok
                    assert crear_producto(
                        "Harina Kg",
                        "Kg",
                        None,
                        codigo="HARI-KG",
                        tipo_articulo="consumible",
                    ).ok
                    p_aceite = next(p for p in data.productos if p.codigo == "ACEI-L")
                    p_harina = next(p for p in data.productos if p.codigo == "HARI-KG")
                    assert prv.crear_proveedor("Prov T", codigo="PT", ctx=ctx).ok
                    pid = data.proveedores[0].id
                    self.assertTrue(
                        prv.vincular_producto_proveedor(
                            p_aceite.id,
                            pid,
                            unidad_compra="Caja",
                            factor_compra="6",
                            ctx=ctx,
                        ).ok
                    )
                    self.assertTrue(
                        prv.vincular_producto_proveedor(
                            p_harina.id,
                            pid,
                            unidad_compra="Paquete",
                            factor_compra="2,5",
                            ctx=ctx,
                        ).ok
                    )
                    assert rec.crear_receta(
                        "Salsa Test",
                        [IngredienteReceta(producto_id=p_aceite.id, cantidad=0.5)],
                        porciones_estandar=1,
                    ).ok

                    mapa = {p_aceite.nombre: p_aceite, p_harina.nombre: p_harina}
                    rows = [
                        {
                            **grid.empty_row(),
                            "producto": p_aceite.nombre,
                            "cantidad": 2,
                            "unidad": "Caja",
                            "precio_unitario": 12,
                            "igic_pct": 0,
                            grid.META_PROD_ID: p_aceite.id,
                        },
                        {
                            **grid.empty_row(),
                            "producto": p_harina.nombre,
                            "cantidad": 3,
                            "unidad": "Paquete",
                            "precio_unitario": 4,
                            "igic_pct": 0,
                            grid.META_PROD_ID: p_harina.id,
                        },
                    ]
                    preview = grid.calcular_totales_grid(
                        rows,
                        mapa_prod_por_label=mapa,
                        data=data,
                        proveedor_id=pid,
                    )
                    assert preview is not None
                    self.assertEqual(preview.lineas[0].cantidad_inventario, Decimal("12"))
                    self.assertEqual(
                        preview.lineas[0].coste_unitario_inventario, Decimal("2")
                    )
                    self.assertEqual(preview.lineas[1].cantidad_inventario, Decimal("7.5"))

                    rows[0]["cantidad"] = 4
                    preview2 = grid.calcular_totales_grid(
                        rows,
                        mapa_prod_por_label=mapa,
                        data=data,
                        proveedor_id=pid,
                    )
                    assert preview2 is not None
                    self.assertEqual(preview2.lineas[0].cantidad_inventario, Decimal("24"))
                    rows[0]["cantidad"] = 2

                    synced = grid.sincronizar_precios_fila(
                        {**rows[0], "precio_total": 24, "precio_unitario": 0},
                        campo_editado="precio_total",
                    )
                    diag = grid.diagnostico_conversion_filas(
                        [{**rows[0], **synced}],
                        mapa_prod_por_label=mapa,
                        data=data,
                        proveedor_id=pid,
                    )
                    self.assertEqual(diag[0]["factor"], Decimal("6"))

                    lineas = [
                        {
                            "producto_id": p_aceite.id,
                            "client_line_key": "k1",
                            "cantidad_compra": "2",
                            "unidad_compra": "Caja",
                            "unidad_inventario": "L",
                            "precio_unitario_compra": "12",
                            "impuesto_porcentaje": "0",
                            "factor_conversion": None,
                        },
                        {
                            "producto_id": p_harina.id,
                            "client_line_key": "k2",
                            "cantidad_compra": "3",
                            "unidad_compra": "Paquete",
                            "unidad_inventario": "Kg",
                            "precio_unitario_compra": "4",
                            "impuesto_porcentaje": "0",
                            "factor_conversion": None,
                        },
                    ]
                    g = compra.guardar_borrador(
                        data,
                        tipo="albaran",
                        proveedor_id=pid,
                        referencia_externa="P1-CONV",
                        lineas=lineas,
                    )
                    self.assertTrue(g.ok, g.mensaje)
                    doc = g.documento
                    assert doc is not None
                    self.assertEqual(doc.lineas[0].factor_conversion, Decimal("6"))
                    self.assertEqual(doc.lineas[0].cantidad_inventario, Decimal("12"))
                    self.assertEqual(doc.lineas[1].factor_conversion, Decimal("2.5"))
                    self.assertEqual(doc.lineas[1].cantidad_inventario, Decimal("7.5"))
                    snap["doc_id"] = doc.id
                    snap["aceite_id"] = p_aceite.id
                    snap["rel_id"] = data.relaciones_producto_proveedor[0].id
                    g2 = compra.guardar_borrador(
                        data,
                        tipo="albaran",
                        proveedor_id=pid,
                        referencia_externa="P1-CONV",
                        lineas=lineas,
                        documento_id=doc.id,
                    )
                    self.assertTrue(g2.ok, g2.mensaje)
                    self.assertEqual(
                        g2.documento.lineas[0].factor_conversion, Decimal("6")
                    )
                return data

            transactional_update_appdata(path, seed)
            data = read_appdata_json(path)
            doc = next(d for d in data.documentos if d.id == snap["doc_id"])
            h = compra.construir_hash_documento(doc)
            tok = str(uuid.uuid4())
            conf = compra.confirmar_compra(
                doc.id, confirmacion_id=tok, contenido_hash=h, json_path=path
            )
            self.assertTrue(conf.ok, conf.mensaje)
            after = read_appdata_json(path)
            lotes_aceite = [
                l
                for l in after.lotes
                if l.producto_id == snap["aceite_id"]
                and not getattr(l, "anulado", False)
            ]
            self.assertEqual(len(lotes_aceite), 1)
            self.assertEqual(float(lotes_aceite[0].cantidad), 12.0)
            self.assertEqual(float(lotes_aceite[0].precio_total), 24.0)
            self.assertEqual(
                float(lotes_aceite[0].precio_total) / float(lotes_aceite[0].cantidad),
                2.0,
            )
            with patch("app.core.services.receta_service.get_data", return_value=after):
                sim = rec.simular_receta(after.recetas[0].id, 1)
                self.assertTrue(sim.ok)
                self.assertEqual(sim.coste_total, 1.0)

            conf2 = compra.confirmar_compra(
                doc.id, confirmacion_id=tok, contenido_hash=h, json_path=path
            )
            self.assertTrue(conf2.ok)
            after2 = read_appdata_json(path)
            self.assertEqual(len(after2.lotes), 2)
            self.assertEqual(len(after2.movimientos), 2)

            def bump_factor(d: AppData) -> AppData:
                rel = next(
                    r
                    for r in d.relaciones_producto_proveedor
                    if r.id == snap["rel_id"]
                )
                rel.factor_compra = Decimal("99")
                return d

            transactional_update_appdata(path, bump_factor)
            confirmed = read_appdata_json(path)
            cdoc = next(d for d in confirmed.documentos if d.id == doc.id)
            self.assertEqual(cdoc.lineas[0].factor_conversion, Decimal("6"))
            self.assertEqual(cdoc.lineas[0].cantidad_inventario, Decimal("12"))
            self.assertEqual(
                next(
                    r
                    for r in confirmed.relaciones_producto_proveedor
                    if r.id == snap["rel_id"]
                ).factor_compra,
                Decimal("99"),
            )

            from app.core.services import anulacion_documento_service as anul

            an = anul.anular_documento_confirmado(
                documento_id=doc.id, motivo="p1-test", json_path=path
            )
            self.assertTrue(an.ok, an.mensaje)
            final = read_appdata_json(path)
            stock_aceite = sum(
                float(l.cantidad_restante)
                for l in final.lotes
                if l.producto_id == snap["aceite_id"]
                and not getattr(l, "anulado", False)
            )
            self.assertEqual(stock_aceite, 0.0)
            self.assertEqual(len(final.movimientos), 4)


if __name__ == "__main__":
    unittest.main()
