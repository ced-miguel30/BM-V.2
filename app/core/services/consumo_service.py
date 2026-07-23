"""Servicio de análisis y predicción de consumo."""

from datetime import date, datetime

from app.core.repositories.data_repository import DataRepository
from app.core.services.data_service import get_repository
from app.core.services.desayuno_service import fecha_mas_antigua as _fecha_mas_antigua_desayuno
from app.core.services.desayuno_service import stock_disponible
from app.core.services.excel_bloques import RegistroExportable
from app.core.services.exportacion_semanal_service import ConfiguracionExportacionModulo
from app.core.services.unidad_service import presentacion_legible
from app.core.storage.session_store import get_data


def _coste_medio_unidad(repo: DataRepository, producto_id: str) -> float:
    lotes = [l for l in repo.data.lotes if l.producto_id == producto_id and l.cantidad > 0]
    if not lotes:
        return 0.0
    total_precio = sum(l.precio_total for l in lotes)
    total_cant = sum(l.cantidad for l in lotes)
    return total_precio / total_cant if total_cant > 0 else 0.0


def consumo_medio_diario_por_producto() -> dict[str, float]:
    """Media de cantidad consumida por producto y por día con desayuno."""
    repo = get_repository()
    dias = {d.fecha for d in repo.data.desayunos}
    if not dias:
        return {}

    totales: dict[str, float] = {}
    for desayuno in repo.data.desayunos:
        for linea in desayuno.lineas:
            totales[linea.producto_id] = totales.get(linea.producto_id, 0) + linea.cantidad

    return {pid: total / len(dias) for pid, total in totales.items()}


def consumo_medio_por_huesped_por_producto() -> dict[str, float]:
    """Cantidad media consumida por huésped y producto según registros de desayuno."""
    repo = get_repository()
    totales: dict[str, float] = {}
    total_huespedes = 0

    for desayuno in repo.data.desayunos:
        if desayuno.num_huespedes <= 0:
            continue
        total_huespedes += desayuno.num_huespedes
        for linea in desayuno.lineas:
            totales[linea.producto_id] = totales.get(linea.producto_id, 0) + linea.cantidad

    if total_huespedes <= 0:
        return {}

    return {pid: total / total_huespedes for pid, total in totales.items()}


def media_huespedes_historico() -> float | None:
    repo = get_repository()
    valores = [d.num_huespedes for d in repo.data.desayunos if d.num_huespedes > 0]
    if not valores:
        return None
    return sum(valores) / len(valores)


