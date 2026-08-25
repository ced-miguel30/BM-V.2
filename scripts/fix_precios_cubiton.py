"""Revaloriza CUBITON (p17) a 0,80 €/Ud y CUBITON PICADO (p148) a 0,90 €/Ud.

Los lotes IMPORT-AGO26 usaban 2,50 €/Ud placeholder; el inventario inicial
de p17 ~1,03 €. Aplica el precio real de bolsa y reescribe consumos/mermas.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\fix_precios_cubiton.py
  .\\.venv\\Scripts\\python.exe scripts\\fix_precios_cubiton.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.services.revalorizacion_primer_precio_service import (
    revalorizar_producto_primer_precio,
)

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
BACKUP_DIR = HOTEL.parent / "backups"
TAG = "[fix-precios-cubiton]"

# Precio real bolsa (usuario)
PRECIOS = {
    "p17": 0.80,   # CUBITON
    "p148": 0.90,  # CUBITON PICADO
}


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="fix-cubiton",
            actor_label="Fix precios Cubiton",
            role=ROL_DIRECCION,
            session_id="fix-cubiton-session",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="fix",
        )
    )


def _boot() -> None:
    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()


def _backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"datos_hotel_pre_cubiton_{stamp}.json"
    shutil.copy2(HOTEL, dest)
    return dest


def _ya_aplicado(data) -> bool:
    for a in getattr(data, "actividades", None) or []:
        det = getattr(a, "detalle", None) or ""
        if TAG in det:
            return True
    return False


def _coste_svc(data, pid: str) -> tuple[float, float]:
    qty = coste = 0.0
    for r in getattr(data, "registros_servicio", None) or []:
        if getattr(r, "anulado", False):
            continue
        for ln in getattr(r, "lineas", None) or []:
            if getattr(ln, "producto_id", None) == pid:
                qty += float(ln.cantidad or 0)
                coste += float(ln.coste or 0)
    return qty, coste


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not HOTEL.is_file():
        print(f"No existe {HOTEL}")
        return 1

    _boot()
    store = get_container().app_data_store
    data = store.get()

    if _ya_aplicado(data) and not args.dry_run:
        print(f"Ya aplicado ({TAG}). Nada que hacer.")
        return 0

    antes = {pid: _coste_svc(data, pid) for pid in PRECIOS}
    print("Antes:")
    for pid, (q, c) in antes.items():
        print(f"  {pid}: {q:.4g} Ud = {c:.2f} EUR")

    if args.dry_run:
        for pid, unit in PRECIOS.items():
            q, _ = antes[pid]
            print(f"  dry-run {pid} = {q * unit:.2f} EUR @ {unit:.2f} EUR/Ud")
        return 0

    bak = _backup()
    print(f"Backup: {bak}")

    data = store.get()
    for pid, unit in PRECIOS.items():
        r = revalorizar_producto_primer_precio(
            data,
            pid,
            unit,
            doc_id="manual-precio-bolsa-cubiton",
            actor="fix-cubiton",
        )
        print(
            f"  {pid} @{unit:.2f}: svc={r.registros_servicio} merma={r.registros_merma} "
            f"frags={r.fragmentos_actualizados} lotes={r.lotes_provisionales} mov={r.movimientos_actualizados}"
        )

    # Marca idempotente en la última actividad
    if data.actividades:
        act = data.actividades[0]
        det = getattr(act, "detalle", "") or ""
        if TAG not in det:
            act.detalle = f"{TAG} {det}".strip()

    from app.core.services.desayuno_service import _ctx

    _ctx().uow.commit(data)
    data = store.get()
    print("Despues:")
    for pid in PRECIOS:
        q, c = _coste_svc(data, pid)
        print(f"  {pid}: {q:.4g} Ud = {c:.2f} EUR")
    print("Persistido", HOTEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
