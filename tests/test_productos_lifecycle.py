"""Productos — lifecycle controlado (activo, edición, protecciones)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.auth.session import clear_test_session, set_test_session
from app.core.models import (
    AppData,
    IngredienteReceta,
    LoteStock,
    Producto,
    Receta,
    UnidadProducto,
)
from app.core.services.stock_service import (
    crear_producto,
    desactivar_producto,
    editar_producto,
    eliminar_producto,
    mapa_productos,
    reactivar_producto,
)
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


class TestProductosLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.demo_before = DEMO_FILE.read_bytes()
        self.data = AppData()
        self._p_get = patch(
            "app.core.services.stock_service.get_data", return_value=self.data
        )
        self._p_persist = patch(
            "app.core.services.stock_service.persist_data", side_effect=lambda d: d
        )
        self._p_get.start()
        self._p_persist.start()
        self.addCleanup(self._p_get.stop)
        self.addCleanup(self._p_persist.stop)

    def tearDown(self) -> None:
        self.assertEqual(DEMO_FILE.read_bytes(), self.demo_before)
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_01_crear_producto_valido(self) -> None:
        r = crear_producto(
            "Aceite Oliva", "L", 1.5, codigo="ACE-01", tipo_articulo="consumible"
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.productos), 1)
        self.assertTrue(self.data.productos[0].activo)
        self.assertEqual(self.data.productos[0].stock_minimo, 1.5)

    def test_02_rechazar_nombre_duplicado_equivalente(self) -> None:
        self.assertTrue(
            crear_producto(
                "Pan Blanco", "Ud", None, codigo="PAN-01", tipo_articulo="consumible"
            ).ok
        )
        r = crear_producto(
            "  pan   blanco ", "Ud", None, codigo="PAN-02", tipo_articulo="consumible"
        )
        self.assertFalse(r.ok)
        self.assertIn("existe", r.mensaje.lower())

    def test_03_editar_campos_seguros(self) -> None:
        crear_producto("Leche", "L", 2, codigo="LEC-01", tipo_articulo="consumible")
        pid = self.data.productos[0].id
        r = editar_producto(pid, nombre="Leche Entera", stock_minimo=3.5)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(self.data.productos[0].nombre, "Leche Entera")
        self.assertEqual(self.data.productos[0].stock_minimo, 3.5)

    def test_04_rechazar_stock_minimo_negativo(self) -> None:
        crear_producto("Harina", "Kg", None, codigo="HAR-01", tipo_articulo="consumible")
        r = editar_producto(self.data.productos[0].id, stock_minimo=-1)
        self.assertFalse(r.ok)
        self.assertIn("negativo", r.mensaje.lower())

    def test_05_desactivar_producto(self) -> None:
        crear_producto("Azúcar", "Kg", None, codigo="AZU-01", tipo_articulo="consumible")
        pid = self.data.productos[0].id
        self.assertTrue(desactivar_producto(pid).ok)
        self.assertFalse(self.data.productos[0].activo)

    def test_06_inactivo_no_en_selecciones_nuevas(self) -> None:
        crear_producto("Sal", "Kg", None, codigo="SAL-01", tipo_articulo="consumible")
        pid = self.data.productos[0].id
        desactivar_producto(pid)
        self.assertEqual(mapa_productos(self.data, solo_activos=True), {})
        self.assertIn("Sal", mapa_productos(self.data, solo_activos=False))

    def test_07_inactivo_conservado_en_historico(self) -> None:
        crear_producto("Vinagre", "L", None, codigo="VIN-01", tipo_articulo="consumible")
        p = self.data.productos[0]
        self.data.lotes.append(
            LoteStock("l1", p.id, 10.0, 5.0, 5.0)
        )
        desactivar_producto(p.id)
        self.assertEqual(self.data.lotes[0].producto_id, p.id)
        self.assertFalse(p.activo)

    def test_08_bloquear_eliminacion_referenciado(self) -> None:
        crear_producto("Huevo", "Ud", None, codigo="HUE-01", tipo_articulo="consumible")
        p = self.data.productos[0]
        self.data.recetas.append(
            Receta("r1", "Tortilla", [IngredienteReceta(p.id, 2)], porciones_estandar=1)
        )
        r = eliminar_producto(p.id)
        self.assertFalse(r.ok)
        self.assertIn("histórico", r.mensaje.lower())
        self.assertEqual(len(self.data.productos), 1)

    def test_09_bloquear_cambio_unidad_con_historico(self) -> None:
        crear_producto("Aceite", "L", None, codigo="ACE-02", tipo_articulo="consumible")
        p = self.data.productos[0]
        self.data.lotes.append(LoteStock("l2", p.id, 12.0, 6.0, 6.0))
        r = editar_producto(p.id, unidad="Kg")
        self.assertFalse(r.ok)
        self.assertIn("unidad", r.mensaje.lower())
        self.assertEqual(p.unidad, UnidadProducto.L)

    def test_09b_cambio_unidad_sin_historico(self) -> None:
        crear_producto("Temp", "Ud", None, codigo="TMP-01", tipo_articulo="consumible")
        p = self.data.productos[0]
        r = editar_producto(p.id, unidad="Kg")
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(p.unidad, UnidadProducto.KG)

    def test_20_demo_no_escrito(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).joinpath("x.json").write_text("{}", encoding="utf-8")
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)


if __name__ == "__main__":
    unittest.main()
