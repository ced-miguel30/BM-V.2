"""Browser E2E — autenticación, roles y terminales."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from tests.browser.fixtures_minimos import LOGIN_DIR, PASS_DIR
from tests.browser.harness import BrowserE2ECase


class TestUiAuth(BrowserE2ECase):
    def test_01_login_incorrecto(self) -> None:
        try:
            self.login(LOGIN_DIR, "WrongPass99")
            body = self.page.content()
            self.assertIn("Credenciales incorrectas", body)
            # Sigue en puerta de acceso
            self.assertGreater(
                self.page.get_by_role("button", name="Entrar").count(), 0
            )
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("login_ko")
            raise

    def test_02_login_logout_direccion(self) -> None:
        try:
            self.login_dir()
            self.assertGreater(
                self.page.get_by_role("button", name="Cerrar sesión").count(), 0
            )
            # Dirección ve Dashboard / Análisis
            content = self.page.content().lower()
            self.assertTrue(
                "dashboard" in content or "registros" in content or "stock" in content
            )
            self.logout()
            self.assertGreater(
                self.page.get_by_role("button", name="Entrar").count(), 0
            )
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("login_logout")
            raise

    def test_03_restaurante_sin_analisis_ni_config(self) -> None:
        try:
            self.login_rest()
            # Terminal restaurante catch-all: UI dedicada
            body = self.page.content()
            self.assertNotIn("Configuración", body)
            # Sin símbolo € de costes en cabeceras de gestoría (heurística)
            # El terminal no debe ofrecer Análisis
            self.assertNotIn("Análisis", body)
            self.logout()
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("rest_limits")
            raise

    def test_04_terminal_restaurante(self) -> None:
        try:
            self.open_terminal_restaurante()
            body = self.page.content()
            self.assertIn("Terminal Restaurante", body)
            self.assertNotIn("Análisis", body)
            self.logout()
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("term_rest")
            raise

    def test_05_terminal_inventario_sin_economicos(self) -> None:
        try:
            self.open_terminal_inventario()
            body = self.page.content()
            self.assertIn("Terminal Inventario", body)
            self.assertNotIn("Análisis", body)
            self.assertNotIn("Configuración", body)
            # Heurística: no gestionar costes
            self.assertNotIn("Gestor costes", body)
            self.logout()
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("term_inv")
            raise

    def test_06_admin_login(self) -> None:
        try:
            self.login_adm()
            self.assertGreater(
                self.page.get_by_role("button", name="Cerrar sesión").count(), 0
            )
            self.logout()
            self.assert_demo_intact()
        except Exception:
            self.on_fail_screenshot("admin")
            raise


if __name__ == "__main__":
    unittest.main()
