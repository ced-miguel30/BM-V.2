"""Guard arquitectónico: fronteras sin Streamlit/páginas/UI."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module.split(".")[0])
                found.add(node.module)
    return found


def _forbidden_hits(path: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    hits = []
    imports = _imports_of(path)
    text = path.read_text(encoding="utf-8")
    for pref in forbidden_prefixes:
        if pref in imports or any(i == pref or i.startswith(pref + ".") for i in imports):
            hits.append(f"import:{pref}")
        if "session_state" in text and pref == "session_state":
            # solo flag genérico cuando se pida session_state
            hits.append("session_state")
    return hits


class TestArchitectureBoundaries(unittest.TestCase):
    FORBIDDEN_UI = ("streamlit", "app.pages", "app.ui", "app.presentation")

    def test_models_no_streamlit_pages_ui(self) -> None:
        for path in _py_files(APP / "core" / "models"):
            imports = _imports_of(path)
            for bad in self.FORBIDDEN_UI:
                self.assertFalse(
                    any(i == bad or i.startswith(bad + ".") for i in imports),
                    f"{path.relative_to(ROOT)} importa {bad}",
                )

    def test_application_no_streamlit_pages_ui(self) -> None:
        for path in _py_files(APP / "core" / "application"):
            imports = _imports_of(path)
            for bad in self.FORBIDDEN_UI:
                self.assertFalse(
                    any(i == bad or i.startswith(bad + ".") for i in imports),
                    f"{path.relative_to(ROOT)} importa {bad}",
                )

    def test_reusable_services_no_session_state(self) -> None:
        """Servicios reutilizables no deben tocar session_state ni Streamlit."""
        services = APP / "core" / "services"
        # session_store ya no es servicio; listado completo under services
        for path in _py_files(services):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "session_state",
                text,
                f"{path.relative_to(ROOT)} usa session_state",
            )
            imports = _imports_of(path)
            self.assertNotIn("streamlit", imports)
            self.assertFalse(any(i.startswith("streamlit") for i in imports))

    def test_pages_do_not_write_json_directly(self) -> None:
        """Páginas no deben json.dump / open escritura a datos_hotel."""
        for path in list(_py_files(APP / "pages")) + list(_py_files(APP / "ui")):
            text = path.read_text(encoding="utf-8")
            # Permitir Path para logos/componentes; prohibir dump del demo
            self.assertNotIn("datos_hotel.json", text, str(path))
            if "json.dump" in text or "json.dumps" in text and "save" in text.lower():
                # Allow comments; flag real dump calls
                tree = ast.parse(text, filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute) and node.attr == "dump":
                        self.fail(f"{path.relative_to(ROOT)} usa json.dump")

    def test_streamlit_adapters_only_under_presentation(self) -> None:
        """Adaptadores con import streamlit no viven en models/application."""
        for folder in (APP / "core" / "models", APP / "core" / "application"):
            for path in _py_files(folder):
                imports = _imports_of(path)
                self.assertNotIn("streamlit", imports)

    def test_session_store_is_shim_without_streamlit(self) -> None:
        path = APP / "core" / "storage" / "session_store.py"
        imports = _imports_of(path)
        self.assertNotIn("streamlit", imports)
        text = path.read_text(encoding="utf-8")
        self.assertIn("Shim", text)
        self.assertIn("get_container", text)


if __name__ == "__main__":
    unittest.main()
