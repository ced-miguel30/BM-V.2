"""Modelo de usuario."""

from dataclasses import dataclass


from app.core.models.enums import RolUsuario


@dataclass
class Usuario:
    id: str
    nombre: str
    rol: RolUsuario
    activo: bool = True
    login: str = ""
    password_hash: str = ""
    creado_en: str | None = None
    modificado_en: str | None = None
