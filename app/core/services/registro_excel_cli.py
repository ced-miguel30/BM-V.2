"""CLI import Excel operativo desde BM-Launcher (servidor sin .venv)."""

from __future__ import annotations

import sys
from pathlib import Path


def _prepare_import_modules() -> None:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass and meipass not in sys.path:
            sys.path.insert(0, meipass)
        return
    root = Path(__file__).resolve().parents[3]
    scripts = root / "scripts"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if scripts.is_dir() and str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


def run_import_excel_cli(extra_argv: list[str]) -> int:
    """Ejecuta import_registro_operativo_excel.main con argv extra."""
    _prepare_import_modules()

    saved = list(sys.argv)
    try:
        sys.argv = ["import_registro_operativo_excel"] + list(extra_argv)
        import import_registro_operativo_excel as imp

        return int(imp.main())
    finally:
        sys.argv = saved


def run_build_plantilla_cli(extra_argv: list[str]) -> int:
    _prepare_import_modules()

    saved = list(sys.argv)
    try:
        sys.argv = ["build_plantilla_desayuno_excel"] + list(extra_argv)
        import build_plantilla_desayuno_excel as gen

        return int(gen.main())
    finally:
        sys.argv = saved
