"""Modelo de configuración del hotel."""

from dataclasses import dataclass


@dataclass
class ConfiguracionHotel:
    nombre_establecimiento: str
    moneda: str
    simbolo_moneda: str = "€"
    logo_path: str | None = None
