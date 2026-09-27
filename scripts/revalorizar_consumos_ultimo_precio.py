"""Revaloriza costes de desayunos ya guardados (D61): FIFO lote + último precio.

No mueve stock. Reescribe coste de fragmentos/líneas/total y snapshots de
movimientos de consumo vinculados. Idempotente si se vuelve a ejecutar.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\revalorizar_consumos_ultimo_precio.py ^
      --path D:\\work\\2-BM-DATOS\\data\\datos_hotel.json
  .\\.venv\\Scripts\\python.exe scripts\\revalorizar_consumos_ultimo_precio.py ^
      --path D:\\work\\2-BM-DATOS\\data\\datos_hotel.json --desde 2026-08-22 --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_fecha(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    s = str(v)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _unit_lote(lote: dict) -> float:
    q = _f(lote.get("cantidad"))
    if q <= 0:
        return 0.0
    return _f(lote.get("precio_total")) / q


def _build_lotes_por_producto(lotes: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for l in lotes:
        if l.get("anulado"):
            continue
        pid = l.get("producto_id")
        if not pid:
            continue
        out.setdefault(str(pid), []).append(l)
    for pid, lst in out.items():
        lst.sort(
            key=lambda x: (
                _parse_fecha(x.get("fecha_compra")) or date.min,
                str(x.get("id") or ""),
            )
        )
    return out


def _ultimo_con_precio(
    por_prod: dict[str, list[dict]],
    producto_id: str,
    *,
    hasta: date | None,
) -> dict | None:
    cands = []
    for l in por_prod.get(producto_id, []):
        if _unit_lote(l) <= 0:
            continue
        fc = _parse_fecha(l.get("fecha_compra"))
        if hasta is not None and fc is not None and fc > hasta:
            continue
        cands.append(l)
    return cands[-1] if cands else None


def _unit_para_frag(
    lote_by_id: dict[str, dict],
    por_prod: dict[str, list[dict]],
    frag: dict,
    *,
    hasta: date | None,
) -> float:
    lid = str(frag.get("lote_id") or "")
    lote = lote_by_id.get(lid)
    if lote is not None:
        u = _unit_lote(lote)
        if u > 0:
            return u
    pid = str(frag.get("producto_id") or (lote or {}).get("producto_id") or "")
    if not pid:
        return 0.0
    vig = _ultimo_con_precio(por_prod, pid, hasta=hasta)
    if vig is None:
        # fallback: último con precio sin tope de fecha
        vig = _ultimo_con_precio(por_prod, pid, hasta=None)
    return _unit_lote(vig) if vig else 0.0


def _reval_registro(
    reg: dict,
    *,
    lote_by_id: dict[str, dict],
    por_prod: dict[str, list[dict]],
) -> tuple[float, float, int]:
    """Devuelve (coste_antes, coste_despues, frags_cambiados)."""
    antes = _f(reg.get("coste_total"))
    hasta = _parse_fecha(reg.get("fecha"))
    frags_ch = 0
    por_producto: dict[str, float] = {}

    detalles = reg.get("lineas_detalle") or []
    if detalles:
        for det in detalles:
            if not isinstance(det, dict):
                continue
            frags = det.get("consumos_lote") or []
            if frags:
                suma = 0.0
                for frag in frags:
                    if not isinstance(frag, dict):
                        continue
                    qty = _f(frag.get("cantidad"))
                    old = _f(frag.get("coste"))
                    unit = _unit_para_frag(
                        lote_by_id, por_prod, frag, hasta=hasta,
                    )
                    new = round(qty * unit, 2)
                    if abs(new - old) > 0.005:
                        frags_ch += 1
                    frag["coste"] = new
                    suma += new
                det["coste"] = round(suma, 2)
            else:
                # Sin fragmentos: valorizar cantidad al precio vigente del producto
                pid = str(det.get("producto_id") or "")
                qty = _f(det.get("cantidad"))
                vig = _ultimo_con_precio(por_prod, pid, hasta=hasta)
                unit = _unit_lote(vig) if vig else 0.0
                new = round(qty * unit, 2)
                if abs(new - _f(det.get("coste"))) > 0.005:
                    frags_ch += 1
                det["coste"] = new
            pid = str(det.get("producto_id") or "")
            if pid:
                por_producto[pid] = round(
                    por_producto.get(pid, 0.0) + _f(det.get("coste")), 2
                )
    else:
        # Solo líneas agregadas
        for ln in reg.get("lineas") or []:
            if not isinstance(ln, dict):
                continue
            pid = str(ln.get("producto_id") or "")
            qty = _f(ln.get("cantidad"))
            vig = _ultimo_con_precio(por_prod, pid, hasta=hasta)
            unit = _unit_lote(vig) if vig else 0.0
            new = round(qty * unit, 2)
            if abs(new - _f(ln.get("coste"))) > 0.005:
                frags_ch += 1
            ln["coste"] = new
            por_producto[pid] = new

    if por_producto:
        for ln in reg.get("lineas") or []:
            if not isinstance(ln, dict):
                continue
            pid = str(ln.get("producto_id") or "")
            if pid in por_producto:
                ln["coste"] = por_producto[pid]
        reg["coste_total"] = round(sum(por_producto.values()), 2)
    else:
        reg["coste_total"] = round(
            sum(_f(ln.get("coste")) for ln in (reg.get("lineas") or []) if isinstance(ln, dict)),
            2,
        )
    return antes, _f(reg["coste_total"]), frags_ch


def _patch_movimientos(data: dict, reg: dict) -> int:
    """Alinea snapshots de movimientos consumo del registro con fragmentos."""
    rid = reg.get("id")
    if not rid:
        return 0
    # mapa origen_linea_id detNN:fragNN → coste/cant
    mapa: dict[str, tuple[float, float]] = {}
    for di, det in enumerate(reg.get("lineas_detalle") or []):
        if not isinstance(det, dict):
            continue
        frags = det.get("consumos_lote") or []
        if not frags:
            continue
        for fi, frag in enumerate(frags):
            if not isinstance(frag, dict):
                continue
            key = f"det{di:02d}:frag{fi:02d}"
            mapa[key] = (_f(frag.get("cantidad")), _f(frag.get("coste")))
    n = 0
    for m in data.get("movimientos") or []:
        if not isinstance(m, dict):
            continue
        if m.get("origen_id") != rid:
            continue
        if str(m.get("tipo") or "") != "consumo":
            continue
        if str(m.get("direccion") or "") not in ("salida", "SALIDA", ""):
            # aceptar salida tipica
            pass
        ol = str(m.get("origen_linea_id") or "")
        if ol not in mapa:
            continue
        qty, coste = mapa[ol]
        old = _f(m.get("coste_total_snapshot"))
        if abs(old - coste) > 0.005:
            n += 1
        m["coste_total_snapshot"] = round(coste, 2)
        m["coste_unitario_snapshot"] = (
            round(coste / qty, 6) if qty > 0 else 0.0
        )
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", type=Path, required=True)
    ap.add_argument("--desde", type=str, default="2026-08-22")
    ap.add_argument("--hasta", type=str, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--incluir-servicios", action="store_true")
    args = ap.parse_args()
    path = args.path
    if not path.is_file():
        print("No existe", path)
        return 1
    desde = date.fromisoformat(args.desde[:10])
    hasta = date.fromisoformat(args.hasta[:10]) if args.hasta else None

    print("Cargando", path.resolve())
    data = json.loads(path.read_text(encoding="utf-8"))
    lotes = data.get("lotes") or []
    lote_by_id = {str(l["id"]): l for l in lotes if isinstance(l, dict) and l.get("id")}
    por_prod = _build_lotes_por_producto(lotes)

    cambiados = []
    total_frags = 0
    total_movs = 0

    def _en_rango(reg: dict) -> bool:
        if reg.get("anulado"):
            return False
        f = _parse_fecha(reg.get("fecha"))
        if f is None or f < desde:
            return False
        if hasta is not None and f > hasta:
            return False
        return True

    for reg in data.get("desayunos") or []:
        if not isinstance(reg, dict) or not _en_rango(reg):
            continue
        antes, despues, nfrag = _reval_registro(
            reg, lote_by_id=lote_by_id, por_prod=por_prod,
        )
        nmov = _patch_movimientos(data, reg)
        total_frags += nfrag
        total_movs += nmov
        if abs(antes - despues) > 0.005 or nfrag or nmov:
            cambiados.append(
                (str(reg.get("fecha"))[:10], reg.get("id"), antes, despues, nfrag)
            )

    if args.incluir_servicios:
        for reg in data.get("registros_servicio") or []:
            if not isinstance(reg, dict) or not _en_rango(reg):
                continue
            antes, despues, nfrag = _reval_registro(
                reg, lote_by_id=lote_by_id, por_prod=por_prod,
            )
            nmov = _patch_movimientos(data, reg)
            total_frags += nfrag
            total_movs += nmov
            if abs(antes - despues) > 0.005 or nfrag or nmov:
                cambiados.append(
                    (
                        str(reg.get("fecha"))[:10],
                        reg.get("id"),
                        antes,
                        despues,
                        nfrag,
                    )
                )

    print(f"Registros tocados: {len(cambiados)}  frags~={total_frags}  movs={total_movs}")
    for f, i, a, d, nf in cambiados[:40]:
        print(f"  {f} {i}: {a:.2f} -> {d:.2f} (frags_delta~{nf})")
    if len(cambiados) > 40:
        print(f"  ... +{len(cambiados) - 40} mas")

    if args.dry_run:
        print("DRY-RUN: no se escribe.")
        return 0

    bak = path.with_suffix(
        path.suffix + f".bak_reval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    shutil.copy2(path, bak)
    print("Backup:", bak)

    meta = data.get("meta")
    if isinstance(meta, dict) and "revision" in meta:
        try:
            meta["revision"] = int(meta["revision"]) + 1
        except (TypeError, ValueError):
            pass

    tmp = path.with_suffix(".tmp_reval.json")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    print("Escrito:", path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
