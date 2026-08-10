"""Viewmodels Administración operativa Flet — sin información económica."""

from __future__ import annotations

from dataclasses import dataclass, fields

from app.presentation.flet.viewmodels import (
    CAMPOS_ECONOMICOS_PROHIBIDOS,
    FeedbackVM,
    SessionVM,
)


@dataclass(frozen=True)
class ResponsableMermaVM:
    id: str
    nombre: str
    activo: bool


@dataclass(frozen=True)
class PendingChangeVM:
    """Resumen previo a confirmar una mutación."""

    kind: str  # crear | renombrar | desactivar | reactivar
    resumen: str
    responsable_id: str = ""
    nombre: str = ""


@dataclass(frozen=True)
class AdminScreenVM:
    session: SessionVM
    responsables: tuple[ResponsableMermaVM, ...]
    filtro: str = ""
    feedback: FeedbackVM | None = None
    pending: PendingChangeVM | None = None
    mutando: bool = False
    motivos_fijos: tuple[str, ...] = ()


def assert_admin_sin_economia(*tipos: type) -> None:
    for cls in tipos:
        nombres = {f.name.lower() for f in fields(cls)}
        for prohibido in CAMPOS_ECONOMICOS_PROHIBIDOS:
            assert prohibido not in nombres, f"{cls.__name__} campo económico {prohibido}"
            assert not any(prohibido in n for n in nombres if len(prohibido) > 2)
