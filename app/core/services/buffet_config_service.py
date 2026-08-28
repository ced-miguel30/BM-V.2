"""Configuración editable del consumo buffet (seed y sincronización Excel)."""

from __future__ import annotations

from app.core.application.id_generator import next_id
from app.core.models import AppData, ResponsableMerma
from app.core.models.buffet import (
    TIPO_LINEA_JARRA_ZUMO,
    TIPO_LINEA_RECETA_ESTANDAR,
    TIPO_LINEA_SIMPLE,
    LineaConfigBuffet,
)
from app.core.services import desayuno_service as des

RECETA_ESTANDAR_BUFFET = "Estándar buffet desayuno diario"
RESPONSABLE_IMPORT_BUFFET = "Import Excel buffet"

# Productos porciones / jarras (editables en ConfigBuffet si faltan en catálogo).
_PORCIONES_SEED: tuple[tuple[str, str, str, float], ...] = (
    ("Mantequilla porcion", "p152", "gr", 0.015),
    ("Margarina porcion", "p153", "gr", 0.015),
    ("Mermelada fresa", "p160", "gr", 0.02),
    ("Mermelada naranja", "p161", "gr", 0.02),
    ("Mermelada melocoton", "p162", "gr", 0.02),
    ("Pate porcion", "p164", "gr", 0.02),
    ("Sobrasada porcion", "p165", "gr", 0.02),
    ("Tomate natural porcion", "p166", "gr", 0.03),
)

_JARRAS_SEED: tuple[tuple[str, str, str, float], ...] = (
    ("Jarra leche entera 1L", "p127", "Ud", 1.0),
    ("Jarra leche semi 1L", "p128", "Ud", 1.0),
    ("Jarra zumo manzana", "", "Ud", 1.0),
    ("Jarra zumo piña", "", "Ud", 1.0),
    ("Jarra zumo cranberry", "", "Ud", 1.0),
    ("Jarra zumo naranja", "b06", "Ud", 1.0),
)


def _linea(
    data: AppData,
    *,
    seccion: str,
    orden: int,
    label: str,
    producto_id: str,
    unidad: str,
    cantidad_defecto: float,
    tipo_linea: str = TIPO_LINEA_SIMPLE,
    producto_bote_id: str | None = None,
    receta_id: str | None = None,
    ids_acumulados: list[str] | None = None,
) -> LineaConfigBuffet:
    existentes = [c.id for c in data.config_buffet] + list(ids_acumulados or [])
    nuevo_id = next_id("cb", existentes)
    if ids_acumulados is not None:
        ids_acumulados.append(nuevo_id)
    return LineaConfigBuffet(
        id=nuevo_id,
        seccion=seccion,
        orden=orden,
        label=label,
        producto_id=producto_id,
        unidad=unidad,
        cantidad_defecto=cantidad_defecto,
        activo=True,
        tipo_linea=tipo_linea,
        producto_bote_id=producto_bote_id,
        receta_id=receta_id,
    )


def _receta_buffet_id(data: AppData) -> str | None:
    for rec in data.recetas:
        if rec.nombre.strip().lower() == RECETA_ESTANDAR_BUFFET.lower():
            return rec.id
    return None


def seed_config_buffet(data: AppData) -> list[LineaConfigBuffet]:
    """Genera la configuración por defecto desde extras desayuno + líneas fijas."""
    from app.core.services.desayuno_service import _EXTRAS_RAPIDOS_DESAYUNO

    lineas: list[LineaConfigBuffet] = []
    ids_nuevos: list[str] = []
    orden = 1

    def push(
        seccion: str,
        label: str,
        producto_id: str,
        unidad: str,
        cantidad: float,
        *,
        tipo_linea: str = TIPO_LINEA_SIMPLE,
        producto_bote_id: str | None = None,
        receta_id: str | None = None,
    ) -> None:
        nonlocal orden
        lineas.append(
            _linea(
                data,
                seccion=seccion,
                orden=orden,
                label=label,
                producto_id=producto_id,
                unidad=unidad,
                cantidad_defecto=cantidad,
                tipo_linea=tipo_linea,
                producto_bote_id=producto_bote_id,
                receta_id=receta_id,
                ids_acumulados=ids_nuevos,
            )
        )
        orden += 1

    frutas = {
        "Kiwi", "Papaya", "Melon", "Sandia", "Pomelo", "Naranja", "Platano",
        "Pina", "Melocoton almibar",
    }
    embutidos = {
        "Paleta iberica", "Mortadela", "Salchichon iberico",
        "Queso gofio", "Queso pimenton", "Queso fresco",
    }
    panes = {
        "Pan gallego", "Pan maiz", "Pan centeno", "Baguettina",
    }
    bolleria = {
        "Napolitana cacao", "Chic crema", "Lazo cereal",
        "Croissant mantequilla", "Croissant chocolate", "Surtido reposteria",
    }

    for extra in _EXTRAS_RAPIDOS_DESAYUNO:
        label = extra.label
        if label in frutas:
            seccion = "Frutas"
        elif label in embutidos:
            seccion = "Embutidos"
        elif label in panes:
            seccion = "Pan"
        elif label in bolleria:
            seccion = "Bolleria"
        else:
            continue
        push(
            seccion,
            label,
            extra.producto_id,
            extra.unidad_mostrar,
            float(extra.cantidad),
        )

    receta_id = _receta_buffet_id(data)
    push(
        "Estandar",
        RECETA_ESTANDAR_BUFFET,
        "",
        "porciones",
        1.0,
        tipo_linea=TIPO_LINEA_RECETA_ESTANDAR,
        receta_id=receta_id,
    )

    for label, pid, unidad, qty in _JARRAS_SEED:
        if label == "Jarra zumo naranja":
            push(
                "Jarras",
                label,
                pid,
                unidad,
                qty,
                tipo_linea=TIPO_LINEA_JARRA_ZUMO,
                producto_bote_id="b28",
            )
        else:
            push("Jarras", label, pid, unidad, qty)

    for label, pid, unidad, qty in _PORCIONES_SEED:
        push("Porciones", label, pid, unidad, qty)

    return lineas


