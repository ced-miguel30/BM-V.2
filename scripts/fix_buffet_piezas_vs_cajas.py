"""Convierte panes/bollería buffet: piezas individuales → fracción de caja.

El estándar buffet registró 8 baguettinas como 8 Ud-caja (66 ud/caja).
Corrige recetas r136/r137, consumos históricos y stock.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\fix_buffet_piezas_vs_cajas.py
  .\\.venv\\Scripts\\python.exe scripts\\fix_buffet_piezas_vs_cajas.py --dry-run
"""

from __future__ import annotations

import argparse
import json
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
from app.core.models import CategoriaReceta, IngredienteReceta, LineaDesayuno
from app.core.models.enums import TipoMovimiento
from app.core.services import receta_service as rec_svc
from app.core.services.movimiento_service import origen_linea_id_consumo
from app.core.services.pack_unidades import UNIDADES_POR_PAQUETE, piezas_a_ud_paquete

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
BACKUP_DIR = HOTEL.parent / "backups"
TAG = "[fix-buffet-piezas-caja]"

# Piezas diarias del estándar (como se pensaron operativamente)
BUFFET_PIEZAS: dict[str, float] = {
    "p05": 2.0,
    "p357": 2.0,
    "p276": 4.0,
    "p252": 8.0,
    "p251": 6.0,
    "p294": 12.0,
    "p250": 8.0,
    "p249": 9.0,
    "b01": 9.0,
}
# p08 surtido ya en Kg — no tocar


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="fix-buffet",
            actor_label="Fix buffet piezas",
            role=ROL_DIRECCION,
            session_id="fix-buffet-session",
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
    dest = BACKUP_DIR / f"datos_hotel_pre_buffet_piezas_{stamp}.json"
    shutil.copy2(HOTEL, dest)
    return dest


