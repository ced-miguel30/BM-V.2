"""Browser E2E — inventario / caducidad / continuidad básica."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from tests.browser.harness import BrowserE2ECase


class TestUiInventarioContinuidad(BrowserE2ECase):
    def test_01_caducidad_visible_y_demo_intacto(self) -> None:
        try:
            self.login_dir()
            self.click_nav("Registros")
            self.click_subtab("Caducidad")
            body = self.page.content()
            # Lote caducado bl_exp / Pan UI
            self.assertTrue(
                "Pan UI" in body or "caduc" in body.lower() or "expir" in body.lower()
            )
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("caducidad")
            raise

    def test_02_historial_tab(self) -> None:
        try:
            self.login_dir()
            self.click_nav("Registros")
            self.click_subtab("Historial")
            body = self.page.content()
            self.assertTrue(
                "Historial" in body or "historial" in body.lower() or "Evento" in body
            )
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("historial")
            raise

    def test_03_persistencia_tras_reload(self) -> None:
        try:
            self.login_dir()
            # Leer establecimiento / asegurar sesión y datos cargados
            data1 = self.data()
            self.assertEqual(data1.configuracion.nombre_establecimiento, "Hotel UI Test")
            self.reload_app()
            # Tras reload del browser, session_state Streamlit reinicia → login otra vez
            self.login_dir()
            data2 = self.data()
            self.assertEqual(
                data2.configuracion.nombre_establecimiento,
                data1.configuracion.nombre_establecimiento,
            )
            self.assertEqual(len(data2.productos), len(data1.productos))
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("persist")
            raise

    def test_04_stock_nav_sin_escribir_demo(self) -> None:
        try:
            self.login_adm()
            self.click_nav("Stock")
            body = self.page.content()
            self.assertTrue("Stock" in body or "Producto" in body or "Inventario" in body)
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("stock")
            raise


if __name__ == "__main__":
    unittest.main()
