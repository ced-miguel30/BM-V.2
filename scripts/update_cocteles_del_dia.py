"""Actualiza cócteles del día (lun–dom) en datos_hotel.json.

Calendario:
  Lunes: Espresso Martini
  Martes: Margarita
  Miércoles: Piña Colada
  Jueves: Blue Hawaii
  Viernes: Caipirinha
  Sábado: Sex on the Beach
  Domingo: Royal Marina

También asegura las recetas Blue Hawaii y Espresso Martini.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\update_cocteles_del_dia.py
  .\\.venv\\Scripts\\python.exe scripts\\update_cocteles_del_dia.py --path RUTA\\datos_hotel.json
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.services.receta_service import NOMBRES_COCTEL_POR_WEEKDAY_DEFAULT
from scripts.seed_recetas_cocktails import _ensure, _specs

COCTELES = NOMBRES_COCTEL_POR_WEEKDAY_DEFAULT


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="seed-dir",
            actor_label="Seed Dirección",
            role=ROL_DIRECCION,
            session_id="seed-session",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="seed",
        )
    )


def _default_paths() -> list[Path]:
    paths: list[Path] = []
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "BM-V2-local" / "data" / "datos_hotel.json"
    if local.exists():
        paths.append(local)
    entrega = (
        Path(r"C:\Users\User\Desktop\HOTEL\BM-ENTREGA-SERVIDOR-20260825_0239")
        / "2-BM-DATOS"
        / "data"
        / "datos_hotel.json"
    )
    if entrega.exists():
        paths.append(entrega)
    # DATOS HOTEL si tiene el JSON dentro
    datos_hotel = Path(r"C:\Users\User\Desktop\HOTEL\DATOS HOTEL")
    for candidate in (
        datos_hotel / "datos_hotel.json",
        datos_hotel / "data" / "datos_hotel.json",
    ):
        if candidate.exists():
            paths.append(candidate)
    # shared root from env if set
    demo = (os.environ.get("BM_DEMO_FILE") or "").strip()
    if demo:
        p = Path(demo)
        if p.exists() and p not in paths:
            paths.append(p)
    root = (os.environ.get("BM_INSTANCE_ROOT") or "").strip()
    if root:
        p = Path(root) / "data" / "datos_hotel.json"
        if p.exists() and p not in paths:
            paths.append(p)
    # unique
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def update_one(hotel: Path) -> None:
    print(f"\n=== {hotel} ===")
    reset_container()
    configure_for_flet(data_path=str(hotel))
    _auth()

    # Asegurar recetas (incluye Blue Hawaii + Espresso Martini).
    for nombre, ings, extras in _specs(get_container().app_data_store.get()):
        if nombre not in ("Blue Hawaii", "Espresso Martini") and nombre not in COCTELES:
            continue
        data = get_container().app_data_store.get()
        ings2 = list(ings)
        rid = _ensure(data, nombre, ings2, extras=extras)
        print(f"  receta OK {nombre} -> {rid}")

    # También asegurar el resto del calendario por si faltaba alguno.
    data = get_container().app_data_store.get()
    for nombre in COCTELES:
        found = next(
            (r for r in data.recetas if r.nombre.strip().lower() == nombre.lower() and r.activo),
            None,
        )
        if found is None:
            # Reintentar vía _specs completas
            pass
    # Re-run full cocktail seed for missing names in calendar
    for nombre, ings, extras in _specs(get_container().app_data_store.get()):
        if nombre not in COCTELES:
            continue
        data = get_container().app_data_store.get()
        rid = _ensure(data, nombre, list(ings), extras=extras)
        print(f"  calendario OK {nombre} -> {rid}")

    data = get_container().app_data_store.get()
    if data.configuracion is None:
        raise SystemExit("Sin configuracion en datos_hotel.json")
    data.configuracion.cocteles_del_dia = tuple(COCTELES)
    get_container().app_data_store.persist(data)
    print("  cocteles_del_dia =")
    dias = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
    for d, n in zip(dias, COCTELES, strict=True):
        print(f"    {d}: {n}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", type=Path, action="append", default=None)
    args = ap.parse_args()
    targets = list(args.path) if args.path else _default_paths()
    if not targets:
        raise SystemExit("No se encontró ningún datos_hotel.json")
    for p in targets:
        if not p.exists():
            raise SystemExit(f"No existe: {p}")
        update_one(p)
    print("\nHecho.")


if __name__ == "__main__":
    main()
