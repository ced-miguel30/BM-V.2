"""Backfill aproximado: café con leche, americano y té verde en desayunos activos.

Reparte ~40 bebidas (con variación) entre los desayunos no anulados del hotel
live, descontando stock FIFO y ampliando lineas / registros_recetas / detalle.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\backfill_bebidas_desayunos.py
  .\\.venv\\Scripts\\python.exe scripts\\backfill_bebidas_desayunos.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.models import LineaDesayuno, TipoServicio
from app.core.services import desayuno_service as des
from app.core.services import movimiento_service as mov_svc
from app.core.services.detalle_origen_service import (
    asignar_consumos_lote,
    asignar_costes_proporcionales,
    construir_lineas_detalle,
    validar_consumos_lote,
)

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
BACKUP_DIR = HOTEL.parent / "backups"

# Recetas bebida desayuno (IDs live hotel)
RECETA_CAFE_LECHE = "r81"
RECETA_AMERICANO = "r80"
RECETA_TE_VERDE = "r145"

# ~40 bebidas totales con variación ligera
POOL = (
    [RECETA_CAFE_LECHE] * 16
    + [RECETA_AMERICANO] * 13
    + [RECETA_TE_VERDE] * 11
)  # 40
SEED = 20260825
TAG_OBS = "[backfill-bebidas-40]"


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="backfill-dir",
            actor_label="Backfill Dirección",
            role=ROL_DIRECCION,
            session_id="backfill-bebidas-session",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="backfill",
        )
    )


def _boot() -> None:
    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()


def _backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"datos_hotel_pre_bebidas_{stamp}.json"
    shutil.copy2(HOTEL, dest)
    return dest


def _distribucion(desayuno_ids: list[str]) -> dict[str, dict[str, int]]:
    """Asigna porciones por desayuno: {desayuno_id: {receta_id: porciones}}.

    Cada desayuno activo recibe al menos 1 bebida; el resto se reparte con variación.
    """
    rng = random.Random(SEED)
    pool = list(POOL)
    rng.shuffle(pool)
    ids = list(desayuno_ids)
    assign: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for i, did in enumerate(ids):
        assign[did][pool[i]] += 1
    for rid in pool[len(ids) :]:
        assign[rng.choice(ids)][rid] += 1
    return {k: dict(v) for k, v in assign.items()}


def _ya_backfilleado(reg) -> bool:
    obs = getattr(reg, "observaciones", "") or ""
    if TAG_OBS in obs:
        return True
    nombres = {
        (rr.nombre_receta or "").strip().lower()
        for rr in (getattr(reg, "registros_recetas", None) or [])
    }
    return {"americano", "cafe con leche", "te verde"} <= nombres


def _merge_lineas(existentes: list[LineaDesayuno], nuevas: list[LineaDesayuno]) -> list[LineaDesayuno]:
    por_pid: dict[str, LineaDesayuno] = {}
    for ln in existentes:
        por_pid[ln.producto_id] = LineaDesayuno(
            ln.producto_id, float(ln.cantidad), float(ln.coste), bool(ln.es_extra)
        )
    for ln in nuevas:
        if ln.producto_id in por_pid:
            cur = por_pid[ln.producto_id]
            por_pid[ln.producto_id] = LineaDesayuno(
                ln.producto_id,
                round(cur.cantidad + ln.cantidad, 4),
                round(cur.coste + ln.coste, 2),
                cur.es_extra or ln.es_extra,
            )
        else:
            por_pid[ln.producto_id] = LineaDesayuno(
                ln.producto_id, float(ln.cantidad), float(ln.coste), bool(ln.es_extra)
            )
    return list(por_pid.values())


def _aplicar_a_desayuno(reg, por_receta: dict[str, int], *, dry_run: bool) -> dict:
    context = des._ctx()
    des.limpiar_cesta()
    added = []
    for rid, porciones in sorted(por_receta.items()):
        if porciones <= 0:
            continue
        r = des.anadir_receta_a_cesta(rid, float(porciones))
        if not r.ok:
            des.limpiar_cesta()
            return {"ok": False, "id": reg.id, "error": r.mensaje, "recetas": por_receta}
        added.append((rid, porciones))

    if not added:
        return {"ok": True, "id": reg.id, "skipped": True, "reason": "sin porciones"}

    fusionado = des._aplanar_cesta()
    grupos = list(des.get_cesta_recetas())
    cesta_suelta = list(des.get_cesta())
    plan = des._plan_stock_fusionado(context.data(), fusionado)
    if not plan.ok:
        des.limpiar_cesta()
        return {
            "ok": False,
            "id": reg.id,
            "error": "STOCK_INSUFICIENTE",
            "detalle": [str(d) for d in (plan.deficits or [])],
            "recetas": por_receta,
        }

    summary = {
        "ok": True,
        "id": reg.id,
        "fecha": reg.fecha.isoformat() if hasattr(reg.fecha, "isoformat") else str(reg.fecha),
        "recetas": por_receta,
        "productos": {pid: cant for pid, (cant, _) in fusionado.items()},
    }
    if dry_run:
        des.limpiar_cesta()
        return summary

    data = context.data()
    demandas = {pid: cant for pid, (cant, _) in fusionado.items() if cant > 0}
    extras = {pid: es for pid, (cant, es) in fusionado.items() if cant > 0}

    from app.core.application.inventory_ops import aplicar_descuento_atomico

    resultado_desc = aplicar_descuento_atomico(context, demandas)
    costes_agregados = resultado_desc.costes
    lineas_nuevas = [
        LineaDesayuno(pid, demandas[pid], costes_agregados.get(pid, 0.0), extras[pid])
        for pid in demandas
    ]
    lineas_detalle_nuevas = construir_lineas_detalle(
        cesta_suelta,
        grupos,
        tipo_servicio=TipoServicio.DESAYUNO.value,
        registro_id=reg.id,
        data=data,
    )
    asignar_costes_proporcionales(lineas_detalle_nuevas, costes_agregados, dict(demandas))
    asignar_consumos_lote(lineas_detalle_nuevas, resultado_desc.movimientos)
    validar_consumos_lote(
        lineas_detalle_nuevas, resultado_desc.movimientos, costes_agregados, data
    )
    registros_nuevos = des._construir_registros_recetas(data, grupos)

    base_det_idx = len(reg.lineas_detalle or [])
    reg.lineas = _merge_lineas(list(reg.lineas or []), lineas_nuevas)
    reg.registros_recetas = list(reg.registros_recetas or []) + registros_nuevos
    reg.lineas_detalle = list(reg.lineas_detalle or []) + lineas_detalle_nuevas
    reg.coste_total = round(sum(l.coste for l in reg.lineas), 2)
    obs = (reg.observaciones or "").strip()
    reg.observaciones = f"{obs} {TAG_OBS}".strip() if obs else TAG_OBS

    from app.core.services.ubicacion_stock_service import ubicacion_preferida_lote

    for di, det in enumerate(lineas_detalle_nuevas):
        for fi, frag in enumerate(getattr(det, "consumos_lote", None) or []):
            if float(getattr(frag, "cantidad", 0) or 0) <= 0:
                continue
            ubi = ubicacion_preferida_lote(data, frag.lote_id)
            r = mov_svc.espejo_consumo_fragmento(
                producto_id=frag.producto_id,
                lote_id=frag.lote_id,
                cantidad=frag.cantidad,
                fecha=reg.fecha,
                origen_tipo=mov_svc.ORIGEN_TIPO_DESAYUNO,
                registro_id=reg.id,
                det_idx=base_det_idx + di,
                frag_idx=fi,
                coste_total=frag.coste,
                hora=reg.hora,
                usuario_id=context.actor.id or None,
                ubicacion_origen_id=ubi,
                ctx=context,
                commit=False,
            )
            if not r.ok and not getattr(r, "duplicado", False):
                raise RuntimeError(f"Espejo consumo falló en {reg.id}: {r.mensaje}")

    des.limpiar_cesta()
    summary["coste_add"] = round(sum(l.coste for l in lineas_nuevas), 2)
    summary["coste_total"] = reg.coste_total
    return summary


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
    activos = sorted(
        [d for d in data.desayunos if not getattr(d, "anulado", False)],
        key=lambda d: (d.fecha, d.id),
    )
    if not activos:
        print("No hay desayunos activos")
        return 1

    # Idempotencia global: un solo backfill sobre el hotel live
    if any(_ya_backfilleado(d) for d in activos):
        print("Ya backfilleado (tag presente en algún desayuno activo). Nada que hacer.")
        return 0

    pendientes = list(activos)
    dist = _distribucion([d.id for d in pendientes])
    totals: dict[str, int] = defaultdict(int)
    for por in dist.values():
        for rid, n in por.items():
            totals[rid] += n

    nombres = {r.id: r.nombre for r in data.recetas}
    print(
        "Distribución:",
        {nombres.get(k, k): v for k, v in totals.items()},
        "total",
        sum(totals.values()),
        "desayunos tocados",
        len(dist),
    )

    report = {"ok": [], "errors": [], "dry_run": args.dry_run}
    by_id = {d.id: d for d in pendientes}
    for did, por in sorted(dist.items()):
        reg = by_id[did]
        res = _aplicar_a_desayuno(reg, por, dry_run=args.dry_run)
        if res.get("ok"):
            report["ok"].append(res)
        else:
            report["errors"].append(res)
            print("ERROR", res)
            break

    if not args.dry_run and not report["errors"]:
        context = des._ctx()
        from app.core.services.alert_service import sincronizar_alertas

        sincronizar_alertas(context)
        context.uow.commit(data)
        print("Persistido en", HOTEL)

    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "ok": len(report["ok"]),
                "errors": len(report["errors"]),
                "totales_receta": {nombres.get(k, k): v for k, v in totals.items()},
                "muestra": report["ok"][:5],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
