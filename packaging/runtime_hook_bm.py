"""Runtime hook — datos productivos fuera del árbol del ejecutable."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_paths() -> None:
    # Carpeta del onedir / exe
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent

    # Instancia por defecto junto al usuario (nunca dentro del instalable reemplazable)
    local = Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
    instance = Path(os.environ.get("BM_INSTANCE_ROOT") or (local / "BM-V2-local"))
    instance.mkdir(parents=True, exist_ok=True)
    (instance / "data").mkdir(exist_ok=True)
    (instance / "backups").mkdir(exist_ok=True)
    (instance / "logs").mkdir(exist_ok=True)
    (instance / "exports").mkdir(exist_ok=True)

    data_file = instance / "data" / "datos_hotel.json"
    os.environ.setdefault("BM_DEPLOY_PROFILE", "hotel")
    os.environ.setdefault("BM_INSTANCE_ROOT", str(instance))
    if not data_file.exists():
        # Primera ejecución: copiar demo de referencia embebido si existe
        candidates = [
            base / "data" / "demo" / "datos_hotel.json",
            base / "_internal" / "data" / "demo" / "datos_hotel.json",
        ]
        for src in candidates:
            if src.is_file():
                data_file.write_bytes(src.read_bytes())
                break
    os.environ.setdefault("BM_DEMO_FILE", str(data_file))
    os.environ.setdefault("BM_FLET_VIEW", "desktop")
    os.environ.setdefault("BM_FLET_TERMINAL", "launcher")


_ensure_paths()
