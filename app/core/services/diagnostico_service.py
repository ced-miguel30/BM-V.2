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
    num_ajustes: int
    num_lineas_ajuste: int

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
    # Fase 10.5 — trazabilidad por lote (solo lectura).
    num_lineas_con_trazabilidad_lote: int = 0
    sin_trazabilidad_historica_lote: list[str] = field(default_factory=list)
    incidencias_trazabilidad_lote: list[str] = field(default_factory=list)
    nota_trazabilidad_lote: str = (
        "Limitación: sin versión de registro, una línea con consumos_lote vacío "
        "se etiqueta como «Sin trazabilidad histórica por lote» (no corrupción). "
        "El alta nueva exige consumos_lote completo antes de persistir."
    )


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

    for ajuste in getattr(data, "ajustes", []) or []:
        for linea in ajuste.lineas:
            if linea.producto_id not in producto_ids:
                huerfanas.append(
                    f"Ajuste {ajuste.id} → producto inexistente {linea.producto_id}"
                )
            if linea.lote_id and linea.lote_id not in lote_ids:
                huerfanas.append(
                    f"Ajuste {ajuste.id} → lote inexistente {linea.lote_id}"
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
    duplicidades.extend(
        _ids_duplicados([a.id for a in getattr(data, "ajustes", []) or []], "Ajuste")
    )

    otras: list[str] = []
    nombres_prod = [p.nombre.strip().lower() for p in data.productos if p.nombre]
    if len(nombres_prod) != len(set(nombres_prod)):
        otras.append("Hay nombres de producto repetidos (mismo nombre, distinto id).")

    num_con_traza = 0
    sin_traza_hist: list[str] = []
    incid_traza: list[str] = []
    lotes_map = {l.id: l for l in data.lotes}

    def _revisar_detalle(etiqueta: str, det) -> None:
        nonlocal num_con_traza
        if det.cantidad <= 0:
            return
        consumos = getattr(det, "consumos_lote", None) or []
        if not consumos:
            sin_traza_hist.append(
                f"{etiqueta}: Sin trazabilidad histórica por lote "
                f"(producto {det.producto_id}, cant. {det.cantidad:g})"
            )
            return
        num_con_traza += 1
        suma_cant = round(sum(c.cantidad for c in consumos), 4)
        suma_coste = round(sum(c.coste for c in consumos), 2)
        if abs(suma_cant - round(det.cantidad, 4)) > 1e-9:
            incid_traza.append(
                f"{etiqueta}: Incidencia: trazabilidad por lote incompleta "
                f"(cantidad {suma_cant:g} ≠ {det.cantidad:g})"
            )
        if suma_coste != round(det.coste, 2):
            incid_traza.append(
                f"{etiqueta}: Incidencia: trazabilidad por lote incompleta "
                f"(coste {suma_coste:.2f} ≠ {det.coste:.2f})"
            )
        for c in consumos:
            if not c.lote_id:
                incid_traza.append(
                    f"{etiqueta}: Incidencia: trazabilidad por lote incompleta "
                    "(lote_id vacío)"
                )
                continue
            if c.producto_id != det.producto_id:
                incid_traza.append(
                    f"{etiqueta}: Incidencia: trazabilidad por lote incompleta "
                    f"(producto fragmento {c.producto_id} ≠ {det.producto_id})"
                )
            lote = lotes_map.get(c.lote_id)
            if lote is None:
                incid_traza.append(
                    f"{etiqueta}: Incidencia: trazabilidad por lote incompleta "
                    f"(lote inexistente {c.lote_id})"
                )
            elif lote.producto_id != c.producto_id:
                incid_traza.append(
                    f"{etiqueta}: Incidencia: trazabilidad por lote incompleta "
                    f"(lote {c.lote_id} es {lote.producto_id}, no {c.producto_id})"
                )

    for desayuno in data.desayunos:
        for det in desayuno.lineas_detalle:
            _revisar_detalle(f"Desayuno {desayuno.id}", det)
    for reg in data.registros_servicio:
        for det in reg.lineas_detalle:
            _revisar_detalle(f"Registro {reg.id} ({reg.tipo_servicio})", det)

    num_detalle = sum(len(d.lineas_detalle) for d in data.desayunos) + sum(
        len(r.lineas_detalle) for r in data.registros_servicio
    )
    num_lineas_merma = sum(len(m.lineas) for m in data.mermas)
    ajustes = getattr(data, "ajustes", []) or []
    num_lineas_ajuste = sum(len(a.lineas) for a in ajustes)

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
        num_ajustes=len(ajustes),
        num_lineas_ajuste=num_lineas_ajuste,
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
        num_lineas_con_trazabilidad_lote=num_con_traza,
        sin_trazabilidad_historica_lote=sin_traza_hist,
        incidencias_trazabilidad_lote=incid_traza,
    )
