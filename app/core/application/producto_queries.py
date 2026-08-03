"""Casos de uso piloto: lectura de productos (Fase 3).

No cambia la UI. Equivalente funcional a DataRepository.get_producto /
listados usados por stock, sin acoplar Streamlit en el caso de uso.
"""

from __future__ import annotations

from app.core.application.adapters.json_producto_repository import JsonProductoRepository
from app.core.application.context import AppContext
from app.core.application.ports.producto_repository import ProductoRepositoryPort
from app.core.models import Producto


def _repo(ctx: AppContext, repo: ProductoRepositoryPort | None = None) -> ProductoRepositoryPort:
    return repo if repo is not None else JsonProductoRepository(ctx.uow)


def obtener_producto(
    ctx: AppContext,
    producto_id: str,
    *,
    repo: ProductoRepositoryPort | None = None,
) -> Producto | None:
    return _repo(ctx, repo).get_by_id(producto_id)


def listar_productos(
    ctx: AppContext,
    *,
    es_bebida: bool | None = None,
    solo_activos: bool = True,
    repo: ProductoRepositoryPort | None = None,
) -> list[Producto]:
    return _repo(ctx, repo).listar(es_bebida=es_bebida, solo_activos=solo_activos)


def mapa_productos_nombre_id(
    ctx: AppContext,
    *,
    es_bebida: bool | None = None,
    solo_activos: bool = True,
    repo: ProductoRepositoryPort | None = None,
) -> dict[str, str]:
    """Misma forma que stock_service.mapa_productos: nombre → id."""
    return {
        p.nombre: p.id
        for p in listar_productos(
            ctx, es_bebida=es_bebida, solo_activos=solo_activos, repo=repo,
        )
    }