def prediccion_necesidades(huespedes_esperados: int) -> dict:
    """Estima productos y costes según consumo histórico por huésped."""
    repo = get_repository()
    medias = consumo_medio_por_huesped_por_producto()
    media_huespedes = media_huespedes_historico()

    if huespedes_esperados <= 0:
        return {
            "productos": [],
            "coste_estimado": 0.0,
            "coste_estimado_fmt": repo.formato_precio(0),
            "recomendaciones": ["Indique el número esperado de huéspedes."],
            "media_huespedes": media_huespedes,
            "dias_historico": len({d.fecha for d in repo.data.desayunos}),
        }

    if not medias:
        return {
            "productos": [],
            "coste_estimado": 0.0,
            "coste_estimado_fmt": repo.formato_precio(0),
            "recomendaciones": [
                "No hay historial de desayunos con huéspedes para estimar necesidades. "
                "Registre desayunos indicando el número de huéspedes.",
            ],
            "media_huespedes": media_huespedes,
            "dias_historico": len({d.fecha for d in repo.data.desayunos}),
        }

    productos = []
    coste_total = 0.0
    recomendaciones: list[str] = []
    faltantes = []

    for producto in sorted(repo.data.productos, key=lambda p: p.nombre):
        media = medias.get(producto.id)
        if not media or media <= 0:
            continue

        cantidad_est = round(media * huespedes_esperados, 2)
        stock = stock_disponible(repo.data, producto.id)
        coste_u = _coste_medio_unidad(repo, producto.id)
        coste_est = round(cantidad_est * coste_u, 2)
        coste_total += coste_est

        deficit = max(0, cantidad_est - stock)
        productos.append({
            "producto": producto.nombre,
            "unidad": producto.unidad.value,
            "media_por_huesped": round(media, 4),
            "cantidad_estimada": cantidad_est,
            "stock_actual": stock,
            "coste_estimado": coste_est,
            "coste_estimado_fmt": repo.formato_precio(coste_est),
            "deficit": round(deficit, 2),
        })

        if deficit > 0:
            faltantes.append(
                f"«{producto.nombre}»: faltan ~{deficit:g} {producto.unidad.value} "
                f"(stock {stock:g}, estimado {cantidad_est:g})."
            )

    if faltantes:
        recomendaciones.append("Revise compras para los siguientes productos:")
        recomendaciones.extend(faltantes[:5])
        if len(faltantes) > 5:
            recomendaciones.append(f"... y {len(faltantes) - 5} producto(s) más.")
    else:
        recomendaciones.append(
            f"Con {huespedes_esperados} huéspedes, el stock actual cubre la estimación."
        )

    stock_bajo = repo.productos_stock_bajo()
    if stock_bajo:
        nombres = ", ".join(p.nombre for p, _ in stock_bajo[:3])
        recomendaciones.append(f"Atención: stock bajo en {nombres}.")

    return {
        "productos": productos,
        "coste_estimado": round(coste_total, 2),
        "coste_estimado_fmt": repo.formato_precio(coste_total),
        "recomendaciones": recomendaciones,
        "media_huespedes": media_huespedes,
        "dias_historico": len({d.fecha for d in repo.data.desayunos}),
    }


def consumo_por_producto_periodo(inicio: date, fin: date) -> list[dict]:
    repo = get_repository()
    totales: dict[str, float] = {}
    for desayuno in repo.data.desayunos:
        if inicio <= desayuno.fecha <= fin:
            for linea in desayuno.lineas:
                totales[linea.producto_id] = totales.get(linea.producto_id, 0) + linea.cantidad

    return [
        {
            "producto": repo.get_nombre_producto(pid),
            "cantidad": cantidad,
        }
        for pid, cantidad in sorted(totales.items(), key=lambda x: x[1], reverse=True)
    ]


# ---------------------------------------------------------------------------
# Fase 5 — Rankings de consumo (productos / recetas / bebidas)
# ---------------------------------------------------------------------------
#
# El consumo por producto (directo + vía receta, ya consolidado y sin doble
# contabilización) está en `RegistroDesayuno.lineas`: `_aplanar_cesta()` fusiona
# en una única cantidad neta por producto tanto los productos sueltos como los
# ingredientes de receta (con sus extras/omisiones) antes de descontar stock.
# Por eso no hace falta "sumar" aquí directo + receta por separado: ya viene
# sumado una sola vez por producto y por registro.
#
# Las recetas, en cambio, no están en `lineas` (solo sus ingredientes): se
# cuentan a partir de `registros_recetas`, como una entidad independiente de
# sus ingredientes (que sí cuentan en el ranking de productos/bebidas).


def _agregar_consumo_productos(inicio: date, fin: date) -> dict[str, dict]:
    """Cantidad, coste y nº de registros por producto en `[inicio, fin]`
    (fechas de desayuno, inclusive). Usa siempre la unidad nativa del
    producto, así que no requiere conversión para sumar entre registros."""
    repo = get_repository()
    agregados: dict[str, dict] = {}
    for desayuno in repo.data.desayunos:
        if not (inicio <= desayuno.fecha <= fin):
            continue
        for linea in desayuno.lineas:
            if linea.cantidad <= 0:
                continue
            entry = agregados.setdefault(linea.producto_id, {"cantidad": 0.0, "coste": 0.0, "usos": 0})
            entry["cantidad"] = round(entry["cantidad"] + linea.cantidad, 4)
            entry["coste"] = round(entry["coste"] + linea.coste, 2)
            entry["usos"] += 1
    return agregados


