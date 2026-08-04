"""Migración histórica documental explícita (A8 / Plan v3 §6).

Nunca escribe el demo canónico. Opera sobre rutas/copias que aporte el caller.
Idempotente: segunda ejecución sin cambios nuevos.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.core.application.id_generator import next_id
from app.core.models import AppData, EstadoDocumento, TipoDocumento
from app.core.models.conciliacion import ConciliacionLineaDocumento, EstadoConciliacion
from app.core.models.documento import LineaDocumento
from app.core.services.persistencia_appdata import (
    read_appdata_json,
    transactional_update_appdata,
)
from app.data.serializers import appdata_to_dict


@dataclass
class InformeMigracion:
    confirmacion_ids_asignados: list[tuple[str, str]] = field(default_factory=list)
    conciliaciones_creadas: list[str] = field(default_factory=list)
    pendientes_revision: list[dict] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    sin_cambios: bool = False
    dry_run: bool = False
    backup_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "confirmacion_ids_asignados": [
                {"documento_id": a, "confirmacion_id": b}
                for a, b in self.confirmacion_ids_asignados
            ],
            "conciliaciones_creadas": list(self.conciliaciones_creadas),
            "pendientes_revision": list(self.pendientes_revision),
            "errores": list(self.errores),
            "sin_cambios": self.sin_cambios,
            "dry_run": self.dry_run,
            "backup_path": self.backup_path,
        }


def _estado(doc) -> str:
    e = doc.estado
    return e.value if hasattr(e, "value") else str(e)


def _tipo(doc) -> str:
    t = doc.tipo
    return t.value if hasattr(t, "value") else str(t)


def _qty_inv(ln: LineaDocumento) -> Decimal | None:
    if ln.cantidad_inventario is not None:
        return Decimal(str(ln.cantidad_inventario))
    if ln.cantidad_compra is not None and ln.factor_conversion is not None:
        return Decimal(str(ln.cantidad_compra)) * Decimal(str(ln.factor_conversion))
    # Legacy: cantidad ambigua — no inventar como inventario seguro
    return None


def migrar_appdata(data: AppData) -> InformeMigracion:
    """Aplica migración sobre una copia AppData en memoria. No persiste."""
    informe = InformeMigracion()
    if not hasattr(data, "conciliaciones_documento") or data.conciliaciones_documento is None:
        data.conciliaciones_documento = []

    existentes = {
        getattr(d, "confirmacion_id", None)
        for d in data.documentos
        if getattr(d, "confirmacion_id", None)
    }

    # 1) confirmacion_id para documentos no borrador sin token
    for doc in data.documentos:
        est = _estado(doc)
        if est == EstadoDocumento.BORRADOR.value:
            continue
        if getattr(doc, "confirmacion_id", None):
            continue
        while True:
            nuevo = str(uuid.uuid4())
            if nuevo not in existentes:
                break
        doc.confirmacion_id = nuevo
        existentes.add(nuevo)
        informe.confirmacion_ids_asignados.append((doc.id, nuevo))

    # 2) Enlaces legacy → conciliación solo si inequívoco
    lineas_por_id: dict[str, tuple] = {}
    for doc in data.documentos:
        for ln in doc.lineas:
            lineas_por_id[ln.id] = (doc, ln)

    for doc in data.documentos:
        if _tipo(doc) != TipoDocumento.FACTURA.value:
            continue
        if _estado(doc) == EstadoDocumento.BORRADOR.value:
            continue
        for ln in doc.lineas:
            origen = getattr(ln, "linea_origen_id", None)
            if not origen:
                continue
            # Ya marcada pendiente
            if getattr(ln, "legacy_conciliacion_estado", None) == "pendiente_revision":
                continue
            # ¿Ya hay conciliación activa para este par?
            ya = any(
                c.linea_factura_id == ln.id
                and c.linea_albaran_id == origen
                and (
                    (c.estado.value if hasattr(c.estado, "value") else str(c.estado))
                    == EstadoConciliacion.ACTIVA.value
                )
                for c in data.conciliaciones_documento
            )
            if ya:
                continue

            ref = lineas_por_id.get(origen)
            if ref is None:
                ln.legacy_conciliacion_estado = "pendiente_revision"
                informe.pendientes_revision.append(
                    {
                        "linea_factura_id": ln.id,
                        "motivo": "enlace_roto",
                        "linea_origen_id": origen,
                    }
                )
                continue
            doc_alb, ln_alb = ref
            if _tipo(doc_alb) != TipoDocumento.ALBARAN.value:
                ln.legacy_conciliacion_estado = "pendiente_revision"
                informe.pendientes_revision.append(
                    {
                        "linea_factura_id": ln.id,
                        "motivo": "origen_no_albaran",
                        "linea_origen_id": origen,
                    }
                )
                continue
            if _estado(doc_alb) != EstadoDocumento.CONFIRMADO.value:
                ln.legacy_conciliacion_estado = "pendiente_revision"
                informe.pendientes_revision.append(
                    {
                        "linea_factura_id": ln.id,
                        "motivo": "albaran_no_confirmado",
                        "linea_origen_id": origen,
                    }
                )
                continue
            if ln.producto_id != ln_alb.producto_id:
                ln.legacy_conciliacion_estado = "pendiente_revision"
                informe.pendientes_revision.append(
                    {
                        "linea_factura_id": ln.id,
                        "motivo": "producto_distinto",
                        "linea_origen_id": origen,
                    }
                )
                continue

            # Otra factura confirmada enlazando la misma línea origen
            otras = [
                (d, l)
                for d in data.documentos
                for l in d.lineas
                if l.id != ln.id
                and getattr(l, "linea_origen_id", None) == origen
                and _tipo(d) == TipoDocumento.FACTURA.value
                and _estado(d) != EstadoDocumento.BORRADOR.value
            ]
            if otras:
                ln.legacy_conciliacion_estado = "pendiente_revision"
                informe.pendientes_revision.append(
                    {
                        "linea_factura_id": ln.id,
                        "motivo": "multiples_facturas",
                        "linea_origen_id": origen,
                    }
                )
                continue

            qty_f = _qty_inv(ln)
            qty_a = _qty_inv(ln_alb)
            # Legacy float cantidad: solo inequívoco si ambas cantidades float iguales
            if qty_f is None and qty_a is None:
                if float(ln.cantidad) == float(ln_alb.cantidad) and float(ln.cantidad) > 0:
                    qty_a = Decimal(str(ln_alb.cantidad))
                else:
                    ln.legacy_conciliacion_estado = "pendiente_revision"
                    informe.pendientes_revision.append(
                        {
                            "linea_factura_id": ln.id,
                            "motivo": "cantidades_ambiguas",
                            "linea_origen_id": origen,
                        }
                    )
                    continue
            elif qty_f is None or qty_a is None or qty_f != qty_a:
                ln.legacy_conciliacion_estado = "pendiente_revision"
                informe.pendientes_revision.append(
                    {
                        "linea_factura_id": ln.id,
                        "motivo": "cantidades_distintas",
                        "linea_origen_id": origen,
                    }
                )
                continue

            cid = next_id(
                "con",
                [c.id for c in data.conciliaciones_documento],
            )
            conc = ConciliacionLineaDocumento(
                id=cid,
                linea_factura_id=ln.id,
                linea_albaran_id=origen,
                cantidad_conciliada=qty_a,
                fecha=doc.fecha_documento,
                estado=EstadoConciliacion.ACTIVA,
                confirmacion_id=getattr(doc, "confirmacion_id", None),
                creado_en=datetime.now(),
            )
            data.conciliaciones_documento.append(conc)
            informe.conciliaciones_creadas.append(cid)
            # No borrar legacy; solo dejar de marcar pendiente
            if getattr(ln, "legacy_conciliacion_estado", None) == "pendiente_revision":
                ln.legacy_conciliacion_estado = None

    if (
        not informe.confirmacion_ids_asignados
        and not informe.conciliaciones_creadas
        and not informe.pendientes_revision
        and not informe.errores
    ):
        informe.sin_cambios = True
    return informe


def migrar_json_path(
    json_path: Path | str,
    *,
    backup_dir: Path | str | None = None,
    dry_run: bool = False,
    informe_path: Path | str | None = None,
) -> InformeMigracion:
    """Migración atómica de un fichero JSON (copia de trabajo, nunca demo real)."""
    path = Path(json_path).resolve()
    backup_written = None
    if backup_dir is not None and path.exists() and not dry_run:
        bdir = Path(backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_written = bdir / f"{path.name}.bak.{stamp}"
        shutil.copy2(path, backup_written)

    if dry_run:
        data = read_appdata_json(path)
        informe = migrar_appdata(data)
        informe.dry_run = True
        informe.backup_path = str(backup_written) if backup_written else None
        if informe_path:
            Path(informe_path).write_text(
                json.dumps(informe.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return informe

    holder: dict = {"informe": None}

    def _mutate(data: AppData) -> AppData:
        holder["informe"] = migrar_appdata(data)
        return data

    transactional_update_appdata(path, _mutate)
    informe = holder["informe"] or InformeMigracion(sin_cambios=True)
    informe.backup_path = str(backup_written) if backup_written else None
    if informe_path:
        Path(informe_path).write_text(
            json.dumps(informe.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return informe
