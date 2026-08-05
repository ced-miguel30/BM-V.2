"""Resumen operativo para la barra lateral."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.services.data_service import get_repository


@dataclass
class AlertaSidebar:
    tipo: str
    titulo: str
    detalle: str


def resumen_sidebar() -> dict:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    repo = get_repository()
    negativos = repo.productos_stock_negativo()
    agotados = repo.productos_stock_cero()
    stock_bajo = repo.productos_stock_bajo()

    alertas: list[AlertaSidebar] = []

    if not repo.desayuno_registrado_hoy():
        alertas.append(AlertaSidebar(
            "warning",
            "Desayuno pendiente",
            "Hoy no se ha registrado el desayuno.",
        ))

    if negativos:
        nombres = ", ".join(
            f"{p.nombre} ({stock:g})" for p, stock in negativos[:3]
        )
        extra = f" (+{len(negativos) - 3})" if len(negativos) > 3 else ""
        alertas.append(AlertaSidebar(
            "danger",
            f"Stock negativo ({len(negativos)})",
            nombres + extra,
        ))

    if agotados:
        nombres = ", ".join(p.nombre for p in agotados[:3])
        extra = f" (+{len(agotados) - 3})" if len(agotados) > 3 else ""
        alertas.append(AlertaSidebar(
            "danger",
            f"Sin stock ({len(agotados)})",
            nombres + extra,
        ))

    if stock_bajo:
        nombres = ", ".join(p.nombre for p, _ in stock_bajo[:3])
        extra = f" (+{len(stock_bajo) - 3})" if len(stock_bajo) > 3 else ""
        alertas.append(AlertaSidebar(
            "warning",
            f"Stock bajo ({len(stock_bajo)})",
            nombres + extra,
        ))

    if not alertas:
        alertas.append(AlertaSidebar(
            "ok",
            "Operación normal",
            "Sin alertas críticas de stock.",
        ))

    return {
        "coste_consumo_mes": repo.formato_precio(repo.coste_consumo_mes()),
        "coste_total_mes": repo.formato_precio(repo.coste_total_mes()),
        "alertas": alertas,
    }
