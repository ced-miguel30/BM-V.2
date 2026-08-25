"""Runtime hook — datos productivos fuera del árbol del ejecutable.

Contrato dos carpetas:
  BM-CODIGO = carpeta del exe / onedir (reemplazable al actualizar versión)
  BM-DATOS  = BM_INSTANCE_ROOT (default %%LOCALAPPDATA%%\\BM-V2-local; no tocar al
              actualizar código)
Sustituir solo código no cambia BM_INSTANCE_ROOT: el default no depende de la
ruta del exe.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_CODIGO_TXT = "BM-CODIGO.txt"
_DATOS_TXT = "BM-DATOS.txt"

_CODIGO_BODY = (
    "Carpeta de aplicacion (BM-CODIGO).\n"
    "\n"
    "Sustituir COMPLETA al actualizar la version (exe + _internal).\n"
    "No borrar ni mezclar con BM-DATOS.\n"
    "El acceso directo debe apuntar a BM-Launcher.exe dentro de esta carpeta.\n"
    "\n"
    "Ruta tipica: C:\\Apps\\BM-V2\\\n"
    "Datos productivos: ver BM-DATOS.txt en %%LOCALAPPDATA%%\\BM-V2-local\\\n"
)

_DATOS_BODY = (
    "Carpeta de datos del hotel (BM-DATOS).\n"
    "\n"
    "Sustituir COMPLETA al llevar/traer la base (casa <-> hotel).\n"
    "Incluye: data\\datos_hotel.json, data\\documentos\\, backups\\, exports\\, logs\\.\n"
    "No mezclar con una actualizacion de codigo.\n"
    "\n"
    "Ruta tipica (un PC / exe): %%LOCALAPPDATA%%\\BM-V2-local\\\n"
    "Variable: BM_INSTANCE_ROOT\n"
)


def _write_marker(path: Path, body: str) -> None:
    try:
        if not path.is_file():
            path.write_text(body, encoding="utf-8")
    except OSError:
        pass


def _ensure_paths() -> None:
    # Carpeta del onedir / exe = BM-CODIGO (reemplazable)
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent

    # BM-DATOS: fuera del árbol del exe. Default fijo bajo LOCALAPPDATA
    # (independiente de dónde esté instalado el código → swap de código seguro).
    local = Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
    instance = Path(os.environ.get("BM_INSTANCE_ROOT") or (local / "BM-V2-local"))
    instance.mkdir(parents=True, exist_ok=True)
    for sub in ("data", "backups", "logs", "exports"):
        (instance / sub).mkdir(exist_ok=True)
    (instance / "data" / "documentos").mkdir(exist_ok=True)

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

    _write_marker(instance / _DATOS_TXT, _DATOS_BODY)
    if getattr(sys, "frozen", False):
        _write_marker(base / _CODIGO_TXT, _CODIGO_BODY)


_ensure_paths()
