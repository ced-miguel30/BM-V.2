"""Importación productos desde Excel PRECIO."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.auth.session import clear_test_session, set_test_session
from app.core.models import AppData, ConfiguracionHotel
from app.core.services.productos_import_service import (
    COD_COCINA,
    COD_ECONOMATO,
    importar_productos_desde_excel,
    mapear_unidad_excel,
    mensaje_resumen,
)
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _xlsx_precio(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Productos"
    ws.append(
        [
            "Nº",
            "Descripción",
            "Inventario",
            "Unidad medida base",
            "Coste ajustado",
            "Coste unitario",
            "Cód. categoría producto",
            "Descripción 2",
        ]
    )
    # 101 cocina, stock>0
    ws.append(["C000101", "CARNE VACA TEST", 2.5, "KG", True, 10.0, "101", ""])
    # 102 desayuno cocina
    ws.append(["C000102", "CROISSANT TEST 30UD", 10, "UD", True, 0.5, "102", ""])
    # 104 bebida economato
    ws.append(["C000104", "AGUA SIN GAS TEST 1L", 20, "LT", True, 0.4, "104", ""])
    # stock 0 → producto sin lote
    ws.append(["C000105", "SALSA SETAS TEST", 0, "KG", True, 3.0, "105", ""])
    # sin coste → fallback 0.01
    ws.append(["C000106", "MANZANA TEST", 5, "KG", True, 0, "106", ""])
    # fuera de filtro (limpieza)
    ws.append(["C000201", "LIMPIAMETALES TEST", 1, "UD", True, 6.0, "201", ""])
    wb.save(path)


class TestProductosImportExcel(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.demo_before = DEMO_FILE.read_bytes()
        self.data = AppData(
            configuracion=ConfiguracionHotel(
                "H",
                "EUR",
                ledger_activation_iso="2026-01-01T00:00:00",
                ledger_balance_mode="shadow",
            )
        )
        self._patches = [
            patch("app.core.services.stock_service.get_data", return_value=self.data),
            patch(
                "app.core.services.stock_service.persist_data",
                side_effect=lambda d: d,
            ),
            patch("app.core.services.catalogo_service.get_data", return_value=self.data),
            patch(
                "app.core.services.catalogo_service.persist_data",
                side_effect=lambda d: d,
            ),
            patch(
                "app.core.services.productos_import_service.get_data",
                return_value=self.data,
            ),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.xlsx = Path(self.tmp.name) / "precio.xlsx"
        _xlsx_precio(self.xlsx)

    def tearDown(self) -> None:
        self.assertEqual(DEMO_FILE.read_bytes(), self.demo_before)
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_mapear_unidad(self) -> None:
        self.assertEqual(mapear_unidad_excel("UD"), "Ud")
        self.assertEqual(mapear_unidad_excel("KG"), "Kg")
        self.assertEqual(mapear_unidad_excel("LT"), "L")

    def test_import_crea_ubicaciones_productos_lotes(self) -> None:
        r = importar_productos_desde_excel(self.xlsx)
        self.assertGreaterEqual(r.ubicaciones_creadas, 3)
        self.assertEqual(r.productos_creados, 5)
        self.assertEqual(r.lotes_creados, 4)  # 105 stock 0
        self.assertEqual(r.omitidos_filtro, 1)
        self.assertFalse(r.errores, mensaje_resumen(r))

        codes = {
            getattr(p, "codigo", None): p for p in self.data.productos
        }
        self.assertIn("C000101", codes)
        self.assertEqual(codes["C000101"].unidad.value if hasattr(codes["C000101"].unidad, "value") else codes["C000101"].unidad, "Kg")
        ubi_ids = {u.codigo: u.id for u in self.data.ubicaciones}
        self.assertEqual(codes["C000101"].ubicacion_ids, [ubi_ids[COD_COCINA]])
        self.assertEqual(codes["C000102"].servicios_disponibles, ["desayuno"])
        self.assertEqual(codes["C000104"].ubicacion_ids, [ubi_ids[COD_ECONOMATO]])
        self.assertTrue(codes["C000104"].es_bebida)

        lote_agua = next(l for l in self.data.lotes if l.producto_id == codes["C000104"].id)
        self.assertEqual(lote_agua.cantidad_restante, 20)
        self.assertEqual(lote_agua.precio_total, 8.0)  # 0.4 * 20

        lote_manzana = next(l for l in self.data.lotes if l.producto_id == codes["C000106"].id)
        self.assertEqual(lote_manzana.precio_total, 0.01)

        self.assertTrue(any(m.ubicacion_destino_id == ubi_ids[COD_COCINA] for m in self.data.movimientos))

    def test_idempotente(self) -> None:
        r1 = importar_productos_desde_excel(self.xlsx)
        r2 = importar_productos_desde_excel(self.xlsx)
        self.assertEqual(r1.productos_creados, 5)
        self.assertEqual(r2.productos_creados, 0)
        self.assertEqual(r2.omitidos_existentes, 5)
        self.assertEqual(len(self.data.productos), 5)


if __name__ == "__main__":
    unittest.main()
