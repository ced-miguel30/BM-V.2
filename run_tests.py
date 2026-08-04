"""Runner canónico de tests (Fase A1).

Activa el aislamiento del JSON demo y ejecuta unittest discover.
"""

from __future__ import annotations

import os
import sys
import unittest


def main() -> int:
    os.environ["BM_TEST_ISOLATION"] = "1"
    # Carga el paquete tests (solo fija BM_TEST_ISOLATION; sin monkeypatch).
    import tests  # noqa: F401

    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_*.py", top_level_dir=".")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
