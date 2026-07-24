"""Diagnóstico técnico de solo lectura sobre AppData.

No muta datos, no escribe archivos y no corrige incidencias.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.models import AppData, UnidadProducto


@dataclass(frozen=True)
class ResumenDiagnostico:
    """Resultado inmutable del diagnóstico (solo lectura)."""

    num_productos: int
    num_recetas: int
    num_lotes_activos: int
    num_compras: int
    num_registros: int
    num_registros_desayuno: int
    num_registros_servicio: int
    num_lineas_detalle: int
    num_mermas: int
    num_lineas_merma: int

    lotes_stock_negativo: list[str] = field(default_factory=list)
    productos_stock_negativo: list[str] = field(default_factory=list)
    referencias_huerfanas: list[str] = field(default_factory=list)
    recetas_sin_ingredientes: list[str] = field(default_factory=list)
    productos_sin_unidad: list[str] = field(default_factory=list)
    productos_sin_servicio: list[str] = field(default_factory=list)
    recetas_sin_servicio: list[str] = field(default_factory=list)
    productos_sin_servicio_msg: str = ""
    registros_sin_snapshots: list[str] = field(default_factory=list)
    posibles_duplicidades: list[str] = field(default_factory=list)
    otras_incidencias: list[str] = field(default_factory=list)


def _ids_duplicados(ids: list[str], etiqueta: str) -> list[str]:
    vistos: set[str] = set()
    dupes: set[str] = set()
    for i in ids:
        if i in vistos:
            dupes.add(i)
        else:
            vistos.add(i)
    return [f"{etiqueta} id duplicado: {i}" for i in sorted(dupes)]


def generar_diagnostico(data: AppData) -> ResumenDiagnostico:
    """Analiza AppData sin modificarlo."""
    producto_ids = {p.id for p in data.productos}
    receta_ids = {r.id for r in data.recetas}
    lote_ids = {l.id for l in data.lotes}

    lotes_activos = [l for l in data.lotes if l.cantidad_restante > 0]
    lotes_negativos = [
        f"{l.id} ({l.producto_id}: {l.cantidad_restante:g})"
        for l in data.lotes
        if l.cantidad_restante < 0
    ]

    productos_neg = []
    for p in data.productos:
        stock = sum(l.cantidad_restante for l in data.lotes if l.producto_id == p.id)
        if stock < 0:
            productos_neg.append(f"{p.nombre} ({p.id}: {stock:g})")

    huerfanas: list[str] = []
    for lote in data.lotes:
        if lote.producto_id not in producto_ids:
            huerfanas.append(f"Lote {lote.id} → producto inexistente {lote.producto_id}")

    for receta in data.recetas:
        for ing in receta.ingredientes:
            if ing.producto_id not in producto_ids:
                huerfanas.append(
                    f"Receta {receta.id} ingrediente → producto inexistente {ing.producto_id}"
                )

    for desayuno in data.desayunos:
        for linea in desayuno.lineas:
            if linea.producto_id not in producto_ids:
                huerfanas.append(
                    f"Desayuno {desayuno.id} línea → producto inexistente {linea.producto_id}"
                )
        for reg_rec in desayuno.registros_recetas:
            if reg_rec.receta_id not in receta_ids:
                huerfanas.append(
                    f"Desayuno {desayuno.id} → receta inexistente {reg_rec.receta_id}"
                )
        for det in desayuno.lineas_detalle:
            if det.producto_id not in producto_ids:
                huerfanas.append(
                    f"Desayuno {desayuno.id} detalle → producto inexistente {det.producto_id}"
                )

    for reg in data.registros_servicio:
        for linea in reg.lineas:
            if linea.producto_id not in producto_ids:
                huerfanas.append(
                    f"Registro {reg.id} ({reg.tipo_servicio}) → producto inexistente {linea.producto_id}"
                )
        for reg_rec in reg.registros_recetas:
            if reg_rec.receta_id not in receta_ids:
                huerfanas.append(
                    f"Registro {reg.id} → receta inexistente {reg_rec.receta_id}"
                )
        for det in reg.lineas_detalle:
            if det.producto_id not in producto_ids:
                huerfanas.append(
                    f"Registro {reg.id} detalle → producto inexistente {det.producto_id}"
                )

    for merma in data.mermas:
        for linea in merma.lineas:
            if linea.producto_id not in producto_ids:
                huerfanas.append(
                    f"Merma {merma.id} → producto inexistente {linea.producto_id}"
                )
            if linea.lote_id and linea.lote_id not in lote_ids:
                huerfanas.append(
                    f"Merma {merma.id} → lote inexistente {linea.lote_id}"
                )

    recetas_vacias = [
        f"{r.nombre} ({r.id})" for r in data.recetas if not r.ingredientes
    ]

    sin_unidad: list[str] = []
    for p in data.productos:
        unidad = getattr(p, "unidad", None)
        if unidad is None or not isinstance(unidad, UnidadProducto):
            sin_unidad.append(f"{p.nombre} ({p.id})")

    sin_servicio_prod = [
        f"{p.nombre} ({p.id})"
        for p in data.productos
        if not getattr(p, "servicios_disponibles", None)
    ]
    sin_servicio_rec = [
        f"{r.nombre} ({r.id})"
        for r in data.recetas
        if not getattr(r, "servicios_disponibles", None)
    ]
    msg_servicios = (
        f"Productos sin servicios_disponibles: {len(sin_servicio_prod)}. "
        f"Recetas sin servicios_disponibles: {len(sin_servicio_rec)}. "
        "Vacío = No configurado (aún no se filtran registros; eso es Fase 4B)."
    )

    sin_snapshots: list[str] = []
    for desayuno in data.desayunos:
        tiene_consumo = bool(desayuno.lineas) or bool(desayuno.registros_recetas)
        if tiene_consumo and not desayuno.lineas_detalle:
            sin_snapshots.append(
                f"Desayuno {desayuno.id} ({desayuno.fecha}): sin lineas_detalle"
            )
        for reg_rec in desayuno.registros_recetas:
            if not getattr(reg_rec, "categoria_receta_snapshot", None):
                sin_snapshots.append(
                    f"Desayuno {desayuno.id} receta {reg_rec.receta_id}: "
                    "sin categoria_receta_snapshot"
                )

    for reg in data.registros_servicio:
        tiene_consumo = bool(reg.lineas) or bool(reg.registros_recetas)
        if tiene_consumo and not reg.lineas_detalle:
            sin_snapshots.append(
                f"Registro {reg.id} ({reg.tipo_servicio}, {reg.fecha}): sin lineas_detalle"
            )
        for reg_rec in reg.registros_recetas:
            if not getattr(reg_rec, "categoria_receta_snapshot", None):
                sin_snapshots.append(
                    f"Registro {reg.id} receta {reg_rec.receta_id}: "
                    "sin categoria_receta_snapshot"
                )

    for merma in data.mermas:
        for idx, linea in enumerate(merma.lineas, start=1):
            if getattr(linea, "tipo_servicio_snapshot", None) is None:
                sin_snapshots.append(
                    f"Merma {merma.id} línea {idx}: sin tipo_servicio_snapshot "
                    "(Sin desglose histórico)"
                )

    duplicidades = []
    duplicidades.extend(_ids_duplicados([p.id for p in data.productos], "Producto"))
    duplicidades.extend(_ids_duplicados([r.id for r in data.recetas], "Receta"))
    duplicidades.extend(_ids_duplicados([l.id for l in data.lotes], "Lote"))
    duplicidades.extend(_ids_duplicados([d.id for d in data.desayunos], "Desayuno"))
    duplicidades.extend(
        _ids_duplicados([r.id for r in data.registros_servicio], "Registro servicio")
    )
    duplicidades.extend(_ids_duplicados([m.id for m in data.mermas], "Merma"))

    otras: list[str] = []
    nombres_prod = [p.nombre.strip().lower() for p in data.productos if p.nombre]
    if len(nombres_prod) != len(set(nombres_prod)):
        otras.append("Hay nombres de producto repetidos (mismo nombre, distinto id).")

    num_detalle = sum(len(d.lineas_detalle) for d in data.desayunos) + sum(
        len(r.lineas_detalle) for r in data.registros_servicio
    )
    num_lineas_merma = sum(len(m.lineas) for m in data.mermas)

    return ResumenDiagnostico(
        num_productos=len(data.productos),
        num_recetas=len(data.recetas),
        num_lotes_activos=len(lotes_activos),
        num_compras=len(data.lotes),
        num_registros=len(data.desayunos) + len(data.registros_servicio),
        num_registros_desayuno=len(data.desayunos),
        num_registros_servicio=len(data.registros_servicio),
        num_lineas_detalle=num_detalle,
        num_mermas=len(data.mermas),
        num_lineas_merma=num_lineas_merma,
        lotes_stock_negativo=lotes_negativos,
        productos_stock_negativo=productos_neg,
        referencias_huerfanas=huerfanas,
        recetas_sin_ingredientes=recetas_vacias,
        productos_sin_unidad=sin_unidad,
        productos_sin_servicio=sin_servicio_prod,
        recetas_sin_servicio=sin_servicio_rec,
        productos_sin_servicio_msg=msg_servicios,
        registros_sin_snapshots=sin_snapshots,
        posibles_duplicidades=duplicidades,
        otras_incidencias=otras,
    )
