"""Aplica precios de docs/añadidos manual/correcion coste productos.xlsx.

Revaloriza consumos/mermas desde el primer registro (D60) sobre
D:\\work\\2-BM-DATOS (espejo hotel).

Uso:
  py -3 scripts/fix_correcion_costes_excel.py --dry-run
  py -3 scripts/fix_correcion_costes_excel.py
"""

from __future__ import annotations

import argparse
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

HOTEL = Path(r"D:\work\2-BM-DATOS\data\datos_hotel.json")
BACKUP_DIR = HOTEL.parent / "backups"
TAG = "[fix-correcion-costes-excel]"
DOC_ID = "manual-correcion-costes-excel"

# Mapeo acordado (fiambre omitido: sin precio y 0 consumos).
# Higos en Kg → 3,802 €/kg. Nata = pastelería b76. Tirma = b48 (producto).
PRECIOS: dict[str, float] = {
    "p348": 20.02,  # ANGUS CARNE
    "p254": 0.627,  # ARTIS MALTA 100GRS 30UD
    "p187": 0.30,  # ARTIS MINI ARLEQUIN
    "p149": 1.24,  # BUEN LUGAR GOFIO DE MILLO
    "p113": 0.90,  # CALDO SOLUBLE COCIDO/VERDURA
    "p156": 4.31,  # CANELA MOLIDA
    "p111": 22.598,  # CARNE PICADA PERSONAL
    "p375": 6.298,  # CHORIZO CANARIO ROJO
    "p382": 8.688,  # CHORIZO CRIOLLO FRESCO
    "p157": 0.95,  # COLORANTE NATURAL
    "p337": 22.598,  # COSTILLAS CERDO
    "p359": 3.802,  # HIGOS PREMIUN CAJA 5KG (€/kg)
    "p351": 3.50,  # KAKI
    "p74": 1.25,  # LECHUGA BATAVIA
    "p180": 2.1616,  # MANDARINAS
    "p314": 2.80,  # MINI HOOPS AZUCAR
    "p200": 2.50,  # MUESLI FRUTOS ROJOS S/G
    "b76": 1.60,  # NATA KRONA PASTELERIA 1L
    "p172": 2.9898,  # NECTARINA
    "p28": 0.36,  # PAN PERRITO
    "p402": 14.2857,  # PATA ASADA
    "p295": 8.2272,  # PECHUGA PAVO
    "p326": 11.28,  # QUESO CURADO VALSEQUILLO
    "p297": 4.48,  # QUESO PARMESANO
    "p325": 8.50,  # QUESO SEMI BLANCO VALSEQUILLO
    "p328": 8.4532,  # QUESO SEMI ROJO
    "p47": 8.5006,  # QUESO SEMICURADO AHUMADO
    "p376": 8.75,  # SALCHICHA FRANKFURT
    "p383": 1.30,  # SALMOREJO FRESCO
    "p224": 1.50,  # SALSA COCKTAIL
    "p41": 1.53,  # SALSA SETAS
    "p374": 27.451,  # SECRETO IBERICO
    "p340": 2.40,  # SOLES CACAO MINI
    "p166": 19.90,  # TARTA ZANAHORIA
    "b48": 5.815,  # TIRMA AMBROSIA (producto; es_bebida=False)
}


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="fix-correcion-costes",
            actor_label="Fix corrección costes Excel",
            role=ROL_DIRECCION,
            session_id="fix-correcion-costes-session",
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
    dest = BACKUP_DIR / f"datos_hotel_pre_correcion_costes_{stamp}.json"
    shutil.copy2(HOTEL, dest)
    return dest


def _ya_aplicado(data) -> bool:
    for a in getattr(data, "actividades", None) or []:
        det = getattr(a, "detalle", None) or ""
        if TAG in det:
            return True
    return False


def _coste_producto(data, pid: str) -> tuple[float, float]:
    qty = coste = 0.0
    for key in ("desayunos", "registros_servicio", "mermas"):
        for r in getattr(data, key, None) or []:
            if getattr(r, "anulado", False):
                continue
            for ln in getattr(r, "lineas", None) or []:
                if getattr(ln, "producto_id", None) == pid:
                    qty += float(getattr(ln, "cantidad", 0) or 0)
                    coste += float(getattr(ln, "coste", 0) or 0)
    return qty, coste


def _asegurar_tirma_producto(data) -> None:
    """Tirma mal clasificada en traspaso Noray: debe ser producto, no bebida."""
    for p in getattr(data, "productos", None) or []:
        if getattr(p, "id", None) != "b48":
            continue
        if getattr(p, "es_bebida", False):
            p.es_bebida = False
        return


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

    ids = {p.id for p in data.productos}
    missing = [pid for pid in PRECIOS if pid not in ids]
    if missing:
        print("IDs no encontrados:", ", ".join(missing))
        return 1

    print(f"Productos a revalorizar: {len(PRECIOS)}")
    antes = {pid: _coste_producto(data, pid) for pid in PRECIOS}
    con_consumo = [(pid, q, c) for pid, (q, c) in antes.items() if q > 0 or c > 0]
    print(f"Con consumo histórico: {len(con_consumo)}")
    for pid, q, c in sorted(con_consumo, key=lambda x: -x[2])[:15]:
        nombre = next(p.nombre for p in data.productos if p.id == pid)
        print(f"  {pid} {nombre}: qty={q:.4g} coste={c:.2f} → @{PRECIOS[pid]}")

    if args.dry_run:
        print("dry-run: sin escribir")
        return 0

    bak = _backup()
    print(f"Backup: {bak}")

    data = store.get()
    _asegurar_tirma_producto(data)

    total_frags = total_mov = 0
    for pid, unit in PRECIOS.items():
        r = revalorizar_producto_primer_precio(
            data,
            pid,
            unit,
            doc_id=DOC_ID,
            actor="fix-correcion-costes",
        )
        total_frags += r.fragmentos_actualizados
        total_mov += r.movimientos_actualizados
        if (
            r.registros_desayuno
            or r.registros_servicio
            or r.registros_merma
            or r.fragmentos_actualizados
            or r.lotes_provisionales
        ):
            print(
                f"  {pid} @{unit}: des={r.registros_desayuno} svc={r.registros_servicio} "
                f"mer={r.registros_merma} frags={r.fragmentos_actualizados} "
                f"lotes={r.lotes_provisionales} mov={r.movimientos_actualizados}"
            )

    if data.actividades:
        act = data.actividades[0]
        det = getattr(act, "detalle", "") or ""
        if TAG not in det:
            act.detalle = f"{TAG} {det}".strip()

    store.persist(data)
    data = store.get()
    print(f"Fragmentos={total_frags} movimientos={total_mov}")
    print("Despues (top con consumo):")
    for pid, q0, _ in sorted(con_consumo, key=lambda x: -x[2])[:10]:
        q, c = _coste_producto(data, pid)
        print(f"  {pid}: qty={q:.4g} coste={c:.2f} EUR (@{PRECIOS[pid]})")
    print("Persistido", HOTEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
