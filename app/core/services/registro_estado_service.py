"""Estado diario de registros de servicio (cabecera operativa)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.models import AppData


@dataclass(frozen=True)
class EstadoRegistroDia:
    fecha: date
    tipo_servicio: str
    registros_activos: int
    ultimo_id: str | None
    etiqueta: str


def estado_registro_dia(
    data: AppData,
    *,
    tipo_servicio: str,
    fecha: date,
) -> EstadoRegistroDia:
    """Cuenta registros activos (no anulados) del día para un servicio.

    No impone unicidad diaria: solo informa. Varios registros el mismo día
    son válidos (p. ej. turnos); la idempotencia va por clave de confirmación.
    """
    activos: list[tuple[str, object]] = []
    if tipo_servicio == "desayuno":
        for d in data.desayunos:
            if d.fecha == fecha and not getattr(d, "anulado", False):
                activos.append((d.id, d.hora))
    else:
        for r in data.registros_servicio:
            if (
                r.tipo_servicio == tipo_servicio
                and r.fecha == fecha
                and not getattr(r, "anulado", False)
            ):
                activos.append((r.id, r.hora))

    activos.sort(key=lambda x: (x[1] is None, x[1] or 0, x[0]))
    n = len(activos)
    ultimo = activos[-1][0] if activos else None
    if n == 0:
        etiqueta = "Sin registro confirmado hoy"
    elif n == 1:
        etiqueta = f"1 registro confirmado (ref. {ultimo})"
    else:
        etiqueta = f"{n} registros confirmados hoy (último: {ultimo})"
    return EstadoRegistroDia(
        fecha=fecha,
        tipo_servicio=tipo_servicio,
        registros_activos=n,
        ultimo_id=ultimo,
        etiqueta=etiqueta,
    )
