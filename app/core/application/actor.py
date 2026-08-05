"""Actor actual de la operación.

Tras F16 la identidad preferente proviene de la sesión autenticada.
``usuario_actual_id`` en AppData se mantiene por compatibilidad.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.models import AppData, Usuario


@dataclass(frozen=True)
class Actor:
    id: str
    nombre: str
    rol: str
    actor_type: str = "usuario"
    terminal_id: str | None = None


def actor_desde_usuario(usuario: Usuario | None) -> Actor:
    if usuario is None:
        return Actor(id="", nombre="Usuario", rol="")
    from app.core.auth.roles import rol_canonico

    rol = rol_canonico(usuario.rol)
    return Actor(id=usuario.id, nombre=usuario.nombre, rol=rol)


def actor_desde_auth_session() -> Actor | None:
    """Si hay sesión F16 activa, construye el Actor correspondiente."""
    try:
        from app.core.auth.session import get_auth_session

        s = get_auth_session()
    except Exception:  # noqa: BLE001
        return None
    if s is None or not s.authenticated:
        return None
    return Actor(
        id=s.actor_id,
        nombre=s.actor_label,
        rol=s.role,
        actor_type=s.actor_type,
        terminal_id=s.terminal_id,
    )


def actor_desde_appdata(data: AppData) -> Actor:
    auth = actor_desde_auth_session()
    if auth is not None:
        return auth
    usuario: Usuario | None = None
    for u in data.usuarios:
        if u.id == data.usuario_actual_id:
            usuario = u
            break
    if usuario is None and data.usuarios:
        usuario = data.usuarios[0]
    return actor_desde_usuario(usuario)
