"""Desayuno inglés: incluye huevo frito (p48) en ficha y en registros históricos.

- Actualiza receta r11 con 1× HUEVO CASCARA (huevo frito).
- En históricos, suma 1 huevo por ración de «Desayuno ingles» salvo:
  - ya hay p48 atribuido a r11 en el detalle,
  - la ración omitió el huevo,
  - o ya lleva huevo como extra (p48 / p46 revuelto) — tipo distinto del frito.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\fix_desayuno_ingles_huevo.py --dry-run
  .\\.venv\\Scripts\\python.exe scripts\\fix_desayuno_ingles_huevo.py
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
from app.core.models import CategoriaReceta, IngredienteReceta
from app.core.models.desayuno import LineaDesayuno
from app.core.models.enums import OrigenConsumo, TipoServicio
from app.core.models.registro_servicio import ConsumoLoteDetalle, LineaDetalleOrigen
from app.core.services import receta_service as rec_svc
from app.core.services.inventory_batch_service import descontar_lotes
from app.core.services.movimiento_service import (
    ORIGEN_TIPO_DESAYUNO,
    espejo_consumo_fragmento,
)
from app.core.services.text_search import normalizar_texto

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
BACKUP_DIR = HOTEL.parent / "backups"
RECETA_ID = "r11"
RECETA_NOMBRE = "Desayuno ingles"
HUEVO_FRITO = "p48"
HUEVO_REVUELTO = "p46"
CANT_FRITO = 1.0
TAG = "[fix-ingles-huevo-frito]"


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="fix-ingles-huevo",
            actor_label="Fix Desayuno ingles huevo",
            role=ROL_DIRECCION,
            session_id="fix-ingles-huevo-session",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="fix",
        )
    )


def _boot(path: Path) -> None:
    reset_container()
    configure_for_flet(data_path=str(path))
    _auth()


def _backup(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"datos_hotel_pre_ingles_huevo_{stamp}.json"
    shutil.copy2(path, dest)
    return dest


def _corregir_receta(*, dry_run: bool) -> dict:
    receta = rec_svc.obtener_receta(RECETA_ID)
    if receta is None:
        return {"ok": False, "error": f"Receta {RECETA_ID} no encontrada"}
    if any(i.producto_id == HUEVO_FRITO for i in receta.ingredientes):
        return {"ok": True, "skipped": True, "mensaje": "Receta ya incluye huevo"}
    ings = list(receta.ingredientes) + [
        IngredienteReceta(HUEVO_FRITO, CANT_FRITO, 1.0, "Ud")
    ]
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "mensaje": f"Añadiría {HUEVO_FRITO} x{CANT_FRITO:g} Ud a {RECETA_NOMBRE}",
        }
    r = rec_svc.editar_receta(
        RECETA_ID,
        RECETA_NOMBRE,
        ings,
        CategoriaReceta.DESAYUNO,
        servicios_disponibles=list(receta.servicios_disponibles or ["desayuno"]),
        porciones_estandar=float(receta.porciones_estandar or 1.0),
        extras_sugeridos=list(getattr(receta, "extras_sugeridos", None) or []),
    )
    return {"ok": r.ok, "mensaje": r.mensaje}


def _rr_ya_lleva_huevo(rr) -> str | None:
    """Devuelve motivo si no hay que añadir huevo frito a esta ración."""
    nombre = normalizar_texto(getattr(rr, "nombre_receta", "") or "")
    if "sin huevo" in nombre:
        return "nombre_sin_huevo"
    omitidos = {o.producto_id for o in (getattr(rr, "omisiones", None) or [])}
    if HUEVO_FRITO in omitidos:
        return "omitido"
    for ex in getattr(rr, "extras", None) or []:
        pid = getattr(ex, "producto_id", None)
        if pid == HUEVO_REVUELTO:
            return "extra_revuelto"
        if pid == HUEVO_FRITO:
            return "extra_huevo"
    return None


def _reagregar_lineas_desayuno(reg) -> None:
    por_pid: dict[str, LineaDesayuno] = {}
    prev_extra = {ln.producto_id: ln.es_extra for ln in (reg.lineas or [])}
    for det in getattr(reg, "lineas_detalle", None) or []:
        pid = det.producto_id
        if pid not in por_pid:
            por_pid[pid] = LineaDesayuno(pid, 0.0, 0.0, prev_extra.get(pid, False))
        cur = por_pid[pid]
        por_pid[pid] = LineaDesayuno(
            pid,
            round(cur.cantidad + float(det.cantidad or 0), 6),
            round(cur.coste + float(det.coste or 0), 2),
            cur.es_extra,
        )
    reg.lineas = [por_pid[pid] for pid in sorted(por_pid)]
    reg.coste_total = round(sum(float(l.coste or 0) for l in reg.lineas), 2)


def _corregir_historico(data, *, dry_run: bool) -> dict:
    from app.core.services.desayuno_service import _ctx

    stats = {
        "desayunos": 0,
        "raciones_ingles": 0,
        "huevos_anadidos": 0.0,
        "saltadas": 0,
        "motivos": {},
    }
    ctx = _ctx()

    for reg in data.desayunos:
        if getattr(reg, "anulado", False):
            continue
        obs = (getattr(reg, "observaciones", None) or "")
        if TAG in obs and not dry_run:
            # Idempotente: si ya se aplicó el tag, no repetir
            ya_p48 = sum(
                float(det.cantidad or 0)
                for det in (reg.lineas_detalle or [])
                if det.producto_id == HUEVO_FRITO
                and getattr(det, "receta_origen_id", None) == RECETA_ID
            )
            if ya_p48 > 0:
                continue

        rrs = list(getattr(reg, "registros_recetas", None) or [])
        ingleses = [
            rr
            for rr in rrs
            if normalizar_texto(getattr(rr, "nombre_receta", "") or "") == "desayuno ingles"
            or getattr(rr, "receta_id", None) == RECETA_ID
        ]
        if not ingleses:
            continue

        # Huevo ya atribuido a la ficha r11 en este registro
        p48_r11 = sum(
            float(det.cantidad or 0)
            for det in (reg.lineas_detalle or [])
            if det.producto_id == HUEVO_FRITO
            and getattr(det, "receta_origen_id", None) == RECETA_ID
        )

        a_anadir = 0.0
        for rr in ingleses:
            porc = float(getattr(rr, "porciones", 1) or 1)
            stats["raciones_ingles"] += porc
            motivo = _rr_ya_lleva_huevo(rr)
            if motivo:
                stats["saltadas"] += 1
                stats["motivos"][motivo] = stats["motivos"].get(motivo, 0) + 1
                continue
            a_anadir += porc * CANT_FRITO

        # Si el detalle ya tiene exactamente el huevo de ficha, no tocar
        if p48_r11 > 0 and abs(p48_r11 - a_anadir) < 1e-6 and a_anadir > 0:
            continue
        if a_anadir <= 0:
            continue

        # Evitar doble si ya hay p48_r11 parcial: solo la diferencia
        falta = round(max(a_anadir - p48_r11, 0.0), 6)
        if falta <= 0:
            continue

        stats["desayunos"] += 1
        stats["huevos_anadidos"] += falta
        if dry_run:
            continue

        desc = descontar_lotes(data, HUEVO_FRITO, falta, permitir_negativo=True)
        det = LineaDetalleOrigen(
            origen=OrigenConsumo.INGREDIENTE_RECETA.value,
            producto_id=HUEVO_FRITO,
            cantidad=falta,
            coste=round(desc.coste, 2),
            receta_origen_id=RECETA_ID,
            registro_origen_id=reg.id,
            tipo_servicio=TipoServicio.DESAYUNO.value,
            categoria_receta=CategoriaReceta.DESAYUNO.value,
            categoria_receta_snapshot=CategoriaReceta.DESAYUNO.value,
            consumos_lote=[
                ConsumoLoteDetalle(m.lote_id, m.producto_id, m.cantidad, m.coste)
                for m in desc.movimientos
            ],
        )
        if reg.lineas_detalle is None:
            reg.lineas_detalle = []
        det_idx = len(reg.lineas_detalle)
        reg.lineas_detalle.append(det)

        for fi, frag in enumerate(det.consumos_lote):
            r = espejo_consumo_fragmento(
                producto_id=frag.producto_id,
                lote_id=frag.lote_id,
                cantidad=frag.cantidad,
                fecha=getattr(reg, "fecha", None) or ctx.clock.today(),
                origen_tipo=ORIGEN_TIPO_DESAYUNO,
                registro_id=reg.id,
                det_idx=det_idx,
                frag_idx=fi,
                coste_total=frag.coste,
                hora=getattr(reg, "hora", None),
                ctx=ctx,
                commit=False,
            )
            if not r.ok and not r.duplicado:
                raise RuntimeError(f"Espejo p48 {reg.id} det{det_idx}: {r.mensaje}")

        _reagregar_lineas_desayuno(reg)
        obs2 = (reg.observaciones or "").strip()
        if TAG not in obs2:
            reg.observaciones = f"{obs2} {TAG}".strip() if obs2 else TAG

    return {"ok": True, **stats}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--path", type=Path, default=HOTEL)
    args = parser.parse_args()

    if not args.path.exists():
        print("No existe", args.path)
        return 1

    backup = None if args.dry_run else _backup(args.path)
    if backup:
        print("Backup:", backup)

    _boot(args.path)
    data = get_container().app_data_store.get()

    r_rec = _corregir_receta(dry_run=args.dry_run)
    print("Receta:", r_rec)
    if not r_rec.get("ok"):
        return 1

    r_hist = _corregir_historico(data, dry_run=args.dry_run)
    print("Historico:", r_hist)
    if not r_hist.get("ok"):
        return 1

    if not args.dry_run:
        from app.core.services.desayuno_service import _ctx

        _ctx().uow.commit(data)
        print("Guardado:", args.path)
    else:
        print("Dry-run: sin guardar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
