"""Rellena el hueco de desayunos 23/08–02/09/2026 con una cesta media histórica.

Fuente: desayunos activos (no buffet) 01–21/08 + 03–12/09.
Consume stock FIFO real. Idempotente: clave desayuno-media-YYYY-MM-DD-v1.

Uso:
  py -3 scripts/rellenar_desayunos_media_hueco.py --path D:\\work\\2-BM-DATOS\\data\\datos_hotel.json --dry-run
  py -3 scripts/rellenar_desayunos_media_hueco.py --path D:\\work\\2-BM-DATOS\\data\\datos_hotel.json
"""
from __future__ import annotations

import argparse
import math
import shutil
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.services import desayuno_service as des
from app.core.services.receta_service import (
    ETIQUETA_TOSTADA_DEL_DIA,
    receta_tostada_del_dia,
)

GAP_START = date(2026, 8, 23)
GAP_END = date(2026, 9, 2)
CLAVE_VER = "v1"
OBS = "Relleno media historica (no Excel real)"


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="relleno-media-des",
            actor_label="Relleno media desayuno",
            role=ROL_DIRECCION,
            session_id="relleno-media-des-session",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="relleno-media",
        )
    )


def _boot(path: Path) -> None:
    reset_container()
    configure_for_flet(data_path=str(path))
    _auth()


def _clave(fecha: date) -> str:
    return f"desayuno-media-{fecha.isoformat()}-{CLAVE_VER}"


def _es_fuente(d) -> bool:
    if getattr(d, "anulado", False):
        return False
    clave = str(getattr(d, "clave_idempotencia", None) or "")
    if "buffet" in clave.lower():
        return False
    f = d.fecha if isinstance(d.fecha, date) else date.fromisoformat(str(d.fecha)[:10])
    h = int(getattr(d, "num_huespedes", 0) or 0)
    if h < 5:
        return False
    if date(2026, 8, 1) <= f <= date(2026, 8, 21):
        return True
    if date(2026, 9, 3) <= f <= date(2026, 9, 12):
        return True
    return False


def _es_tostada_dia_nombre(nombre: str | None, receta_id: str | None, rec_map: dict) -> bool:
    if nombre and "tostada" in nombre.lower() and any(
        d in nombre.lower()
        for d in ("lunes", "martes", "miercoles", "miércoles", "jueves", "viernes", "sabado", "sábado", "domingo", "del dia", "del día")
    ):
        return True
    if receta_id and receta_id in rec_map:
        n = (rec_map[receta_id].nombre or "").lower()
        return "tostada" in n and any(
            d in n
            for d in ("lunes", "martes", "miercoles", "miércoles", "jueves", "viernes", "sabado", "sábado", "domingo")
        )
    return False


def _largest_remainder(weights: dict[str, float], total: int) -> dict[str, int]:
    """Asigna enteros que suman `total` proporcionales a weights."""
    if total <= 0 or not weights:
        return {}
    s = sum(weights.values())
    if s <= 0:
        return {}
    raw = {k: (v / s) * total for k, v in weights.items()}
    floors = {k: int(math.floor(x)) for k, x in raw.items()}
    rem = total - sum(floors.values())
    fracs = sorted(((raw[k] - floors[k], k) for k in floors), reverse=True)
    out = dict(floors)
    for i in range(rem):
        out[fracs[i % len(fracs)][1]] += 1
    return {k: v for k, v in out.items() if v > 0}


def _cesta_media(data) -> tuple[int, dict[str, int], float]:
    """Devuelve (huespedes, {receta_id|TOSTADA_DIA: qty}, avg_hues)."""
    rec_map = {r.id: r for r in data.recetas if getattr(r, "activo", True)}
    freq: Counter[str] = Counter()
    hues: list[int] = []
    n_days = 0
    for d in data.desayunos:
        if not _es_fuente(d):
            continue
        n_days += 1
        hues.append(int(d.num_huespedes or 0))
        for rr in d.registros_recetas or []:
            rid = getattr(rr, "receta_id", None) or ""
            por = float(getattr(rr, "porciones", None) or getattr(rr, "cantidad", None) or 1)
            nombre = None
            if rid in rec_map:
                nombre = rec_map[rid].nombre
            if _es_tostada_dia_nombre(nombre, rid, rec_map):
                freq["__TOSTADA_DIA__"] += por
            elif rid:
                freq[rid] += por
    if n_days < 1 or not freq:
        raise SystemExit("No hay desayunos fuente para calcular la media.")
    avg_h = sum(hues) / len(hues)
    target = max(1, int(round(avg_h)))
    # Media por día → pesos; luego enteros ~ target
    weights = {k: v / n_days for k, v in freq.items()}
    cesta = _largest_remainder(weights, target)
    return target, cesta, avg_h


