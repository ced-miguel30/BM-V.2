"""C1 — navegación de compras: único flujo visible «Compras y documentos».

No ejecuta Streamlit. Comprueba que F10–F12 y «Compras» (lote) no están
en la nav productiva; los renderers legacy permanecen en el módulo.

    python -m unittest tests.test_c1_compras_nav -v
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.pages import stock
from app.ui.theme import APP_VERSION, NAV_SECTIONS
from app.main import PAGES


class TestC1ComprasNav(unittest.TestCase):
    def test_unico_flujo_compras_visible(self) -> None:
        keys = list(stock._SUBTABS.keys())
        self.assertEqual(
            keys,
            [
                "Productos",
                stock.TAB_COMPRAS_DOCUMENTOS,
                "Documentos",
                "Inventario",
                "Traslados",
            ],
        )
        self.assertEqual(stock.TAB_COMPRAS_DOCUMENTOS, "Compras y documentos")
        self.assertNotIn("Albaranes", keys)
        self.assertNotIn("Facturas", keys)
        self.assertNotIn("Rectificativas", keys)
        self.assertNotIn("Compras", keys)
        self.assertNotIn("Registro 13.5", keys)

    def test_no_dos_controles_registrar_compra(self) -> None:
        """Solo una pestaña de registro operativo de compra en Stock."""
        compra_like = [
            k
            for k in stock._SUBTABS
            if "compra" in k.lower() or "albaran" in k.lower() or "factura" in k.lower()
        ]
        self.assertEqual(compra_like, [stock.TAB_COMPRAS_DOCUMENTOS])

    def test_legacy_renderers_retenidos_no_visibles(self) -> None:
        self.assertIn("Albaranes", stock._SUBTABS_LEGACY_HIDDEN)
        self.assertIn("Facturas", stock._SUBTABS_LEGACY_HIDDEN)
        self.assertIn("Rectificativas", stock._SUBTABS_LEGACY_HIDDEN)
        self.assertIn("Compras", stock._SUBTABS_LEGACY_HIDDEN)
        self.assertTrue(callable(stock._render_tab_albaranes))
        self.assertTrue(callable(stock._render_tab_facturas))
        self.assertTrue(callable(stock._render_tab_rectificativas))
        self.assertTrue(callable(stock._render_tab_compras))
        for name in ("Albaranes", "Facturas", "Rectificativas", "Compras"):
            self.assertNotIn(name, stock._SUBTABS)

    def test_remap_session_legacy_a_canonico(self) -> None:
        fake_st = MagicMock()
        for legacy in ("Albaranes", "Facturas", "Rectificativas", "Compras", "Registro 13.5"):
            store = {"stock_subtab": legacy}
            fake_st.session_state = store
            with patch.object(stock, "st", fake_st):
                stock._normalizar_stock_subtab_session()
            self.assertEqual(store["stock_subtab"], stock.TAB_COMPRAS_DOCUMENTOS)

    def test_lazy_import_registro_compras(self) -> None:
        import inspect

        src = inspect.getsource(stock._render_tab_registro_135)
        self.assertIn("registro_compras_135", src)
        import app.ui.registro_compras_135 as reg

        self.assertTrue(callable(reg.render_registro_compras_135))
        # Import del módulo stock no debe fallar (renderers legacy accesibles).
        self.assertTrue(callable(stock._render_tab_albaranes))

    def test_nav_general_intacta(self) -> None:
        self.assertIn("Stock", NAV_SECTIONS)
        self.assertEqual(NAV_SECTIONS["Stock"], "stock")
        self.assertIn("stock", PAGES)
        self.assertEqual(PAGES["stock"], stock.render)

    def test_version_refleja_flujo_unificado(self) -> None:
        self.assertIn("Compras y documentos", APP_VERSION)
        self.assertNotIn("Albaranes", APP_VERSION)
        self.assertNotIn("Facturas", APP_VERSION)
        self.assertNotIn("Rectificativas", APP_VERSION)

    def test_canonico_apunta_a_registro_135(self) -> None:
        self.assertIs(
            stock._SUBTABS[stock.TAB_COMPRAS_DOCUMENTOS],
            stock._render_tab_registro_135,
        )


if __name__ == "__main__":
    unittest.main()
