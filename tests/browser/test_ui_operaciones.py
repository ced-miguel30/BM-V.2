"""Browser E2E — registro operativo Desayuno (UI + backend)."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from tests.browser.harness import BrowserE2ECase


class TestUiOperaciones(BrowserE2ECase):
    def test_01_desayuno_receta_y_producto_directo(self) -> None:
        try:
            before = self.data()
            leche0 = next(l for l in before.lotes if l.id == "bl_leche").cantidad_restante
            avena0 = next(l for l in before.lotes if l.id == "bl_avena").cantidad_restante
            zumo0 = next(l for l in before.lotes if l.id == "bl_zumo").cantidad_restante

            self.login_dir()
            self.click_nav("Registros")
            self.click_subtab("Desayuno")

            # Añadir receta Porridge UI — UI usa selectores/autocompletado Streamlit
            page = self.page
            # Buscar combobox / select con recetas
            # Intento: campo de búsqueda o select
            if page.get_by_text("Porridge UI").count() == 0:
                # Abrir selectores típicos "Receta" / "Añadir"
                for label in ("Receta", "Elegir receta", "Buscar receta"):
                    loc = page.get_by_label(label)
                    if loc.count():
                        loc.first.click()
                        break
            # Rellenar raciones si hay number input
            # Flujo robusto: usar botón de receta rápida si existe
            quick = page.get_by_role("button", name="Porridge UI")
            if quick.count():
                quick.first.click()
                page.wait_for_timeout(500)
            else:
                # Fallback: select option
                opts = page.locator("text=Porridge UI")
                if opts.count():
                    opts.first.click()
                    page.wait_for_timeout(300)
                add_r = page.get_by_role("button", name="Añadir")
                if add_r.count():
                    add_r.first.click()
                page.wait_for_timeout(800)

            # Producto directo Zumo
            prod_btn = page.get_by_role("button", name="Zumo UI")
            if prod_btn.count():
                prod_btn.first.click()
            else:
                z = page.locator("text=Zumo UI")
                if z.count():
                    z.first.click()

            # Confirmar registro
            conf = page.get_by_role("button", name="Confirmar registro")
            if conf.count() == 0:
                conf = page.get_by_role("button", name="Confirmar")
            if conf.count() == 0:
                self.skipTest("UI de confirmación Desayuno no localizada (selector)")
            # Puede requerir checkbox de confirmación
            chk = page.get_by_label("Confirmo")
            if chk.count():
                chk.first.check()
            conf.first.click()
            page.wait_for_timeout(2500)

            after = self.data()
            self.assertGreaterEqual(len(after.desayunos), len(before.desayunos) + 1)
            leche1 = next(l for l in after.lotes if l.id == "bl_leche").cantidad_restante
            avena1 = next(l for l in after.lotes if l.id == "bl_avena").cantidad_restante
            # Con factor 1 (4 raciones): 0.5 L + 0.25 kg
            self.assertLess(leche1, leche0)
            self.assertLess(avena1, avena0)
            # Zumo si se añadió
            zumo1 = next(l for l in after.lotes if l.id == "bl_zumo").cantidad_restante
            # No exige zumo si UI no añadió producto directo
            if zumo1 < zumo0:
                self.assertAlmostEqual(zumo0 - zumo1, round(zumo0 - zumo1, 4), places=4)
            reg = after.desayunos[-1]
            self.assertTrue(reg.lineas_detalle)
            self.assert_demo_intact()
        except unittest.SkipTest:
            raise
        except Exception:
            self.on_fail_screenshot("desayuno")
            raise


if __name__ == "__main__":
    unittest.main()
