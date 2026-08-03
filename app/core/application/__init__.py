"""Fase 3 — fronteras de aplicación (contexto, UoW, puertos).

No reemplaza session_store ni cambia la UI. Los servicios existentes
siguen usando get_data/persist_data; la migración es progresiva (Fase 4).
"""

from app.core.application.actor import Actor, actor_desde_appdata
from app.core.application.auditoria import registrar_actividad
from app.core.application.clock import Clock, SystemClock
from app.core.application.context import AppContext, build_app_context
from app.core.application.id_generator import next_id
from app.core.application.producto_queries import listar_productos, obtener_producto
from app.core.application.unit_of_work import InMemoryUnitOfWork, JsonSessionUnitOfWork, UnitOfWork

__all__ = [
    "Actor",
    "AppContext",
    "Clock",
    "InMemoryUnitOfWork",
    "JsonSessionUnitOfWork",
    "SystemClock",
    "UnitOfWork",
    "actor_desde_appdata",
    "build_app_context",
    "listar_productos",
    "next_id",
    "obtener_producto",
    "registrar_actividad",
]
