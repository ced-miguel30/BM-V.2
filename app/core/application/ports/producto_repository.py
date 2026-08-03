"""Puerto de lectura de productos (piloto Fase 3)."""

from __future__ import annotations

from typing import Protocol

from app.core.models import Producto


class ProductoRepositoryPort(Protocol):
    def get_by_id(self, producto_id: str) -> Producto | None: ...

    def listar(self, *, es_bebida: bool | None = None, solo_activos: bool = True) -> list[Producto]: ...
