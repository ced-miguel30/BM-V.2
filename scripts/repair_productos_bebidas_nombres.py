"""Repara productos hotel: bebidas = cat 104; limpia C00000x del nombre.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\repair_productos_bebidas_nombres.py
"""

from __future__ import annotations

import os
from pathlib import Path

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.services.productos_import_service import (
    es_bebida_por_categoria_y_nombre,
    limpiar_nombre_producto,
    _servicios_para,
)
from app.core.storage.session_store import persist_data


def main() -> None:
    hotel = Path(os.environ.get("LOCALAPPDATA", "")) / "BM-V2-local" / "data" / "datos_hotel.json"
    if not hotel.is_file():
        raise SystemExit(f"No existe {hotel}")
    reset_container()
    configure_for_flet(data_path=hotel)
    data = get_container().app_data_store.get()

    n_beb = n_nom = n_serv = 0
    for p in data.productos:
        cat = str(getattr(p, "categoria_inventario", None) or "").strip()
        want_beb = es_bebida_por_categoria_y_nombre(categoria=cat, nombre=p.nombre or "")
        if bool(p.es_bebida) != want_beb:
            p.es_bebida = want_beb
            n_beb += 1
        limpio = limpiar_nombre_producto(p.nombre or "")
        if limpio and limpio != p.nombre:
            p.nombre = limpio
            n_nom += 1
        serv = _servicios_para(categoria=cat, es_bebida=p.es_bebida)
        if list(p.servicios_disponibles or []) != serv:
            p.servicios_disponibles = list(serv)
            n_serv += 1

    persist_data(data)
    bebs = sum(1 for p in data.productos if p.es_bebida)
    print(
        f"OK reparado: es_bebida_cambios={n_beb} nombres={n_nom} "
        f"servicios={n_serv} · bebidas_final={bebs}/{len(data.productos)}"
    )
    for p in data.productos:
        if p.es_bebida and any(
            x in (p.nombre or "").upper()
            for x in ("AGUACATE", "QUESO", "CROISSANT", "COLA DE RAPE", "CRISPIES")
        ):
            print(
                "AVISO aún bebida:",
                p.codigo,
                p.nombre,
                "cat",
                getattr(p, "categoria_inventario", None),
            )


if __name__ == "__main__":
    main()