def ranking_productos_periodo(
    inicio: date,
    fin: date,
    *,
    es_bebida: bool = False,
    ascendente: bool = False,
    limite: int = 5,
) -> list[dict]:
    """Ranking de productos (o bebidas, si `es_bebida=True`) más/menos
    consumidos en el periodo. Solo incluye elementos con consumo > 0."""
    repo = get_repository()
    agregados = _agregar_consumo_productos(inicio, fin)

    # Se ordena por la cantidad nativa (antes de convertir a unidad legible)
    # para que la comparación entre productos del mismo tipo sea consistente
    # con independencia de qué unidad de presentación se elija para mostrar.
    candidatos = [
        (producto, datos)
        for producto_id, datos in agregados.items()
        if (producto := repo.get_producto(producto_id))
        and producto.es_bebida == es_bebida
        and datos["cantidad"] > 0
    ]
    candidatos.sort(key=lambda item: item[1]["cantidad"], reverse=not ascendente)

    filas = []
    for producto, datos in candidatos[:limite]:
        cantidad_mostrar, unidad_mostrar = presentacion_legible(datos["cantidad"], producto.unidad)
        filas.append({
            "nombre": producto.nombre,
            "cantidad": cantidad_mostrar,
            "unidad": unidad_mostrar,
            "cantidad_fmt": f"{cantidad_mostrar:g} {unidad_mostrar}",
            "usos": datos["usos"],
            "coste": datos["coste"],
            "coste_fmt": repo.formato_precio(datos["coste"]),
        })
    return filas


def ranking_recetas_periodo(
    inicio: date,
    fin: date,
    *,
    ascendente: bool = False,
    limite: int = 5,
) -> list[dict]:
    """Ranking de recetas más/menos consumidas (en porciones registradas),
    sin contabilizar sus ingredientes como recetas independientes."""
    repo = get_repository()
    agregados: dict[str, dict] = {}
    for desayuno in repo.data.desayunos:
        if not (inicio <= desayuno.fecha <= fin):
            continue
        for registro_receta in desayuno.registros_recetas:
            if registro_receta.porciones <= 0:
                continue
            entry = agregados.setdefault(
                registro_receta.receta_id,
                {"nombre": registro_receta.nombre_receta, "porciones": 0.0, "usos": 0},
            )
            entry["porciones"] = round(entry["porciones"] + registro_receta.porciones, 2)
            entry["usos"] += 1

    filas = [
        {
            "nombre": datos["nombre"],
            "cantidad": datos["porciones"],
            "unidad": "porciones",
            "cantidad_fmt": f"{datos['porciones']:g} porciones",
            "usos": datos["usos"],
            "coste": None,
            "coste_fmt": "—",
        }
        for datos in agregados.values()
        if datos["porciones"] > 0
    ]
    filas.sort(key=lambda f: f["cantidad"], reverse=not ascendente)
    return filas[:limite]


def fecha_mas_antigua() -> date | None:
    """El consumo proviene de los registros de desayuno: reutiliza su fecha
    más antigua para sembrar exportaciones pendientes."""
    return _fecha_mas_antigua_desayuno()


