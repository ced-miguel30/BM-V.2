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
CREATE INDEX IF NOT EXISTS ix_bc_movs_doc ON bc_movs(documento);

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

-- Atajos del Excel/registro: "Bacon" = 0,015 KG de C00000028. Editables, sin código especial.
CREATE TABLE IF NOT EXISTS atajos(
  etiqueta TEXT NOT NULL,
  grupo TEXT NOT NULL,                 -- extra | leche | bebida | buffet | omitir
  producto TEXT REFERENCES productos(codigo),
  receta_id TEXT REFERENCES recetas(id),
  cantidad REAL NOT NULL DEFAULT 1,    -- por unidad del atajo (unidad base BC / raciones)
  sustituye TEXT,                      -- grupo de sustitución (huevo | pan): reemplaza al de la receta
  activo INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(grupo, etiqueta)         -- la misma etiqueta puede ser extra de plato y concepto de buffet
);
-- Productos intercambiables dentro de una receta (huevo frito -> pochado, pan blanco -> integral).
CREATE TABLE IF NOT EXISTS sustitucion(
  grupo TEXT NOT NULL,
  producto TEXT NOT NULL REFERENCES productos(codigo),
  PRIMARY KEY(grupo, producto)
);
-- "Tostada del dia" / "Coctel del dia": receta según día de la semana (0 = lunes).
CREATE TABLE IF NOT EXISTS recetas_dia(
  etiqueta TEXT NOT NULL,
  dia_semana INTEGER NOT NULL CHECK(dia_semana BETWEEN 0 AND 6),
  receta_id TEXT NOT NULL REFERENCES recetas(id),
  PRIMARY KEY(etiqueta, dia_semana)
);

