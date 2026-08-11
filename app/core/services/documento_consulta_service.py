"""Búsqueda y exportación documental (Fase 13).

Solo lectura + ficheros de exportación. No confirma/anula documentos.
Sin OCR. Sin API.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import Actividad, AppData, ArchivoDocumental, Documento
from app.core.services.text_search import coincide_busqueda
from app.core.storage.session_store import get_data, persist_data
from app.core.storage.instance_paths import get_exports_root


def _exports_documentos_dir() -> Path:
    return get_exports_root(for_write=True) / "documentos"


def __getattr__(name: str):
    if name == "EXPORTS_DIR":
        return _exports_documentos_dir()
    if name == "PROJECT_ROOT":
        from app.core.storage.demo_files import PROJECT_ROOT as _pr

        return _pr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass
class FiltroDocumentos:
    texto: str | None = None
    tipo: str | None = None  # albaran|factura|rectificativa
    estado: str | None = None
    proveedor_id: str | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None


@dataclass
class ResultadoExportacionDocumental:
    ok: bool
    mensaje: str
    ruta: Path | None = None
    nombre_archivo: str | None = None
    filas: int = 0
    contenido: bytes | None = None


def _ctx(ctx: AppContext | None = None) -> AppContext:
    if ctx is not None:
        return ctx
    from app.core.application.actor import actor_desde_appdata
    from app.core.application.clock import SystemClock

    class _Uow:
        def get_data(self) -> AppData:
            return get_data()

        def commit(self, data: AppData | None = None) -> AppData:
            return persist_data(data if data is not None else get_data())

    uow = _Uow()
    return AppContext(
        uow=uow,
        actor=actor_desde_appdata(uow.get_data()),
        clock=SystemClock(),
    )


def _enum_str(v) -> str:
    return v.value if hasattr(v, "value") else str(v or "")


def _texto_documento(doc: Documento) -> str:
    partes = [
        doc.id,
        _enum_str(doc.tipo),
        _enum_str(doc.estado),
        doc.proveedor_nombre_snapshot or "",
        doc.referencia_externa or "",
        doc.nif_cif_snapshot or "",
        doc.notas or "",
        doc.motivo_rectificacion or "",
        doc.documento_rectificado_id or "",
    ]
    for ln in doc.lineas or []:
        partes.append(ln.producto_nombre_snapshot or "")
        partes.append(ln.producto_id or "")
        partes.append(ln.linea_origen_id or "")
    return " ".join(partes)


def buscar_documentos(
    filtro: FiltroDocumentos | None = None,
    *,
    ctx: AppContext | None = None,
    data: AppData | None = None,
) -> list[Documento]:
    """Filtra documentos en memoria. Orden: fecha desc, id desc."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)

    if data is None:
        data = _ctx(ctx).uow.get_data()
    f = filtro or FiltroDocumentos()
    out: list[Documento] = []
    for doc in getattr(data, "documentos", []) or []:
        if f.tipo and _enum_str(doc.tipo) != f.tipo:
            continue
        if f.estado and _enum_str(doc.estado) != f.estado:
            continue
        if f.proveedor_id and (doc.proveedor_id or "") != f.proveedor_id:
            continue
        if f.fecha_desde and doc.fecha_documento < f.fecha_desde:
            continue
        if f.fecha_hasta and doc.fecha_documento > f.fecha_hasta:
            continue
        if f.texto and not coincide_busqueda(_texto_documento(doc), f.texto):
            continue
        out.append(doc)
    return sorted(out, key=lambda d: (d.fecha_documento, d.id), reverse=True)


def buscar_archivos(
    *,
    texto: str | None = None,
    documento_id: str | None = None,
    solo_activos: bool = True,
    ctx: AppContext | None = None,
    data: AppData | None = None,
) -> list[ArchivoDocumental]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)

    if data is None:
        data = _ctx(ctx).uow.get_data()
    out: list[ArchivoDocumental] = []
    for a in getattr(data, "archivos_documentales", []) or []:
        if solo_activos and not getattr(a, "activo", True):
            continue
        if documento_id and (a.documento_id or "") != documento_id:
            continue
        if texto:
            blob = " ".join(
                [
                    a.id,
                    a.nombre_original or "",
                    a.sha256 or "",
                    a.documento_id or "",
                    a.notas or "",
                ]
            )
            if not coincide_busqueda(blob, texto):
                continue
        out.append(a)
    return sorted(out, key=lambda a: a.id, reverse=True)


