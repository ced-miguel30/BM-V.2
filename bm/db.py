"""SQLite: un único fichero, un único proceso escritor (el servidor web)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("BM_DB", Path(__file__).resolve().parent.parent / "datos" / "bm.sqlite"))

SCHEMA = """
-- Maestro de artículos de Business Central (+ productos heredados de BM v2 sin código BC).
CREATE TABLE IF NOT EXISTS productos(
  codigo TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  unidad TEXT,
  categoria TEXT,
  es_tpv INTEGER NOT NULL DEFAULT 0,
  activo INTEGER NOT NULL DEFAULT 1,
  coste_ref REAL,                      -- "Coste unitario" del maestro BC (último recurso)
  origen TEXT NOT NULL DEFAULT 'bc'    -- 'bc' | 'bm2'
);

-- Copia literal de "Movimientos de producto" de BC. n_mov es la clave de BC: reimportar = actualizar.
CREATE TABLE IF NOT EXISTS bc_movs(
  n_mov INTEGER PRIMARY KEY,
  fecha TEXT NOT NULL,
  tipo TEXT NOT NULL,                  -- Compra | Ajuste negativo | Ajuste positivo | Transferencia
  tipo_doc TEXT,
  documento TEXT,
  producto TEXT NOT NULL,
  proveedor TEXT,
  almacen TEXT,
  cantidad REAL NOT NULL,
  coste_unit REAL,
  coste_total REAL
);
CREATE INDEX IF NOT EXISTS ix_bc_movs_prod ON bc_movs(producto, fecha);

CREATE TABLE IF NOT EXISTS recetas(
  id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  servicio TEXT,
  porciones REAL NOT NULL DEFAULT 1,
  activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS receta_lineas(
  receta_id TEXT NOT NULL REFERENCES recetas(id) ON DELETE CASCADE,
  producto TEXT NOT NULL REFERENCES productos(codigo),
  cantidad REAL NOT NULL               -- unidad base BC, por receta completa (porciones)
);

-- Un hecho físico = un consumo. ref es la clave de idempotencia (reimportar no duplica).
CREATE TABLE IF NOT EXISTS consumos(
  id INTEGER PRIMARY KEY,
  fecha TEXT NOT NULL,
  servicio TEXT,                       -- desayuno | comida | cena | bebidas
  tipo TEXT NOT NULL DEFAULT 'consumo',-- consumo | merma
  origen TEXT NOT NULL,                -- manual | excel | tpv | bm2
  ref TEXT UNIQUE,
  comensales INTEGER,
  nota TEXT,
  usuario TEXT,
  creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  anulado INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_consumos_fecha ON consumos(fecha);
CREATE TABLE IF NOT EXISTS consumo_lineas(
  id INTEGER PRIMARY KEY,
  consumo_id INTEGER NOT NULL REFERENCES consumos(id) ON DELETE CASCADE,
  producto TEXT NOT NULL REFERENCES productos(codigo),
  cantidad REAL NOT NULL,              -- unidad base BC
  receta_id TEXT,
  coste REAL,                          -- lo rellena costing.valorar()
  coste_estado TEXT,                   -- fifo | provisional | sin_stock | sin_precio
  coste_legacy REAL                    -- coste que tenía en BM v2 (solo comparación)
);
CREATE INDEX IF NOT EXISTS ix_lineas_consumo ON consumo_lineas(consumo_id);
CREATE INDEX IF NOT EXISTS ix_lineas_producto ON consumo_lineas(producto);

-- Traza FIFO: de qué movimiento BC (albarán) sale el coste de cada línea. Se recalcula entera.
CREATE TABLE IF NOT EXISTS asignaciones(
  linea_id INTEGER NOT NULL REFERENCES consumo_lineas(id) ON DELETE CASCADE,
  n_mov INTEGER,                       -- NULL = sin lote (precio de respaldo)
  cantidad REAL NOT NULL,
  coste_unit REAL
);
CREATE INDEX IF NOT EXISTS ix_asig_linea ON asignaciones(linea_id);

-- Artículos de TPV (PV000xxx) -> qué consumen. Se configura una vez.
CREATE TABLE IF NOT EXISTS tpv_articulos(
  codigo TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  categoria TEXT,
  servicio TEXT,
  receta_id TEXT REFERENCES recetas(id),
  producto TEXT REFERENCES productos(codigo),
  factor REAL NOT NULL DEFAULT 1,      -- unidades de producto por unidad vendida
  precio REAL,                         -- PVP unitario (para deducir cantidades del importe)
  ignorar INTEGER NOT NULL DEFAULT 0
);
-- Ventas TPV agregadas por día y artículo: reimportar un día lo sustituye, nunca duplica.
CREATE TABLE IF NOT EXISTS tpv_ventas(
  fecha TEXT NOT NULL,
  codigo TEXT NOT NULL REFERENCES tpv_articulos(codigo),
  importe REAL NOT NULL,               -- neto (devoluciones restadas); cantidad = importe / precio
  PRIMARY KEY(fecha, codigo)
);

CREATE TABLE IF NOT EXISTS usuarios(
  id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  login TEXT UNIQUE,
  rol TEXT NOT NULL,
  password_hash TEXT,
  activo INTEGER NOT NULL DEFAULT 1
);

-- Equivalencias BM v2 -> BC (para migrar histórico y recetas).
CREATE TABLE IF NOT EXISTS mapa_bm2(
  bm2_id TEXT PRIMARY KEY,
  bm2_nombre TEXT,
  bm2_unidad TEXT,
  codigo TEXT NOT NULL,
  factor REAL NOT NULL DEFAULT 1,      -- cantidad BC = cantidad BM2 * factor
  revisar TEXT                         -- motivo si la equivalencia es dudosa
);

CREATE TABLE IF NOT EXISTS ajustes(clave TEXT PRIMARY KEY, valor TEXT);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con