def _enum_val(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _actualizar_recetas_buffet() -> list[str]:
    data = get_container().app_data_store.get()
    msgs: list[str] = []
    for rid in ("r136", "r137"):
        rec = next((r for r in data.recetas if r.id == rid), None)
        if rec is None:
            msgs.append(f"{rid}: no encontrada")
            continue
        nuevos: list[IngredienteReceta] = []
        for ing in rec.ingredientes:
            pid = ing.producto_id
            if pid in BUFFET_PIEZAS:
                piezas = BUFFET_PIEZAS[pid]
                nuevos.append(
                    IngredienteReceta(
                        pid,
                        piezas_a_ud_paquete(pid, piezas),
                        piezas,
                        "Ud",
                    )
                )
            else:
                nuevos.append(ing)
        cat = rec.categoria if hasattr(rec.categoria, "value") else rec.categoria
        r = rec_svc.editar_receta(
            rid,
            rec.nombre,
            nuevos,
            cat or CategoriaReceta.DESAYUNO,
            servicios_disponibles=list(rec.servicios_disponibles or ["desayuno"]),
            porciones_estandar=float(rec.porciones_estandar or 1.0),
        )
        msgs.append(f"{rid} {rec.nombre}: {r.ok} {r.mensaje}")
    return msgs


def _corregir_consumos(data, *, dry_run: bool) -> dict:
    """Divide consumos de panes/bollería empaquetados por unidades/paquete."""
    lotes = {l.id: l for l in data.lotes}
    stats = {"detalles": 0, "por_pid": {}, "stock_devuelto": 0.0, "regs": 0}
    pids = set(BUFFET_PIEZAS)

    for reg in data.desayunos:
        if getattr(reg, "anulado", False):
            continue
        touched = False
        detalle = list(getattr(reg, "lineas_detalle", None) or [])
        for di, det in enumerate(detalle):
            if det.producto_id not in pids:
                continue
            pack = UNIDADES_POR_PAQUETE.get(det.producto_id)
            if not pack or pack <= 1:
                continue
            old_q = float(det.cantidad or 0)
            if old_q <= 0:
                continue
            # Ya corregido si cantidad << piezas típicas del buffet (p.ej. 8/66≈0.12)
            # Heurística: si parece piezas enteras de buffet (>= 1 y no fracción de caja)
            if old_q < 0.5:
                continue
            new_q = round(old_q / pack, 6)
            scale = new_q / old_q
            stats["detalles"] += 1
            stats["por_pid"][det.producto_id] = stats["por_pid"].get(
                det.producto_id, {"antes": 0.0, "despues": 0.0}
            )
            stats["por_pid"][det.producto_id]["antes"] += old_q
            stats["por_pid"][det.producto_id]["despues"] += new_q
            if dry_run:
                touched = True
                continue

            det.cantidad = new_q
            det.coste = round(float(det.coste or 0) * scale, 2)
            for fi, frag in enumerate(list(getattr(det, "consumos_lote", None) or [])):
                f_old = float(frag.cantidad or 0)
                if f_old <= 0:
                    continue
                f_new = round(f_old / pack, 6)
                excess = round(f_old - f_new, 6)
                frag.cantidad = f_new
                frag.coste = round(float(frag.coste or 0) * (f_new / f_old), 2)
                lote = lotes.get(frag.lote_id)
                if lote is not None and not getattr(lote, "anulado", False):
                    lote.cantidad_restante = round(
                        float(lote.cantidad_restante) + excess, 6
                    )
                    stats["stock_devuelto"] += excess
                linea = origen_linea_id_consumo(di, fi)
                for m in data.movimientos:
                    if getattr(m, "origen_id", None) != reg.id:
                        continue
                    if getattr(m, "origen_linea_id", None) != linea:
                        continue
                    if _enum_val(getattr(m, "tipo", "")) != TipoMovimiento.CONSUMO.value:
                        continue
                    m.cantidad = f_new
                    m.coste_total_snapshot = frag.coste
                    if f_new > 0:
                        m.coste_unitario_snapshot = round(frag.coste / f_new, 6)
            touched = True

        if not touched:
            continue
        stats["regs"] += 1
        if dry_run:
            continue

        otras = [ln for ln in (reg.lineas or []) if ln.producto_id not in pids]
        por_pid: dict[str, LineaDesayuno] = {}
        prev_extra = {
            ln.producto_id: ln.es_extra
            for ln in (reg.lineas or [])
            if ln.producto_id in pids
        }
        for det in detalle:
            if det.producto_id not in pids:
                continue
            if det.producto_id not in por_pid:
                por_pid[det.producto_id] = LineaDesayuno(det.producto_id, 0.0, 0.0, False)
            cur = por_pid[det.producto_id]
            por_pid[det.producto_id] = LineaDesayuno(
                det.producto_id,
                round(cur.cantidad + float(det.cantidad), 6),
                round(cur.coste + float(det.coste or 0), 2),
                prev_extra.get(det.producto_id, False),
            )
        reg.lineas = otras + list(por_pid.values())
        reg.coste_total = round(sum(float(l.coste or 0) for l in reg.lineas), 2)
        obs = (reg.observaciones or "").strip()
        if TAG not in obs:
            reg.observaciones = f"{obs} {TAG}".strip() if obs else TAG

    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not HOTEL.exists():
        print("No existe", HOTEL)
        return 1

    if not args.dry_run:
        print("Backup:", _backup())

    _boot()
    data = get_container().app_data_store.get()

    def _tot(pid: str) -> float:
        return sum(
            float(ln.cantidad or 0)
            for des in data.desayunos
            if not getattr(des, "anulado", False)
            for ln in (des.lineas or [])
            if ln.producto_id == pid
        )

    print("Antes baguettina p252:", _tot("p252"))
    if not args.dry_run:
        for m in _actualizar_recetas_buffet():
            print(m)
        data = get_container().app_data_store.get()

    stats = _corregir_consumos(data, dry_run=args.dry_run)
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("Dry-run OK")
        return 0

    from app.core.services.desayuno_service import _ctx

    _ctx().uow.commit(data)
    data = get_container().app_data_store.get()
    print("Después baguettina p252:", _tot("p252"))
    print("Persistido", HOTEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
