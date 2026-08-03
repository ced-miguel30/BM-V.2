"""Actor actual de la operación (no es autenticación final)."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.models import AppData, Usuario


@dataclass(frozen=True)
class Actor:
    id: str
    nombre: str
    rol: str


def actor_desde_usuario(usuario: Usuario | None) -> Actor:
    if usuario is None:
        return Actor(id="", nombre="Usuario", rol="")
    rol = usuario.rol.value if hasattr(usuario.rol, "value") else str(usuario.rol)
    return Actor(id=usuario.id, nombre=usuario.nombre, rol=rol)


def actor_desde_appdata(data: AppData) -> Actor:
    usuario: Usuario | None = None
    for u in data.usuarios:
        if u.id == data.usuario_actual_id:
            usuario = u
            break
    if usuario is None and data.usuarios:
        usuario = data.usuarios[0]
    return actor_desde_usuario(usuario)
