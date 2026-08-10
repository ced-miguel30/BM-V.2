"""Runner canónico de tests (Fase A1).

Activa el aislamiento del JSON demo y ejecuta unittest discover.
Excluye ``tests/browser`` (Playwright): usar ``python run_browser_tests.py``.
"""

from __future__ import annotations

import os
import unittest


def main() -> int:
    os.environ["BM_TEST_ISOLATION"] = "1"
    # Carga el paquete tests (solo fija BM_TEST_ISOLATION; sin monkeypatch).
    import tests  # noqa: F401

    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_*.py", top_level_dir=".")
    filtered = unittest.TestSuite()

    def _walk(s: unittest.TestSuite) -> None:
        for item in s:
            if isinstance(item, unittest.TestSuite):
                _walk(item)
            else:
                mod = getattr(item, "__module__", "") or ""
                if mod.startswith("tests.browser"):
                    continue
                filtered.addTest(item)

    _walk(suite)
    result = unittest.TextTestRunner(verbosity=2).run(filtered)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