def _gap_dates() -> list[date]:
    out: list[date] = []
    d = GAP_START
    while d <= GAP_END:
        out.append(d)
        d += timedelta(days=1)
    return out


def _ya_ok(data, fecha: date) -> object | None:
    clave = _clave(fecha)
    return next(
        (
            d
            for d in data.desayunos
            if getattr(d, "clave_idempotencia", None) == clave
            and not getattr(d, "anulado", False)
        ),
        None,
    )


def _cargar_cesta(cesta: dict[str, int], fecha: date) -> None:
    des.limpiar_cesta()
    for rid, qty in cesta.items():
        if rid == "__TOSTADA_DIA__":
            rec = receta_tostada_del_dia(fecha)
            if rec is None:
                raise ValueError(f"Sin tostada del dia para {fecha}")
            r = des.anadir_receta_a_cesta(rec.id, float(qty))
        else:
            r = des.anadir_receta_a_cesta(rid, float(qty))
        if not r.ok:
            raise ValueError(r.mensaje)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        type=Path,
        default=Path(r"D:\work\2-BM-DATOS\data\datos_hotel.json"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.path.exists():
        print("No existe", args.path)
        return 1

    _boot(args.path)
    data = get_container().app_data_store.get()
    target, cesta, avg_h = _cesta_media(data)
    rec_map = {r.id: r.nombre for r in data.recetas}

    print("=== Relleno media desayunos ===")
    print("Datos:", args.path.resolve())
    print(f"Media huespedes fuente: {avg_h:.1f} → objetivo {target}")
    print("Cesta tipo:")
    for rid, qty in sorted(cesta.items(), key=lambda x: -x[1]):
        label = ETIQUETA_TOSTADA_DEL_DIA if rid == "__TOSTADA_DIA__" else rec_map.get(rid, rid)
        print(f"  {qty:2d} x {label} ({rid})")
    print(f"Hueco: {GAP_START} .. {GAP_END} ({len(_gap_dates())} dias)")
    print(f"dry_run={args.dry_run}")

    if not args.dry_run:
        bak_dir = args.path.parent / "backups"
        bak_dir.mkdir(parents=True, exist_ok=True)
        bak = bak_dir / f"datos_hotel_pre_relleno_media_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy2(args.path, bak)
        print("Backup:", bak)

    n_ok = n_skip = n_err = 0
    for fecha in _gap_dates():
        existente = _ya_ok(data, fecha)
        if existente is not None:
            print(f"  {fecha}: SKIP {_clave(fecha)} → {existente.id}")
            n_skip += 1
            continue
        try:
            if args.dry_run:
                _cargar_cesta(cesta, fecha)
                des.limpiar_cesta()
                print(f"  {fecha}: DRY-RUN OK huespedes={target} clave={_clave(fecha)}")
                n_ok += 1
                continue
            _cargar_cesta(cesta, fecha)
            res = des.registrar_desayuno(
                fecha,
                target,
                clave_idempotencia=_clave(fecha),
                observaciones=OBS,
            )
            if not res.ok:
                des.limpiar_cesta()
                print(f"  {fecha}: ERROR {res.mensaje}")
                n_err += 1
                continue
            data = get_container().app_data_store.get()
            reg = _ya_ok(data, fecha)
            rid = getattr(reg, "id", "?") if reg else "?"
            print(f"  {fecha}: OK {rid} huespedes={target}")
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            des.limpiar_cesta()
            print(f"  {fecha}: ERROR {exc}")
            n_err += 1

    print(f"Resumen: ok={n_ok} skip={n_skip} error={n_err}")
    return 1 if n_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
