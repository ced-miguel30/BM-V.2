"""Modelo de configuración y registro diario de consumo buffet."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time


TIPO_LINEA_SIMPLE = "simple"
TIPO_LINEA_JARRA_ZUMO = "jarra_zumo"
TIPO_LINEA_RECETA_ESTANDAR = "receta_estandar"

MOTIVO_BUFFET_CONSUMO = "consumo"
MOTIVO_BUFFET_MERMA = "merma"
MOTIVO_BUFFET_EXPIRACION = "expiracion"
MOTIVO_BUFFET_LIMPIEZA = "limpieza"

MOTIVOS_BUFFET_VALORES = frozenset(
    {
        MOTIVO_BUFFET_CONSUMO,
        MOTIVO_BUFFET_MERMA,
        MOTIVO_BUFFET_EXPIRACION,
        MOTIVO_BUFFET_LIMPIEZA,
    }
)


@dataclass
class LineaConfigBuffet:
    id: str
    seccion: str
    orden: int
    label: str
    producto_id: str
    unidad: str
    cantidad_defecto: float
    activo: bool = True
    tipo_linea: str = TIPO_LINEA_SIMPLE
    producto_bote_id: str | None = None
    receta_id: str | None = None


@dataclass
class LineaRegistroBuffet:
    config_id: str
    label: str
    cantidad: float
    motivo: str
    naranjas_cantidad: float | None = None
    zumo_bote_cantidad: float | None = None
    coste_snapshot: float = 0.0
    notas: str = ""


@dataclass
class RegistroBuffetDiario:
    id: str
    fecha: date
    lineas: list[LineaRegistroBuffet] = field(default_factory=list)
    coste_total: float = 0.0
    clave_idempotencia: str | None = None
    registrado_por: str = ""
    hora: time | None = None
    observaciones: str = ""
    anulado: bool = False
    fecha_anulacion: date | None = None
    hora_anulacion: time | None = None
    motivo_anulacion: str = ""
    referencia_anulacion: str = ""
    anulado_por: str = ""
