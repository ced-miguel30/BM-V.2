"""Adaptador JSON/in-memory del puerto de productos."""

from __future__ import annotations

from app.core.application.unit_of_work import UnitOfWork
from app.core.models import Producto


class JsonProductoRepository:
    """Lee productos desde AppData vía UnitOfWork (sin Streamlit directo)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def get_by_id(self, producto_id: str) -> Producto | None:
        return next(
            (p for p in self._uow.get_data().productos if p.id == producto_id),
            None,
        )

    def listar(self, *, es_bebida: bool | None = None, solo_activos: bool = True) -> list[Producto]:
        items = list(self._uow.get_data().productos)
        # `activo` en Producto; getattr mantiene compatibilidad con datos antiguos.
        if solo_activos:
            items = [p for p in items if getattr(p, "activo", True)]
        if es_bebida is not None:
            items = [p for p in items if bool(p.es_bebida) is es_bebida]
        return sorted(items, key=lambda p: p.nombre.lower())
