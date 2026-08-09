"""Consulta operativa unificada de eventos (lectura + deep-links de anulación).

No fusiona motores: agrega vistas de desayunos, registros_servicio, mermas y
ajustes. La anulación se delega a los servicios existentes por tipo.
Los ajustes NO admiten soft-anulación: corrección = ajuste compensatorio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Any

from app.core.models import AppData
from app.core.repositories.data_repository import DataRepository
from app.core.storage.session_store import get_data

TIPO_DESAYUNO = "desayuno"
TIPO_SERVICIO = "registro_servicio"
TIPO_MERMA = "merma"
TIPO_AJUSTE = "ajuste"


@dataclass(frozen=True)
class EventoHistorial:
    tipo: str
    id: str
    fecha: date
    hora: time | None
    servicio: str
    responsable: str
    resumen: str
    coste: float | None
    anulado: bool
    estado: str
    familia: str


def _data(data: AppData | None = None) -> AppData:
    return data if data is not None else get_data()


def _en_rango(f: date, desde: date | None, hasta: date | None) -> bool:
    if desde and f < desde:
        return False
    if hasta and f > hasta:
        return False
    return True


def listar_eventos_operativos(
    *,
    desde: date | None = None,
    hasta: date | None = None,
    tipo: str | None = None,
    servicio: str | None = None,
    solo_activos: bool = False,
    busqueda: str = "",
    data: AppData | None = None,
) -> list[EventoHistorial]:
    """Lista unificada (más reciente primero)."""
    app = _data(data)
    repo = DataRepository(app)
    eventos: list[EventoHistorial] = []
    q = (busqueda or "").strip().casefold()

    if tipo in (None, TIPO_DESAYUNO):
        for d in app.desayunos:
            if not _en_rango(d.fecha, desde, hasta):
                continue
            anulado = bool(getattr(d, "anulado", False))
            if solo_activos and anulado:
                continue
            if servicio and servicio != "desayuno":
                continue
            resumen = (
                f"{len(d.lineas)} línea(s), {len(d.registros_recetas)} receta(s)"
            )
            if q and q not in d.id.casefold() and q not in (d.registrado_por or "").casefold():
                if q not in resumen.casefold():
                    continue
            eventos.append(EventoHistorial(
                tipo=TIPO_DESAYUNO,
                id=d.id,
                fecha=d.fecha,
                hora=d.hora,
                servicio="desayuno",
                responsable=d.registrado_por or "",
                resumen=resumen,
                coste=float(d.coste_total),
                anulado=anulado,
                estado="Anulado" if anulado else "Activo",
                familia="consumo",
            ))

    if tipo in (None, TIPO_SERVICIO):
        for r in app.registros_servicio:
            if not _en_rango(r.fecha, desde, hasta):
                continue
            anulado = bool(getattr(r, "anulado", False))
            if solo_activos and anulado:
                continue
            if servicio and r.tipo_servicio != servicio:
                continue
            resumen = (
                f"{r.tipo_servicio}: {len(r.lineas)} línea(s), "
                f"{len(r.registros_recetas)} receta(s)"
            )
            if q and q not in r.id.casefold() and q not in (r.registrado_por or "").casefold():
                if q not in resumen.casefold() and q not in r.tipo_servicio.casefold():
                    continue
            eventos.append(EventoHistorial(
                tipo=TIPO_SERVICIO,
                id=r.id,
                fecha=r.fecha,
                hora=r.hora,
                servicio=r.tipo_servicio,
                responsable=r.registrado_por or "",
                resumen=resumen,
                coste=float(r.coste_total),
                anulado=anulado,
                estado="Anulado" if anulado else "Activo",
                familia="consumo",
            ))

    if tipo in (None, TIPO_MERMA):
        for m in app.mermas:
            if not _en_rango(m.fecha, desde, hasta):
                continue
            anulado = bool(getattr(m, "anulado", False))
            if solo_activos and anulado:
                continue
            servicios_ln = {
                getattr(ln, "tipo_servicio_snapshot", None) or "—"
                for ln in m.lineas
            }
            svc = ",".join(sorted(servicios_ln)) if servicios_ln else "—"
            if servicio and servicio not in servicios_ln and servicio != "merma":
                # filtro flexible: coincidencia en snapshots
                if servicio not in svc:
                    continue
            nombres = []
            for ln in m.lineas:
                nom = ln.producto_nombre_snapshot or repo.get_nombre_producto(ln.producto_id)
                nombres.append(nom)
            resumen = f"Merma: {', '.join(nombres[:3])}"
            if q and q not in m.id.casefold() and q not in (m.registrado_por or "").casefold():
                if q not in resumen.casefold():
                    continue
            eventos.append(EventoHistorial(
                tipo=TIPO_MERMA,
                id=m.id,
                fecha=m.fecha,
                hora=m.hora,
                servicio=svc,
                responsable=m.registrado_por or "",
                resumen=resumen,
                coste=float(m.coste_total),
                anulado=anulado,
                estado="Anulado" if anulado else "Activo",
                familia="merma",
            ))

    if tipo in (None, TIPO_AJUSTE):
        for a in getattr(app, "ajustes", []) or []:
            if not _en_rango(a.fecha, desde, hasta):
                continue
            if servicio and servicio not in ("ajuste", "general", ""):
                continue
            resumen = f"Ajuste: {len(a.lineas)} línea(s)"
            if q and q not in a.id.casefold() and q not in (a.registrado_por or "").casefold():
                if q not in resumen.casefold():
                    continue
            eventos.append(EventoHistorial(
                tipo=TIPO_AJUSTE,
                id=a.id,
                fecha=a.fecha,
                hora=getattr(a, "hora", None),
                servicio="ajuste",
                responsable=getattr(a, "registrado_por", "") or "",
                resumen=resumen,
                coste=None,
                anulado=False,
                estado="Activo (compensar con nuevo ajuste si procede)",
                familia="ajuste",
            ))

    eventos.sort(
        key=lambda e: (e.fecha, e.hora or time.min, e.id),
        reverse=True,
    )
    return eventos


def detalle_evento(
    tipo: str,
    evento_id: str,
    *,
    data: AppData | None = None,
) -> dict[str, Any] | None:
    """Detalle ligero para UI; None si no existe."""
    app = _data(data)
    repo = DataRepository(app)

    if tipo == TIPO_DESAYUNO:
        reg = next((d for d in app.desayunos if d.id == evento_id), None)
        if not reg:
            return None
        return {
            "tipo": tipo,
            "id": reg.id,
            "fecha": reg.fecha,
            "hora": reg.hora,
            "responsable": reg.registrado_por,
            "coste_total": reg.coste_total,
            "anulado": bool(getattr(reg, "anulado", False)),
            "observaciones": getattr(reg, "observaciones", "") or "",
            "lineas": [
                {
                    "producto": repo.get_nombre_producto(ln.producto_id),
                    "cantidad": ln.cantidad,
                    "coste": ln.coste,
                }
                for ln in reg.lineas
            ],
            "recetas": [
                {"nombre": rr.nombre_receta, "porciones": rr.porciones}
                for rr in reg.registros_recetas
            ],
            "puede_anular": not bool(getattr(reg, "anulado", False)),
            "correccion": "anular + nuevo registro (sin edición destructiva)",
        }

    if tipo == TIPO_SERVICIO:
        reg = next((r for r in app.registros_servicio if r.id == evento_id), None)
        if not reg:
            return None
        return {
            "tipo": tipo,
            "id": reg.id,
            "fecha": reg.fecha,
            "hora": reg.hora,
            "servicio": reg.tipo_servicio,
            "responsable": reg.registrado_por,
            "coste_total": reg.coste_total,
            "anulado": bool(getattr(reg, "anulado", False)),
            "observaciones": getattr(reg, "observaciones", "") or "",
            "lineas": [
                {
                    "producto": repo.get_nombre_producto(ln.producto_id),
                    "cantidad": ln.cantidad,
                    "coste": ln.coste,
                }
                for ln in reg.lineas
            ],
            "recetas": [
                {"nombre": rr.nombre_receta, "porciones": rr.porciones}
                for rr in reg.registros_recetas
            ],
            "puede_anular": not bool(getattr(reg, "anulado", False)),
            "correccion": "anular + nuevo registro (sin edición destructiva)",
        }

    if tipo == TIPO_MERMA:
        reg = next((m for m in app.mermas if m.id == evento_id), None)
        if not reg:
            return None
        return {
            "tipo": tipo,
            "id": reg.id,
            "fecha": reg.fecha,
            "hora": reg.hora,
            "responsable": reg.registrado_por,
            "coste_total": reg.coste_total,
            "anulado": bool(getattr(reg, "anulado", False)),
            "lineas": [
                {
                    "producto": ln.producto_nombre_snapshot
                    or repo.get_nombre_producto(ln.producto_id),
                    "cantidad": ln.cantidad,
                    "motivo": ln.motivo.value if hasattr(ln.motivo, "value") else ln.motivo,
                    "lote_id": ln.lote_id,
                    "servicio": getattr(ln, "tipo_servicio_snapshot", None),
                }
                for ln in reg.lineas
            ],
            "puede_anular": not bool(getattr(reg, "anulado", False)),
            "correccion": "anular merma (compensación de lotes)",
        }

    if tipo == TIPO_AJUSTE:
        reg = next((a for a in (getattr(app, "ajustes", []) or []) if a.id == evento_id), None)
        if not reg:
            return None
        return {
            "tipo": tipo,
            "id": reg.id,
            "fecha": reg.fecha,
            "hora": getattr(reg, "hora", None),
            "responsable": getattr(reg, "registrado_por", ""),
            "lineas": [
                {
                    "producto": ln.producto_nombre_snapshot
                    or repo.get_nombre_producto(ln.producto_id),
                    "lote_id": ln.lote_id,
                    "delta": ln.delta,
                    "motivo": ln.motivo.value if hasattr(ln.motivo, "value") else str(ln.motivo),
                }
                for ln in reg.lineas
            ],
            "puede_anular": False,
            "correccion": "Crear ajuste compensatorio (sin soft-anulación).",
        }

    return None
