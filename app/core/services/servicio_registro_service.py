"""Motor común de registro de servicio (comida / cena / bebidas).

Configurable por `tipo_servicio`, prefijo de sesión y categorías de receta
permitidas. Desayuno sigue en `desayuno_service` (datos históricos en
`AppData.desayunos`); este motor escribe en `AppData.registros_servicio`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from app.core.models import (
    AppData,
    CategoriaReceta,
    ExtraRecetaServicio,
    LineaServicio,
    OmisionRecetaServicio,
    RegistroRecetaServicio,
    RegistroServicio,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services.cesta_service import (
    GrupoRecetaCesta,
    ModPendienteReceta,
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
    planificar_descuento,
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
    stock_disponible,
)
from app.core.services.stock_service import disponible_en_servicio
from app.core.services.text_search import coincide_busqueda
from app.core.services.receta_service import factor_desde_registro_receta
from app.core.services.unidad_service import resolver_presentacion
from app.core.storage.session_store import get_data, persist_data
from app.core.application.context import AppContext
from app.core.application.id_generator import next_id

TITULOS = {
    "comida": "Registro de Comida",
    "cena": "Registro de Cena",
    "bebidas": "Registro de Bebidas",
}

ETIQUETAS_TIPO = {
    "comida": "Comida",
    "cena": "Cena",
    "bebidas": "Bebidas",
}

ID_PREFIX = {
    "comida": "co",
    "cena": "ce",
    "bebidas": "be",
}


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


class ServicioRegistro:
    """API de cesta + registro + exportación para un tipo de servicio."""

    def __init__(
        self,
        tipo_servicio: str,
        session_prefix: str,
        categorias_receta_permitidas: list[CategoriaReceta],
        *,
        solo_bebidas_sueltas: bool = False,
        titulo_documento: str | None = None,
        export_tipo: str | None = None,
    ) -> None:
        self.tipo_servicio = tipo_servicio
        self.categorias_permitidas = list(categorias_receta_permitidas)
        self.solo_bebidas_sueltas = solo_bebidas_sueltas
        self.titulo_documento = titulo_documento or TITULOS.get(tipo_servicio, f"Registro de {tipo_servicio}")
        self.etiqueta = ETIQUETAS_TIPO.get(tipo_servicio, tipo_servicio.capitalize())
        self._id_prefix = ID_PREFIX.get(tipo_servicio, tipo_servicio[:2])
        # Clave de meta/carpeta de exportación; independiente de tipo_servicio
        # para no chocar con exportaciones de stock u otros módulos.
        self._export_tipo = export_tipo or tipo_servicio
        self._cesta = crear_motor_cesta(session_prefix)

    # --- Cesta (delegación) -------------------------------------------------

    def get_cesta(self):
        return self._cesta.get_cesta()

    def get_cesta_recetas(self):
        return self._cesta.get_cesta_recetas()

    def get_mods_pendientes(self):
        return self._cesta.get_mods_pendientes()

    def limpiar_mods_pendientes(self) -> None:
        self._cesta.limpiar_mods_pendientes()

    def limpiar_cesta(self) -> None:
        self._cesta.limpiar_cesta()

    def cesta_vacia(self) -> bool:
        return self._cesta.cesta_vacia()

    def anadir_a_cesta(
        self,
        producto_id: str,
        cantidad: float,
        *,
        ctx: AppContext | None = None,
    ) -> ResultadoOperacion:
        if self.solo_bebidas_sueltas:
            data = _ctx(ctx).data()
            producto = DataRepository(data).get_producto(producto_id)
            if producto and not producto.es_bebida:
                return ResultadoOperacion(
                    False,
                    "En el registro de bebidas solo se pueden añadir productos marcados como bebida.",
                )
        r = self._cesta.anadir_a_cesta(producto_id, cantidad)
        return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)

    def anadir_receta_a_cesta(
        self,
        receta_id: str,
        porciones: float,
        mods_pendientes: list[ModPendienteReceta] | None = None,
    ) -> ResultadoOperacion:
        r = self._cesta.anadir_receta_a_cesta(
            receta_id,
            porciones,
            mods_pendientes,
            categorias_permitidas=self.categorias_permitidas,
        )
        return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)

    def anadir_mod_pendiente_receta(self, producto_id: str, cantidad: float) -> ResultadoOperacion:
        r = self._cesta.anadir_mod_pendiente_receta(producto_id, cantidad)
        return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)

    def quitar_mod_pendiente(self, mod_id: str) -> None:
        self._cesta.quitar_mod_pendiente(mod_id)

    def quitar_grupo_receta(self, grupo_id: str) -> None:
        self._cesta.quitar_grupo_receta(grupo_id)

    def quitar_linea_grupo(self, grupo_id: str, linea_id: str) -> None:
        self._cesta.quitar_linea_grupo(grupo_id, linea_id)

    def paso_linea_grupo(self, grupo_id: str, linea_id: str) -> float:
        return self._cesta.paso_linea_grupo(grupo_id, linea_id)

    def ajustar_linea_grupo(self, grupo_id: str, linea_id: str, delta: float) -> ResultadoOperacion:
        r = self._cesta.ajustar_linea_grupo(grupo_id, linea_id, delta)
        return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)

    def modificar_linea_grupo(self, grupo_id: str, linea_id: str, cantidad: float) -> ResultadoOperacion:
        r = self._cesta.modificar_linea_grupo(grupo_id, linea_id, cantidad)
        return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)

    def modificar_porciones_grupo(self, grupo_id: str, porciones: float) -> ResultadoOperacion:
        r = self._cesta.modificar_porciones_grupo(grupo_id, porciones)
        return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)

    def ajustar_porciones_grupo(self, grupo_id: str, delta: float) -> ResultadoOperacion:
        r = self._cesta.ajustar_porciones_grupo(grupo_id, delta)
        return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)

    def paso_linea_suelta(self, linea_id: str) -> float:
        return self._cesta.paso_linea_suelta(linea_id)

    def quitar_linea_suelta(self, linea_id: str) -> None:
        self._cesta.quitar_linea_suelta(linea_id)

    def ajustar_cantidad_suelto(self, linea_id: str, delta: float) -> ResultadoOperacion:
        r = self._cesta.ajustar_cantidad_suelto(linea_id, delta)
        return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)

    def modificar_cantidad_suelto(self, linea_id: str, cantidad: float) -> ResultadoOperacion:
        r = self._cesta.modificar_cantidad_suelto(linea_id, cantidad)
        return ResultadoOperacion(r.ok, r.mensaje, r.codigo, r.detalle_stock)

    def coste_total_cesta(self, *, ctx: AppContext | None = None) -> float:
        data = _ctx(ctx).data()
        total = sum(
            calcular_coste_linea(data, l.producto_id, max(l.cantidad, 0))
            for l in self.get_cesta()
        )
        for grupo in self.get_cesta_recetas():
            for ing in grupo.ingredientes:
                total += calcular_coste_linea(data, ing.producto_id, max(ing.cantidad, 0))
        return round(total, 2)

    def productos_catalogo(self, buscar: str = "", *, ctx: AppContext | None = None) -> list[dict]:
        data = _ctx(ctx).data()
        resultado = []
        termino = buscar.strip()
        for producto in sorted(data.productos, key=lambda p: p.nombre):
            if not getattr(producto, "activo", True):
                continue
            if self.solo_bebidas_sueltas and not producto.es_bebida:
                continue
            if not disponible_en_servicio(producto.servicios_disponibles, self.tipo_servicio):
                continue
            if termino and not coincide_busqueda(producto.nombre, termino):
                continue
            stock = stock_disponible(data, producto.id)
            resultado.append({
                "id": producto.id,
                "nombre": producto.nombre,
                "unidad": producto.unidad.value,
                "stock": stock,
                "es_bebida": bool(getattr(producto, "es_bebida", False)),
                "etiqueta": f"{producto.nombre} ({stock:g} {producto.unidad.value})",
            })
        return resultado

    def productos_disponibles(self, buscar: str = "") -> list[dict]:
        return [p for p in self.productos_catalogo(buscar) if p["stock"] > 0]

    # --- Persistencia -------------------------------------------------------

    def _aplanar_cesta(self) -> dict[str, tuple[float, bool]]:
        fusionado: dict[str, tuple[float, bool]] = {}
        for linea in self.get_cesta():
            cantidad, es_extra = fusionado.get(linea.producto_id, (0.0, False))
            fusionado[linea.producto_id] = (
                round(cantidad + linea.cantidad, 4),
                es_extra or linea.es_extra,
            )
        for grupo in self.get_cesta_recetas():
            for ing in grupo.ingredientes:
                cantidad, es_extra = fusionado.get(ing.producto_id, (0.0, False))
                fusionado[ing.producto_id] = (
                    round(cantidad + ing.cantidad, 4),
                    es_extra or ing.es_extra,
                )
        return {pid: (max(c, 0), e) for pid, (c, e) in fusionado.items() if c != 0}

    def _construir_registros_recetas(
        self, data: AppData, grupos: list[GrupoRecetaCesta],
    ) -> list[RegistroRecetaServicio]:
        repo = DataRepository(data)
        registros: list[RegistroRecetaServicio] = []
        for grupo in grupos:
            receta = repo.get_receta(grupo.receta_id)
            template_ids = {i.producto_id for i in receta.ingredientes} if receta else set()
            presentes_base = {
                i.producto_id for i in grupo.ingredientes
                if i.es_base_receta and i.cantidad > 0
            }
            omisiones = [
                OmisionRecetaServicio(pid)
                for pid in sorted(template_ids - presentes_base)
            ]
            extras: list[ExtraRecetaServicio] = []
            for i in grupo.ingredientes:
                if i.es_base_receta and i.cantidad < 0:
                    extras.append(ExtraRecetaServicio(i.producto_id, i.cantidad))
                elif i.es_extra or (not i.es_base_receta and i.cantidad > 0):
                    extras.append(ExtraRecetaServicio(i.producto_id, i.cantidad))
                elif i.es_omision or (not i.es_base_receta and i.cantidad < 0):
                    extras.append(ExtraRecetaServicio(i.producto_id, i.cantidad))
            cat = receta.categoria.value if receta else None
            registros.append(RegistroRecetaServicio(
                grupo.receta_id,
                grupo.nombre_receta,
                grupo.porciones,
                extras,
                omisiones,
                categoria_receta=cat,
                categoria_receta_snapshot=cat,
                porciones_estandar_snapshot=grupo.porciones_estandar,
                factor_aplicado=grupo.factor_aplicado,
            ))
        return registros

    def _plan_stock(
        self,
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

    def previsualizar_stock(self, *, ctx: AppContext | None = None) -> PlanDescuentoStock:
        if self.cesta_vacia():
            return PlanDescuentoStock()
        return self._plan_stock(_ctx(ctx).data(), self._aplanar_cesta())

    def registrar(
        self,
        fecha: date,
        num_huespedes: int = 0,
        *,
        ignorar_stock: bool = False,
        clave_idempotencia: str | None = None,
        ctx: AppContext | None = None,
    ) -> ResultadoOperacion:
        """Registra con descuento atómico. `ignorar_stock` deshabilitado (Fase 9)."""
        from app.core.auth.permissions import Permiso
        from app.core.auth.session import session_tiene_permiso
        from app.core.auth.usecase_guard import usecase_deny_message

        denied = usecase_deny_message(Permiso.ACCEDER_REGISTRO)
        if denied:
            return ResultadoOperacion(False, denied)

        _ = ignorar_stock

        if self.cesta_vacia():
            return ResultadoOperacion(
                False,
                "La cesta está vacía. Añada productos o recetas antes de registrar.",
            )
        context = _ctx(ctx)
        if fecha > context.clock.today():
            return ResultadoOperacion(False, f"No puede registrar {self.etiqueta.lower()} en fechas futuras.")

        data = context.data()
        clave = (clave_idempotencia or "").strip() or None
        if clave:
            existente = next(
                (
                    r for r in data.registros_servicio
                    if r.tipo_servicio == self.tipo_servicio
                    and getattr(r, "clave_idempotencia", None) == clave
                    and not getattr(r, "anulado", False)
                ),
                None,
            )
            if existente is not None:
                return ResultadoOperacion(
                    True,
                    f"{self.etiqueta} ya confirmada — ref. {existente.id}.",
                    codigo="IDEMPOTENTE",
                )

        fusionado = self._aplanar_cesta()
        grupos = list(self.get_cesta_recetas())
        cesta_suelta = list(self.get_cesta())

        plan = self._plan_stock(data, fusionado)
        if not plan.ok:
            return ResultadoOperacion(
                False,
                f"Stock insuficiente para registrar {self.etiqueta.lower()}. "
                "No se ha modificado nada.",
                codigo="STOCK_INSUFICIENTE",
                detalle_stock=plan.deficits,
            )

        existentes = [r.id for r in data.registros_servicio if r.tipo_servicio == self.tipo_servicio]
        existentes += [r.id for r in data.registros_servicio]
        registro_id = next_id(self._id_prefix, existentes)

        demandas = {pid: cant for pid, (cant, _) in fusionado.items() if cant > 0}
        extras = {pid: es_extra for pid, (cant, es_extra) in fusionado.items() if cant > 0}

        snap = snapshot_cantidades_restantes(data)
        n_regs = len(data.registros_servicio)
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
                LineaServicio(pid, demandas[pid], costes_agregados.get(pid, 0.0), extras[pid])
                for pid in demandas
            ]
            cantidades_agregadas = dict(demandas)

            lineas_detalle = construir_lineas_detalle(
                cesta_suelta,
                grupos,
                tipo_servicio=self.tipo_servicio,
                registro_id=registro_id,
                data=data,
            )
            asignar_costes_proporcionales(lineas_detalle, costes_agregados, cantidades_agregadas)
            asignar_consumos_lote(lineas_detalle, resultado_desc.movimientos)
            validar_consumos_lote(
                lineas_detalle, resultado_desc.movimientos, costes_agregados, data,
            )

            registros_recetas = self._construir_registros_recetas(data, grupos)
            coste_total = round(sum(l.coste for l in lineas), 2)
            registro = RegistroServicio(
                registro_id,
                self.tipo_servicio,
                fecha,
                lineas,
                coste_total,
                context.actor.nombre,
                num_huespedes,
                registros_recetas,
                context.clock.now().time(),
                lineas_detalle,
                clave_idempotencia=clave,
            )
            data.registros_servicio.append(registro)

            from app.core.services import movimiento_service as mov_svc

            mov_svc.escribir_espejos_consumo_registro(
                origen_tipo=mov_svc.ORIGEN_TIPO_REGISTRO_SERVICIO,
                registro_id=registro_id,
                lineas_detalle=lineas_detalle,
                fecha=fecha,
                hora=registro.hora,
                usuario_id=context.actor.id or None,
                ctx=context,
            )

            detalle_recetas = f" — {len(registros_recetas)} receta(s)" if registros_recetas else ""
            ver_costes = session_tiene_permiso(Permiso.CONSULTAR_COSTES)
            resumen_econ = f" — {coste_total:.2f} €" if ver_costes else ""
            _registrar_actividad(
                context,
                f"Registro {self.etiqueta.lower()}",
                (
                    f"{self.etiqueta} del {fecha.strftime('%d/%m/%Y')}"
                    f"{resumen_econ}{detalle_recetas}"
                ),
            )
            context.uow.commit(data)
        except Exception:
            restaurar_cantidades_restantes(data, snap)
            del data.registros_servicio[n_regs:]
            del data.movimientos[n_movimientos:]
            if len(data.actividades) > n_actividades:
                del data.actividades[n_actividades:]
            raise

        self.limpiar_cesta()

        from app.core.services.alert_service import sincronizar_alertas
        sincronizar_alertas(context)

        ver_costes = session_tiene_permiso(Permiso.CONSULTAR_COSTES)
        if ver_costes:
            msg = (
                f"{self.etiqueta} registrada — ref. {registro_id} — "
                f"{coste_total:.2f} € ({len(lineas)} producto(s))."
            )
        else:
            msg = (
                f"{self.etiqueta} registrada — ref. {registro_id} "
                f"({len(lineas)} producto(s))."
            )
        return ResultadoOperacion(True, msg)

    def historial_ordenado(self, *, ctx: AppContext | None = None) -> list[RegistroServicio]:
        data = _ctx(ctx).data()
        return sorted(
            [r for r in data.registros_servicio if r.tipo_servicio == self.tipo_servicio],
            key=lambda r: (r.fecha, r.hora or time.min),
            reverse=True,
        )

    def fecha_mas_antigua(self, *, ctx: AppContext | None = None) -> date | None:
        fechas = [
            r.fecha for r in _ctx(ctx).data().registros_servicio
            if r.tipo_servicio == self.tipo_servicio
        ]
        return min(fechas) if fechas else None

    def registros_exportables(
        self,
        inicio: date,
        hasta: datetime,
        *,
        ctx: AppContext | None = None,
    ) -> list[RegistroExportable]:
        data = _ctx(ctx).data()
        repo = DataRepository(data)
        fin = hasta.date()
        columnas = ["Tipo", "Producto / Receta", "Detalle", "Cantidad", "Unidad", "Coste", "Origen"]

        resultado: list[RegistroExportable] = []
        for reg in data.registros_servicio:
            if reg.tipo_servicio != self.tipo_servicio:
                continue
            if not (inicio <= reg.fecha <= fin):
                continue

            filas: list[list] = []
            for rr in reg.registros_recetas:
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
                    rr.categoria_receta or "",
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
                        cantidad_mostrar, unidad_mostrar, "", "ingrediente_receta",
                    ])
                for extra in rr.extras:
                    nombre = repo.get_nombre_producto(extra.producto_id)
                    producto = repo.get_producto(extra.producto_id)
                    unidad = producto.unidad.value if producto else ""
                    etiqueta = "c/ extra" if extra.cantidad > 0 else "s/"
                    filas.append([
                        "Extra/Omisión", nombre, etiqueta, abs(extra.cantidad), unidad, "", "extra_receta",
                    ])

            for det in reg.lineas_detalle:
                if det.origen != "producto_directo":
                    continue
                nombre = repo.get_nombre_producto(det.producto_id)
                producto = repo.get_producto(det.producto_id)
                unidad = producto.unidad.value if producto else ""
                filas.append([
                    "Producto", nombre, "", det.cantidad, unidad, det.coste, det.origen,
                ])

            resultado.append(RegistroExportable(
                fecha=reg.fecha,
                hora=reg.hora,
                tipo=self.etiqueta,
                identificador=reg.id,
                usuario=reg.registrado_por or None,
                columnas=columnas,
                filas=filas,
                resumen=[
                    ("Coste total", repo.formato_precio(reg.coste_total)),
                    ("Estado", "Anulado" if getattr(reg, "anulado", False) else "Activo"),
                ],
            ))
        return resultado

    def configuracion_exportacion(self) -> ConfiguracionExportacionModulo:
        return ConfiguracionExportacionModulo(
            tipo=self._export_tipo,
            titulo_documento=self.titulo_documento,
            obtener_registros=self.registros_exportables,
        )


def crear_servicio(
    tipo_servicio: str,
    session_prefix: str,
    categorias_receta_permitidas: list[CategoriaReceta],
    *,
    solo_bebidas_sueltas: bool = False,
    titulo_documento: str | None = None,
    export_tipo: str | None = None,
) -> ServicioRegistro:
    return ServicioRegistro(
        tipo_servicio,
        session_prefix,
        categorias_receta_permitidas,
        solo_bebidas_sueltas=solo_bebidas_sueltas,
        titulo_documento=titulo_documento,
        export_tipo=export_tipo,
    )


# Reexport útiles para páginas futuras
__all__ = [
    "ServicioRegistro",
    "ResultadoOperacion",
    "crear_servicio",
    "etiqueta_linea_suelta",
    "etiqueta_linea_receta",
    "calcular_coste_linea",
    "stock_disponible",
]
