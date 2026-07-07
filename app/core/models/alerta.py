"""Modelo de alerta operativa."""

from dataclasses import dataclass
from datetime import date

from app.core.models.enums import TipoAlerta


@dataclass
class AlertaOperativa:
    id: str
    tipo: TipoAlerta
    titulo: str
    mensaje: str
    fecha: date
    activa: bool = True
    producto_id: str | None = None
