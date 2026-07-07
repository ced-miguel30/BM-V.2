"""Modelo de usuario temporal."""

from dataclasses import dataclass

from app.core.models.enums import RolUsuario


@dataclass
class Usuario:
    id: str
    nombre: str
    rol: RolUsuario
    activo: bool = True
