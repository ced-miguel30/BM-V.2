"""Ensalada césar: pan de molde p09 (1 reb) en lugar de mini chapata p03.

Corrige la receta r51 y el registro co48 (TPV 21/08/2026).

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\fix_ensalada_cesar_pan_molde.py --dry-run
  .\\.venv\\Scripts\\python.exe scripts\\fix_ensalada_cesar_pan_molde.py
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
from app.core.models.registro_servicio import ConsumoLoteDetalle, LineaServicio
from app.core.services import receta_service as rec_svc
from app.core.services.inventory_batch_service import descontar_lotes
from app.core.services.movimiento_service import (
    ORIGEN_TIPO_REGISTRO_SERVICIO,
    espejo_consumo_fragmento,
    origen_linea_id_consumo,
)
from app.core.services.pack_unidades import piezas_a_ud_paquete

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
BACKUP_DIR = HOTEL.parent / "backups"
RECETA_ID = "r51"
RECETA_NOMBRE = "Ensalada cesar"
REGISTRO_ID = "co48"
PAN_VIEJO = "p03"
PAN_NUEVO = "p09"
REB_POR_RACION = piezas_a_ud_paquete(PAN_NUEVO, 1.0)
TAG = "[fix-ensalada-cesar-p09]"


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="fix-cesar",
            actor_label="Fix Ensalada cesar",
            role=ROL_DIRECCION,
            session_id="fix-cesar-session",
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
    dest = BACKUP_DIR / f"datos_hotel_pre_cesar_p09_{stamp}.json"
    shutil.copy2(HOTEL, dest)
    return dest


def _ingredientes_cesar_corregidos(receta) -> list[IngredienteReceta]:
    ings: list[IngredienteReceta] = []
    for ing in receta.ingredientes:
        if ing.producto_id == PAN_VIEJO:
            continue
        ings.append(ing)
    ings.append(
        IngredienteReceta(
            PAN_NUEVO,
            REB_POR_RACION,
            1.0,
            "reb",
        )
    )
    return ings


def _corregir_receta(*, dry_run: bool) -> dict:
    data = get_container().app_data_store.get()
    receta = rec_svc.obtener_receta(RECETA_ID)
    if receta is None:
        return {"ok": False, "error": f"Receta {RECETA_ID} no encontrada"}
    pan = next((i for i in receta.ingredientes if i.producto_id in {PAN_VIEJO, PAN_NUEVO}), None)
    if pan and pan.producto_id == PAN_NUEVO and abs(float(pan.cantidad) - REB_POR_RACION) < 1e-6:
        return {"ok": True, "skipped": True, "mensaje": "Receta ya corregida"}
    ings = _ingredientes_cesar_corregidos(receta)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "ingredientes": [
                {
                    "producto_id": i.producto_id,
                    "cantidad": i.cantidad,
                    "presentacion": f"{i.cantidad_presentacion} {i.unidad_presentacion}",
                }
                for i in ings
            ],
        }
    r = rec_svc.editar_receta(
        RECETA_ID,
        RECETA_NOMBRE,
        ings,
        CategoriaReceta.COMIDA,
        servicios_disponibles=list(receta.servicios_disponibles or ["comida"]),
        porciones_estandar=float(receta.porciones_estandar or 1.0),
    )
    return {"ok": r.ok, "mensaje": r.mensaje}


def _buscar_otros_p03_r51(data) -> list[dict]:
    hallazgos: list[dict] = []
    for reg in data.registros_servicio:
        if getattr(reg, "anulado", False):
            continue
        for det in getattr(reg, "lineas_detalle", None) or []:
            if det.producto_id != PAN_VIEJO:
                continue
            if getattr(det, "receta_origen_id", None) != RECETA_ID:
                continue
            hallazgos.append(
                {
                    "registro_id": reg.id,
                    "fecha": str(getattr(reg, "fecha", "")),
                    "cantidad_p03": float(det.cantidad or 0),
                }
            )
    return hallazgos


def _reagregar_lineas_servicio(reg) -> None:
    por_pid: dict[str, LineaServicio] = {}
    for det in getattr(reg, "lineas_detalle", None) or []:
        pid = det.producto_id
        if pid not in por_pid:
            por_pid[pid] = LineaServicio(pid, 0.0, 0.0, False)
        cur = por_pid[pid]
        por_pid[pid] = LineaServicio(
            pid,
            round(cur.cantidad + float(det.cantidad or 0), 6),
            round(cur.coste + float(det.coste or 0), 2),
            cur.es_extra,
        )
    prev_extra = {ln.producto_id: ln.es_extra for ln in (reg.lineas or [])}
    reg.lineas = [
        LineaServicio(pid, ln.cantidad, ln.coste, prev_extra.get(pid, ln.es_extra))
        for pid, ln in sorted(por_pid.items())
    ]
    reg.coste_total = round(sum(float(l.coste or 0) for l in reg.lineas), 2)


def _corregir_registro_co48(data, *, dry_run: bool) -> dict:
    from app.core.services.desayuno_service import _ctx

    reg = next((r for r in data.registros_servicio if r.id == REGISTRO_ID), None)
    if reg is None:
        return {"ok": False, "error": f"Registro {REGISTRO_ID} no encontrado"}
    if getattr(reg, "anulado", False):
        return {"ok": False, "error": f"Registro {REGISTRO_ID} anulado"}

    detalle = list(getattr(reg, "lineas_detalle", None) or [])
    indices = [
        i
        for i, det in enumerate(detalle)
        if det.producto_id == PAN_VIEJO and getattr(det, "receta_origen_id", None) == RECETA_ID
    ]
    if not indices:
        p09 = sum(
            float(det.cantidad or 0)
            for det in detalle
            if det.producto_id == PAN_NUEVO and getattr(det, "receta_origen_id", None) == RECETA_ID
        )
        if p09 > 0:
            return {"ok": True, "skipped": True, "mensaje": "co48 ya usa p09 para r51"}
        return {"ok": False, "error": "No hay línea p03/r51 en co48"}

    stats = {"indices": indices, "p03_devuelto": 0.0, "p09_descontado": 0.0}
    lotes = {l.id: l for l in data.lotes}

    for di in indices:
        det = detalle[di]
        old_qty = float(det.cantidad or 0)
        porciones = old_qty  # 1 Ud chapata por ración → old_qty = nº raciones
        new_qty = round(porciones * REB_POR_RACION, 6)
        stats["p03_devuelto"] += old_qty
        stats["p09_descontado"] += new_qty

        if dry_run:
            continue

        # Devolver stock p03 y eliminar movimientos de consumo previos.
        for fi, frag in enumerate(list(getattr(det, "consumos_lote", None) or [])):
            f_qty = float(frag.cantidad or 0)
            if f_qty <= 0:
                continue
            lote = lotes.get(frag.lote_id)
            if lote is not None and not getattr(lote, "anulado", False):
                lote.cantidad_restante = round(float(lote.cantidad_restante) + f_qty, 6)
            linea_id = origen_linea_id_consumo(di, fi)
            data.movimientos = [
                m
                for m in data.movimientos
                if not (
                    getattr(m, "origen_id", None) == REGISTRO_ID
                    and getattr(m, "origen_linea_id", None) == linea_id
                    and getattr(m, "producto_id", None) == PAN_VIEJO
                )
            ]

        desc = descontar_lotes(data, PAN_NUEVO, new_qty, permitir_negativo=True)
        det.producto_id = PAN_NUEVO
        det.cantidad = new_qty
        det.coste = round(desc.coste, 2)
        det.consumos_lote = [
            ConsumoLoteDetalle(m.lote_id, m.producto_id, m.cantidad, m.coste)
            for m in desc.movimientos
        ]

        ctx = _ctx()
        for fi, frag in enumerate(det.consumos_lote):
            r = espejo_consumo_fragmento(
                producto_id=frag.producto_id,
                lote_id=frag.lote_id,
                cantidad=frag.cantidad,
                fecha=getattr(reg, "fecha", None) or ctx.clock.today(),
                origen_tipo=ORIGEN_TIPO_REGISTRO_SERVICIO,
                registro_id=REGISTRO_ID,
                det_idx=di,
                frag_idx=fi,
                coste_total=frag.coste,
                hora=getattr(reg, "hora", None),
                ctx=ctx,
                commit=False,
            )
            if not r.ok and not r.duplicado:
                raise RuntimeError(f"Espejo p09 co48 det{di}: {r.mensaje}")

    if not dry_run:
        _reagregar_lineas_servicio(reg)
        obs = (reg.observaciones or "").strip()
        if TAG not in obs:
            reg.observaciones = f"{obs} {TAG}".strip() if obs else TAG

    return {"ok": True, **stats}


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

    otros = _buscar_otros_p03_r51(data)
    print("Consumos p03/r51 en registros activos:", json.dumps(otros, indent=2, ensure_ascii=False))

    rec = _corregir_receta(dry_run=args.dry_run)
    print("Receta r51:", json.dumps(rec, indent=2, ensure_ascii=False))
    if not rec.get("ok"):
        return 1

    if not args.dry_run:
        data = get_container().app_data_store.get()

    reg = _corregir_registro_co48(data, dry_run=args.dry_run)
    print("Registro co48:", json.dumps(reg, indent=2, ensure_ascii=False))
    if not reg.get("ok"):
        return 1

    sim = rec_svc.simular_receta(RECETA_ID, 3.0)
    pan_lineas = [ln for ln in (sim.lineas or []) if ln.producto_id in {PAN_VIEJO, PAN_NUEVO}]
    print(
        "Simulación 3 raciones:",
        json.dumps(
            [{"pid": ln.producto_id, "qty": ln.cantidad_nativa} for ln in pan_lineas],
            indent=2,
        ),
    )

    if args.dry_run:
        print("Dry-run: sin persistir.")
        return 0

    from app.core.services.desayuno_service import _ctx

    _ctx().uow.commit(data)
    print("Persistido", HOTEL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
