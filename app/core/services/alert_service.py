"""Servicio de alertas operativas de stock.

Fase 4B: lecturas/escrituras vía AppContext (UoW, reloj, actor, auditoría).
La firma pública se mantiene; `session_store` sigue detrás del UoW JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.application.context import AppContext, build_app_context
from app.core.application.id_generator import next_id
from app.core.models import AlertaOperativa, AppData, EstadoAlerta, TipoAlerta
from app.core.repositories.data_repository import DataRepository

DIAS_EXPIRACION_DEFECTO = 5

_TIPOS_STOCK_AUTO = {
    TipoAlerta.STOCK_BAJO,
    TipoAlerta.STOCK_CERO,
    TipoAlerta.STOCK_NEGATIVO,
    TipoAlerta.EXPIRACION_PROXIMA,
    TipoAlerta.EXPIRADO,
}

_TIPOS_DESAYUNO_AUTO = {TipoAlerta.DESAYUNO_NO_REGISTRADO}

_TIPOS_AUTO = _TIPOS_STOCK_AUTO | _TIPOS_DESAYUNO_AUTO

_ESTADOS_ABIERTOS = {
    EstadoAlerta.PENDIENTE.value,
    EstadoAlerta.REVISADA.value,
}

_ESTADOS_CIERRE = {
    EstadoAlerta.RESUELTA.value,
    EstadoAlerta.IGNORADA.value,
}


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


def _ctx(ctx: AppContext | None = None) -> AppContext:
    return ctx if ctx is not None else build_app_context()


def _registrar_actividad(ctx: AppContext, accion: str, detalle: str) -> None:
    from app.core.application.auditoria import registrar_actividad

    registrar_actividad(ctx, accion, detalle, commit=False)


def _estado_alerta(alerta: AlertaOperativa) -> str:
    valor = getattr(alerta, "estado", None) or EstadoAlerta.PENDIENTE.value
    try:
        return EstadoAlerta(valor).value
    except ValueError:
        return EstadoAlerta.PENDIENTE.value


def _firma_alerta(alerta: AlertaOperativa) -> str:
    """Identificador estable para recordar alertas automáticas descartadas."""
    if alerta.tipo in {TipoAlerta.STOCK_BAJO, TipoAlerta.STOCK_CERO, TipoAlerta.STOCK_NEGATIVO}:
        return f"{alerta.tipo.value}|{alerta.producto_id or ''}"
    if alerta.tipo in {TipoAlerta.EXPIRADO, TipoAlerta.EXPIRACION_PROXIMA}:
        lote_id = getattr(alerta, "lote_id", None) or _lote_id_desde_mensaje(alerta.mensaje)
        return f"{alerta.tipo.value}|{alerta.producto_id or ''}|{lote_id}"
    if alerta.tipo == TipoAlerta.DESAYUNO_NO_REGISTRADO:
        return alerta.tipo.value
    return f"{alerta.tipo.value}|{alerta.producto_id or ''}|{alerta.mensaje}"


def _lote_id_desde_mensaje(mensaje: str) -> str:
    marcador = "lote "
    inicio = mensaje.find(marcador)
    if inicio == -1:
        return mensaje
    resto = mensaje[inicio + len(marcador):]
    return resto.split(" ", 1)[0]


def _conservar_alertas(data: AppData) -> list[AlertaOperativa]:
    """Mantiene alertas manuales y las que no se regeneran automáticamente."""
    return [
        a for a in data.alertas
        if a.tipo not in _TIPOS_AUTO
    ]


def _mapa_estados_previos(data: AppData) -> dict[str, str]:
    return {
        _firma_alerta(a): _estado_alerta(a)
        for a in data.alertas
        if a.tipo in _TIPOS_AUTO
    }


def _aplicar_estados_previos(
    candidatas: list[AlertaOperativa],
    previos: dict[str, str],
) -> None:
    for alerta in candidatas:
        alerta.estado = previos.get(_firma_alerta(alerta), EstadoAlerta.PENDIENTE.value)


def _generar_alertas_stock(data: AppData, repo: DataRepository, hoy: date) -> list[AlertaOperativa]:
    nuevas: list[AlertaOperativa] = []
    contador = 1

    for producto, stock in repo.productos_stock_bajo():
        nuevas.append(AlertaOperativa(
            f"a_tmp{contador:02d}",
            TipoAlerta.STOCK_BAJO,
            f"Stock bajo — {producto.nombre}",
            f"Quedan {stock:g} {producto.unidad.value}. Stock mínimo: {producto.stock_minimo:g}.",
            hoy,
            producto_id=producto.id,
        ))
        contador += 1

    for producto in repo.productos_stock_cero():
        nuevas.append(AlertaOperativa(
            f"a_tmp{contador:02d}",
            TipoAlerta.STOCK_CERO,
            f"Stock agotado — {producto.nombre}",
            "No quedan unidades disponibles.",
            hoy,
            producto_id=producto.id,
        ))
        contador += 1

    for producto, stock in repo.productos_stock_negativo():
        nuevas.append(AlertaOperativa(
            f"a_tmp{contador:02d}",
            TipoAlerta.STOCK_NEGATIVO,
            f"Stock negativo — {producto.nombre}",
            f"Inventario en −{abs(stock):g} {producto.unidad.value}.",
            hoy,
            producto_id=producto.id,
        ))
        contador += 1

    for lote in data.lotes:
        if getattr(lote, "anulado", False):
            continue
        if lote.cantidad_restante <= 0 or not lote.fecha_expiracion:
            continue
        producto = repo.get_producto(lote.producto_id)
        if not producto:
            continue
        dias_umbral = lote.alerta_expiracion_dias or DIAS_EXPIRACION_DEFECTO
        dias_restantes = (lote.fecha_expiracion - hoy).days
        fecha_compra_txt = (
            lote.fecha_compra.strftime("%d/%m/%Y") if lote.fecha_compra else "sin fecha"
        )

        if dias_restantes < 0:
            nuevas.append(AlertaOperativa(
                f"a_tmp{contador:02d}",
                TipoAlerta.EXPIRADO,
                f"Producto expirado — {producto.nombre}",
                f"El lote {lote.id} (compra {fecha_compra_txt}) expiró hace {abs(dias_restantes)} día(s).",
                hoy,
                producto_id=producto.id,
                lote_id=lote.id,
            ))
            contador += 1
        elif dias_restantes <= dias_umbral:
            nuevas.append(AlertaOperativa(
                f"a_tmp{contador:02d}",
                TipoAlerta.EXPIRACION_PROXIMA,
                f"Próximo a expirar — {producto.nombre}",
                f"El lote {lote.id} (compra {fecha_compra_txt}) expira en {dias_restantes} día(s).",
                hoy,
                producto_id=producto.id,
                lote_id=lote.id,
            ))
            contador += 1

    return nuevas


def _desayuno_registrado(data: AppData, hoy: date) -> bool:
    """Misma regla que DataRepository.desayuno_registrado_hoy, con fecha inyectable."""
    return any(d.fecha == hoy for d in data.desayunos)


def _generar_alerta_desayuno(data: AppData, hoy: date) -> list[AlertaOperativa]:
    if _desayuno_registrado(data, hoy):
        return []
    return [AlertaOperativa(
        "a_tmp_desayuno",
        TipoAlerta.DESAYUNO_NO_REGISTRADO,
        "Desayuno de hoy no registrado",
        "Aún no se ha registrado el consumo del desayuno de hoy.",
        hoy,
    )]


def _reasignar_ids(alertas: list[AlertaOperativa]) -> None:
    for i, alerta in enumerate(alertas, start=1):
        alerta.id = f"a{i:02d}"


def _filtrar_auto_descartadas(
    candidatas: list[AlertaOperativa],
    descartadas: set[str],
) -> list[AlertaOperativa]:
    return [a for a in candidatas if _firma_alerta(a) not in descartadas]


def _limpiar_descartadas_obsoletas(
    data: AppData,
    candidatas: list[AlertaOperativa],
) -> None:
    firmas_vigentes = {_firma_alerta(a) for a in candidatas}
    data.alertas_descartadas = [
        firma for firma in data.alertas_descartadas if firma in firmas_vigentes
    ]


def sincronizar_alertas(ctx: AppContext | None = None) -> AppData:
    """Regenera alertas automáticas de stock y desayuno; conserva las manuales."""
    context = _ctx(ctx)
    data = context.data()
    repo = DataRepository(data)
    hoy = context.clock.today()

    estados_previos = _mapa_estados_previos(data)
    conservadas = _conservar_alertas(data)
    auto_stock_raw = _generar_alertas_stock(data, repo, hoy)
    auto_desayuno_raw = _generar_alerta_desayuno(data, hoy)
    todas_candidatas = auto_stock_raw + auto_desayuno_raw

    _limpiar_descartadas_obsoletas(data, todas_candidatas)
    descartadas = set(data.alertas_descartadas)
    auto_stock = _filtrar_auto_descartadas(auto_stock_raw, descartadas)
    auto_desayuno = _filtrar_auto_descartadas(auto_desayuno_raw, descartadas)
    _aplicar_estados_previos(auto_stock + auto_desayuno, estados_previos)

    data.alertas = conservadas + auto_stock + auto_desayuno
    _reasignar_ids(data.alertas)
    return context.uow.commit(data)


def crear_alerta_manual(
    titulo: str,
    mensaje: str,
    producto_id: str | None = None,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    titulo = titulo.strip()
    mensaje = mensaje.strip()
    if not titulo:
        return ResultadoOperacion(False, "El título es obligatorio.")
    if not mensaje:
        return ResultadoOperacion(False, "El mensaje es obligatorio.")

    context = _ctx(ctx)
    data = context.data()
    if producto_id and not DataRepository(data).get_producto(producto_id):
        return ResultadoOperacion(False, "El producto seleccionado no existe.")

    alerta = AlertaOperativa(
        next_id("a", [a.id for a in data.alertas]),
        TipoAlerta.MANUAL,
        titulo,
        mensaje,
        context.clock.today(),
        producto_id=producto_id,
        estado=EstadoAlerta.PENDIENTE.value,
    )
    data.alertas.append(alerta)
    _registrar_actividad(context, "Alerta manual", f"«{titulo}» creada")
    context.uow.commit(data)
    return ResultadoOperacion(True, "Alerta manual creada correctamente.")


def cambiar_estado_alerta(
    alerta_id: str,
    nuevo_estado: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    """Cambia el workflow de una alerta. Revisada no oculta la causa persistente."""
    try:
        estado = EstadoAlerta(nuevo_estado)
    except ValueError:
        return ResultadoOperacion(False, "Estado de alerta no válido.")

    context = _ctx(ctx)
    data = context.data()
    usuario = context.actor.nombre
    for alerta in data.alertas:
        if alerta.id != alerta_id:
            continue

        anterior = _estado_alerta(alerta)
        alerta.estado = estado.value

        if estado.value in _ESTADOS_CIERRE:
            if alerta.tipo in _TIPOS_AUTO:
                firma = _firma_alerta(alerta)
                if firma not in data.alertas_descartadas:
                    data.alertas_descartadas.append(firma)
            else:
                alerta.activa = False
        elif estado.value in _ESTADOS_ABIERTOS:
            if alerta.tipo in _TIPOS_AUTO:
                firma = _firma_alerta(alerta)
                data.alertas_descartadas = [
                    f for f in data.alertas_descartadas if f != firma
                ]
            else:
                alerta.activa = True

        _registrar_actividad(
            context,
            "Estado alerta",
            f"{usuario} cambió «{alerta.titulo}» de {anterior} a {estado.value}",
        )
        context.uow.commit(data)
        return ResultadoOperacion(True, f"Alerta marcada como {estado.value}.")

    return ResultadoOperacion(False, "No se encontró la alerta.")


def remover_alerta(
    alerta_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    """Compatibilidad: equivale a Ignorada."""
    return cambiar_estado_alerta(alerta_id, EstadoAlerta.IGNORADA.value, ctx=ctx)


def resolver_alerta(
    alerta_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    """Compatibilidad: equivale a Resuelta."""
    return cambiar_estado_alerta(alerta_id, EstadoAlerta.RESUELTA.value, ctx=ctx)


def alerta_esta_abierta(alerta: AlertaOperativa) -> bool:
    return bool(alerta.activa) and _estado_alerta(alerta) in _ESTADOS_ABIERTOS


def alertas_stock_activas(data: AppData) -> list[AlertaOperativa]:
    """Alertas de stock visibles (pendiente/revisada)."""
    tipos = _TIPOS_STOCK_AUTO | {TipoAlerta.MANUAL}
    return [
        a for a in data.alertas
        if alerta_esta_abierta(a) and a.tipo in tipos
    ]


def alertas_operativas_abiertas(data: AppData) -> list[AlertaOperativa]:
    """Todas las alertas abiertas para dashboard / resumen operativo."""
    return [a for a in data.alertas if alerta_esta_abierta(a)]