def registros_exportables(inicio: date, hasta: datetime) -> list[RegistroExportable]:
    """Historial detallado de consumo (no solo los rankings) entre `inicio`
    y `hasta`, para la exportación semanal del «Registro de Consumo»."""
    data = get_data()
    repo = DataRepository(data)
    fin = hasta.date()
    columnas = [
        "Tipo", "Producto o receta", "Cantidad visible", "Unidad visible",
        "Cantidad interna", "Unidad interna", "Coste", "Relación con receta",
    ]

    resultado: list[RegistroExportable] = []
    for desayuno in data.desayunos:
        if not (inicio <= desayuno.fecha <= fin):
            continue

        # Productos que son ingrediente (no omitido) de alguna receta usada en
        # este registro, con el/los nombre(s) de receta — informativo, ya que
        # `lineas` fusiona directo + vía receta en una única cantidad neta.
        origen_receta: dict[str, set[str]] = {}
        for registro_receta in desayuno.registros_recetas:
            receta = repo.get_receta(registro_receta.receta_id)
            omitidos = {o.producto_id for o in registro_receta.omisiones}
            for ingrediente in (receta.ingredientes if receta else []):
                if ingrediente.producto_id in omitidos:
                    continue
                origen_receta.setdefault(ingrediente.producto_id, set()).add(registro_receta.nombre_receta)

        filas: list[list] = []
        for registro_receta in desayuno.registros_recetas:
            filas.append([
                "Receta", registro_receta.nombre_receta, registro_receta.porciones, "porciones",
                "", "", "", "",
            ])

        for linea in desayuno.lineas:
            if linea.cantidad <= 0:
                continue
            producto = repo.get_producto(linea.producto_id)
            if not producto:
                continue
            tipo = "Bebida" if producto.es_bebida else "Producto"
            cantidad_mostrar, unidad_mostrar = presentacion_legible(linea.cantidad, producto.unidad)
            hay_conversion = unidad_mostrar != producto.unidad.value
            recetas_origen = origen_receta.get(linea.producto_id)
            relacion = ", ".join(sorted(recetas_origen)) if recetas_origen else "Directo"
            filas.append([
                tipo,
                repo.get_nombre_producto(linea.producto_id),
                cantidad_mostrar,
                unidad_mostrar,
                round(linea.cantidad, 4) if hay_conversion else "",
                producto.unidad.value if hay_conversion else "",
                linea.coste,
                relacion,
            ])

        resultado.append(RegistroExportable(
            fecha=desayuno.fecha,
            hora=desayuno.hora,
            tipo="Consumo",
            identificador=desayuno.id,
            usuario=desayuno.registrado_por or None,
            columnas=columnas,
            filas=filas,
            resumen=[
                ("Huéspedes", str(desayuno.num_huespedes)),
                ("Coste total", repo.formato_precio(desayuno.coste_total)),
            ],
        ))

    # Comida / Cena / Bebidas: detalle histórico desde lineas_detalle.
    for registro in data.registros_servicio:
        if not (inicio <= registro.fecha <= fin):
            continue
        filas_s: list[list] = []
        for rr in registro.registros_recetas:
            filas_s.append([
                "Receta",
                rr.nombre_receta,
                rr.porciones,
                "porciones",
                "",
                "",
                "",
                rr.categoria_receta_snapshot or rr.categoria_receta or registro.tipo_servicio,
            ])
        for det in registro.lineas_detalle:
            if det.cantidad <= 0:
                continue
            producto = repo.get_producto(det.producto_id)
            if not producto:
                continue
            es_bebida = (
                det.es_bebida_snapshot
                if det.es_bebida_snapshot is not None
                else producto.es_bebida
            )
            tipo = "Bebida" if es_bebida else "Producto"
            if det.origen == "extra_receta":
                tipo = f"Extra ({tipo})"
            elif det.origen == "ingrediente_receta":
                tipo = f"Ingrediente ({tipo})"
            cantidad_mostrar, unidad_mostrar = presentacion_legible(det.cantidad, producto.unidad)
            hay_conversion = unidad_mostrar != producto.unidad.value
            relacion = det.receta_origen_id or "Directo"
            if det.receta_origen_id:
                rec = repo.get_receta(det.receta_origen_id)
                relacion = rec.nombre if rec else det.receta_origen_id
            filas_s.append([
                tipo,
                producto.nombre,
                cantidad_mostrar,
                unidad_mostrar,
                round(det.cantidad, 4) if hay_conversion else "",
                producto.unidad.value if hay_conversion else "",
                det.coste,
                relacion,
            ])
        resultado.append(RegistroExportable(
            fecha=registro.fecha,
            hora=registro.hora,
            tipo=f"Consumo ({registro.tipo_servicio})",
            identificador=registro.id,
            usuario=registro.registrado_por or None,
            columnas=columnas,
            filas=filas_s,
            resumen=[
                ("Servicio", registro.tipo_servicio),
                ("Coste total", repo.formato_precio(registro.coste_total)),
            ],
        ))
    return resultado


