"""Recetas — costes, rendimiento, activo e integración con registro."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from datetime import date
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
from app.core.models import (
    AppData,
    IngredienteReceta,
    LoteStock,
    Producto,
    UnidadProducto,
)
from app.core.services import compra_registro_service as compra
from app.core.services import proveedor_service as prv
from app.core.services import receta_service as rec
from app.core.services.persistencia_appdata import (
    read_appdata_json,
    transactional_update_appdata,
)
from app.core.services.receta_service import listar_recetas, valorar_receta
from app.core.services.stock_service import crear_producto, desactivar_producto
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _ctx(data: AppData):
    return build_app_context(uow=InMemoryUnitOfWork(data))


class TestRecetasCostesYActivo(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.demo_before = DEMO_FILE.read_bytes()
        self.data = AppData(
            productos=[
                Producto("pa", "Aceite", UnidadProducto.L, codigo="A"),
                Producto("pb", "Harina", UnidadProducto.KG, codigo="B"),
            ]
        )
        self.data.lotes = [
            LoteStock("la", "pa", 20.0, 10.0, 10.0),  # 2 €/L
            LoteStock("lb", "pb", 40.0, 10.0, 10.0),  # 4 €/kg
        ]
        self._patch_rec = patch(
            "app.core.services.receta_service.get_data", return_value=self.data
        )
        self._patch_rec_p = patch(
            "app.core.services.receta_service.persist_data", side_effect=lambda d: d
        )
        self._patch_rec.start()
        self._patch_rec_p.start()
        self.addCleanup(self._patch_rec.stop)
        self.addCleanup(self._patch_rec_p.stop)

    def tearDown(self) -> None:
        self.assertEqual(DEMO_FILE.read_bytes(), self.demo_before)
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_10_crear_un_ingrediente(self) -> None:
        r = rec.crear_receta(
            "Sola",
            [IngredienteReceta("pa", 0.5)],
            porciones_estandar=2,
        )
        self.assertTrue(r.ok, r.mensaje)

    def test_11_crear_varios(self) -> None:
        r = rec.crear_receta(
            "Mix",
            [IngredienteReceta("pa", 0.5), IngredienteReceta("pb", 0.25)],
            porciones_estandar=4,
        )
        self.assertTrue(r.ok, r.mensaje)

    def test_12_rechazar_rendimiento_cero(self) -> None:
        r = rec.crear_receta(
            "Bad",
            [IngredienteReceta("pa", 0.5)],
            porciones_estandar=0,
        )
        self.assertFalse(r.ok)

    def test_13_rechazar_cantidad_cero(self) -> None:
        r = rec.crear_receta(
            "BadQty",
            [IngredienteReceta("pa", 0)],
            porciones_estandar=1,
        )
        self.assertFalse(r.ok)

    def test_14_rechazar_duplicado(self) -> None:
        r = rec.crear_receta(
            "Dup",
            [IngredienteReceta("pa", 0.1), IngredienteReceta("pa", 0.2)],
            porciones_estandar=1,
        )
        self.assertFalse(r.ok)
        self.assertIn("Aceite", r.mensaje)

    def test_15_eliminar_ingrediente_por_nombre(self) -> None:
        self.assertTrue(
            rec.crear_receta(
                "ConDos",
                [IngredienteReceta("pa", 0.5), IngredienteReceta("pb", 0.25)],
                porciones_estandar=4,
            ).ok
        )
        rid = self.data.recetas[0].id
        r = rec.editar_receta(
            rid,
            "ConDos",
            [IngredienteReceta("pa", 0.5)],
            porciones_estandar=4,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.recetas[0].ingredientes), 1)

    def test_16_17_coste_total_y_por_racion(self) -> None:
        self.assertTrue(
            rec.crear_receta(
                "CosteOK",
                [IngredienteReceta("pa", 0.5), IngredienteReceta("pb", 0.25)],
                porciones_estandar=4,
            ).ok
        )
        val = valorar_receta(self.data.recetas[0].id)
        self.assertTrue(val.ok, val.mensaje)
        self.assertTrue(val.coste_completo)
        self.assertEqual(val.coste_total, 2.0)  # 1 + 1
        self.assertEqual(val.coste_por_racion, 0.5)

    def test_18_coste_incompleto(self) -> None:
        self.data.lotes = []  # sin lotes
        self.assertTrue(
            rec.crear_receta(
                "SinCoste",
                [IngredienteReceta("pa", 0.5)],
                porciones_estandar=1,
            ).ok
        )
        val = valorar_receta(self.data.recetas[0].id)
        self.assertTrue(val.ok)
        self.assertFalse(val.coste_completo)
        self.assertGreaterEqual(val.ingredientes_sin_coste, 1)

    def test_19_recalcular_tras_cantidad(self) -> None:
        self.assertTrue(
            rec.crear_receta(
                "Qty",
                [IngredienteReceta("pa", 0.5)],
                porciones_estandar=1,
            ).ok
        )
        rid = self.data.recetas[0].id
        self.assertEqual(valorar_receta(rid).coste_total, 1.0)
        rec.editar_receta(
            rid, "Qty", [IngredienteReceta("pa", 1.0)], porciones_estandar=1
        )
        self.assertEqual(valorar_receta(rid).coste_total, 2.0)

    def test_22_producto_inactivo_en_receta(self) -> None:
        self.assertTrue(
            rec.crear_receta(
                "ConInact",
                [IngredienteReceta("pa", 0.5)],
                porciones_estandar=1,
            ).ok
        )
        with patch("app.core.services.stock_service.get_data", return_value=self.data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            desactivar_producto("pa")
        val = valorar_receta(self.data.recetas[0].id)
        self.assertTrue(val.ok)
        self.assertTrue(val.lineas[0].producto_inactivo)
        # no se puede añadir otro inactivo nuevo
        r = rec.editar_receta(
            self.data.recetas[0].id,
            "ConInact",
            [IngredienteReceta("pa", 0.5), IngredienteReceta("pb", 0.1)],
            porciones_estandar=1,
        )
        # pb activo OK; pa permitido por existente
        self.assertTrue(r.ok, r.mensaje)
        # añadir solo un inactivo nuevo (simular producto nuevo inactivo):
        self.data.productos.append(
            Producto("pz", "InactNew", UnidadProducto.UD, codigo="Z", activo=False)
        )
        r2 = rec.editar_receta(
            self.data.recetas[0].id,
            "ConInact",
            [IngredienteReceta("pa", 0.5), IngredienteReceta("pz", 1)],
            porciones_estandar=1,
        )
        self.assertFalse(r2.ok)

    def test_23_24_activo_en_listado_registro(self) -> None:
        self.assertTrue(
            rec.crear_receta(
                "Activa",
                [IngredienteReceta("pa", 0.1)],
                porciones_estandar=1,
                servicios_disponibles=["desayuno"],
            ).ok
        )
        self.assertTrue(
            rec.crear_receta(
                "Off",
                [IngredienteReceta("pb", 0.1)],
                porciones_estandar=1,
                servicios_disponibles=["desayuno"],
            ).ok
        )
        rid_off = next(r.id for r in self.data.recetas if r.nombre == "Off")
        self.assertTrue(rec.desactivar_receta(rid_off).ok)
        activas = listar_recetas(servicio_disponible="desayuno", solo_activas=True)
        nombres = {r.nombre for r in activas}
        self.assertIn("Activa", nombres)
        self.assertNotIn("Off", nombres)
        todas = listar_recetas(solo_activas=False)
        self.assertEqual(len(todas), 2)


class TestValoracionTrasCompra(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.demo_before = DEMO_FILE.read_bytes()

    def tearDown(self) -> None:
        self.assertEqual(DEMO_FILE.read_bytes(), self.demo_before)

    def test_20_21_fifo_tras_compra_y_historico(self) -> None:
        """Compra nueva a 3 €/L: FIFO consume primero lote 2 €/L.

        Receta 0,5 L: si el lote antiguo (10 L @ 2 €) cubre → sigue 1 €.
        Si pedimos 11 L teórico en otra simulación, parte a 3 €.
        """
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
                    assert crear_producto(
                        "Aceite L",
                        "L",
                        None,
                        codigo="ACE-L",
                        tipo_articulo="consumible",
                    ).ok
                    p = data.productos[0]
                    # Lote inicial 10 L a 2 €/L
                    data.lotes.append(
                        LoteStock(
                            "l0",
                            p.id,
                            precio_total=20.0,
                            cantidad=10.0,
                            cantidad_restante=10.0,
                            fecha_compra=date(2026, 1, 1),
                        )
                    )
                    assert rec.crear_receta(
                        "Vinagreta",
                        [IngredienteReceta(p.id, 0.5)],
                        porciones_estandar=1,
                    ).ok
                    snap["pid"] = p.id
                    snap["rid"] = data.recetas[0].id
                    with patch(
                        "app.core.services.receta_service.get_data", return_value=data
                    ):
                        v0 = valorar_receta(snap["rid"])
                        self.assertEqual(v0.coste_total, 1.0)
                    ctx = _ctx(data)
                    assert prv.crear_proveedor("Prov", codigo="PR", ctx=ctx).ok
                    g = compra.guardar_borrador(
                        data,
                        tipo="albaran",
                        proveedor_id=data.proveedores[0].id,
                        lineas=[
                            {
                                "producto_id": p.id,
                                "client_line_key": "k1",
                                "cantidad_compra": "5",
                                "unidad_compra": "L",
                                "unidad_inventario": "L",
                                "precio_unitario_compra": "3",
                                "impuesto_porcentaje": "0",
                            }
                        ],
                    )
                    self.assertTrue(g.ok, g.mensaje)
                    snap["doc"] = g.documento.id
                return data

            transactional_update_appdata(path, seed)
            data = read_appdata_json(path)
            doc = next(d for d in data.documentos if d.id == snap["doc"])
            h = compra.construir_hash_documento(doc)
            conf = compra.confirmar_compra(
                doc.id,
                confirmacion_id=str(uuid.uuid4()),
                contenido_hash=h,
                json_path=path,
            )
            self.assertTrue(conf.ok, conf.mensaje)
            after = read_appdata_json(path)
            with patch("app.core.services.receta_service.get_data", return_value=after):
                # 0,5 L sigue del lote antiguo @ 2 € → 1 € (FIFO)
                v1 = valorar_receta(snap["rid"])
                self.assertEqual(v1.coste_total, 1.0)
                # simular consumo grande: 11 L → 10*2 + 1*3 = 23
                sim = rec.simular_receta(snap["rid"], porciones_simuladas=22)
                # standard 1 → factor 22 → 0.5*22 = 11 L
                self.assertTrue(sim.ok)
                self.assertAlmostEqual(sim.coste_total, 23.0, places=2)


if __name__ == "__main__":
    unittest.main()
