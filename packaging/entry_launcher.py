"""Entrypoint empaquetable del launcher Flet BM‑V.2."""

from __future__ import annotations

import os
import sys


def _ensure_root_on_path() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root not in sys.path:
        sys.path.insert(0, root)


def main() -> None:
    _ensure_root_on_path()
    os.environ.setdefault("BM_FLET_TERMINAL", "launcher")
    from app.presentation.flet.main_launcher import main as flet_main

    flet_main()


if __name__ == "__main__":
    import multiprocessing as _mp

    _mp.freeze_support()
    # Workers aislados: no Flet / no WriterLock (evita tumbar la UI).
    if len(sys.argv) >= 4 and sys.argv[1] == "--bm-tpv-ocr":
        _ensure_root_on_path()
        from app.core.services.tpv_ocr_cli import run_ocr_worker

        raise SystemExit(run_ocr_worker(sys.argv[2], sys.argv[3]))
    if len(sys.argv) >= 5 and sys.argv[1] == "--bm-tpv-import":
        _ensure_root_on_path()
        from app.core.services.tpv_ocr_cli import run_import_worker

        raise SystemExit(run_import_worker(sys.argv[2], sys.argv[3], sys.argv[4]))
    if len(sys.argv) >= 2 and sys.argv[1] == "--bm-import-excel":
        _ensure_root_on_path()
        from app.core.services.registro_excel_cli import run_import_excel_cli

        raise SystemExit(run_import_excel_cli(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "--bm-build-excel":
        _ensure_root_on_path()
        from app.core.services.registro_excel_cli import run_build_plantilla_cli

        raise SystemExit(run_build_plantilla_cli(sys.argv[2:]))
    main()
