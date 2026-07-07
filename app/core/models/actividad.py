"""Modelo de registro de actividad."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Actividad:
    id: str
    fecha_hora: datetime
    usuario: str
    accion: str
    detalle: str
