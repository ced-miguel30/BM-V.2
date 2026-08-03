"""Fase 5 — espacios de trabajo (lógica pura de navegación).

No prueba la UI Streamlit completa. Verifica matriz, deep-links y
ausencia de dependencia de Streamlit / persistencia.

Ejecutar:

    py -m unittest tests.test_fase5_espacios -v
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application import espacios as esp


class TestFase5Espacios(unittest.TestCase):
    def test_01_secciones_registro(self) -> None:
        self.assertEqual(
            esp.secciones_operativas(esp.ESPACIO_REGISTRO),
            (esp.SECCION_REGISTROS,),
        )
        self.assertEqual(
            esp.secciones_visibles(esp.ESPACIO_REGISTRO),
            (esp.SECCION_REGISTROS, esp.SECCION_CONFIGURACION),
        )

    def test_02_secciones_gestor(self) -> None:
        self.assertEqual(
            esp.secciones_operativas(esp.ESPACIO_GESTOR),
            (esp.SECCION_DASHBOARD, esp.SECCION_ANALISIS),
        )

    def test_03_secciones_inventario(self) -> None:
        self.assertEqual(
            esp.secciones_operativas(esp.ESPACIO_INVENTARIO),
            (esp.SECCION_STOCK, esp.SECCION_RECETAS),
        )

    def test_04_configuracion_global(self) -> None:
        self.assertIn(esp.SECCION_CONFIGURACION, esp.SECCIONES_GLOBALES)
        for espacio in esp.ESPACIOS_ORDEN:
            self.assertIn(esp.SECCION_CONFIGURACION, esp.secciones_visibles(espacio))
        self.assertIsNone(esp.espacio_para_seccion(esp.SECCION_CONFIGURACION))

    def test_05_espacio_desconocido_controlado(self) -> None:
        self.assertEqual(esp.normalizar_espacio(None), esp.ESPACIO_DEFAULT)
        self.assertEqual(esp.normalizar_espacio("no-existe"), esp.ESPACIO_DEFAULT)
        self.assertEqual(esp.ESPACIO_DEFAULT, esp.ESPACIO_GESTOR)
        self.assertEqual(
            esp.secciones_operativas("xyz"),
            esp.SECCIONES_POR_ESPACIO[esp.ESPACIO_GESTOR],
        )

    def test_06_registros_pertenece_a_registro(self) -> None:
        self.assertEqual(
            esp.espacio_para_seccion(esp.SECCION_REGISTROS),
            esp.ESPACIO_REGISTRO,
        )

    def test_07_dashboard_analisis_pertenecen_a_gestor(self) -> None:
        self.assertEqual(
            esp.espacio_para_seccion(esp.SECCION_DASHBOARD),
            esp.ESPACIO_GESTOR,
        )
        self.assertEqual(
            esp.espacio_para_seccion(esp.SECCION_ANALISIS),
            esp.ESPACIO_GESTOR,
        )

    def test_08_stock_recetas_pertenecen_a_inventario(self) -> None:
        self.assertEqual(
            esp.espacio_para_seccion(esp.SECCION_STOCK),
            esp.ESPACIO_INVENTARIO,
        )
        self.assertEqual(
            esp.espacio_para_seccion(esp.SECCION_RECETAS),
            esp.ESPACIO_INVENTARIO,
        )

    def test_09_configuracion_no_fuerza_cambio_espacio(self) -> None:
        estado = esp.aplicar_seccion_pendiente(
            esp.ESPACIO_REGISTRO,
            esp.SECCION_REGISTROS,
            esp.SECCION_CONFIGURACION,
        )
        self.assertEqual(estado.espacio, esp.ESPACIO_REGISTRO)
        self.assertEqual(estado.seccion, esp.SECCION_CONFIGURACION)
        self.assertFalse(estado.destino_desconocido)

    def test_10_deeplink_registro_a_stock(self) -> None:
        estado = esp.resolver_navegacion(
            espacio_actual=esp.ESPACIO_REGISTRO,
            seccion_actual=esp.SECCION_REGISTROS,
            seccion_pendiente=esp.SECCION_STOCK,
        )
        self.assertEqual(estado.espacio, esp.ESPACIO_INVENTARIO)
        self.assertEqual(estado.seccion, esp.SECCION_STOCK)

    def test_11_deeplink_inventario_a_dashboard(self) -> None:
        estado = esp.resolver_navegacion(
            espacio_actual=esp.ESPACIO_INVENTARIO,
            seccion_actual=esp.SECCION_STOCK,
            seccion_pendiente=esp.SECCION_DASHBOARD,
        )
        self.assertEqual(estado.espacio, esp.ESPACIO_GESTOR)
        self.assertEqual(estado.seccion, esp.SECCION_DASHBOARD)

    def test_12_seccion_invalida_al_cambiar_espacio(self) -> None:
        estado = esp.aplicar_cambio_espacio(
            esp.ESPACIO_INVENTARIO,
            esp.SECCION_DASHBOARD,
        )
        self.assertEqual(estado.espacio, esp.ESPACIO_INVENTARIO)
        self.assertEqual(estado.seccion, esp.SECCION_STOCK)

    def test_13_configuracion_se_conserva_al_cambiar_espacio(self) -> None:
        estado = esp.aplicar_cambio_espacio(
            esp.ESPACIO_INVENTARIO,
            esp.SECCION_CONFIGURACION,
        )
        self.assertEqual(estado.espacio, esp.ESPACIO_INVENTARIO)
        self.assertEqual(estado.seccion, esp.SECCION_CONFIGURACION)

    def test_14_destino_pendiente_desconocido_sin_bucle(self) -> None:
        a = esp.resolver_navegacion(
            espacio_actual=esp.ESPACIO_GESTOR,
            seccion_actual=esp.SECCION_DASHBOARD,
            seccion_pendiente="SecciónQueNoExiste",
        )
        b = esp.resolver_navegacion(
            espacio_actual=a.espacio,
            seccion_actual=a.seccion,
            seccion_pendiente="SecciónQueNoExiste",
        )
        self.assertTrue(a.destino_desconocido)
        self.assertEqual(a.espacio, esp.ESPACIO_GESTOR)
        self.assertEqual(a.seccion, esp.SECCION_DASHBOARD)
        self.assertEqual((a.espacio, a.seccion), (b.espacio, b.seccion))

    def test_15_logica_pura_no_importa_streamlit(self) -> None:
        path = ROOT / "app" / "core" / "application" / "espacios.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        self.assertFalse(
            any(name == "streamlit" or name.startswith("streamlit.") for name in imports),
            f"espacios.py no debe importar Streamlit; imports={imports}",
        )
        mod = sys.modules["app.core.application.espacios"]
        self.assertFalse(
            any(k == "st" or k == "streamlit" or str(k).startswith("streamlit") for k in vars(mod)),
        )

    def test_16_navegacion_no_modifica_datos_ni_persistencia(self) -> None:
        path = ROOT / "app" / "core" / "application" / "espacios.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        prohibidos = (
            "app.core.storage.session_store",
            "app.data.serializers",
            "app.core.models",
            "streamlit",
        )
        for token in prohibidos:
            self.assertFalse(
                any(name == token or name.startswith(token + ".") for name in imports),
                f"espacios.py no debe importar {token}; imports={imports}",
            )

        names_called: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    names_called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    names_called.add(node.func.attr)
        for fn in ("persist_data", "get_data", "init_data"):
            self.assertNotIn(fn, names_called)

        before = set(sys.modules)
        esp.resolver_navegacion(
            espacio_actual=esp.ESPACIO_REGISTRO,
            seccion_actual=esp.SECCION_REGISTROS,
            seccion_pendiente=esp.SECCION_STOCK,
        )
        nuevos = set(sys.modules) - before
        self.assertFalse(
            any("session_store" in m or "serializers" in m for m in nuevos),
            f"resolver_navegacion no debe cargar persistencia; nuevos={nuevos}",
        )


if __name__ == "__main__":
    unittest.main()
