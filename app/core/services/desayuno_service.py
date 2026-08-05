"""Servicio de registro de desayuno — consumo y FIFO.

La lógica de lotes vive en `inventory_batch_service` y la cesta en
`cesta_service` (prefijo «desayuno», claves históricas). La API pública
de este módulo se mantiene para no romper páginas ni tests existentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from app.core.models import (
    AppData,
    ExtraRecetaDesayuno,
    LineaDesayuno,
    OmisionRecetaDesayuno,
    RegistroDesayuno,
    RegistroRecetaDesayuno,
    TipoServicio,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services.cesta_service import (
    PASO_CANTIDAD,
    GrupoRecetaCesta,
    LineaCesta,
    LineaCestaIngrediente,
    ModPendienteReceta,
    cantidad_texto_linea_receta,
    crear_motor_cesta,
    etiqueta_linea_receta,
    etiqueta_linea_suelta,
)
from app.core.services.detalle_origen_service import (
    asignar_consumos_lote,
    asignar_costes_proporcionales,
    construir_lineas_detalle,
    validar_consumos_lote,
)
from app.core.services.excel_bloques import RegistroExportable
from app.core.services.exportacion_semanal_service import ConfiguracionExportacionModulo
from app.core.services.inventory_batch_service import (
    PlanDescuentoStock,
    calcular_coste_linea,
    descontar_lotes,
    planificar_descuento,
    snapshot_cantidades_restantes,
    restaurar_cantidades_restantes,
    stock_disponible,
)
from app.core.services.stock_service import disponible_en_servicio
from app.core.services.text_search import coincide_busqueda
from app.core.services.receta_service import factor_desde_registro_receta
from app.core.services.unidad_service import resolver_presentacion
from app.core.storage.session_store import get_data, persist_data
from app.core.application.context import AppContext
from app.core.application.id_generator import next_id

# Reexportaciones públicas (compatibilidad con imports existentes).
__all__ = [
    "PASO_CANTIDAD",
    "ResultadoOperacion",
    "LineaCesta",
    "LineaCestaIngrediente",
    "GrupoRecetaCesta",
    "ModPendienteReceta",
    "stock_disponible",
    "calcular_coste_linea",
    "etiqueta_linea_suelta",
    "etiqueta_linea_receta",
    "cantidad_texto_linea_receta",
]

CESTA_SESSION_KEY = "bm_cesta_desayuno"
CESTA_RECETAS_KEY = "bm_cesta_recetas"
GRUPO_COUNTER_KEY = "bm_grupo_receta_counter"
LINEA_COUNTER_KEY = "bm_linea_cesta_counter"
MODS_PENDIENTES_KEY = "bm_receta_pendiente_mods"

_cesta = crear_motor_cesta("desayuno")

# Categorías de receta permitidas en el registro de desayuno (independiente
# de tipo_servicio): Desayuno + Bebidas.
from app.core.models import CategoriaReceta

CATEGORIAS_RECETA_DESAYUNO = [CategoriaReceta.DESAYUNO, CategoriaReceta.BEBIDAS]


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str
    codigo: str | None = None
    detalle_stock: list[str] | None = None


class _CompatSessionUow:
    """UoW sobre get_data/persist_data del módulo (parcheable en tests)."""

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


def _registrar_actividad(ctx: AppContext, accion: str, detalle: str) -> None:
    from app.core.application.auditoria import registrar_actividad

    registrar_actividad(ctx, accion, detalle, commit=False)


def _descontar_fifo(data: AppData, producto_id: str, cantidad: float, *, permitir_negativo: bool = False) -> float:
    """Alias interno: el comportamiento sigue siendo FIFO por fecha_compra."""
    return descontar_lotes(
        data, producto_id, cantidad, permitir_negativo=permitir_negativo,
    ).coste


def get_cesta() -> list[LineaCesta]:
    return _cesta.get_cesta()


def get_cesta_recetas() -> list[GrupoRecetaCesta]:
    return _cesta.get_cesta_recetas()


def get_mods_pendientes() -> list[ModPendienteReceta]:
    return _cesta.get_mods_pendientes()


def limpiar_mods_pendientes() -> None:
    _cesta.limpiar_mods_pendientes()


def limpiar_cesta() -> None:
    _cesta.limpiar_cesta()


def cesta_vacia() -> bool:
    return _cesta.cesta_vacia()


def productos_catalogo(
    buscar: str = "",
    *,
    servicio: str | None = None,
    ctx: AppContext | None = None,
) -> list[dict]:
    data = _ctx(ctx).data()
    resultado = []
    termino = buscar.strip()
    for producto in sorted(data.productos, key=lambda p: p.nombre):
        if servicio is not None and not disponible_en_servicio(
            producto.servicios_disponibles, servicio,
        ):
            continue
        if termino and not coincide_busqueda(producto.nombre, termino):
            continue
        stock = stock_disponible(data, producto.id)
        resultado.append({
            "id": producto.id,
            "nombre": producto.nombre,
            "unidad": producto.unidad.value,
            "stock": stock,
            "etiqueta": f"{producto.nombre} ({stock:g} {producto.unidad.value})",
        })
    return resultado


def productos_disponibles(
    buscar: str = "",
    *,
    servicio: str | None = None,
    ctx: AppContext | None = None,
) -> list[dict]:
    return [
        p for p in productos_catalogo(buscar, servicio=servicio, ctx=ctx) if p["stock"] > 0
    ]


def anadir_mod_pendiente_receta(producto_id: str, cantidad: float) -> ResultadoOperacion:
    r = _cesta.anadir_mod_pendiente_receta(producto_id, cantidad)
    return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)


def quitar_mod_pendiente(mod_id: str) -> None:
    _cesta.quitar_mod_pendiente(mod_id)


def anadir_a_cesta(producto_id: str, cantidad: float) -> ResultadoOperacion:
    r = _cesta.anadir_a_cesta(producto_id, cantidad)
    return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)


def anadir_receta_a_cesta(
    receta_id: str,
    porciones: float,
    mods_pendientes: list[ModPendienteReceta] | None = None,
) -> ResultadoOperacion:
    r = _cesta.anadir_receta_a_cesta(
        receta_id,
        porciones,
        mods_pendientes,
        categorias_permitidas=CATEGORIAS_RECETA_DESAYUNO,
    )
    return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)


def quitar_grupo_receta(grupo_id: str) -> None:
    _cesta.quitar_grupo_receta(grupo_id)


def quitar_linea_grupo(grupo_id: str, linea_id: str) -> None:
    _cesta.quitar_linea_grupo(grupo_id, linea_id)


def paso_linea_grupo(grupo_id: str, linea_id: str) -> float:
    return _cesta.paso_linea_grupo(grupo_id, linea_id)


def ajustar_linea_grupo(grupo_id: str, linea_id: str, delta: float) -> ResultadoOperacion:
    r = _cesta.ajustar_linea_grupo(grupo_id, linea_id, delta)
    return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)


def modificar_linea_grupo(grupo_id: str, linea_id: str, cantidad: float) -> ResultadoOperacion:
    r = _cesta.modificar_linea_grupo(grupo_id, linea_id, cantidad)
    return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)


def modificar_porciones_grupo(grupo_id: str, porciones: float) -> ResultadoOperacion:
    r = _cesta.modificar_porciones_grupo(grupo_id, porciones)
    return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)


def ajustar_porciones_grupo(grupo_id: str, delta: float) -> ResultadoOperacion:
    r = _cesta.ajustar_porciones_grupo(grupo_id, delta)
    return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)


def paso_linea_suelta(linea_id: str) -> float:
    return _cesta.paso_linea_suelta(linea_id)


def quitar_linea_suelta(linea_id: str) -> None:
    _cesta.quitar_linea_suelta(linea_id)


def ajustar_cantidad_suelto(linea_id: str, delta: float) -> ResultadoOperacion:
    r = _cesta.ajustar_cantidad_suelto(linea_id, delta)
    return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)


def modificar_cantidad_suelto(linea_id: str, cantidad: float) -> ResultadoOperacion:
    r = _cesta.modificar_cantidad_suelto(linea_id, cantidad)
    return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)


def coste_total_cesta(*, ctx: AppContext | None = None) -> float:
    data = _ctx(ctx).data()
    total = sum(
        calcular_coste_linea(data, l.producto_id, max(l.cantidad, 0))
        for l in get_cesta()
    )
    for grupo in get_cesta_recetas():
        for ing in grupo.ingredientes:
            total += calcular_coste_linea(data, ing.producto_id, max(ing.cantidad, 0))
    return round(total, 2)


def _aplanar_cesta() -> dict[str, tuple[float, bool]]:
    fusionado: dict[str, tuple[float, bool]] = {}
    for linea in get_cesta():
        cantidad, es_extra = fusionado.get(linea.producto_id, (0.0, False))
        fusionado[linea.producto_id] = (
            round(cantidad + linea.cantidad, 4),
            es_extra or linea.es_extra,
        )
    for grupo in get_cesta_recetas():
        for ing in grupo.ingredientes:
            cantidad, es_extra = fusionado.get(ing.producto_id, (0.0, False))
            fusionado[ing.producto_id] = (
                round(cantidad + ing.cantidad, 4),
                es_extra or ing.es_extra,
            )
    return {pid: (max(c, 0), e) for pid, (c, e) in fusionado.items() if c != 0}


def _construir_registros_recetas(data: AppData, grupos: list[GrupoRecetaCesta]) -> list[RegistroRecetaDesayuno]:
    repo = DataRepository(data)
    registros: list[RegistroRecetaDesayuno] = []
    for grupo in grupos:
        receta = repo.get_receta(grupo.receta_id)
        template_ids = {i.producto_id for i in receta.ingredientes} if receta else set()
        presentes_base = {
            i.producto_id for i in grupo.ingredientes
            if i.es_base_receta and i.cantidad > 0
        }
        omisiones = [
            OmisionRecetaDesayuno(pid)
            for pid in sorted(template_ids - presentes_base)
        ]
        extras: list[ExtraRecetaDesayuno] = []
        for i in grupo.ingredientes:
            if i.es_base_receta and i.cantidad < 0:
                extras.append(ExtraRecetaDesayuno(i.producto_id, i.cantidad))
            elif i.es_extra or (not i.es_base_receta and i.cantidad > 0):
                extras.append(ExtraRecetaDesayuno(i.producto_id, i.cantidad))
            elif i.es_omision or (not i.es_base_receta and i.cantidad < 0):
                extras.append(ExtraRecetaDesayuno(i.producto_id, i.cantidad))
        registros.append(RegistroRecetaDesayuno(
            grupo.receta_id,
            grupo.nombre_receta,
            grupo.porciones,
            extras,
            omisiones,
            categoria_receta_snapshot=receta.categoria.value if receta else None,
            porciones_estandar_snapshot=grupo.porciones_estandar,
            factor_aplicado=grupo.factor_aplicado,
        ))
    return registros


def _plan_stock_fusionado(
    data: AppData,
    fusionado: dict[str, tuple[float, bool]],
) -> PlanDescuentoStock:
    repo = DataRepository(data)
    demandas = {pid: cant for pid, (cant, _) in fusionado.items() if cant > 0}
    nombres = {pid: repo.get_nombre_producto(pid) for pid in demandas}
    unidades: dict[str, str] = {}
    for pid in demandas:
        producto = repo.get_producto(pid)
        unidades[pid] = producto.unidad.value if producto else ""
    return planificar_descuento(data, demandas, nombres=nombres, unidades=unidades)


def previsualizar_stock_registro(*, ctx: AppContext | None = None) -> PlanDescuentoStock:
    """Preview actual/salida/resultante de la cesta (sin mutar)."""
    if cesta_vacia():
        return PlanDescuentoStock()
    return _plan_stock_fusionado(_ctx(ctx).data(), _aplanar_cesta())


def registrar_desayuno(
    fecha: date,
    num_huespedes: int,
    *,
    ignorar_stock: bool = False,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    """Registra el desayuno con descuento atómico.

    `ignorar_stock` queda deshabilitado (Fase 9): se ignora el bypass.
    """
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_REGISTRO)
    if denied:
        return ResultadoOperacion(False, denied)

    _ = ignorar_stock  # Bypass retirado; no permitir stock negativo.

    if cesta_vacia():
        return ResultadoOperacion(
            False,
            "La cesta está vacía. Añada productos o recetas antes de registrar.",
        )

    context = _ctx(ctx)
    if fecha > context.clock.today():
        return ResultadoOperacion(False, "No puede registrar desayunos en fechas futuras.")

    if num_huespedes < 1:
        return ResultadoOperacion(False, "Indique al menos 1 huésped.")

    data = context.data()

    fusionado = _aplanar_cesta()
    grupos = list(get_cesta_recetas())
    cesta_suelta = list(get_cesta())

    plan = _plan_stock_fusionado(data, fusionado)
    if not plan.ok:
        return ResultadoOperacion(
            False,
            "Stock insuficiente para registrar el desayuno. No se ha modificado nada.",
            codigo="STOCK_INSUFICIENTE",
            detalle_stock=plan.deficits,
        )

    registro_id = next_id("d", [d.id for d in data.desayunos])
    demandas = {pid: cant for pid, (cant, _) in fusionado.items() if cant > 0}
    extras = {pid: es_extra for pid, (cant, es_extra) in fusionado.items() if cant > 0}

    snap = snapshot_cantidades_restantes(data)
    n_desayunos = len(data.desayunos)
    n_actividades = len(data.actividades)
    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []
    n_movimientos = len(data.movimientos)
    try:
        from app.core.application.inventory_ops import (
            aplicar_descuento_atomico as aplicar_descuento_ctx,
        )

        resultado_desc = aplicar_descuento_ctx(context, demandas)
        costes_agregados = resultado_desc.costes
        lineas = [
            LineaDesayuno(pid, demandas[pid], costes_agregados.get(pid, 0.0), extras[pid])
            for pid in demandas
        ]
        cantidades_agregadas = dict(demandas)

        lineas_detalle = construir_lineas_detalle(
            cesta_suelta,
            grupos,
            tipo_servicio=TipoServicio.DESAYUNO.value,
            registro_id=registro_id,
            data=data,
        )
        asignar_costes_proporcionales(lineas_detalle, costes_agregados, cantidades_agregadas)
        asignar_consumos_lote(lineas_detalle, resultado_desc.movimientos)
        validar_consumos_lote(
            lineas_detalle, resultado_desc.movimientos, costes_agregados, data,
        )

        registros_recetas = _construir_registros_recetas(data, grupos)
        coste_total = round(sum(l.coste for l in lineas), 2)
        registro = RegistroDesayuno(
            registro_id,
            fecha,
            lineas,
            coste_total,
            context.actor.nombre,
            num_huespedes,
            registros_recetas,
            context.clock.now().time(),
            lineas_detalle,
        )
        data.desayunos.append(registro)

        from app.core.services import movimiento_service as mov_svc

        mov_svc.escribir_espejos_consumo_registro(
            origen_tipo=mov_svc.ORIGEN_TIPO_DESAYUNO,
            registro_id=registro_id,
            lineas_detalle=lineas_detalle,
            fecha=fecha,
            hora=registro.hora,
            usuario_id=context.actor.id or None,
            ctx=context,
        )

        detalle_recetas = ""
        if registros_recetas:
            detalle_recetas = f" — {len(registros_recetas)} receta(s)"

        _registrar_actividad(
            context,
            "Registro desayuno",
            f"Desayuno del {fecha.strftime('%d/%m/%Y')} — {coste_total:.2f} € — {num_huespedes} huéspedes{detalle_recetas}",
        )
        context.uow.commit(data)
    except Exception:
        restaurar_cantidades_restantes(data, snap)
        del data.desayunos[n_desayunos:]
        del data.movimientos[n_movimientos:]
        if len(data.actividades) > n_actividades:
            del data.actividades[n_actividades:]
        raise

    limpiar_cesta()

    from app.core.services.alert_service import sincronizar_alertas
    sincronizar_alertas(context)

    return ResultadoOperacion(
        True,
        f"Desayuno registrado — {coste_total:.2f} € ({len(lineas)} producto(s)).",
    )


def fecha_mas_antigua(*, ctx: AppContext | None = None) -> date | None:
    fechas = [d.fecha for d in _ctx(ctx).data().desayunos]
    return min(fechas) if fechas else None


def registros_exportables(
    inicio: date,
    hasta: datetime,
    *,
    ctx: AppContext | None = None,
) -> list[RegistroExportable]:
    data = _ctx(ctx).data()
    repo = DataRepository(data)
    fin = hasta.date()
    columnas = ["Tipo", "Producto / Receta", "Detalle", "Cantidad", "Unidad", "Coste"]

    resultado: list[RegistroExportable] = []
    for d in data.desayunos:
        if not (inicio <= d.fecha <= fin):
            continue

        filas: list[list] = []
        for rr in d.registros_recetas:
            factor = factor_desde_registro_receta(rr)
            est_txt = (
                f"{rr.porciones_estandar_snapshot:g}"
                if rr.porciones_estandar_snapshot
                else "—"
            )
            filas.append([
                "Receta",
                rr.nombre_receta,
                f"{rr.porciones:g} porciones (est. {est_txt}, factor {factor:g})",
                rr.porciones,
                "porciones",
                "",
            ])

            receta = repo.get_receta(rr.receta_id)
            omitidos = {o.producto_id for o in rr.omisiones}
            for ing in (receta.ingredientes if receta else []):
                if ing.producto_id in omitidos:
                    continue
                producto_ing = repo.get_producto(ing.producto_id)
                if not producto_ing:
                    continue
                cantidad_mostrar, unidad_mostrar = resolver_presentacion(
                    ing.cantidad,
                    producto_ing.unidad,
                    cantidad_presentacion=ing.cantidad_presentacion,
                    unidad_presentacion=ing.unidad_presentacion,
                    factor=factor,
                )
                filas.append([
                    "Ingrediente", repo.get_nombre_producto(ing.producto_id), "",
                    cantidad_mostrar, unidad_mostrar, "",
                ])

            for extra in rr.extras:
                nombre = repo.get_nombre_producto(extra.producto_id)
                producto = repo.get_producto(extra.producto_id)
                unidad = producto.unidad.value if producto else ""
                etiqueta = "c/ extra" if extra.cantidad > 0 else "s/"
                filas.append(["Extra/Omisión", nombre, etiqueta, abs(extra.cantidad), unidad, ""])
            for omision in rr.omisiones:
                nombre = repo.get_nombre_producto(omision.producto_id)
                filas.append(["Omisión", nombre, "Sin este ingrediente base", "—", "", ""])

        for ln in d.lineas:
            nombre = repo.get_nombre_producto(ln.producto_id)
            producto = repo.get_producto(ln.producto_id)
            unidad = producto.unidad.value if producto else ""
            filas.append(["Producto", nombre, "[extra]" if ln.es_extra else "", ln.cantidad, unidad, ln.coste])

        resultado.append(RegistroExportable(
            fecha=d.fecha,
            hora=d.hora,
            tipo="Desayuno",
            identificador=d.id,
            usuario=d.registrado_por or None,
            columnas=columnas,
            filas=filas,
            resumen=[
                ("Huéspedes", str(d.num_huespedes)),
                ("Coste total", repo.formato_precio(d.coste_total)),
                ("Estado", "Anulado" if getattr(d, "anulado", False) else "Activo"),
            ],
        ))
    return resultado


def configuracion_exportacion() -> ConfiguracionExportacionModulo:
    return ConfiguracionExportacionModulo(
        tipo="desayuno",
        titulo_documento="Registro de Desayuno",
        obtener_registros=registros_exportables,
    )


class DesayunoRegistroAdapter:
    """Fachada duck-typed para la UI compartida de registro (Fase 6).

    No fusiona storage: sigue usando desayunos[] y desayuno_service.
    """

    def __init__(self) -> None:
        self.tipo_servicio = TipoServicio.DESAYUNO.value
        self.etiqueta = "Desayuno"

    def productos_catalogo(self, buscar: str = "") -> list[dict]:
        return productos_catalogo(buscar, servicio=self.tipo_servicio)

    def get_cesta(self):
        return get_cesta()

    def get_cesta_recetas(self):
        return get_cesta_recetas()

    def get_mods_pendientes(self):
        return get_mods_pendientes()

    def limpiar_cesta(self) -> None:
        limpiar_cesta()

    def cesta_vacia(self) -> bool:
        return cesta_vacia()

    def anadir_mod_pendiente_receta(self, producto_id: str, cantidad: float) -> ResultadoOperacion:
        return anadir_mod_pendiente_receta(producto_id, cantidad)

    def quitar_mod_pendiente(self, mod_id: str) -> None:
        quitar_mod_pendiente(mod_id)

    def anadir_a_cesta(self, producto_id: str, cantidad: float) -> ResultadoOperacion:
        return anadir_a_cesta(producto_id, cantidad)

    def anadir_receta_a_cesta(self, receta_id: str, porciones: float, mods=None) -> ResultadoOperacion:
        return anadir_receta_a_cesta(receta_id, porciones, mods)

    def quitar_grupo_receta(self, grupo_id: str) -> None:
        quitar_grupo_receta(grupo_id)

    def quitar_linea_grupo(self, grupo_id: str, linea_id: str) -> None:
        quitar_linea_grupo(grupo_id, linea_id)

    def paso_linea_grupo(self, grupo_id: str, linea_id: str) -> float:
        return paso_linea_grupo(grupo_id, linea_id)

    def ajustar_linea_grupo(self, grupo_id: str, linea_id: str, delta: float) -> ResultadoOperacion:
        return ajustar_linea_grupo(grupo_id, linea_id, delta)

    def modificar_porciones_grupo(self, grupo_id: str, porciones: float) -> ResultadoOperacion:
        return modificar_porciones_grupo(grupo_id, porciones)

    def ajustar_porciones_grupo(self, grupo_id: str, delta: float) -> ResultadoOperacion:
        return ajustar_porciones_grupo(grupo_id, delta)

    def paso_linea_suelta(self, linea_id: str) -> float:
        return paso_linea_suelta(linea_id)

    def quitar_linea_suelta(self, linea_id: str) -> None:
        quitar_linea_suelta(linea_id)

    def ajustar_cantidad_suelto(self, linea_id: str, delta: float) -> ResultadoOperacion:
        return ajustar_cantidad_suelto(linea_id, delta)

    def coste_total_cesta(self) -> float:
        return coste_total_cesta()

    def previsualizar_stock(self) -> PlanDescuentoStock:
        return previsualizar_stock_registro()

    def registrar(
        self,
        fecha: date,
        num_huespedes: int = 0,
        *,
        ignorar_stock: bool = False,
        ctx: AppContext | None = None,
    ) -> ResultadoOperacion:
        return registrar_desayuno(
            fecha, int(num_huespedes), ignorar_stock=ignorar_stock, ctx=ctx,
        )

    def historial_ordenado(self, *, ctx: AppContext | None = None):
        data = _ctx(ctx).data()
        return sorted(
            data.desayunos,
            key=lambda r: (r.fecha, r.hora or time.min),
            reverse=True,
        )

    def registros_exportables(
        self,
        inicio: date,
        hasta: datetime,
        *,
        ctx: AppContext | None = None,
    ):
        return registros_exportables(inicio, hasta, ctx=ctx)

    def configuracion_exportacion(self) -> ConfiguracionExportacionModulo:
        return configuracion_exportacion()


desayuno_registro = DesayunoRegistroAdapter()