def configuracion_exportacion() -> ConfiguracionExportacionModulo:
    return ConfiguracionExportacionModulo(
        tipo="consumo",
        titulo_documento="Registro de Consumo",
        obtener_registros=registros_exportables,
    )


# ---------------------------------------------------------------------------
# Fase 3 — Rankings multi-categoría (capa analítica)
# ---------------------------------------------------------------------------


def _fmt_productos(filas: list[dict], repo: DataRepository) -> list[dict]:
    from app.core.models import UnidadProducto

    out = []
    for f in filas:
        unidad = f.get("unidad_normalizada") or ""
        try:
            up = UnidadProducto(unidad) if unidad else None
        except ValueError:
            up = None
        if up is not None:
            cant, uni = presentacion_legible(f["cantidad_normalizada"], up)
            cantidad_fmt = f"{cant:g} {uni}"
        else:
            cantidad_fmt = f"{f['cantidad_normalizada']:g} {unidad}".strip()
        tipos = f.get("tipos") or []
        tipo_txt = ", ".join(tipos) if tipos else ("Bebida" if f.get("es_bebida") else "Producto")
        out.append({
            "nombre": f["nombre"],
            "cantidad": f["cantidad_normalizada"],
            "unidad": unidad,
            "cantidad_fmt": cantidad_fmt,
            "usos": f["usos"],
            "coste": f["coste"],
            "coste_fmt": repo.formato_precio(f["coste"]),
            "tipo": tipo_txt,
        })
    return out


def _fmt_recetas(filas: list[dict], repo: DataRepository) -> list[dict]:
    return [
        {
            "nombre": f["nombre"],
            "cantidad": f["porciones"],
            "unidad": "porciones",
            "cantidad_fmt": f"{f['porciones']:g} porciones",
            "usos": f["usos"],
            "coste": f.get("coste", 0.0),
            "coste_fmt": repo.formato_precio(f.get("coste", 0.0)),
            "categoria_receta": f.get("categoria_receta") or "—",
        }
        for f in filas
    ]


def ranking_analitico_productos(
    inicio: date,
    fin: date,
    *,
    ascendente: bool = False,
    limite: int = 10,
    tipo_servicio: str | None = None,
    bucket: str | None = None,
    tipos_elemento: list[str] | None = None,
    solo_consumo_bebida: bool | None = None,
    busqueda: str | None = None,
) -> list[dict]:
    from app.core.services import analitica_consumo_service as analitica

    repo = get_repository()
    filas = analitica.ranking_productos(
        inicio, fin,
        ascendente=ascendente,
        limite=limite,
        tipo_servicio=tipo_servicio,
        bucket=bucket,
        tipos_elemento=tipos_elemento,
        solo_consumo_bebida=solo_consumo_bebida,
        busqueda=busqueda,
    )
    return _fmt_productos(filas, repo)


def ranking_analitico_recetas(
    inicio: date,
    fin: date,
    *,
    ascendente: bool = False,
    limite: int = 10,
    tipo_servicio: str | None = None,
    categoria_receta: str | None = None,
    busqueda: str | None = None,
) -> list[dict]:
    from app.core.services import analitica_consumo_service as analitica

    repo = get_repository()
    filas = analitica.ranking_recetas(
        inicio, fin,
        ascendente=ascendente,
        limite=limite,
        tipo_servicio=tipo_servicio,
        categoria_receta=categoria_receta,
        busqueda=busqueda,
    )
    return _fmt_recetas(filas, repo)