-- Ubicaciones = almacenes de BC (ECONOMATO, DESAYUNO, SNACK BEBI...) + las que se creen en BM.
CREATE TABLE IF NOT EXISTS ubicaciones(
  codigo TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  activo INTEGER NOT NULL DEFAULT 1
);
-- Almacenes de BC = destinos CONTABLES. Cada uno se asigna a la ubicación FÍSICA donde está el producto
-- (DESAYUNO, SNACK COMI, SNACK BEBI... están todos físicamente en Restaurante y cocina).
CREATE TABLE IF NOT EXISTS almacenes_bc(
  codigo TEXT PRIMARY KEY,
  ubicacion TEXT NOT NULL REFERENCES ubicaciones(codigo),
  centro TEXT REFERENCES centros(codigo)      -- a qué centro de consumo imputa BC ese almacén
);
-- Centros de consumo: servicios de restauración y departamentos. Exclusivos: cada consumo es de uno.
CREATE TABLE IF NOT EXISTS centros(
  codigo TEXT PRIMARY KEY,             -- desayuno | comida | cena | bebidas | pisos | ...
  nombre TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'restauracion',  -- restauracion | departamento
  ubicacion TEXT REFERENCES ubicaciones(codigo),  -- de dónde sale el stock por defecto
  color TEXT NOT NULL DEFAULT 'gray',
  orden INTEGER NOT NULL DEFAULT 99,
  activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS traslados(
  id INTEGER PRIMARY KEY,
  fecha TEXT NOT NULL,
  origen TEXT NOT NULL REFERENCES ubicaciones(codigo),
  destino TEXT NOT NULL REFERENCES ubicaciones(codigo),
  nota TEXT,
  usuario TEXT,
  creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  anulado INTEGER NOT NULL DEFAULT 0,
  CHECK(origen <> destino)
);
CREATE TABLE IF NOT EXISTS traslado_lineas(
  traslado_id INTEGER NOT NULL REFERENCES traslados(id) ON DELETE CASCADE,
  producto TEXT NOT NULL REFERENCES productos(codigo),
  cantidad REAL NOT NULL CHECK(cantidad > 0)
);

-- Recuento: lo contado en una ubicación manda sobre el teórico (solo para los productos contados).
CREATE TABLE IF NOT EXISTS recuentos(
  id INTEGER PRIMARY KEY,
  fecha TEXT NOT NULL,
  ubicacion TEXT NOT NULL REFERENCES ubicaciones(codigo),
  nota TEXT,
  usuario TEXT,
  creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  anulado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS recuento_lineas(
  recuento_id INTEGER NOT NULL REFERENCES recuentos(id) ON DELETE CASCADE,
  producto TEXT NOT NULL REFERENCES productos(codigo),
  contado REAL NOT NULL CHECK(contado >= 0),
  teorico REAL,                        -- stock teórico en el momento de contar (foto)
  PRIMARY KEY(recuento_id, producto)
);

CREATE TABLE IF NOT EXISTS caducidades(
  id INTEGER PRIMARY KEY,
  producto TEXT NOT NULL REFERENCES productos(codigo),
  ubicacion TEXT REFERENCES ubicaciones(codigo),
  cantidad REAL NOT NULL CHECK(cantidad > 0),
  caduca TEXT NOT NULL,
  nota TEXT,
  usuario TEXT,
  creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  estado TEXT NOT NULL DEFAULT 'activa',  -- activa | usada | merma
  cerrado TEXT,
  consumo_id INTEGER REFERENCES consumos(id)
);

-- Proveedores (nombre tal cual llega de BC) con lo que BC no sabe: contacto y cuándo reparten.
CREATE TABLE IF NOT EXISTS proveedores(
  nombre TEXT PRIMARY KEY,
  email TEXT,
  telefono TEXT,
  contacto TEXT,
  dias_reparto TEXT,                   -- "0,3" (0 = lunes). NULL = se deduce del histórico de albaranes
  plazo_dias INTEGER,                  -- días desde que se pide hasta que llega
  pedido_minimo REAL,
  notas TEXT,
  activo INTEGER NOT NULL DEFAULT 1
);
-- Qué albaranes recoge cada factura (export de BC "Líneas factura compra registradas").
CREATE TABLE IF NOT EXISTS factura_albaran(
  factura TEXT NOT NULL,
  albaran TEXT NOT NULL,
  PRIMARY KEY(factura, albaran)
);
-- Foto o PDF del papel (albarán/factura) guardado junto al documento de BC.
CREATE TABLE IF NOT EXISTS adjuntos(
  id INTEGER PRIMARY KEY,
  documento TEXT NOT NULL,
  nombre TEXT NOT NULL,
  fichero TEXT NOT NULL,
  tipo TEXT,
  subido TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  usuario TEXT
);
CREATE INDEX IF NOT EXISTS ix_adjuntos_doc ON adjuntos(documento);

-- Ajustes a mano por producto (si no hay, BM calcula todo solo a partir del consumo).
CREATE TABLE IF NOT EXISTS parametros_producto(
  producto TEXT PRIMARY KEY REFERENCES productos(codigo),
  stock_minimo REAL,                   -- colchón fijo en el hotel (sustituye a los días de seguridad)
  minimo_restaurante REAL,             -- lo mínimo que debe haber en Restaurante y cocina
  lote REAL,                           -- se pide en múltiplos de esto (caja, pack)
  no_pedir INTEGER NOT NULL DEFAULT 0  -- descatalogado o se compra aparte
);

-- Buffet del día confirmado: lo sacado y lo que sobró por concepto (el consumo va a consumos, ref buffet:fecha).
CREATE TABLE IF NOT EXISTS buffet_diario(
  fecha TEXT NOT NULL,
  etiqueta TEXT NOT NULL,
  sacado REAL NOT NULL,
  sobro REAL NOT NULL DEFAULT 0,
  comensales INTEGER,
  PRIMARY KEY(fecha, etiqueta)
);

CREATE TABLE IF NOT EXISTS ajustes(clave TEXT PRIMARY KEY, valor TEXT);

-- Sesiones (sobreviven a reinicios del servidor). Se guarda el hash del token, nunca el token.
CREATE TABLE IF NOT EXISTS sesiones(
  token_hash TEXT PRIMARY KEY,
  usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  creada TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expira TEXT NOT NULL
);

-- Registro de actividad: toda escritura queda con quién y cuándo.
CREATE TABLE IF NOT EXISTS auditoria(
  id INTEGER PRIMARY KEY,
  cuando TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  usuario TEXT,
  metodo TEXT NOT NULL,
  ruta TEXT NOT NULL,
  estado INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_auditoria_cuando ON auditoria(cuando);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    _migrar(con)
    from bm import inventario
    inventario.sembrar(con)
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """Columnas añadidas después de crear la base (ALTER idempotente)."""
    if "seccion" not in {r[1] for r in con.execute("PRAGMA table_info(atajos)")}:  # Fruta, Bollería, Pan... (buffet)
        con.execute("ALTER TABLE atajos ADD COLUMN seccion TEXT")
        con.commit()
    cols = {r[1] for r in con.execute("PRAGMA table_info(consumos)")}
    if "ubicacion" not in cols:  # de qué ubicación sale el stock de este consumo
        con.execute("ALTER TABLE consumos ADD COLUMN ubicacion TEXT REFERENCES ubicaciones(codigo)")
        con.commit()
