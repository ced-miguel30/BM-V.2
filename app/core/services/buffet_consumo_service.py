"""Importación y exportación del consumo buffet diario."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import AppData, MotivoMerma, OrigenServicioMerma, TurnoMerma
from app.core.models.buffet import (
    MOTIVO_BUFFET_CONSUMO,
    MOTIVO_BUFFET_EXPIRACION,
    MOTIVO_BUFFET_LIMPIEZA,
    MOTIVO_BUFFET_MERMA,
    MOTIVOS_BUFFET_VALORES,
    TIPO_LINEA_JARRA_ZUMO,
    TIPO_LINEA_RECETA_ESTANDAR,
    TIPO_LINEA_SIMPLE,
    LineaRegistroBuffet,
    RegistroBuffetDiario,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services import desayuno_service as des
from app.core.services import merma_service
from app.core.services.buffet_config_service import (
    config_por_id,
    config_por_label,
    ensure_config_buffet,
    ensure_responsable_import,
)
from app.core.services.excel_bloques import RegistroExportable
from app.core.services.inventory_batch_service import calcular_coste_linea
from app.core.services.text_search import normalizar_texto
from app.core.storage.session_store import get_data, persist_data


CLAVE_PREFIX = "buffet-xlsx"
CLAVE_VER = "v1"


@dataclass
class LineaBuffetEntrada:
    config_id: str | None
    label: str
    seccion: str
    cantidad: float
    motivo: str
    naranjas: float | None = None
    zumo_bote: float | None = None
    notas: str = ""


@dataclass
class ResultadoImportBuffet:
    ok: bool
    mensaje: str
    skipped: bool = False
    dry_run: bool = False
    registro_id: str | None = None


class _CompatSessionUow:
    def get_data(self) -> AppData:
        return get_data()

    def commit(self, data: AppData | None = None) -> AppData:
        return persist_data(data if data is not None else get_data())


def _ctx(ctx: AppContext | None = None) -> AppContext:
    if ctx is not None:
        return ctx
    from app.core.application.actor import actor_desde_appdata
    from app.core.application.clock import SystemClock

    uow = _CompatSessionUow()
    return AppContext(
        uow=uow,
        actor=actor_desde_appdata(uow.get_data()),
        clock=SystemClock(),
    )


def _norm(s: str) -> str:
    return normalizar_texto(s or "")


def _clave(fecha: date) -> str:
    return f"{CLAVE_PREFIX}-{fecha.isoformat()}-{CLAVE_VER}"


def _ya_importado(data: AppData, fecha: date) -> RegistroBuffetDiario | None:
    clave = _clave(fecha)
    return next(
        (
            r
            for r in data.registros_buffet
            if getattr(r, "clave_idempotencia", None) == clave
            and not getattr(r, "anulado", False)
        ),
        None,
    )


def _motivo_merma(motivo_buffet: str) -> str:
    if motivo_buffet == MOTIVO_BUFFET_MERMA:
        return MotivoMerma.MERMA.value
    if motivo_buffet == MOTIVO_BUFFET_EXPIRACION:
        return MotivoMerma.EXPIRACION.value
    if motivo_buffet == MOTIVO_BUFFET_LIMPIEZA:
        return MotivoMerma.OTRO.value
    raise ValueError(f"Motivo no es merma: {motivo_buffet}")


def _parse_motivo(raw: str) -> str:
    key = _norm(raw)
    mapping = {
        "consumo": MOTIVO_BUFFET_CONSUMO,
        "merma": MOTIVO_BUFFET_MERMA,
        "expiracion": MOTIVO_BUFFET_EXPIRACION,
        "expiración": MOTIVO_BUFFET_EXPIRACION,
        "limpieza": MOTIVO_BUFFET_LIMPIEZA,
    }
    val = mapping.get(key)
    if val is None:
        raise ValueError(f"Motivo inválido «{raw}» (use Consumo/Merma/Expiración/Limpieza)")
    return val


def _resolver_config(data: AppData, entrada: LineaBuffetEntrada):
    if entrada.config_id:
        cfg = config_por_id(data, entrada.config_id)
        if cfg:
            return cfg
    cfg = config_por_label(data, entrada.label)
    if cfg:
        return cfg
    raise ValueError(f"Concepto buffet no configurado: «{entrada.label}»")


def _coste_linea(data: AppData, producto_id: str, cantidad: float) -> float:
    if not producto_id or cantidad <= 0:
        return 0.0
    return round(calcular_coste_linea(data, producto_id, cantidad), 2)


def _coste_receta(data: AppData, receta_id: str, porciones: float) -> float:
    rec = next((r for r in data.recetas if r.id == receta_id), None)
    if rec is None or porciones <= 0:
        return 0.0
    total = 0.0
    for ing in rec.ingredientes or []:
        total += calcular_coste_linea(
            data, ing.producto_id, float(ing.cantidad or 0) * porciones
        )
    return round(total, 2)


def _anadir_consumo(
    data: AppData,
    cfg,
    entrada: LineaBuffetEntrada,
) -> float:
    coste = 0.0
    qty = float(entrada.cantidad)
    if qty <= 0:
        return 0.0

    if cfg.tipo_linea == TIPO_LINEA_RECETA_ESTANDAR:
        rid = cfg.receta_id
        if not rid:
            rec = next(
                (r for r in data.recetas if _norm(r.nombre) == _norm(cfg.label)),
                None,
            )
            rid = rec.id if rec else None
        if not rid:
            raise ValueError(f"Receta estándar no encontrada: «{cfg.label}»")
        r = des.anadir_receta_a_cesta(rid, qty)
        if not r.ok:
            raise ValueError(r.mensaje)
        coste = _coste_receta(data, rid, qty)
    elif cfg.tipo_linea == TIPO_LINEA_JARRA_ZUMO:
        naranjas = float(entrada.naranjas or 0)
        bote = float(entrada.zumo_bote or 0)
        if naranjas > 0 and cfg.producto_id:
            r = des.anadir_a_cesta(cfg.producto_id, naranjas)
            if not r.ok:
                raise ValueError(r.mensaje)
            coste += _coste_linea(data, cfg.producto_id, naranjas)
        if bote > 0:
            pid_bote = cfg.producto_bote_id or "b28"
            r = des.anadir_a_cesta(pid_bote, bote)
            if not r.ok:
                raise ValueError(r.mensaje)
            coste += _coste_linea(data, pid_bote, bote)
        if naranjas <= 0 and bote <= 0 and cfg.producto_id:
            r = des.anadir_a_cesta(cfg.producto_id, qty)
            if not r.ok:
                raise ValueError(r.mensaje)
            coste += _coste_linea(data, cfg.producto_id, qty)
    else:
        if not cfg.producto_id:
            raise ValueError(f"ProductoId vacío en «{cfg.label}»")
        nativa = round(float(cfg.cantidad_defecto or 1.0) * qty, 6)
        r = des.anadir_a_cesta(cfg.producto_id, nativa)
        if not r.ok:
            raise ValueError(r.mensaje)
        coste = _coste_linea(data, cfg.producto_id, nativa)
    return round(coste, 2)


def _anadir_merma(
    data: AppData,
    cfg,
    entrada: LineaBuffetEntrada,
    *,
    ctx: AppContext,
) -> float:
    motivo = _motivo_merma(entrada.motivo)
    comentario = f"Buffet {cfg.label}"
    if entrada.motivo == MOTIVO_BUFFET_LIMPIEZA:
        comentario = f"Limpieza buffet — {cfg.label}"
    if entrada.notas:
        comentario = f"{comentario}. {entrada.notas}"

    resp = ensure_responsable_import(data)
    coste_total = 0.0

    def _merma_producto(producto_id: str, cantidad: float) -> None:
        nonlocal coste_total
        if not producto_id or cantidad <= 0:
            return
        lotes = merma_service.lotes_disponibles(producto_id, ctx=ctx)
        if not lotes:
            raise ValueError(f"Sin lote con stock para merma «{cfg.label}» ({producto_id})")
        lote_id = lotes[0]["id"]
        r = merma_service.anadir_a_cesta_merma(
            lote_id,
            cantidad,
            motivo,
            OrigenServicioMerma.DESAYUNO.value,
            comentario=comentario,
            turno_snapshot=TurnoMerma.MANANA.value,
            responsable_id=resp.id,
            responsable_nombre=resp.nombre,
            ctx=ctx,
        )
        if not r.ok:
            raise ValueError(r.mensaje)
        coste_total += merma_service.calcular_coste_lote(lote_id, cantidad, ctx=ctx)

    qty = float(entrada.cantidad)
    if cfg.tipo_linea == TIPO_LINEA_JARRA_ZUMO:
        if entrada.naranjas and cfg.producto_id:
            _merma_producto(cfg.producto_id, float(entrada.naranjas))
        if entrada.zumo_bote and cfg.producto_bote_id:
            _merma_producto(cfg.producto_bote_id, float(entrada.zumo_bote))
        if not entrada.naranjas and not entrada.zumo_bote and cfg.producto_id:
            _merma_producto(cfg.producto_id, qty)
    elif cfg.tipo_linea == TIPO_LINEA_RECETA_ESTANDAR:
        rid = cfg.receta_id
        rec = next((r for r in data.recetas if r.id == rid), None) if rid else None
        if rec is None:
            rec = next(
                (r for r in data.recetas if _norm(r.nombre) == _norm(cfg.label)),
                None,
            )
        if rec is None:
            raise ValueError(f"Receta estándar no encontrada: «{cfg.label}»")
        for ing in rec.ingredientes or []:
            nativa = round(float(ing.cantidad or 0) * qty, 6)
            _merma_producto(ing.producto_id, nativa)
    else:
        if not cfg.producto_id:
            raise ValueError(f"ProductoId vacío en «{cfg.label}»")
        nativa = round(float(cfg.cantidad_defecto or 1.0) * qty, 6)
        _merma_producto(cfg.producto_id, nativa)
    return round(coste_total, 2)


def importar_lineas_buffet(
    fecha: date,
    lineas: list[LineaBuffetEntrada],
    *,
    dry_run: bool = False,
    ctx: AppContext | None = None,
) -> ResultadoImportBuffet:
    """Importa un día de consumo buffet (consumo → desayuno, resto → merma)."""
    context = _ctx(ctx)
    data = context.data()
    ensure_config_buffet(data)

    if not lineas:
        return ResultadoImportBuffet(False, "Sin líneas buffet")

    existente = _ya_importado(data, fecha)
    if existente is not None:
        return ResultadoImportBuffet(
            True,
            f"Ya importado ({existente.id})",
            skipped=True,
            registro_id=existente.id,
        )

    registros_lineas: list[LineaRegistroBuffet] = []
    errores: list[str] = []
    preview: list[str] = []
    coste_total = 0.0

    for i, entrada in enumerate(lineas, start=1):
        try:
            motivo = _parse_motivo(entrada.motivo)
            if motivo not in MOTIVOS_BUFFET_VALORES:
                raise ValueError(f"Motivo inválido: {entrada.motivo}")
            cfg = _resolver_config(data, entrada)
            if dry_run:
                preview.append(f"{cfg.label}x{entrada.cantidad}:{motivo}")
                coste = 0.0
            elif motivo == MOTIVO_BUFFET_CONSUMO:
                coste = _anadir_consumo(data, cfg, entrada)
            else:
                coste = _anadir_merma(data, cfg, entrada, ctx=context)
            registros_lineas.append(
                LineaRegistroBuffet(
                    config_id=cfg.id,
                    label=cfg.label,
                    cantidad=float(entrada.cantidad),
                    motivo=motivo,
                    naranjas_cantidad=entrada.naranjas,
                    zumo_bote_cantidad=entrada.zumo_bote,
                    coste_snapshot=coste,
                    notas=entrada.notas,
                )
            )
            coste_total += coste
        except ValueError as exc:
            errores.append(f"línea {i} ({entrada.label}): {exc}")

    if errores:
        if not dry_run:
            des.limpiar_cesta()
            merma_service.limpiar_cesta_merma()
        return ResultadoImportBuffet(False, " | ".join(errores))

    if dry_run:
        return ResultadoImportBuffet(
            True,
            f"dry-run {fecha}: " + "; ".join(preview),
            dry_run=True,
        )

    hay_consumo = any(l.motivo == MOTIVO_BUFFET_CONSUMO for l in registros_lineas)
    if hay_consumo and not des.cesta_vacia():
        res_des = des.registrar_desayuno(
            fecha,
            1,
            clave_idempotencia=_clave(fecha) + "-des",
            observaciones="Import Excel consumo buffet",
            ctx=context,
        )
        if not res_des.ok and getattr(res_des, "codigo", None) != "IDEMPOTENTE":
            des.limpiar_cesta()
            merma_service.limpiar_cesta_merma()
            return ResultadoImportBuffet(False, res_des.mensaje)

    if merma_service.get_cesta_merma():
        res_m = merma_service.registrar_merma(fecha, ctx=context)
        if not res_m.ok:
            return ResultadoImportBuffet(False, res_m.mensaje)

    reg_id = next_id("bf", [r.id for r in data.registros_buffet])
    registro = RegistroBuffetDiario(
        id=reg_id,
        fecha=fecha,
        lineas=registros_lineas,
        coste_total=round(coste_total, 2),
        clave_idempotencia=_clave(fecha),
        registrado_por=context.actor.nombre,
        hora=context.clock.now().time(),
        observaciones="Import Excel consumo buffet",
    )
    data.registros_buffet.append(registro)
    context.uow.commit(data)
    return ResultadoImportBuffet(True, f"OK {reg_id}", registro_id=reg_id)


def registros_exportables(
    inicio: date,
    hasta: datetime,
    *,
    ctx: AppContext | None = None,
) -> list[RegistroExportable]:
    data = _ctx(ctx).data()
    repo = DataRepository(data)
    fin = hasta.date()
    columnas = [
        "Sección", "Concepto", "Cantidad", "Motivo",
        "Naranjas", "Zumo bote", "Coste", "Notas",
    ]
    out: list[RegistroExportable] = []
    for reg in data.registros_buffet:
        if reg.anulado or reg.fecha < inicio or reg.fecha > fin:
            continue
        filas = []
        for ln in reg.lineas:
            filas.append([
                next((c.seccion for c in data.config_buffet if c.id == ln.config_id), ""),
                ln.label,
                ln.cantidad,
                ln.motivo,
                ln.naranjas_cantidad or "",
                ln.zumo_bote_cantidad or "",
                repo.formato_precio(ln.coste_snapshot),
                ln.notas,
            ])
        out.append(
            RegistroExportable(
                fecha=reg.fecha,
                hora=reg.hora,
                tipo="Consumo buffet",
                identificador=reg.id,
                usuario=reg.registrado_por,
                columnas=columnas,
                filas=filas,
                resumen=[("Coste total", repo.formato_precio(reg.coste_total))],
            )
        )
    return out
