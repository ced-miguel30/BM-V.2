"""Contexto de operación de la aplicación."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.application.actor import Actor, actor_desde_appdata
from app.core.application.clock import Clock, SystemClock
from app.core.application.unit_of_work import JsonSessionUnitOfWork, UnitOfWork
from app.core.models import AppData


@dataclass
class AppContext:
    """Dependencias de borde: UoW, actor, reloj. Sin UI."""

    uow: UnitOfWork
    actor: Actor
    clock: Clock

    def data(self) -> AppData:
        return self.uow.get_data()


def build_app_context(
    *,
    uow: UnitOfWork | None = None,
    clock: Clock | None = None,
    actor: Actor | None = None,
) -> AppContext:
    """Construye el contexto. Por defecto: JSON/sesión + reloj sistema."""
    unit = uow if uow is not None else JsonSessionUnitOfWork()
    clk = clock if clock is not None else SystemClock()
    act = actor if actor is not None else actor_desde_appdata(unit.get_data())
    return AppContext(uow=unit, actor=act, clock=clk)
