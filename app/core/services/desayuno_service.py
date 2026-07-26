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
    asignar_costes_proporcionales,
    construir_lineas_detalle,
)
from app.core.services.excel_bloques import RegistroExportable
from app.core.services.exportacion_semanal_service import ConfiguracionExportacionModulo
from app.core.services.inventory_batch_service import (
    PlanDescuentoStock,
    aplicar_descuento_atomico,
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
    from app.core.models import Actividad

    actividad = Actividad(
        _next_id("act", [a.id for a in data.actividades]),
        datetime.now(),
        _nombre_usuario(data),
        accion,
        detalle,
    )
    data.actividades.insert(0, actividad)


def _descontar_fifo(data: AppData, producto_id: str, cantidad: float, *, permitir_negativo: bool = False) -> float:
    """Alias interno: el comportamiento sigue siendo FIFO por fecha_compra."""
    return descontar_lotes(data, producto_id, cantidad, permitir_negativo=permitir_negativo)


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


def productos_catalogo(buscar: str = "", *, servicio: str | None = None) -> list[dict]:
    data = get_data()
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


def productos_disponibles(buscar: str = "", *, servicio: str | None = None) -> list[dict]:
    return [p for p in productos_catalogo(buscar, servicio=servicio) if p["stock"] > 0]


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


def coste_total_cesta() -> float:
    data = get_data()
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


def previsualizar_stock_registro() -> PlanDescuentoStock:
    """Preview actual/salida/resultante de la cesta (sin mutar)."""
    if cesta_vacia():
        return PlanDescuentoStock()
    return _plan_stock_fusionado(get_data(), _aplanar_cesta())


def registrar_desayuno(
    fecha: date,
    num_huespedes: int,
    *,
    ignorar_stock: bool = False,
) -> ResultadoOperacion:
    """Registra el desayuno con descuento atómico.

    `ignorar_stock` queda deshabilitado (Fase 9): se ignora el bypass.
    """
    _ = ignorar_stock  # Bypass retirado; no permitir stock negativo.

    if cesta_vacia():
        return ResultadoOperacion(
            False,
            "La cesta está vacía. Añada productos o recetas antes de registrar.",
        )

    if fecha > date.today():
        return ResultadoOperacion(False, "No puede registrar desayunos en fechas futuras.")

    if num_huespedes < 1:
        return ResultadoOperacion(False, "Indique al menos 1 huésped.")

    data = get_data()

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

    registro_id = _next_id("d", [d.id for d in data.desayunos])
    demandas = {pid: cant for pid, (cant, _) in fusionado.items() if cant > 0}
    extras = {pid: es_extra for pid, (cant, es_extra) in fusionado.items() if cant > 0}

    snap = snapshot_cantidades_restantes(data)
    n_desayunos = len(data.desayunos)
    n_actividades = len(data.actividades)
    try:
        costes_agregados = aplicar_descuento_atomico(data, demandas)
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

        registros_recetas = _construir_registros_recetas(data, grupos)
        coste_total = round(sum(l.coste for l in lineas), 2)
        registro = RegistroDesayuno(
            registro_id,
            fecha,
            lineas,
            coste_total,
            _nombre_usuario(data),
            num_huespedes,
            registros_recetas,
            datetime.now().time(),
            lineas_detalle,
        )
        data.desayunos.append(registro)

        detalle_recetas = ""
        if registros_recetas:
            detalle_recetas = f" — {len(registros_recetas)} receta(s)"

        _registrar_actividad(
            data,
            "Registro desayuno",
            f"Desayuno del {fecha.strftime('%d/%m/%Y')} — {coste_total:.2f} € — {num_huespedes} huéspedes{detalle_recetas}",
        )
        persist_data(data)
    except Exception:
        restaurar_cantidades_restantes(data, snap)
        del data.desayunos[n_desayunos:]
        del data.actividades[: max(0, len(data.actividades) - n_actividades)]
        raise

    limpiar_cesta()

    from app.core.services.alert_service import sincronizar_alertas
    sincronizar_alertas()

    return ResultadoOperacion(
        True,
        f"Desayuno registrado — {coste_total:.2f} € ({len(lineas)} producto(s)).",
    )


def fecha_mas_antigua() -> date | None:
    fechas = [d.fecha for d in get_data().desayunos]
    return min(fechas) if fechas else None


def registros_exportables(inicio: date, hasta: datetime) -> list[RegistroExportable]:
    data = get_data()
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
    ) -> ResultadoOperacion:
        return registrar_desayuno(fecha, int(num_huespedes), ignorar_stock=ignorar_stock)

    def historial_ordenado(self):
        data = get_data()
        return sorted(
            data.desayunos,
            key=lambda r: (r.fecha, r.hora or time.min),
            reverse=True,
        )

    def registros_exportables(self, inicio: date, hasta: datetime):
        return registros_exportables(inicio, hasta)

    def configuracion_exportacion(self) -> ConfiguracionExportacionModulo:
        return configuracion_exportacion()


desayuno_registro = DesayunoRegistroAdapter()
