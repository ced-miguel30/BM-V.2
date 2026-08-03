"""Fase 1B — invariantes del JSON / anulaciones (solo lectura).

Módulo de diagnóstico separado de los tests de caracterización (Fase 1A).
No muta AppData. Consumido por `diagnostico_service` y la UI de Settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.models import AppData


@dataclass(frozen=True)
class ResumenInvariantesJson:
    """Conteos e incidencias de soft-delete / trazabilidad / coherencia básica."""

    num_registros_anulados: int = 0
    num_mermas_anuladas: int = 0
    num_compras_anuladas: int = 0
    num_registros_activos_con_traza: int = 0
    num_registros_activos_sin_traza: int = 0
    num_mermas_activas_sin_lote: int = 0
    incidencias_invariantes: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)


def _tiene_traza_lote(registro) -> bool:
    detalle = list(getattr(registro, "lineas_detalle", None) or [])
    if not detalle:
        return False
    for det in detalle:
        if float(getattr(det, "cantidad", 0) or 0) <= 0:
            continue
        consumos = getattr(det, "consumos_lote", None) or []
        if not consumos:
            return False
    return any(
        float(getattr(det, "cantidad", 0) or 0) > 0
        for det in detalle
    )


def evaluar_invariantes_json(data: AppData) -> ResumenInvariantesJson:
    """Analiza invariantes de anulación y coherencia mínima sin modificar datos."""
    incidencias: list[str] = []
    notas: list[str] = [
        "Histórico sin consumos_lote: anulación de registro bloqueada (esperado).",
        "Merma sin lote_id: anulación bloqueada (esperado).",
        "Compra anulada conserva cantidad/precio originales; restante = 0.",
        "Este informe es solo lectura; no corrige datos.",
    ]

    n_reg_anul = 0
    n_con_traza = 0
    n_sin_traza = 0

    for d in data.desayunos:
        if getattr(d, "anulado", False):
            n_reg_anul += 1
            if not (getattr(d, "motivo_anulacion", None) or "").strip():
                incidencias.append(f"Desayuno anulado {d.id}: sin motivo_anulacion.")
            continue
        if _tiene_traza_lote(d):
            n_con_traza += 1
        elif getattr(d, "lineas_detalle", None) is not None:
            # Sin detalle o sin consumos → histórico / no anulable automático
            tiene_consumo = bool(d.lineas) or bool(d.registros_recetas) or float(d.coste_total or 0) > 0
            if tiene_consumo and not _tiene_traza_lote(d):
                n_sin_traza += 1

    for r in data.registros_servicio:
        if getattr(r, "anulado", False):
            n_reg_anul += 1
            if not (getattr(r, "motivo_anulacion", None) or "").strip():
                incidencias.append(
                    f"Registro anulado {r.id} ({r.tipo_servicio}): sin motivo_anulacion."
                )
            continue
        if _tiene_traza_lote(r):
            n_con_traza += 1
        else:
            tiene_consumo = bool(r.lineas) or bool(r.registros_recetas) or float(r.coste_total or 0) > 0
            if tiene_consumo:
                n_sin_traza += 1

    n_merma_anul = 0
    n_merma_sin_lote = 0
    for m in data.mermas:
        if getattr(m, "anulado", False):
            n_merma_anul += 1
            if not (getattr(m, "motivo_anulacion", None) or "").strip():
                incidencias.append(f"Merma anulada {m.id}: sin motivo_anulacion.")
            continue
        for i, ln in enumerate(m.lineas, start=1):
            if ln.cantidad > 0 and not ln.lote_id:
                n_merma_sin_lote += 1
                incidencias.append(
                    f"Merma activa {m.id} línea {i}: sin lote_id "
                    "(anulación automática bloqueada)."
                )

    n_compra_anul = 0
    for lote in data.lotes:
        if getattr(lote, "anulado", False):
            n_compra_anul += 1
            if abs(float(lote.cantidad_restante or 0)) > 1e-9:
                incidencias.append(
                    f"Compra anulada {lote.id}: cantidad_restante debería ser 0 "
                    f"(ahora {lote.cantidad_restante:g})."
                )
            if not (getattr(lote, "motivo_anulacion", None) or "").strip():
                incidencias.append(f"Compra anulada {lote.id}: sin motivo_anulacion.")
        elif float(lote.cantidad_restante or 0) < 0:
            incidencias.append(
                f"Lote {lote.id}: stock restante negativo ({lote.cantidad_restante:g})."
            )

    # IDs duplicados (invariante de carga JSON)
    for etiqueta, ids in (
        ("Producto", [p.id for p in data.productos]),
        ("Lote", [l.id for l in data.lotes]),
        ("Desayuno", [d.id for d in data.desayunos]),
        ("Registro servicio", [r.id for r in data.registros_servicio]),
        ("Merma", [m.id for m in data.mermas]),
    ):
        vistos: set[str] = set()
        for i in ids:
            if i in vistos:
                incidencias.append(f"{etiqueta} id duplicado: {i}")
            else:
                vistos.add(i)

    return ResumenInvariantesJson(
        num_registros_anulados=n_reg_anul,
        num_mermas_anuladas=n_merma_anul,
        num_compras_anuladas=n_compra_anul,
        num_registros_activos_con_traza=n_con_traza,
        num_registros_activos_sin_traza=n_sin_traza,
        num_mermas_activas_sin_lote=n_merma_sin_lote,
        incidencias_invariantes=incidencias,
        notas=notas,
    )
