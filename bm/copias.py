"""Copias de seguridad de la base SQLite (copia consistente en caliente con la API de backup)."""

from __future__ import annotations

import shutil
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
    _duplicar(con, destino)
    return destino


def _duplicar(con: sqlite3.Connection, copia: Path) -> None:
    """Segunda copia fuera del servidor (carpeta de red, OneDrive...), si está configurada.
    Si falla, queda anotado en ajustes y sale como aviso; la copia local ya está hecha."""
    extra = (con.execute("SELECT valor FROM ajustes WHERE clave='copias_extra'").fetchone() or [""])[0]
    if not extra:
        return
    try:
        d = Path(extra)
        shutil.copy2(copia, d / copia.name)
        for viejo in sorted(d.glob("bm_*.sqlite"), reverse=True)[CONSERVAR:]:
            viejo.unlink(missing_ok=True)
        error = ""
    except OSError as e:
        error = f"{datetime.now():%d/%m/%Y %H:%M}: {e}"
    con.execute("INSERT OR REPLACE INTO ajustes VALUES('copias_extra_error', ?)", (error,))
    con.commit()


def probar_carpeta(ruta: str) -> None:
    """Comprueba que la carpeta existe y se puede escribir en ella (ValueError si no)."""
    d = Path(ruta)
    if not d.is_dir():
        raise ValueError(f"No existe la carpeta {ruta}")
    prueba = d / ".bm_prueba"
    try:
        prueba.write_text("ok")
        prueba.unlink()
    except OSError as e:
        raise ValueError(f"No se puede escribir en {ruta}: {e}") from e


def listar() -> list[dict]:
    fs = sorted(carpeta().glob("bm_*.sqlite"), reverse=True)
    return [{"nombre": f.name, "tamano": f.stat().st_size, "fecha": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes")} for f in fs]


def hay_copia_de_hoy() -> bool:
    return any(c["nombre"].startswith(f"bm_{datetime.now():%Y%m%d}") for c in listar())
