"""Servicio de análisis y predicción de consumo."""

from datetime import date

from app.core.repositories.data_repository import DataRepository
from app.core.services.data_service import get_repository
from app.core.services.desayuno_service import stock_disponible


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
