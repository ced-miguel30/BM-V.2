"""Anulación soft de registros de merma (Fase 11B).

Reposición al lote_id histórico de cada línea. Sin inventar lotes ni FIFO.
No toca registros de servicio, compras ni ajustes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.core.models import Actividad, AppData, RegistroMerma
from app.core.repositories.data_repository import DataRepository
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)
from app.core.storage.session_store import get_data, persist_data


@dataclass
class ResultadoPuedeAnularMerma:
    ok: bool
    motivos_bloqueo: list[str] = field(default_factory=list)


@dataclass
class PreviewLineaAnulacionMerma:
    producto_id: str
    nombre: str
    lote_id: str
    cantidad_consumida: float
    cantidad_restante_actual: float
    cantidad_a_devolver: float
    cantidad_resultante: float
    unidad: str


@dataclass
class PreviewAnulacionMerma:
    registro_id: str
    estado_actual: str
    lineas: list[PreviewLineaAnulacionMerma] = field(default_factory=list)
    bloqueado: bool = False
    motivos_bloqueo: list[str] = field(default_factory=list)


@dataclass
class ResultadoAnulacionMerma:
    ok: bool
    mensaje: str


def merma_esta_anulada(registro: RegistroMerma | None) -> bool:
    return bool(registro is not None and getattr(registro, "anulado", False))


def _next_id(prefix: str, ids: list[str]) -> str:
    numeros = []
    for item_id in ids:
        sufijo = item_id[len(prefix):]
        if item_id.startswith(prefix) and sufijo.isdigit():
            numeros.append(int(sufijo))
    return f"{prefix}{(max(numeros, default=0) + 1):02d}"


def _nombre_usuario(data: AppData) -> str:
    for u in data.usuarios:
        if u.id == data.usuario_actual_id:
            return u.nombre
    return data.usuarios[0].nombre if data.usuarios else "Usuario"


def _registrar_actividad(data: AppData, accion: str, detalle: str) -> None:
    actividad = Actividad(
        _next_id("act", [a.id for a in data.actividades]),
        datetime.now(),
        _nombre_usuario(data),
        accion,
        detalle,
    )
    data.actividades.insert(0, actividad)


def _buscar_merma(data: AppData, registro_id: str) -> RegistroMerma | None:
    return next((m for m in data.mermas if m.id == registro_id), None)


def _motivos_bloqueo(data: AppData, registro: RegistroMerma) -> list[str]:
    if merma_esta_anulada(registro):
        return ["Registro de merma ya anulado."]

    if not registro.lineas:
        return ["La merma no tiene líneas que reponer."]

    lotes = {l.id: l for l in data.lotes}
    motivos: list[str] = []
    for i, ln in enumerate(registro.lineas, start=1):
        if ln.cantidad <= 0:
            motivos.append(f"Línea {i}: cantidad no positiva.")
            continue
        if not ln.lote_id:
            motivos.append(
                f"Línea {i} (producto {ln.producto_id}): sin lote_id — "
                "trazabilidad insuficiente; anulación bloqueada."
            )
            continue
        lote = lotes.get(ln.lote_id)
        if lote is None:
            motivos.append(f"Línea {i}: lote inexistente {ln.lote_id}.")
            continue
        if lote.producto_id != ln.producto_id:
            motivos.append(
                f"Línea {i}: lote {ln.lote_id} es producto {lote.producto_id}, "
                f"no {ln.producto_id}."
            )

    vistos: set[str] = set()
    unicos: list[str] = []
    for m in motivos:
        if m not in vistos:
            vistos.add(m)
            unicos.append(m)
    return unicos


def puede_anular_merma(data: AppData, registro: RegistroMerma | None) -> ResultadoPuedeAnularMerma:
    if registro is None:
        return ResultadoPuedeAnularMerma(False, ["Registro de merma no encontrado."])
    motivos = _motivos_bloqueo(data, registro)
    return ResultadoPuedeAnularMerma(ok=not motivos, motivos_bloqueo=motivos)


def _agregar_devoluciones(registro: RegistroMerma) -> dict[str, float]:
    por_lote: dict[str, float] = {}
    for ln in registro.lineas:
        if not ln.lote_id or ln.cantidad <= 0:
            continue
        por_lote[ln.lote_id] = round(por_lote.get(ln.lote_id, 0.0) + ln.cantidad, 4)
    return por_lote


def previsualizar_anulacion_merma(
    data: AppData,
    registro: RegistroMerma | None,
) -> PreviewAnulacionMerma:
    puede = puede_anular_merma(data, registro)
    repo = DataRepository(data)
    lotes = {l.id: l for l in data.lotes}
    por_lote = _agregar_devoluciones(registro) if registro else {}

    lineas_prev: list[PreviewLineaAnulacionMerma] = []
    for lote_id, qty in sorted(por_lote.items()):
        lote = lotes.get(lote_id)
        producto_id = lote.producto_id if lote else ""
        if not producto_id and registro:
            for ln in registro.lineas:
                if ln.lote_id == lote_id:
                    producto_id = ln.producto_id
                    break
        producto = repo.get_producto(producto_id) if producto_id else None
        nombre = ""
        unidad = ""
        if registro:
            for ln in registro.lineas:
                if ln.lote_id == lote_id:
                    nombre = ln.producto_nombre_snapshot or ""
                    unidad = ln.unidad_snapshot or ""
                    break
        if producto:
            nombre = nombre or producto.nombre
            unidad = unidad or producto.unidad.value
        restante = float(lote.cantidad_restante) if lote else 0.0
        lineas_prev.append(PreviewLineaAnulacionMerma(
            producto_id=producto_id,
            nombre=nombre or producto_id or "—",
            lote_id=lote_id,
            cantidad_consumida=qty,
            cantidad_restante_actual=restante,
            cantidad_a_devolver=qty,
            cantidad_resultante=round(restante + qty, 4),
            unidad=unidad,
        ))

    estado = "Anulado" if merma_esta_anulada(registro) else "Activo"
    return PreviewAnulacionMerma(
        registro_id=registro.id if registro else "",
        estado_actual=estado,
        lineas=lineas_prev,
        bloqueado=not puede.ok,
        motivos_bloqueo=puede.motivos_bloqueo,
    )


def anular_merma(
    data: AppData | None,
    registro_id: str,
    motivo: str,
    referencia: str = "",
) -> ResultadoAnulacionMerma:
    data = data or get_data()
    motivo_limpio = (motivo or "").strip()
    if not motivo_limpio:
        return ResultadoAnulacionMerma(False, "El motivo de anulación es obligatorio.")

    registro = _buscar_merma(data, registro_id)
    if registro is None:
        return ResultadoAnulacionMerma(False, f"Merma «{registro_id}» no encontrada.")

    if merma_esta_anulada(registro):
        return ResultadoAnulacionMerma(False, "Registro de merma ya anulado.")

    puede = puede_anular_merma(data, registro)
    if not puede.ok:
        return ResultadoAnulacionMerma(
            False,
            "No se puede anular: " + " ".join(puede.motivos_bloqueo),
        )

    snap_lotes = snapshot_cantidades_restantes(data)
    snap_anulado = (
        registro.anulado,
        registro.fecha_anulacion,
        registro.hora_anulacion,
        registro.motivo_anulacion,
        registro.referencia_anulacion,
        registro.anulado_por,
    )
    n_actividades = len(data.actividades)
    por_lote = _agregar_devoluciones(registro)
    lotes = {l.id: l for l in data.lotes}

    try:
        for lote_id, qty in por_lote.items():
            lote = lotes.get(lote_id)
            if lote is None:
                raise ValueError(f"Lote desapareció durante la anulación: {lote_id}.")
            lote.cantidad_restante = round(lote.cantidad_restante + qty, 4)

        ahora = datetime.now()
        registro.anulado = True
        registro.fecha_anulacion = ahora.date()
        registro.hora_anulacion = ahora.time().replace(microsecond=0)
        registro.motivo_anulacion = motivo_limpio
        registro.referencia_anulacion = (referencia or "").strip()
        registro.anulado_por = _nombre_usuario(data)

        _registrar_actividad(
            data,
            "Anulación merma",
            (
                f"Anulada merma {registro_id} — motivo: {motivo_limpio}"
                + (f" — ref: {referencia}" if referencia else "")
            ),
        )
        persist_data(data)
    except Exception as exc:
        restaurar_cantidades_restantes(data, snap_lotes)
        (
            registro.anulado,
            registro.fecha_anulacion,
            registro.hora_anulacion,
            registro.motivo_anulacion,
            registro.referencia_anulacion,
            registro.anulado_por,
        ) = snap_anulado
        del data.actividades[: max(0, len(data.actividades) - n_actividades)]
        return ResultadoAnulacionMerma(
            False, f"Anulación fallida; estado restaurado. ({exc})",
        )

    from app.core.services.alert_service import sincronizar_alertas
    sincronizar_alertas()

    return ResultadoAnulacionMerma(
        True,
        f"Merma {registro_id} anulada. Stock repuesto en {len(por_lote)} lote(s).",
    )
