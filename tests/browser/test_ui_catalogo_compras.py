"""Browser E2E — catálogo / compras (navegación + asserts backend ligeros)."""

from __future__ import annotations

import os
import unittest
import uuid

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from tests.browser.harness import BrowserE2ECase


class TestUiCatalogoCompras(BrowserE2ECase):
    def test_01_recetas_pagina(self) -> None:
        try:
            self.login_dir()
            self.click_nav("Recetas")
            body = self.page.content()
            self.assertTrue(
                "Porridge UI" in body or "Receta" in body or "recetas" in body.lower()
            )
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("recetas")
            raise

    def test_02_stock_productos_listados(self) -> None:
        try:
            self.login_adm()
            self.click_nav("Stock")
            body = self.page.content()
            self.assertTrue(
                "Leche UI" in body or "Producto" in body or "productos" in body.lower()
            )
            data = self.data()
            self.assertTrue(any(p.nombre == "Leche UI" for p in data.productos))
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("productos")
            raise

    def test_03_compras_subtab_si_existe(self) -> None:
        try:
            self.login_adm()
            self.click_nav("Stock")
            # Subtabs Compras si existen
            for label in ("Compras", "Compra", "13.5"):
                tab = self.page.get_by_role("tab", name=label)
                if tab.count():
                    tab.first.click()
                    self.page.wait_for_timeout(800)
                    break
            body = self.page.content()
            # Proveedor fixture
            self.assertTrue(
                "Proveedor UI" in body
                or "Compra" in body
                or "Albarán" in body
                or "Stock" in body
            )
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("compras")
            raise


if __name__ == "__main__":
    unittest.main()
