"""Configuración editable del consumo buffet (seed y sincronización Excel)."""

from __future__ import annotations

from app.core.application.id_generator import next_id
from app.core.models import AppData, IngredienteReceta, Receta, ResponsableMerma
from app.core.models.buffet import (
    TIPO_LINEA_RECETA_ESTANDAR,
    TIPO_LINEA_SIMPLE,
    LineaConfigBuffet,
)
from app.core.models.enums import CategoriaReceta
from app.core.services.text_search import normalizar_texto

RECETA_ESTANDAR_BUFFET = "Estándar buffet desayuno diario"
RESPONSABLE_IMPORT_BUFFET = "Import Excel buffet"

# Receta: 1 L de zumo exprimido → kg de NARANJA ZUMO (b06). Editable en la receta.
RECETA_ZUMO_NARANJA_NATURAL = "Zumo naranja natural 1L"
LABEL_ZUMO_NARANJA_BRIK = "Zumo naranja brik 1L"
PRODUCTO_NARANJA_ZUMO = "b06"
PRODUCTO_ZUMO_BRIK = "b28"
NARANJAS_KG_POR_LITRO_ZUMO = 1.2

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


def ensure_receta_zumo_naranja_natural(data: AppData) -> str:
    """Crea/actualiza la receta 1 L zumo natural → kg NARANJA ZUMO (b06)."""
    if not hasattr(data, "recetas") or data.recetas is None:
        data.recetas = []
    key = normalizar_texto(RECETA_ZUMO_NARANJA_NATURAL)
    existente = next(
        (r for r in data.recetas if normalizar_texto(r.nombre) == key),
        None,
    )
    if existente is not None:
        if not existente.activo:
            existente.activo = True
        ings = list(existente.ingredientes or [])
        if not any(i.producto_id == PRODUCTO_NARANJA_ZUMO for i in ings):
            existente.ingredientes = [
                IngredienteReceta(
                    PRODUCTO_NARANJA_ZUMO,
                    NARANJAS_KG_POR_LITRO_ZUMO,
                    NARANJAS_KG_POR_LITRO_ZUMO,
                    "kg",
                )
            ]
        if existente.porciones_estandar is None:
            existente.porciones_estandar = 1.0
        return existente.id

    rid = next_id("r", [r.id for r in data.recetas])
    data.recetas.append(
        Receta(
            id=rid,
            nombre=RECETA_ZUMO_NARANJA_NATURAL,
            ingredientes=[
                IngredienteReceta(
                    PRODUCTO_NARANJA_ZUMO,
                    NARANJAS_KG_POR_LITRO_ZUMO,
                    NARANJAS_KG_POR_LITRO_ZUMO,
                    "kg",
                )
            ],
            categoria=CategoriaReceta.DESAYUNO,
            servicios_disponibles=["desayuno"],
            porciones_estandar=1.0,
            activo=True,
        )
    )
    return rid


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
    fiambres = {
        "Paleta iberica", "Mortadela", "Salchichon iberico",
        "Queso gofio", "Queso pimenton", "Queso fresco",
        "Queso cheddar", "Queso gouda", "Bacon", "Jamon cocido",
        "Salchicha", "Chorizo", "Salmon",
    }
    panes = {
        "Tostada", "Tostada integral", "Pan blanco", "Pan integral",
        "Tostada sin gluten", "Pan sin gluten",
        "Croissant sin gluten", "Magdalena sin gluten",
        "Pan gallego", "Pan maiz", "Pan centeno", "Baguettina",
        "Napolitana cacao", "Chic crema", "Lazo cereal",
        "Croissant mantequilla", "Croissant chocolate", "Surtido reposteria",
    }

    for extra in _EXTRAS_RAPIDOS_DESAYUNO:
        if extra.label.startswith("Huevo") or extra.label == "Huevos revueltos":
            continue
        if extra.label in frutas:
            seccion = "Frutas"
        elif extra.label in fiambres:
            seccion = "Fiambres"
        elif extra.label in panes:
            seccion = "Pan"
        else:
            seccion = "Otros"
        push(
            seccion,
            extra.label,
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
        push("Jarras", label, pid, unidad, qty)

    rid_zumo = ensure_receta_zumo_naranja_natural(data)
    push(
        "Jarras",
        RECETA_ZUMO_NARANJA_NATURAL,
        "",
        "L",
        1.0,
        tipo_linea=TIPO_LINEA_RECETA_ESTANDAR,
        receta_id=rid_zumo,
    )
    push(
        "Jarras",
        LABEL_ZUMO_NARANJA_BRIK,
        PRODUCTO_ZUMO_BRIK,
        "Ud",
        1.0,
        tipo_linea=TIPO_LINEA_SIMPLE,
    )

    for label, pid, unidad, qty in _PORCIONES_SEED:
        push("Porciones", label, pid, unidad, qty)

    return lineas


def ensure_config_buffet(data: AppData) -> bool:
    """Si falta config_buffet, la siembra. Migra zumo naranja a 2 conceptos."""
    muto = False
    if not data.config_buffet:
        data.config_buffet = seed_config_buffet(data)
        return True
    if _asegurar_conceptos_zumo_naranja(data):
        muto = True
    return muto


def _asegurar_conceptos_zumo_naranja(data: AppData) -> bool:
    """Sustituye jarra_zumo antigua por receta natural + brik (sin columna Excel)."""
    muto = False
    rid = ensure_receta_zumo_naranja_natural(data)

    for cfg in data.config_buffet:
        # Desactivar el concepto legado «Jarra zumo naranja» (tipo jarra_zumo)
        if cfg.tipo_linea == "jarra_zumo" and "naranja" in (cfg.label or "").lower():
            if cfg.activo:
                cfg.activo = False
                muto = True

    labels = {
        normalizar_texto(c.label): c
        for c in data.config_buffet
    }
    key_nat = normalizar_texto(RECETA_ZUMO_NARANJA_NATURAL)
    key_brik = normalizar_texto(LABEL_ZUMO_NARANJA_BRIK)
    ids = [c.id for c in data.config_buffet]
    orden_max = max((c.orden for c in data.config_buffet), default=0)

    nat = labels.get(key_nat)
    if nat is None:
        data.config_buffet.append(
            LineaConfigBuffet(
                id=next_id("cb", ids),
                seccion="Jarras",
                orden=orden_max + 1,
                label=RECETA_ZUMO_NARANJA_NATURAL,
                producto_id="",
                unidad="L",
                cantidad_defecto=1.0,
                activo=True,
                tipo_linea=TIPO_LINEA_RECETA_ESTANDAR,
                receta_id=rid,
            )
        )
        ids.append(data.config_buffet[-1].id)
        orden_max += 1
        muto = True
    else:
        if not nat.activo:
            nat.activo = True
            muto = True
        if nat.tipo_linea != TIPO_LINEA_RECETA_ESTANDAR:
            nat.tipo_linea = TIPO_LINEA_RECETA_ESTANDAR
            muto = True
        if nat.receta_id != rid:
            nat.receta_id = rid
            muto = True

    brik = labels.get(key_brik)
    if brik is None:
        data.config_buffet.append(
            LineaConfigBuffet(
                id=next_id("cb", ids),
                seccion="Jarras",
                orden=orden_max + 1,
                label=LABEL_ZUMO_NARANJA_BRIK,
                producto_id=PRODUCTO_ZUMO_BRIK,
                unidad="Ud",
                cantidad_defecto=1.0,
                activo=True,
                tipo_linea=TIPO_LINEA_SIMPLE,
            )
        )
        muto = True
    else:
        if not brik.activo:
            brik.activo = True
            muto = True
        if brik.producto_id != PRODUCTO_ZUMO_BRIK:
            brik.producto_id = PRODUCTO_ZUMO_BRIK
            muto = True
        if brik.tipo_linea != TIPO_LINEA_SIMPLE:
            brik.tipo_linea = TIPO_LINEA_SIMPLE
            muto = True

    return muto


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
            avisos.append(f"Concepto nuevo no creado automáticamente: «{label}»")
            continue
        if raw.get("seccion"):
            cfg.seccion = str(raw["seccion"]).strip()
        if raw.get("orden") is not None:
            try:
                cfg.orden = int(raw["orden"])
            except (TypeError, ValueError):
                pass
        if raw.get("producto_id") is not None:
            cfg.producto_id = str(raw["producto_id"] or "").strip()
        if raw.get("unidad"):
            cfg.unidad = str(raw["unidad"]).strip()
        if raw.get("cantidad_defecto") is not None:
            try:
                cfg.cantidad_defecto = float(raw["cantidad_defecto"])
            except (TypeError, ValueError):
                pass
        if raw.get("tipo"):
            cfg.tipo_linea = str(raw["tipo"]).strip()
        if "producto_bote" in raw:
            cfg.producto_bote_id = str(raw.get("producto_bote") or "").strip() or None
        if "receta_id" in raw:
            cfg.receta_id = str(raw.get("receta_id") or "").strip() or None
        act = raw.get("activo")
        if act is not None:
            s = str(act).strip().lower()
            cfg.activo = s in ("si", "sí", "1", "true", "yes", "activo")
        actualizadas += 1
    return actualizadas, avisos
