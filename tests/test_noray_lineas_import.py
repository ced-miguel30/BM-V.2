"""Tests importación Excel Noray → compra / stock."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from openpyxl import Workbook

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import clear_test_session
from app.core.models import Ubicacion
from app.core.services.noray_lineas_import_service import (
    MATCH_CONFLICTO,
    MATCH_OK,
    MATCH_REVISAR,
    MATCH_SIN,
    emparejar_lineas_noray,
    parsear_excel_lineas_noray,
)
from app.core.services.persistencia_appdata import transactional_update_appdata
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
)
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import LOGIN_DIR, PASS_DIR, write_browser_fixture

SAMPLES = Path(__file__).resolve().parent.parent / "docs" / "aprender a leer"


def _write_noray_xlsx(
    path: Path,
    *,
    rows: list[tuple] | None = None,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(
        [
            "Tipo",
            "Nº",
            "Descripción",
            "Cód. almacén",
            "Cantidad",
            "Cód. unidad medida",
            "Coste unit. directo",
            "% IVA",
            "Fecha recepción esperada",
        ]
    )
    if rows is None:
        rows = [
            (
                "Artículo",
                "C00009901",
                "Pan UI",
                "ECONOMATO",
                4,
                "Ud",
                1.25,
                0,
                date(2026, 8, 20),
            ),
            (
                "Artículo",
                "C00009902",
                "Producto inexistente XYZ",
                "DESAYUNO",
                2,
                "Ud",
                3.0,
                0,
                date(2026, 8, 20),
            ),
        ]
    for row in rows:
        ws.append(list(row))
    wb.save(path)
    wb.close()


class TestNorayParseService(unittest.TestCase):
    def test_parse_minimal_xlsx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lineas.xlsx"
            _write_noray_xlsx(path)
            r = parsear_excel_lineas_noray(path)
            self.assertTrue(r.ok, r.mensaje)
            self.assertEqual(len(r.lineas), 2)
            self.assertEqual(r.lineas[0].codigo_articulo, "C00009901")
            self.assertEqual(float(r.lineas[0].cantidad), 4.0)
            self.assertEqual(float(r.lineas[0].coste_unitario), 1.25)
            self.assertEqual(r.lineas[0].almacen, "ECONOMATO")

    def test_parse_sample_docs_si_existen(self) -> None:
        for name in ("Líneas (3).xlsx", "Líneas (4).xlsx"):
            path = SAMPLES / name
            if not path.exists():
                self.skipTest(f"Sin muestra {name}")
            r = parsear_excel_lineas_noray(path)
            self.assertTrue(r.ok, r.mensaje)
            self.assertGreater(len(r.lineas), 0)


class _NorayAdminHarness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.json_path = Path(self._tmp.name) / "datos_hotel.json"
        write_browser_fixture(self.json_path)
        reset_container()
        clear_test_session()
        set_demo_file_override(None)
        configure_for_flet(data_path=self.json_path)

        def _seed(data):
            pan = next(p for p in data.productos if p.id == "bp_pan")
            pan.codigo = "C00009901"
            leche = next(p for p in data.productos if p.id == "bp_leche")
            leche.codigo = "C00008888"
            if not getattr(data, "ubicaciones", None):
                data.ubicaciones = []
            data.ubicaciones.append(
                Ubicacion("ubi_eco_test", "Economato", True, codigo="ECO")
            )
            data.ubicaciones.append(
                Ubicacion("ubi_coc_test", "Cocina", True, codigo="COC")
            )
            return data

        transactional_update_appdata(self.json_path, _seed)
        from app.core.storage.session_store import reload_from_disk

        reload_from_disk()
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        reset_container()
        clear_test_session()
        set_demo_file_override(None)
        restore_harness_session()
        self._tmp.cleanup()
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def _login(self) -> TerminalAdministracionPresenter:
        p = TerminalAdministracionPresenter()
        s = p.login(LOGIN_DIR, PASS_DIR)
        self.assertTrue(s.session.authenticated, s.feedback.mensaje if s.feedback else "")
        return p


class TestNorayMatchLogic(_NorayAdminHarness):
    def test_nombre_primero_codigo_verifica_ok(self) -> None:
        data = get_container().app_data_store.get()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.xlsx"
            _write_noray_xlsx(
                path,
                rows=[
                    (
                        "Artículo",
                        "C00009901",
                        "Pan UI",
                        "ECONOMATO",
                        1,
                        "Ud",
                        1.0,
                        0,
                        date(2026, 8, 20),
                    )
                ],
            )
            parsed = parsear_excel_lineas_noray(path)
            matches = emparejar_lineas_noray(data, parsed.lineas)
            self.assertEqual(matches[0].estado, MATCH_OK)
            self.assertEqual(matches[0].producto_id, "bp_pan")

    def test_nombre_ok_codigo_distinto_conflicto(self) -> None:
        data = get_container().app_data_store.get()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conf.xlsx"
            # Nombre Pan UI pero código de Leche
            _write_noray_xlsx(
                path,
                rows=[
                    (
                        "Artículo",
                        "C00008888",
                        "Pan UI",
                        "ECONOMATO",
                        1,
                        "Ud",
                        1.0,
                        0,
                        date(2026, 8, 20),
                    )
                ],
            )
            parsed = parsear_excel_lineas_noray(path)
            matches = emparejar_lineas_noray(data, parsed.lineas)
            self.assertEqual(matches[0].estado, MATCH_CONFLICTO)
            self.assertEqual(matches[0].producto_id, "bp_pan")

    def test_solo_codigo_es_revisar(self) -> None:
        data = get_container().app_data_store.get()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cod.xlsx"
            _write_noray_xlsx(
                path,
                rows=[
                    (
                        "Artículo",
                        "C00009901",
                        "Nombre totalmente distinto ZZ",
                        "ECONOMATO",
                        1,
                        "Ud",
                        1.0,
                        0,
                        date(2026, 8, 20),
                    )
                ],
            )
            parsed = parsear_excel_lineas_noray(path)
            matches = emparejar_lineas_noray(data, parsed.lineas)
            self.assertEqual(matches[0].estado, MATCH_REVISAR)
            self.assertEqual(matches[0].producto_id, "bp_pan")


class TestNorayImportPresenter(_NorayAdminHarness):
    def test_cargar_excel_incluye_sin_match(self) -> None:
        p = self._login()
        xlsx = Path(self._tmp.name) / "noray.xlsx"
        _write_noray_xlsx(xlsx)
        s = p.cargar_excel_noray(str(xlsx))
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertEqual(len(s.compra_lineas), 2)
        self.assertEqual(s.compra_lineas[0].producto_id, "bp_pan")
        self.assertEqual(s.compra_lineas[0].match_estado, "ok")
        self.assertEqual(s.compra_lineas[1].match_estado, "sin_match")
        self.assertEqual(s.compra_lineas[0].ubicacion_destino_id, "ubi_eco_test")
        self.assertAlmostEqual(s.compra_lineas[0].precio_unitario, 1.25)

    def test_crear_producto_desde_linea_sin_match(self) -> None:
        p = self._login()
        xlsx = Path(self._tmp.name) / "noray_crear.xlsx"
        _write_noray_xlsx(xlsx)
        p.cargar_excel_noray(str(xlsx))
        s = p.crear_producto_desde_linea_noray(1)
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        ln = s.compra_lineas[1]
        self.assertEqual(ln.match_estado, "ok")
        self.assertTrue(ln.producto_id)
        self.assertEqual(ln.codigo_noray, "C00009902")
        data = get_container().app_data_store.get()
        prod = next(x for x in data.productos if x.id == ln.producto_id)
        self.assertEqual((prod.codigo or "").strip(), "C00009902")

    def test_verificar_linea_revisar(self) -> None:
        p = self._login()
        xlsx = Path(self._tmp.name) / "rev.xlsx"
        _write_noray_xlsx(
            xlsx,
            rows=[
                (
                    "Artículo",
                    "C00009901",
                    "Nombre totalmente distinto ZZ",
                    "ECONOMATO",
                    2,
                    "Ud",
                    1.0,
                    0,
                    date(2026, 8, 20),
                )
            ],
        )
        s = p.cargar_excel_noray(str(xlsx))
        self.assertEqual(s.compra_lineas[0].match_estado, "revisar")
        s = p.confirmar_match_linea_compra(0)
        self.assertTrue(s.feedback and s.feedback.ok)
        self.assertEqual(s.compra_lineas[0].match_estado, "ok")

    def test_confirmar_import_suma_stock_y_lote(self) -> None:
        p = self._login()
        s = p.crear_proveedor("Prov Noray", "PRV-NORAY-01")
        self.assertTrue(s.feedback and s.feedback.ok)
        prov = next(x for x in s.proveedores if x.codigo == "PRV-NORAY-01")
        data0 = get_container().app_data_store.get()
        stock0 = sum(
            float(l.cantidad_restante)
            for l in data0.lotes
            if l.producto_id == "bp_pan"
        )
        n0 = len([l for l in data0.lotes if l.producto_id == "bp_pan"])

        xlsx = Path(self._tmp.name) / "noray2.xlsx"
        _write_noray_xlsx(xlsx)
        p.cargar_excel_noray(str(xlsx))
        # Quitar línea sin match (no resuelta)
        p.quitar_linea_compra(1)
        p.set_compra_cabecera(prov.id, "NORAY-TEST-1", "albaran")
        s = p.confirmar_compra_borrador()
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")

        data1 = get_container().app_data_store.get()
        stock1 = sum(
            float(l.cantidad_restante)
            for l in data1.lotes
            if l.producto_id == "bp_pan"
        )
        n1 = len([l for l in data1.lotes if l.producto_id == "bp_pan"])
        self.assertEqual(n1, n0 + 1)
        self.assertAlmostEqual(stock1, stock0 + 4.0, places=4)
        docs = [
            d
            for d in (data1.documentos or [])
            if getattr(d, "referencia_externa", None) == "NORAY-TEST-1"
        ]
        self.assertEqual(len(docs), 1)
        ln = docs[0].lineas[0]
        self.assertEqual(ln.ubicacion_destino_id, "ubi_eco_test")


if __name__ == "__main__":
    unittest.main()
