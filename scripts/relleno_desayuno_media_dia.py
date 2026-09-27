"""Rellena un día de desayuno con la plantilla-media del hotel.

Uso:
  python scripts/relleno_desayuno_media_dia.py --path D:\\work\\2-BM-DATOS\\data\\datos_hotel.json --fecha 2026-08-22
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.services import desayuno_service as des
from app.core.services.receta_service import receta_tostada_del_dia

# Misma plantilla que desayuno-media sábados ya cargados (p.ej. 2026-08-29).
# La tostada del día se sustituye por receta_tostada_del_dia(fecha).
_RECIPE_MIX_BASE: list[tuple[str, float]] = [
    ("r1", 5.0),   # Tortilla
    ("r05", 3.0),  # Huevo cocido
    ("r03", 5.0),  # Huevo frito
    ("r14", 1.0),  # Sandwich vegetal
    ("r10", 2.0),  # Tostada champinones
    ("r04", 5.0),  # Huevo pochado
    ("r12", 1.0),  # Sandwich mixto
    ("r11", 3.0),  # Desayuno ingles
    ("r09", 1.0),  # Tostada francesa
    ("r13", 1.0),  # Sandwich de la casa
    ("r149", 1.0), # Huevos revueltos
]

_TOSTADA_DIA_IDS = {
    "r120", "r121", "r122", "r123", "r124", "r125", "r126",
    "r127", "r128", "r129", "r130", "r131",
}


def _session() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="relleno-media",
            actor_label="Relleno media",
            role=ROL_DIRECCION,
            session_id="relleno-media",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="relleno-media",
        )
    )


def rellenar(fecha: date, *, path: Path, huespedes: int = 30) -> int:
    reset_container()
    configure_for_flet(data_path=str(path))
    _session()

    clave = f"desayuno-media-{fecha.isoformat()}-v1"
    data = get_container().app_data_store.get()
    existente = next(
        (
            d
            for d in data.desayunos
            if (getattr(d, "clave_idempotencia", None) == clave
                or (getattr(d, "fecha", None) == fecha))
            and not getattr(d, "anulado", False)
        ),
        None,
    )
    if existente is not None:
        print(f"SKIP: ya hay desayuno {existente.id} el {fecha} / clave {clave}")
        return 0

    des.limpiar_cesta()
    tostada = receta_tostada_del_dia(fecha)
    tostada_id = getattr(tostada, "id", None) if tostada else None

    mix = list(_RECIPE_MIX_BASE)
    if tostada_id:
        mix.append((str(tostada_id), 2.0))
    else:
        # Fallback sábado histórico
        mix.append(("r126", 2.0))

    for rid, porc in mix:
        if rid in _TOSTADA_DIA_IDS and tostada_id and rid != tostada_id:
            continue
        r = des.anadir_receta_a_cesta(rid, float(porc))
        if not r.ok:
            print(f"ERROR cesta {rid} x{porc}: {r.mensaje}")
            des.limpiar_cesta()
            return 1

    res = des.registrar_desayuno(
        fecha,
        int(huespedes),
        clave_idempotencia=clave,
        observaciones="Relleno media historica (no Excel real)",
    )
    print(res.mensaje if hasattr(res, "mensaje") else res)
    if not res.ok:
        des.limpiar_cesta()
        return 1

    data = get_container().app_data_store.get()
    reg = next(
        (d for d in data.desayunos
         if getattr(d, "clave_idempotencia", None) == clave
         and not getattr(d, "anulado", False)),
        None,
    )
    if reg:
        print(
            f"OK id={reg.id} fecha={reg.fecha} hues={reg.num_huespedes} "
            f"coste={getattr(reg, 'coste_total', None)} recetas={len(reg.registros_recetas or [])}"
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--path", type=Path, required=True)
    p.add_argument("--fecha", type=str, default="2026-08-22")
    p.add_argument("--huespedes", type=int, default=30)
    args = p.parse_args()
    if not args.path.is_file():
        print("No existe", args.path)
        return 1
    fecha = date.fromisoformat(args.fecha[:10])
    print("Datos:", args.path.resolve())
    print("Fecha:", fecha)
    return rellenar(fecha, path=args.path, huespedes=args.huespedes)


if __name__ == "__main__":
    raise SystemExit(main())
