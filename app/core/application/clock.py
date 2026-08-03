"""Reloj inyectable (desacopla date.today / datetime.now del dominio)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def today(self) -> date: ...


class SystemClock:
    """Reloj del sistema. Implementación por defecto en producción."""

    def now(self) -> datetime:
        return datetime.now()

    def today(self) -> date:
        return date.today()


class FixedClock:
    """Reloj fijo para pruebas."""

    def __init__(self, momento: datetime) -> None:
        self._momento = momento

    def now(self) -> datetime:
        return self._momento

    def today(self) -> date:
        return self._momento.date()
