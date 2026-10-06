"""Copias de seguridad de la base SQLite (copia consistente en caliente con la API de backup)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from bm import db

CONSERVAR = 30


def carpeta() -> Path:
    d = Path(db.DB_PATH).parent / "copias"
    d.mkdir(parents=True, exist_ok=True)
    return d


def hacer(con: sqlite3.Connection, motivo: str = "auto") -> Path:
    destino = carpeta() / f"bm_{datetime.now():%Y%m%d_%H%M%S}_{motivo}.sqlite"
    with sqlite3.connect(destino) as copia:
        con.backup(copia)
    copia.close()
    for viejo in listar()[CONSERVAR:]:
        (carpeta() / viejo["nombre"]).unlink(missing_ok=True)
    return destino


def listar() -> list[dict]:
    fs = sorted(carpeta().glob("bm_*.sqlite"), reverse=True)
    return [{"nombre": f.name, "tamano": f.stat().st_size, "fecha": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes")} for f in fs]


def hay_copia_de_hoy() -> bool:
    return any(c["nombre"].startswith(f"bm_{datetime.now():%Y%m%d}") for c in listar())
