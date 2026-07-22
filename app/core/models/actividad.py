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
    # Campos estructurados opcionales, rellenados solo por las exportaciones
    # semanales del motor central (ver `exportacion_semanal_service.py`). El
    # resto de actividades (registro de desayuno, merma, etc.) los dejan en
    # `None`: en la exportación del Registro de actividad se muestran vacíos
    # "cuando estén disponibles", tal como pide la Fase 6.
    modulo: str | None = None
    resultado: str | None = None
    tipo_exportacion: str | None = None
    periodo_afectado: str | None = None
    archivo_generado: str | None = None