def documento_a_filas_export(doc: Documento) -> list[dict[str, str]]:
    """Una fila por línea; cabecera sin líneas → una fila vacía de línea."""
    base = {
        "documento_id": doc.id,
        "tipo": _enum_str(doc.tipo),
        "estado": _enum_str(doc.estado),
        "fecha_documento": doc.fecha_documento.isoformat() if doc.fecha_documento else "",
        "proveedor_id": doc.proveedor_id or "",
        "proveedor_nombre": doc.proveedor_nombre_snapshot or "",
        "nif_cif": doc.nif_cif_snapshot or "",
        "referencia_externa": doc.referencia_externa or "",
        "documento_rectificado_id": doc.documento_rectificado_id or "",
        "motivo_rectificacion": doc.motivo_rectificacion or "",
        "notas": doc.notas or "",
        "n_archivos": str(len(doc.archivo_ids or [])),
    }
    if not doc.lineas:
        return [
            {
                **base,
                "linea_id": "",
                "producto_id": "",
                "producto_nombre": "",
                "cantidad": "",
                "precio_total": "",
                "lote_id": "",
                "movimiento_id": "",
                "documento_origen_id": "",
                "linea_origen_id": "",
            }
        ]
    filas = []
    for ln in doc.lineas:
        filas.append(
            {
                **base,
                "linea_id": ln.id,
                "producto_id": ln.producto_id,
                "producto_nombre": ln.producto_nombre_snapshot or "",
                "cantidad": f"{ln.cantidad:g}",
                "precio_total": f"{ln.precio_total:.2f}",
                "lote_id": ln.lote_id or "",
                "movimiento_id": ln.movimiento_id or "",
                "documento_origen_id": ln.documento_origen_id or "",
                "linea_origen_id": ln.linea_origen_id or "",
            }
        )
    return filas


_CSV_FIELDS = [
    "documento_id",
    "tipo",
    "estado",
    "fecha_documento",
    "proveedor_id",
    "proveedor_nombre",
    "nif_cif",
    "referencia_externa",
    "documento_rectificado_id",
    "motivo_rectificacion",
    "notas",
    "n_archivos",
    "linea_id",
    "producto_id",
    "producto_nombre",
    "cantidad",
    "precio_total",
    "lote_id",
    "movimiento_id",
    "documento_origen_id",
    "linea_origen_id",
]


def construir_csv_documentos(documentos: list[Documento]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for doc in documentos:
        for fila in documento_a_filas_export(doc):
            writer.writerow(fila)
    # UTF-8 BOM para Excel en Windows
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def exportar_documentos_csv(
    filtro: FiltroDocumentos | None = None,
    *,
    ctx: AppContext | None = None,
    guardar: bool = True,
    registrar_actividad: bool = True,
) -> ResultadoExportacionDocumental:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoExportacionDocumental(False, denied)

    c = _ctx(ctx)
    data = c.uow.get_data()
    docs = buscar_documentos(filtro, data=data)
    contenido = construir_csv_documentos(docs)
    n_filas = sum(max(len(d.lineas), 1) for d in docs)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre = f"documentos_{stamp}.csv"
    ruta: Path | None = None
    if guardar:
        exports = _exports_documentos_dir()
        exports.mkdir(parents=True, exist_ok=True)
        ruta = exports / nombre
        # No sobrescribir
        if ruta.exists():
            nombre = f"documentos_{stamp}_{datetime.now().strftime('%f')}.csv"
            ruta = exports / nombre
        ruta.write_bytes(contenido)
        if registrar_actividad:
            data.actividades.insert(
                0,
                Actividad(
                    next_id("act", [a.id for a in data.actividades]),
                    datetime.now(),
                    getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
                    "Exportar documentos",
                    f"{nombre}: {len(docs)} documento(s), {n_filas} fila(s)",
                ),
            )
            c.uow.commit(data)
    return ResultadoExportacionDocumental(
        ok=True,
        mensaje=f"Exportados {len(docs)} documento(s) ({n_filas} fila(s)).",
        ruta=ruta,
        nombre_archivo=nombre,
        filas=n_filas,
        contenido=contenido,
    )


def resumen_documento(doc: Documento) -> dict[str, str | int | float]:
    return {
        "id": doc.id,
        "tipo": _enum_str(doc.tipo),
        "estado": _enum_str(doc.estado),
        "fecha": doc.fecha_documento.isoformat() if doc.fecha_documento else "",
        "proveedor": doc.proveedor_nombre_snapshot or "—",
        "referencia": doc.referencia_externa or "—",
        "lineas": len(doc.lineas or []),
        "importe": round(sum(float(ln.precio_total) for ln in doc.lineas or []), 2),
        "archivos": len(doc.archivo_ids or []),
        "rectifica": doc.documento_rectificado_id or "—",
    }
