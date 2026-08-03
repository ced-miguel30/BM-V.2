"""Auditoría única vía AppContext (Fase 3).

Los servicios pueden seguir registrando Actividad a mano hasta Fase 4;
esta función es el punto de entrada canónico nuevo.
"""

from __future__ import annotations

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import Actividad, AppData


def registrar_actividad(
    ctx: AppContext,
    accion: str,
    detalle: str,
    *,
    commit: bool = False,
    data: AppData | None = None,
) -> Actividad:
    """Inserta una Actividad al inicio de la lista. Commit opcional."""
    app = data if data is not None else ctx.data()
    actividad = Actividad(
        next_id("act", [a.id for a in app.actividades]),
        ctx.clock.now(),
        ctx.actor.nombre,
        accion,
        detalle,
    )
    app.actividades.insert(0, actividad)
    if commit:
        ctx.uow.commit(app)
    return actividad
