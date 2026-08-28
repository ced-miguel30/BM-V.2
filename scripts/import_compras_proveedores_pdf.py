"""Importa proveedores y costes unitarios desde «Compras prov.pdf».

Lee el informe Dynamics (últimos 4 meses), crea proveedores que falten,
calcula coste unitario = importe / cantidad facturada y actualiza lotes
y consumos históricos en BM.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\import_compras_proveedores_pdf.py --dry-run
  .\\.venv\\Scripts\\python.exe scripts\\import_compras_proveedores_pdf.py
  .\\.venv\\Scripts\\python.exe scripts\\import_compras_proveedores_pdf.py --pdf "docs/añadidos manual/Compras prov.pdf"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pypdf

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.application.id_generator import next_id
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.models import Actividad, Proveedor, RelacionProductoProveedor
from app.core.services.money import money_round, normalizar_codigo_funcional
from app.core.services.noray_lineas_import_service import _match_producto
from app.core.services.proveedor_service import snapshot_proveedor
from app.core.services.revalorizacion_primer_precio_service import (
    revalorizar_producto_primer_precio,
)
from app.core.services.text_search import normalizar_texto

PDF_DEFAULT = ROOT / "docs" / "añadidos manual" / "Compras prov.pdf"
HOTEL_DEFAULT = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
REPORT_DEFAULT = ROOT / "docs" / "añadidos manual" / "_import_compras_prov_report.json"
TAG = "[import-compras-prov-pdf]"
_UNIDADES = frozenset({"UD", "KG", "LT", "GR", "L", "G", "UN", "UNIDAD"})
_SKIP = (
    "importes en",
    "pag.",
    "compras prov",
    "promociones calero",
    "periodo:",
    "dynamicstoc",
    "viernes,",
    "n producto",
    "descripcion",
    "cantidad",
    "unidad",
    "importe",
    "n telefono",
    "movimiento valor",
)


@dataclass
class LineaCompra:
    codigo: str
    descripcion: str
    cantidad: float
    unidad: str
    importe: float
    proveedor_codigo: str
    proveedor_nombre: str


@dataclass
class ResumenProducto:
    codigo: str
    descripcion: str
    cantidad_total: float = 0.0
    importe_total: float = 0.0
    unidad: str = "UD"
    proveedor_principal: str = ""
    lineas: list[LineaCompra] = field(default_factory=list)

    @property
    def coste_unitario(self) -> float:
        if self.cantidad_total <= 0:
            return 0.0
        return round(self.importe_total / self.cantidad_total, 6)


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="import-compras",
            actor_label="Import compras PDF",
            role=ROL_DIRECCION,
            session_id="import-compras-session",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="import",
        )
    )


def _boot(hotel: Path) -> None:
    reset_container()
    configure_for_flet(data_path=str(hotel))
    _auth()


def _backup(hotel: Path) -> Path:
    backup_dir = hotel.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"datos_hotel_pre_compras_prov_{stamp}.json"
    shutil.copy2(hotel, dest)
    return dest


def _es_skip(line: str) -> bool:
    n = normalizar_texto(line)
    if not n:
        return True
    return any(s in n for s in _SKIP)


def _parse_numero_es(raw: str) -> float:
    s = (raw or "").strip().replace(" ", "")
    if not s:
        return 0.0
    if "," in s:
        if "." in s and s.index(".") < s.index(","):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
    elif s.count(".") == 1:
        left, right = s.split(".")
        if len(right) == 3 and left.isdigit() and right.isdigit():
            s = left + right
    return float(s)


def _es_unidad(line: str) -> bool:
    return (line or "").strip().upper() in _UNIDADES


def _es_codigo_producto(line: str) -> bool:
    return bool(re.fullmatch(r"C\d+", (line or "").strip()))


def _es_codigo_proveedor(line: str) -> bool:
    return bool(re.fullmatch(r"PR\d+", (line or "").strip()))


def parsear_pdf(path: Path) -> tuple[dict[str, str], list[LineaCompra]]:
    reader = pypdf.PdfReader(str(path))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip() and not _es_skip(ln.strip())]

    proveedores: dict[str, str] = {}
    compras: list[LineaCompra] = []
    prov_codigo = ""
    prov_nombre = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if _es_codigo_proveedor(line):
            prov_codigo = line.strip()
            i += 1
            if i >= len(lines):
                break
            prov_nombre = lines[i].strip()
            proveedores[prov_codigo] = prov_nombre
            i += 1
            if i < len(lines) and (
                "telefono" in normalizar_texto(lines[i])
                or re.fullmatch(r"\d{6,12}", lines[i].replace(" ", ""))
            ):
                i += 1
            continue

        if not _es_codigo_producto(line):
            i += 1
            continue

        codigo = line.strip()
        i += 1
        desc_parts: list[str] = []
        while i < len(lines):
            if _es_codigo_producto(lines[i]) or _es_codigo_proveedor(lines[i]):
                break
            if _es_unidad(lines[i]) and i > 0 and re.match(r"^[\d.,]+$", lines[i - 1]):
                break
            if re.match(r"^[\d.,]+$", lines[i]) and i + 1 < len(lines) and _es_unidad(lines[i + 1]):
                break
            desc_parts.append(lines[i])
            i += 1
        if i + 3 > len(lines):
            break
        if not re.match(r"^[\d.,]+$", lines[i]):
            continue
        cantidad = _parse_numero_es(lines[i])
        i += 1
        unidad = lines[i].strip().upper()
        if not _es_unidad(unidad):
            continue
        i += 1
        importe = _parse_numero_es(lines[i])
        i += 1
        if i < len(lines) and re.match(r"^[\d.,]+$", lines[i]):
            i += 1  # descuento línea

        if cantidad <= 0 or importe <= 0:
            continue
        compras.append(
            LineaCompra(
                codigo=codigo,
                descripcion=" ".join(desc_parts).strip(),
                cantidad=cantidad,
                unidad=unidad,
                importe=importe,
                proveedor_codigo=prov_codigo,
                proveedor_nombre=prov_nombre,
            )
        )
    return proveedores, compras


def _agrupar(compras: list[LineaCompra]) -> dict[str, ResumenProducto]:
    por_codigo: dict[str, ResumenProducto] = {}
    vol_prov: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for ln in compras:
        key = normalizar_codigo_funcional(ln.codigo) or ln.codigo
        agg = por_codigo.get(key)
        if agg is None:
            agg = ResumenProducto(codigo=key, descripcion=ln.descripcion, unidad=ln.unidad)
            por_codigo[key] = agg
        agg.cantidad_total += ln.cantidad
        agg.importe_total += ln.importe
        agg.lineas.append(ln)
        vol_prov[key][ln.proveedor_codigo] += ln.importe
    for key, agg in por_codigo.items():
        if vol_prov[key]:
            pr = max(vol_prov[key], key=vol_prov[key].get)
            agg.proveedor_principal = pr
    return por_codigo


def _indice_productos(data):
    by_codigo: dict[str, str] = {}
    for p in data.productos:
        if not getattr(p, "activo", True):
            continue
        cod = normalizar_codigo_funcional(getattr(p, "codigo", None))
        if cod:
            by_codigo[cod] = p.id
    return by_codigo


def _resolver_producto(data, agg: ResumenProducto) -> tuple[str | None, str, list[str]]:
    avisos: list[str] = []
    by_codigo = _indice_productos(data)
    pid = by_codigo.get(agg.codigo)
    if pid:
        return pid, "codigo", avisos
    pid, nombre, _pcod, estado, avisos = _match_producto(data, agg.codigo, agg.descripcion)
    if pid:
        return pid, estado, avisos
    return None, "sin_match", avisos


def _proveedor_por_codigo(data, codigo_pr: str) -> Proveedor | None:
    key = normalizar_codigo_funcional(codigo_pr)
    for p in data.proveedores or []:
        if normalizar_codigo_funcional(getattr(p, "codigo", None)) == key:
            return p
    return None


def _proveedor_por_nombre(data, nombre: str) -> Proveedor | None:
    key = normalizar_texto(nombre)
    for p in data.proveedores or []:
        if normalizar_texto(p.nombre_fiscal) == key:
            return p
    return None


def _crear_proveedor(data, codigo_pr: str, nombre: str) -> Proveedor:
    existente = _proveedor_por_codigo(data, codigo_pr) or _proveedor_por_nombre(data, nombre)
    if existente:
        return existente
    codigo = normalizar_codigo_funcional(codigo_pr) or codigo_pr
    prov = Proveedor(
        id=next_id("prv", [p.id for p in data.proveedores or []]),
        nombre_fiscal=nombre.strip(),
        codigo=codigo,
        activo=True,
        observaciones="Importado desde Compras prov.pdf",
    )
    data.proveedores.append(prov)
    return prov


def _actualizar_lotes_todos(data, producto_id: str, unit: float) -> int:
    n = 0
    for lote in data.lotes:
        if lote.producto_id != producto_id or getattr(lote, "anulado", False):
            continue
        qty = float(getattr(lote, "cantidad", 0) or 0)
        if qty <= 0:
            continue
        lote.precio_total = float(money_round(Decimal(str(qty)) * Decimal(str(unit))))
        n += 1
    return n


def _vincular_o_actualizar(
    data,
    *,
    producto_id: str,
    proveedor_id: str,
    codigo_proveedor: str,
    precio: float,
    preferente: bool,
) -> str:
    rels = data.relaciones_producto_proveedor or []
    existente = next(
        (
            r
            for r in rels
            if r.producto_id == producto_id and r.proveedor_id == proveedor_id and r.activo
        ),
        None,
    )
    prov = next(p for p in data.proveedores if p.id == proveedor_id)
    snap_nombre, snap_nif = snapshot_proveedor(prov)
    precio_d = Decimal(str(round(precio, 6)))
    if existente:
        existente.ultimo_precio_unitario_compra = precio_d
        existente.codigo_proveedor = codigo_proveedor
        if preferente:
            for r in rels:
                if r.producto_id == producto_id and r.activo:
                    r.preferente = r.id == existente.id
        return "actualizado"
    if preferente:
        for r in rels:
            if r.producto_id == producto_id and r.activo:
                r.preferente = False
    rel = RelacionProductoProveedor(
        id=next_id("ppv", [r.id for r in rels]),
        producto_id=producto_id,
        proveedor_id=proveedor_id,
        codigo_proveedor=codigo_proveedor,
        preferente=preferente,
        proveedor_nombre_snapshot=snap_nombre,
        nif_cif_snapshot=snap_nif,
        activo=True,
        ultimo_precio_unitario_compra=precio_d,
    )
    data.relaciones_producto_proveedor.append(rel)
    return "creado"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=PDF_DEFAULT)
    ap.add_argument("--path", type=Path, default=HOTEL_DEFAULT, help="datos_hotel.json")
    ap.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.pdf.is_file():
        print(f"No existe PDF: {args.pdf}")
        return 1
    if not args.path.is_file():
        print(f"No existe datos: {args.path}")
        return 1

    proveedores_pdf, compras = parsear_pdf(args.pdf)
    agregados = _agrupar(compras)
    print(f"PDF: {len(proveedores_pdf)} proveedores, {len(compras)} líneas, {len(agregados)} productos únicos")

    _boot(args.path)
    store = get_container().app_data_store
    data = store.get()

    reporte: dict = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "pdf": str(args.pdf),
        "dry_run": args.dry_run,
        "proveedores_pdf": {k: v for k, v in proveedores_pdf.items()},
        "stats": {},
        "actualizados": [],
        "sin_match": [],
        "omitidos": [],
    }

    prv_creados = 0
    for cod_pr, nombre in proveedores_pdf.items():
        if _proveedor_por_codigo(data, cod_pr) or _proveedor_por_nombre(data, nombre):
            continue
        if args.dry_run:
            prv_creados += 1
        else:
            _crear_proveedor(data, cod_pr, nombre)
            prv_creados += 1

    actualizados = 0
    sin_match = 0
    rel_creadas = rel_act = 0
    lotes_tot = 0

    for codigo, agg in sorted(agregados.items(), key=lambda x: x[0]):
        if agg.coste_unitario <= 0:
            reporte["omitidos"].append({"codigo": codigo, "motivo": "coste cero"})
            continue
        pid, modo, avisos = _resolver_producto(data, agg)
        if not pid:
            sin_match += 1
            reporte["sin_match"].append(
                {
                    "codigo": codigo,
                    "descripcion": agg.descripcion,
                    "coste_calc": agg.coste_unitario,
                    "unidad": agg.unidad,
                    "avisos": avisos,
                }
            )
            continue

        prod = next(p for p in data.productos if p.id == pid)
        pr_cod = agg.proveedor_principal
        pr_nombre = proveedores_pdf.get(pr_cod, "")
        entry = {
            "codigo": codigo,
            "producto_id": pid,
            "nombre_bm": prod.nombre,
            "match": modo,
            "cantidad": round(agg.cantidad_total, 4),
            "importe": round(agg.importe_total, 2),
            "unidad_pdf": agg.unidad,
            "unidad_bm": prod.unidad.value if hasattr(prod.unidad, "value") else str(prod.unidad),
            "coste_unitario": agg.coste_unitario,
            "proveedor": pr_nombre,
            "avisos": avisos,
        }

        if args.dry_run:
            reporte["actualizados"].append(entry)
            actualizados += 1
            continue

        revalorizar_producto_primer_precio(
            data,
            pid,
            agg.coste_unitario,
            doc_id="import-compras-prov-pdf",
            actor="import-compras",
        )
        lotes_n = _actualizar_lotes_todos(data, pid, agg.coste_unitario)
        lotes_tot += lotes_n

        if pr_cod and pr_nombre:
            prov = _crear_proveedor(data, pr_cod, pr_nombre)
            accion = _vincular_o_actualizar(
                data,
                producto_id=pid,
                proveedor_id=prov.id,
                codigo_proveedor=codigo,
                precio=agg.coste_unitario,
                preferente=True,
            )
            if accion == "creado":
                rel_creadas += 1
            else:
                rel_act += 1
            entry["proveedor_id"] = prov.id
            entry["relacion"] = accion
        entry["lotes"] = lotes_n
        reporte["actualizados"].append(entry)
        actualizados += 1

    reporte["stats"] = {
        "proveedores_nuevos": prv_creados,
        "productos_actualizados": actualizados,
        "sin_match": sin_match,
        "relaciones_creadas": rel_creadas,
        "relaciones_actualizadas": rel_act,
        "lotes_revalorizados": lotes_tot,
    }

    if not args.dry_run:
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                datetime.now(),
                "import-compras",
                "Import compras proveedores PDF",
                (
                    f"{TAG} {actualizados} productos, {prv_creados} proveedores nuevos, "
                    f"{rel_creadas} vínculos creados, {lotes_tot} lotes"
                ),
            ),
        )
        from app.core.services.desayuno_service import _ctx

        bak = _backup(args.path)
        print(f"Backup: {bak}")
        _ctx().uow.commit(data)
        print(f"Persistido: {args.path}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Informe: {args.report}")
    print(
        f"Resumen: +{prv_creados} proveedores | {actualizados} costes actualizados | "
        f"{sin_match} sin match | dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