def ensure_config_buffet(data: AppData) -> bool:
    """Si falta config_buffet, la siembra. Devuelve True si mutó."""
    if data.config_buffet:
        return False
    data.config_buffet = seed_config_buffet(data)
    return True


def ensure_responsable_import(data: AppData) -> ResponsableMerma:
    for resp in data.responsables_merma:
        if resp.nombre.strip().lower() == RESPONSABLE_IMPORT_BUFFET.lower():
            if not resp.activo:
                resp.activo = True
            return resp
    rid = next_id("rm", [r.id for r in data.responsables_merma])
    nuevo = ResponsableMerma(rid, RESPONSABLE_IMPORT_BUFFET, True)
    data.responsables_merma.append(nuevo)
    return nuevo


def config_por_label(data: AppData, label: str) -> LineaConfigBuffet | None:
    key = (label or "").strip().lower()
    for cfg in data.config_buffet:
        if cfg.label.strip().lower() == key and cfg.activo:
            return cfg
    return None


def config_por_id(data: AppData, config_id: str) -> LineaConfigBuffet | None:
    return next((c for c in data.config_buffet if c.id == config_id), None)


def sincronizar_desde_excel(
    data: AppData,
    filas: list[dict],
) -> tuple[int, list[str]]:
    """Actualiza config_buffet desde filas ConfigBuffet del Excel.

    Cada fila: seccion, orden, label, producto_id, unidad, tipo, producto_bote,
    receta_id, activo.
    """
    avisos: list[str] = []
    if not filas:
        return 0, avisos

    por_label = {c.label.strip().lower(): c for c in data.config_buffet}
    actualizadas = 0
    for raw in filas:
        label = str(raw.get("label") or "").strip()
        if not label:
            continue
        cfg = por_label.get(label.lower())
        if cfg is None:
            cfg = _linea(
                data,
                seccion=str(raw.get("seccion") or "Otros"),
                orden=int(raw.get("orden") or len(data.config_buffet) + 1),
                label=label,
                producto_id=str(raw.get("producto_id") or "").strip(),
                unidad=str(raw.get("unidad") or "Ud"),
                cantidad_defecto=float(raw.get("cantidad_defecto") or 1.0),
                tipo_linea=str(raw.get("tipo_linea") or TIPO_LINEA_SIMPLE),
                producto_bote_id=(raw.get("producto_bote_id") or None),
                receta_id=(raw.get("receta_id") or None),
            )
            cfg.activo = bool(raw.get("activo", True))
            data.config_buffet.append(cfg)
            por_label[label.lower()] = cfg
            actualizadas += 1
            continue
        cfg.seccion = str(raw.get("seccion") or cfg.seccion)
        cfg.orden = int(raw.get("orden") or cfg.orden)
        pid = str(raw.get("producto_id") or cfg.producto_id or "").strip()
        cfg.producto_id = pid
        cfg.unidad = str(raw.get("unidad") or cfg.unidad)
        if raw.get("cantidad_defecto") is not None:
            cfg.cantidad_defecto = float(raw.get("cantidad_defecto"))
        cfg.tipo_linea = str(raw.get("tipo_linea") or cfg.tipo_linea)
        cfg.producto_bote_id = raw.get("producto_bote_id") or cfg.producto_bote_id
        cfg.receta_id = raw.get("receta_id") or cfg.receta_id
        if raw.get("activo") is not None:
            cfg.activo = bool(raw.get("activo"))
        actualizadas += 1
    data.config_buffet.sort(key=lambda c: (c.seccion, c.orden, c.label))
    return actualizadas, avisos
