"""Runner de tests de navegador Streamlit (Playwright).

No forma parte de ``python run_tests.py`` (suite canónica).
Requiere: ``python -m pip install playwright`` y ``python -m playwright install chromium``.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    os.environ["BM_TEST_ISOLATION"] = "1"
    # Import paquete tests (red de seguridad demo)
    import tests  # noqa: F401

    loader = unittest.TestLoader()
    suite = loader.discover(
        str(ROOT / "tests" / "browser"),
        pattern="test_ui_*.py",
        top_level_dir=str(ROOT),
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
