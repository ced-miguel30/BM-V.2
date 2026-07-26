"""Ajustes de inventario — extensión mínima (Fase 10).

Solo muta `lote.cantidad_restante`. No altera compras históricas
(`precio_total`, `cantidad` original, fechas, proveedor).
Atomicidad: snapshot → aplicar → persistir; fallo restaura.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from app.core.models import (
    Actividad,
    AppData,
    LineaAjuste,
    LoteStock,
    MotivoAjuste,
    RegistroAjuste,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services.formatting import formato_fecha
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)
from app.core.storage.session_store import get_data, persist_data

MOTIVOS_AJUSTE = [m.value for m in MotivoAjuste]


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


@dataclass
class PreviewLineaAjuste:
    lote_id: str
    producto_id: str
    nombre: str
    unidad: str
    cantidad_antes: float
    cantidad_despues: float
    delta: float
    motivo: str
    comentario: str | None
    # Campos de compra (solo lectura en preview; no se tocan).
    cantidad_compra: float
    precio_total: float
    fecha_compra_txt: str


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


def _get_lote(data: AppData, lote_id: str) -> LoteStock | None:
    return next((l for l in data.lotes if l.id == lote_id), None)


def lotes_ajustables(producto_id: str | None = None) -> list[dict]:
    """Lotes existentes para selector de ajuste (incluye restante 0)."""
    data = get_data()
    repo = DataRepository(data)
    out: list[dict] = []
    for lote in sorted(
        data.lotes,
        key=lambda l: (l.fecha_compra or date.min, l.id),
        reverse=True,
    ):
        if producto_id and lote.producto_id != producto_id:
            continue
        producto = repo.get_producto(lote.producto_id)
        if not producto:
            continue
        out.append({
            "id": lote.id,
            "producto_id": lote.producto_id,
            "label": (
                f"{producto.nombre} · {lote.id} · "
                f"restante {lote.cantidad_restante:g} {producto.unidad.value} · "
                f"compra {formato_fecha(lote.fecha_compra)}"
            ),
            "restante": lote.cantidad_restante,
            "unidad": producto.unidad.value,
            "nombre": producto.nombre,
        })
    return out


def previsualizar_ajuste(
    lote_id: str,
    cantidad_despues: float,
    motivo: str,
    comentario: str | None = None,
) -> tuple[PreviewLineaAjuste | None, str | None]:
    """Devuelve preview o (None, error). No muta datos."""
    data = get_data()
    repo = DataRepository(data)
    lote = _get_lote(data, lote_id)
    if not lote:
        return None, "Lote no encontrado."
    producto = repo.get_producto(lote.producto_id)
    if not producto:
        return None, "El producto del lote ya no existe en el catálogo."
    try:
        nueva = float(cantidad_despues)
    except (TypeError, ValueError):
        return None, "Indique una cantidad válida."
    if nueva < 0:
        return None, "La cantidad resultante no puede ser negativa."
    if motivo not in MOTIVOS_AJUSTE:
        return None, "Seleccione un motivo de ajuste válido."
    antes = round(float(lote.cantidad_restante), 4)
    despues = round(nueva, 4)
    if abs(despues - antes) < 1e-9:
        return None, "La cantidad nueva es igual a la actual; no hay ajuste."
    comentario_limpio = (comentario or "").strip() or None
    preview = PreviewLineaAjuste(
        lote_id=lote.id,
        producto_id=lote.producto_id,
        nombre=producto.nombre,
        unidad=producto.unidad.value,
        cantidad_antes=antes,
        cantidad_despues=despues,
        delta=round(despues - antes, 4),
        motivo=motivo,
        comentario=comentario_limpio,
        cantidad_compra=lote.cantidad,
        precio_total=lote.precio_total,
        fecha_compra_txt=formato_fecha(lote.fecha_compra),
    )
    return preview, None


def aplicar_ajuste(
    fecha: date,
    lote_id: str,
    cantidad_despues: float,
    motivo: str,
    comentario: str | None = None,
) -> ResultadoOperacion:
    """Aplica un ajuste de una línea con atomicidad (todo o nada)."""
    if fecha > date.today():
        return ResultadoOperacion(False, "No puede registrar ajustes en fechas futuras.")

    preview, error = previsualizar_ajuste(lote_id, cantidad_despues, motivo, comentario)
    if error or preview is None:
        return ResultadoOperacion(False, error or "No se pudo preparar el ajuste.")

    data = get_data()
    lote = _get_lote(data, lote_id)
    if not lote:
        return ResultadoOperacion(False, "Lote no encontrado.")

    # Guardar campos de compra para comprobar que no se tocan.
    compra_snap = (lote.cantidad, lote.precio_total, lote.fecha_compra, lote.marca_proveedor)

    linea = LineaAjuste(
        producto_id=preview.producto_id,
        lote_id=preview.lote_id,
        cantidad_antes=preview.cantidad_antes,
        cantidad_despues=preview.cantidad_despues,
        motivo=MotivoAjuste(preview.motivo),
        comentario=preview.comentario,
        producto_nombre_snapshot=preview.nombre,
        unidad_snapshot=preview.unidad,
    )

    snap = snapshot_cantidades_restantes(data)
    n_ajustes = len(data.ajustes)
    n_actividades = len(data.actividades)
    try:
        lote.cantidad_restante = preview.cantidad_despues
        if (
            lote.cantidad,
            lote.precio_total,
            lote.fecha_compra,
            lote.marca_proveedor,
        ) != compra_snap:
            raise RuntimeError("Intento de alterar datos de compra; abortado.")

        registro = RegistroAjuste(
            _next_id("aj", [a.id for a in data.ajustes]),
            fecha,
            [linea],
            _nombre_usuario(data),
            hora=datetime.now().time(),
        )
        data.ajustes.append(registro)
        signo = "+" if linea.delta >= 0 else ""
        _registrar_actividad(
            data,
            "Ajuste inventario",
            (
                f"{preview.nombre} lote {lote_id}: "
                f"{preview.cantidad_antes:g} → {preview.cantidad_despues:g} "
                f"{preview.unidad} ({signo}{linea.delta:g}) — {preview.motivo}"
            ),
        )
        persist_data(data)
    except Exception:
        restaurar_cantidades_restantes(data, snap)
        del data.ajustes[n_ajustes:]
        del data.actividades[: max(0, len(data.actividades) - n_actividades)]
        raise

    from app.core.services.alert_service import sincronizar_alertas
    sincronizar_alertas()

    return ResultadoOperacion(
        True,
        (
            f"Ajuste registrado: «{preview.nombre}» "
            f"{preview.cantidad_antes:g} → {preview.cantidad_despues:g} {preview.unidad}."
        ),
    )


def historial_ordenado() -> list[RegistroAjuste]:
    data = get_data()
    return sorted(
        data.ajustes,
        key=lambda a: (a.fecha, a.hora or time.min),
        reverse=True,
    )
