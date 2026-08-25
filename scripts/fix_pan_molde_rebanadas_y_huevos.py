"""Corrige pan molde p09/p11: 1 tostada mal registrada como 1 paquete → 1/31 Ud.

También:
  - Crea «Huevos revueltos» (huevina 0,05 L, igual que tortilla)
  - Actualiza «Huevos rotos» a huevina 0,05 L (mantiene papa + jamón)

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\fix_pan_molde_rebanadas_y_huevos.py
  .\\.venv\\Scripts\\python.exe scripts\\fix_pan_molde_rebanadas_y_huevos.py --dry-run
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
from app.core.models import CategoriaReceta, IngredienteReceta
from app.core.services import receta_service as rec_svc
from app.core.services.movimiento_service import (
    ORIGEN_TIPO_DESAYUNO,
    origen_linea_id_consumo,
)
from app.core.models.enums import TipoMovimiento

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
BACKUP_DIR = HOTEL.parent / "backups"
PAN_IDS = frozenset({"p09", "p11"})
REBANADAS = 31.0
# Umbral: cantidades de tostada correctas son ~0.03–0.13; paquetes erróneos ≥ 0.5
UMBRAL_PAQUETE = 0.5
TAG = "[fix-pan-rebanadas-31]"


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="fix-pan",
            actor_label="Fix pan rebanadas",
            role=ROL_DIRECCION,
            session_id="fix-pan-session",
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
    dest = BACKUP_DIR / f"datos_hotel_pre_pan31_{stamp}.json"
    shutil.copy2(HOTEL, dest)
    return dest


def _enum_val(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _corregir_registros_desayuno(data, *, dry_run: bool) -> dict:
    """Divide por 31 consumos p09/p11 ≥ 0.5 Ud y devuelve stock excesivo a lotes."""
    lotes = {l.id: l for l in data.lotes}
    stats = {
        "detalles": 0,
        "qty_antes": 0.0,
        "qty_despues": 0.0,
        "stock_devuelto": 0.0,
        "regs": 0,
    }

    for reg in data.desayunos:
        if getattr(reg, "anulado", False):
            continue
        touched = False
        detalle = list(getattr(reg, "lineas_detalle", None) or [])
        for di, det in enumerate(detalle):
            if det.producto_id not in PAN_IDS:
                continue
            old_q = float(det.cantidad or 0)
            if old_q < UMBRAL_PAQUETE:
                continue
            new_q = round(old_q / REBANADAS, 6)
            scale = new_q / old_q if old_q else 0
            stats["detalles"] += 1
            stats["qty_antes"] += old_q
            stats["qty_despues"] += new_q
            if dry_run:
                touched = True
                continue

            det.cantidad = new_q
            det.coste = round(float(det.coste or 0) * scale, 2)
            frags = list(getattr(det, "consumos_lote", None) or [])
            for fi, frag in enumerate(frags):
                f_old = float(frag.cantidad or 0)
                if f_old <= 0:
                    continue
                f_new = round(f_old / REBANADAS, 6)
                excess = round(f_old - f_new, 6)
                frag.cantidad = f_new
                frag.coste = round(float(frag.coste or 0) * (f_new / f_old), 2)
                lote = lotes.get(frag.lote_id)
                if lote is not None and not getattr(lote, "anulado", False):
                    lote.cantidad_restante = round(
                        float(lote.cantidad_restante) + excess, 6
                    )
                    stats["stock_devuelto"] += excess
                # espejo consumo
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

        # Reagregar lineas p09/p11 desde detalle
        from app.core.models import LineaDesayuno

        otras = [ln for ln in (reg.lineas or []) if ln.producto_id not in PAN_IDS]
        por_pid: dict[str, LineaDesayuno] = {}
        for det in detalle:
            if det.producto_id not in PAN_IDS:
                continue
            if det.producto_id not in por_pid:
                por_pid[det.producto_id] = LineaDesayuno(
                    det.producto_id, 0.0, 0.0, False
                )
            cur = por_pid[det.producto_id]
            por_pid[det.producto_id] = LineaDesayuno(
                det.producto_id,
                round(cur.cantidad + float(det.cantidad), 6),
                round(cur.coste + float(det.coste or 0), 2),
                cur.es_extra,
            )
        # conservar es_extra de lineas previas
        prev_extra = {
            ln.producto_id: ln.es_extra
            for ln in (reg.lineas or [])
            if ln.producto_id in PAN_IDS
        }
        for pid, ln in por_pid.items():
            por_pid[pid] = LineaDesayuno(
                pid, ln.cantidad, ln.coste, prev_extra.get(pid, False)
            )
        reg.lineas = otras + list(por_pid.values())
        reg.coste_total = round(sum(float(l.coste or 0) for l in reg.lineas), 2)
        obs = (reg.observaciones or "").strip()
        if TAG not in obs:
            reg.observaciones = f"{obs} {TAG}".strip() if obs else TAG

    return stats


def _asegurar_recetas_huevo(data) -> list[str]:
    msgs: list[str] = []
    # Huevos revueltos (nueva)
    existe = next(
        (
            r
            for r in data.recetas
            if (r.nombre or "").strip().lower() == "huevos revueltos"
        ),
        None,
    )
    ings_rev = [
        IngredienteReceta("p46", 0.05, 50.0, "ml"),
    ]
    if existe is None:
        r = rec_svc.crear_receta(
            "Huevos revueltos",
            ings_rev,
            CategoriaReceta.DESAYUNO,
            servicios_disponibles=["desayuno"],
            porciones_estandar=1.0,
        )
        msgs.append(f"crear revueltos: {r.ok} {r.mensaje}")
    else:
        r = rec_svc.editar_receta(
            existe.id,
            "Huevos revueltos",
            ings_rev,
            CategoriaReceta.DESAYUNO,
            servicios_disponibles=["desayuno"],
            porciones_estandar=1.0,
        )
        msgs.append(f"editar revueltos: {r.ok} {r.mensaje}")

    # Huevos rotos → huevina
    rotos = next(
        (r for r in data.recetas if (r.nombre or "").strip().lower() == "huevos rotos"),
        None,
    )
    if rotos is not None:
        ings_rot = [
            IngredienteReceta("p12", 0.15, 150.0, "gr"),
            IngredienteReceta("p102", 0.04, 40.0, "gr"),
            IngredienteReceta("p46", 0.05, 50.0, "ml"),
        ]
        r = rec_svc.editar_receta(
            rotos.id,
            "Huevos rotos",
            ings_rot,
            CategoriaReceta.DESAYUNO,
            servicios_disponibles=["desayuno", "comida"],
            porciones_estandar=1.0,
        )
        msgs.append(f"editar rotos: {r.ok} {r.mensaje}")
    else:
        msgs.append("Huevos rotos: no encontrado")
    return msgs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not HOTEL.exists():
        print("No existe", HOTEL)
        return 1

    backup = None if args.dry_run else _backup()
    if backup:
        print("Backup:", backup)

    _boot()
    data = get_container().app_data_store.get()

    def _tot(pid: str, src=None) -> float:
        src = src or data
        return sum(
            float(ln.cantidad or 0)
            for des in src.desayunos
            if not getattr(des, "anulado", False)
            for ln in (des.lineas or [])
            if ln.producto_id == pid
        )

    print("Antes p09/p11:", {pid: _tot(pid) for pid in PAN_IDS})

    if not args.dry_run:
        msgs = _asegurar_recetas_huevo(get_container().app_data_store.get())
        for m in msgs:
            print(m)
        data = get_container().app_data_store.get()

    stats = _corregir_registros_desayuno(data, dry_run=args.dry_run)
    print("Corrección pan:", json.dumps(stats, indent=2))

    if args.dry_run:
        print("Dry-run: sin persistir.")
        return 0

    from app.core.services.desayuno_service import _ctx

    _ctx().uow.commit(data)
    data = get_container().app_data_store.get()
    print("Después p09/p11:", {pid: _tot(pid, data) for pid in PAN_IDS})
    print("Persistido", HOTEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
