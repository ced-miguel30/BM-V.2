"""Servicio de gestión de stock — productos y lotes."""

from dataclasses import dataclass
from datetime import date, datetime

from app.core.models import Actividad, AppData, LoteStock, Producto, UnidadProducto
from app.core.models.enums import SERVICIOS_DISPONIBLES_VALORES
from app.core.repositories.data_repository import DataRepository
from app.core.services.excel_bloques import RegistroExportable
from app.core.services.exportacion_semanal_service import ConfiguracionExportacionModulo
from app.core.services.formatting import formato_fecha, formato_moneda
from app.core.storage.session_store import get_data, persist_data

UNIDADES = [u.value for u in UnidadProducto]


def normalizar_servicios_disponibles(valores: list[str] | None) -> list[str]:
    """Filtra y ordena valores válidos; no inventa servicios si la lista está vacía."""
    if not valores:
        return []
    orden = ["desayuno", "comida", "cena", "bebidas"]
    limpios = []
    for v in valores:
        if not isinstance(v, str):
            continue
        clave = v.strip().lower()
        if clave in SERVICIOS_DISPONIBLES_VALORES and clave not in limpios:
            limpios.append(clave)
    return [s for s in orden if s in limpios]


def normalizar_categoria_inventario(valor: str | None) -> str | None:
    if valor is None:
        return None
    texto = valor.strip()
    return texto or None


def disponible_en_servicio(
    servicios_disponibles: list[str] | None,
    servicio: str,
    *,
    permitir_general_sin_filtro: bool = True,
) -> bool:
    """True si el ítem puede usarse en el servicio de registro/merma.

    Lista vacía ≠ todos: sin configurar no está disponible.
    Para merma «general» (almacén), por defecto no se exige etiqueta de servicio
    de registro (general no forma parte de servicios_disponibles).
    """
    if servicio == "general" and permitir_general_sin_filtro:
        return True
    if not servicios_disponibles:
        return False
    return servicio in servicios_disponibles


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


def _next_id(prefix: str, ids: list[str]) -> str:
    from app.core.application.id_generator import next_id

    return next_id(prefix, ids)

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


def _normalizar_nombre_producto(nombre: str) -> str:
    return " ".join((nombre or "").strip().split())


def _nombre_duplicado(
    data: AppData, nombre: str, *, excluir_id: str | None = None
) -> bool:
    nombre_norm = _normalizar_nombre_producto(nombre).lower()
    for p in data.productos:
        if excluir_id and p.id == excluir_id:
            continue
        if _normalizar_nombre_producto(p.nombre).lower() == nombre_norm:
            return True
    return False


def _validar_stock_minimo(
    stock_minimo: float | None,
) -> tuple[float | None, str | None]:
    if stock_minimo is None or stock_minimo == "":
        return None, None
    try:
        valor = float(stock_minimo)
    except (TypeError, ValueError):
        return None, "El stock mínimo no es un número válido."
    if valor < 0:
        return None, "El stock mínimo no puede ser negativo."
    if valor == 0:
        return None, None
    return valor, None


def resumen_uso_producto(data: AppData, producto_id: str) -> dict[str, int]:
    """Conteos de referencias operativas (para UI y protecciones)."""
    n_recetas = sum(
        1
        for r in data.recetas
        if any(i.producto_id == producto_id for i in r.ingredientes)
    )
    n_lotes = sum(1 for l in data.lotes if l.producto_id == producto_id)
    n_movs = sum(
        1
        for m in getattr(data, "movimientos", []) or []
        if getattr(m, "producto_id", None) == producto_id
    )
    n_docs = 0
    for d in getattr(data, "documentos", []) or []:
        for ln in getattr(d, "lineas", []) or []:
            if getattr(ln, "producto_id", None) == producto_id:
                n_docs += 1
                break
    n_rel = sum(
        1
        for r in getattr(data, "relaciones_producto_proveedor", []) or []
        if r.producto_id == producto_id and getattr(r, "activo", True)
    )
    return {
        "recetas": n_recetas,
        "lotes": n_lotes,
        "movimientos": n_movs,
        "documentos": n_docs,
        "vinculos": n_rel,
    }


def producto_tiene_historico_unidad(data: AppData, producto_id: str) -> bool:
    """True si cambiar la unidad base invalidaría histórico."""
    uso = resumen_uso_producto(data, producto_id)
    return (
        uso["lotes"] > 0
        or uso["movimientos"] > 0
        or uso["documentos"] > 0
        or uso["recetas"] > 0
    )


def producto_tiene_referencias(data: AppData, producto_id: str) -> bool:
    uso = resumen_uso_producto(data, producto_id)
    return any(v > 0 for v in uso.values())


def crear_producto(
    nombre: str,
    unidad: str,
    stock_minimo: float | None,
    *,
    codigo: str,
    es_bebida: bool = False,
    servicios_disponibles: list[str] | None = None,
    categoria_inventario: str | None = None,
    categoria_id: str | None = None,
    subcategoria_id: str | None = None,
    departamento_ids: list[str] | None = None,
    ubicacion_ids: list[str] | None = None,
    tipo_articulo: str | None = None,
) -> ResultadoOperacion:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message
    from app.core.services.money import normalizar_codigo_funcional

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoOperacion(False, denied)

    nombre = _normalizar_nombre_producto(nombre)
    if not nombre:
        return ResultadoOperacion(
            False,
            "El nombre es obligatorio.",
        )
    if len(nombre) < 2:
        return ResultadoOperacion(False, "El nombre debe tener al menos 2 caracteres.")
    if unidad not in UNIDADES:
        return ResultadoOperacion(False, "Seleccione una unidad válida.")
    codigo_n = normalizar_codigo_funcional(codigo)
    if not codigo_n:
        return ResultadoOperacion(False, "El código es obligatorio en altas nuevas.")

    stock_min, err_sm = _validar_stock_minimo(stock_minimo)
    if err_sm:
        return ResultadoOperacion(False, err_sm)

    data = get_data()
    if any(
        normalizar_codigo_funcional(getattr(p, "codigo", None)) == codigo_n
        for p in data.productos
    ):
        return ResultadoOperacion(False, f"Ya existe un producto con código «{codigo_n}».")
    if _nombre_duplicado(data, nombre):
        tipo = "bebida" if es_bebida else "producto"
        return ResultadoOperacion(False, f"Ya existe un {tipo} llamado «{nombre}».")

    from app.core.services.catalogo_service import (
        normalizar_departamento_ids,
        normalizar_tipo_articulo_conocido,
        normalizar_ubicacion_ids,
        validar_referencias_producto,
        validar_tipo_articulo,
    )

    # Alta nueva: tipo obligatorio (sin backfill automático).
    v_tipo = validar_tipo_articulo(tipo_articulo, obligatorio=True)
    if not v_tipo.ok:
        return ResultadoOperacion(False, v_tipo.mensaje)
    tipo_norm = normalizar_tipo_articulo_conocido(tipo_articulo)

    deps = normalizar_departamento_ids(departamento_ids)
    ubis = normalizar_ubicacion_ids(ubicacion_ids)
    validacion = validar_referencias_producto(
        data,
        categoria_id=categoria_id or None,
        subcategoria_id=subcategoria_id or None,
        departamento_ids=deps,
        ubicacion_ids=ubis,
    )
    if not validacion.ok:
        return ResultadoOperacion(False, validacion.mensaje)

    prefix = "b" if es_bebida else "p"
    ids_mismo_tipo = [p.id for p in data.productos if p.id.startswith(prefix)]

    producto = Producto(
        _next_id(prefix, ids_mismo_tipo),
        nombre,
        UnidadProducto(unidad),
        stock_min,
        es_bebida=es_bebida,
        servicios_disponibles=normalizar_servicios_disponibles(servicios_disponibles),
        categoria_inventario=normalizar_categoria_inventario(categoria_inventario),
        categoria_id=categoria_id or None,
        subcategoria_id=subcategoria_id or None,
        departamento_ids=deps,
        ubicacion_ids=ubis,
        tipo_articulo=tipo_norm,
        codigo=codigo_n,
        activo=True,
    )
    data.productos.append(producto)
    accion = "Crear bebida" if es_bebida else "Crear producto"
    _registrar_actividad(data, accion, f"«{nombre}» ({unidad}) creado")
    persist_data(data)
    tipo_ok = "Bebida" if es_bebida else "Producto"
    return ResultadoOperacion(True, f"{tipo_ok} «{nombre}» creado correctamente.")


def crear_bebida(
    nombre: str,
    unidad: str,
    stock_minimo: float | None,
    *,
    codigo: str,
    servicios_disponibles: list[str] | None = None,
    categoria_inventario: str | None = None,
    categoria_id: str | None = None,
    subcategoria_id: str | None = None,
    departamento_ids: list[str] | None = None,
    ubicacion_ids: list[str] | None = None,
    tipo_articulo: str | None = None,
) -> ResultadoOperacion:
    """Alias para crear un producto marcado como bebida."""
    return crear_producto(
        nombre,
        unidad,
        stock_minimo,
        codigo=codigo,
        es_bebida=True,
        servicios_disponibles=servicios_disponibles,
        categoria_inventario=categoria_inventario,
        categoria_id=categoria_id,
        subcategoria_id=subcategoria_id,
        departamento_ids=departamento_ids,
        ubicacion_ids=ubicacion_ids,
        tipo_articulo=tipo_articulo,
    )


def editar_producto_catalogo(
    producto_id: str,
    *,
    servicios_disponibles: list[str] | None = None,
    categoria_inventario: str | None = None,
    categoria_id: str | None = None,
    subcategoria_id: str | None = None,
    departamento_ids: list[str] | None = None,
    ubicacion_ids: list[str] | None = None,
    tipo_articulo: str | None = None,
) -> ResultadoOperacion:
    """Actualiza campos de catálogo (servicios / categoría / FKs 6A–6C).

    Excepción temporal: un histórico sin clasificar puede seguir con
    ``tipo_articulo=None`` al editar otros campos (sin clasificación automática).
    """
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoOperacion(False, denied)

    data = get_data()
    producto = next((p for p in data.productos if p.id == producto_id), None)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    from app.core.services.catalogo_service import (
        normalizar_departamento_ids,
        normalizar_tipo_articulo_conocido,
        normalizar_ubicacion_ids,
        validar_referencias_producto,
        validar_tipo_articulo,
    )

    # Histórico: None permitido; no forzar consumible.
    v_tipo = validar_tipo_articulo(tipo_articulo, obligatorio=False)
    if not v_tipo.ok:
        return ResultadoOperacion(False, v_tipo.mensaje)
    if tipo_articulo in (None, "", "sin_clasificar"):
        tipo_norm: object | None = None
    else:
        tipo_norm = normalizar_tipo_articulo_conocido(tipo_articulo)
        if tipo_norm is None and tipo_articulo:
            # Conservar desconocido ya cargado si se reenvía igual
            tipo_norm = tipo_articulo

    deps = normalizar_departamento_ids(departamento_ids)
    ubis = normalizar_ubicacion_ids(ubicacion_ids)
    validacion = validar_referencias_producto(
        data,
        categoria_id=categoria_id or None,
        subcategoria_id=subcategoria_id or None,
        departamento_ids=deps,
        ubicacion_ids=ubis,
        categoria_id_anterior=producto.categoria_id,
        subcategoria_id_anterior=producto.subcategoria_id,
        departamento_ids_anteriores=list(producto.departamento_ids),
        ubicacion_ids_anteriores=list(getattr(producto, "ubicacion_ids", []) or []),
    )
    if not validacion.ok:
        return ResultadoOperacion(False, validacion.mensaje)

    producto.servicios_disponibles = normalizar_servicios_disponibles(servicios_disponibles)
    producto.categoria_inventario = normalizar_categoria_inventario(categoria_inventario)
    producto.categoria_id = categoria_id or None
    producto.subcategoria_id = subcategoria_id or None
    producto.departamento_ids = deps
    producto.ubicacion_ids = ubis
    producto.tipo_articulo = tipo_norm  # type: ignore[assignment]
    _registrar_actividad(
        data,
        "Editar catálogo producto",
        f"«{producto.nombre}»: catálogo / tipo de artículo actualizados",
    )
    persist_data(data)
    return ResultadoOperacion(True, f"Producto «{producto.nombre}» actualizado.")


def editar_producto(
    producto_id: str,
    *,
    nombre: str | None = None,
    stock_minimo=...,
    unidad: str | None = None,
) -> ResultadoOperacion:
    """Edita nombre, stock mínimo y (si no hay histórico) unidad base."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoOperacion(False, denied)

    data = get_data()
    producto = next((p for p in data.productos if p.id == producto_id), None)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    if nombre is not None:
        nom = _normalizar_nombre_producto(nombre)
        if len(nom) < 2:
            return ResultadoOperacion(False, "El nombre debe tener al menos 2 caracteres.")
        if _nombre_duplicado(data, nom, excluir_id=producto_id):
            tipo = "bebida" if producto.es_bebida else "producto"
            return ResultadoOperacion(False, f"Ya existe un {tipo} llamado «{nom}».")
        producto.nombre = nom

    if stock_minimo is not ...:
        sm, err_sm = _validar_stock_minimo(stock_minimo)
        if err_sm:
            return ResultadoOperacion(False, err_sm)
        producto.stock_minimo = sm

    if unidad is not None:
        if unidad not in UNIDADES:
            return ResultadoOperacion(False, "Seleccione una unidad válida.")
        unidad_actual = (
            producto.unidad.value
            if hasattr(producto.unidad, "value")
            else str(producto.unidad)
        )
        if unidad != unidad_actual:
            if producto_tiene_historico_unidad(data, producto_id):
                uso = resumen_uso_producto(data, producto_id)
                partes = []
                if uso["lotes"]:
                    partes.append(f"{uso['lotes']} lote(s)")
                if uso["movimientos"]:
                    partes.append(f"{uso['movimientos']} movimiento(s)")
                if uso["documentos"]:
                    partes.append(f"{uso['documentos']} documento(s)")
                if uso["recetas"]:
                    partes.append(f"{uso['recetas']} receta(s)")
                detalle = ", ".join(partes) or "histórico operativo"
                return ResultadoOperacion(
                    False,
                    "No se puede cambiar la unidad base: el producto tiene "
                    f"{detalle}. El histórico no se convierte automáticamente.",
                )
            producto.unidad = UnidadProducto(unidad)

    _registrar_actividad(data, "Editar producto", f"«{producto.nombre}» actualizado")
    persist_data(data)
    return ResultadoOperacion(True, f"Producto «{producto.nombre}» actualizado.")


def desactivar_producto(producto_id: str) -> ResultadoOperacion:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoOperacion(False, denied)

    data = get_data()
    producto = next((p for p in data.productos if p.id == producto_id), None)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")
    if not getattr(producto, "activo", True):
        return ResultadoOperacion(False, "El producto ya está inactivo.")
    producto.activo = False
    _registrar_actividad(data, "Desactivar producto", f"«{producto.nombre}» desactivado")
    persist_data(data)
    return ResultadoOperacion(
        True,
        f"Producto «{producto.nombre}» desactivado. "
        "No aparecerá en compras ni recetas nuevas; el histórico se conserva.",
    )


def reactivar_producto(producto_id: str) -> ResultadoOperacion:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoOperacion(False, denied)

    data = get_data()
    producto = next((p for p in data.productos if p.id == producto_id), None)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")
    if getattr(producto, "activo", True):
        return ResultadoOperacion(False, "El producto ya está activo.")
    producto.activo = True
    _registrar_actividad(data, "Reactivar producto", f"«{producto.nombre}» reactivado")
    persist_data(data)
    return ResultadoOperacion(True, f"Producto «{producto.nombre}» reactivado.")


def eliminar_producto(producto_id: str) -> ResultadoOperacion:
    """Eliminación física solo sin referencias; con histórico → desactivar."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoOperacion(False, denied)

    data = get_data()
    producto = next((p for p in data.productos if p.id == producto_id), None)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")
    if producto_tiene_referencias(data, producto_id):
        uso = resumen_uso_producto(data, producto_id)
        return ResultadoOperacion(
            False,
            (
                f"No se puede eliminar el producto «{producto.nombre}» porque tiene "
                f"histórico (recetas={uso['recetas']}, lotes={uso['lotes']}, "
                f"movimientos={uso['movimientos']}, documentos={uso['documentos']}). "
                "Desactívelo en su lugar."
            ),
        )
    nombre = producto.nombre
    data.productos = [p for p in data.productos if p.id != producto_id]
    _registrar_actividad(data, "Eliminar producto", f"«{nombre}» eliminado")
    persist_data(data)
    return ResultadoOperacion(True, f"Producto «{nombre}» eliminado.")


def registrar_lote(
    producto_id: str,
    precio_total: float,
    cantidad: float,
    fecha_compra: date | None = None,
    fecha_expiracion: date | None = None,
    marca_proveedor: str | None = None,
    alerta_expiracion_dias: int | None = None,
    ubicacion_destino_id: str | None = None,
) -> ResultadoOperacion:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoOperacion(False, denied)

    if not producto_id:
        return ResultadoOperacion(False, "Seleccione un producto.")
    if precio_total <= 0:
        return ResultadoOperacion(False, "El precio total debe ser mayor que 0.")
    if cantidad <= 0:
        return ResultadoOperacion(False, "La cantidad debe ser mayor que 0.")
    if fecha_compra and fecha_expiracion and fecha_expiracion < fecha_compra:
        return ResultadoOperacion(False, "La fecha de expiración no puede ser anterior a la compra.")
    if alerta_expiracion_dias is not None and alerta_expiracion_dias < 0:
        return ResultadoOperacion(False, "Los días de alerta no pueden ser negativos.")

    data = get_data()
    repo = DataRepository(data)
    producto = repo.get_producto(producto_id)
    if not producto:
        return ResultadoOperacion(False, "El producto seleccionado no existe.")

    if ubicacion_destino_id:
        from app.core.services.ubicacion_stock_service import validar_ubicacion_catalogo

        err_u = validar_ubicacion_catalogo(data, ubicacion_destino_id)
        if err_u:
            return ResultadoOperacion(False, err_u)
    elif getattr(producto, "ubicacion_ids", None):
        # Nueva entrada: preferir primera ubicación permitida si hay catálogo.
        # No inventa ubicaciones históricas en lotes previos.
        ubicacion_destino_id = producto.ubicacion_ids[0]

    proveedor = marca_proveedor.strip() if marca_proveedor else None
    alerta_dias = alerta_expiracion_dias if alerta_expiracion_dias and alerta_expiracion_dias > 0 else None

    lote = LoteStock(
        _next_id("l", [l.id for l in data.lotes]),
        producto_id,
        round(precio_total, 2),
        cantidad,
        cantidad,
        fecha_compra,
        fecha_expiracion,
        proveedor,
        alerta_dias,
    )
    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []
    n_lotes = len(data.lotes)
    n_mov = len(data.movimientos)
    data.lotes.append(lote)

    from app.core.application.context import build_app_context
    from app.core.application.unit_of_work import InMemoryUnitOfWork
    from app.core.services import movimiento_service as mov_svc

    ctx_mov = build_app_context(uow=InMemoryUnitOfWork(data))
    espejo = mov_svc.espejo_entrada_lote(
        producto_id=producto_id,
        lote_id=lote.id,
        cantidad=cantidad,
        fecha=fecha_compra or date.today(),
        precio_total=round(precio_total, 2),
        ubicacion_destino_id=ubicacion_destino_id,
        ctx=ctx_mov,
        commit=False,
    )
    if not espejo.ok and not espejo.duplicado:
        del data.lotes[n_lotes:]
        del data.movimientos[n_mov:]
        return ResultadoOperacion(
            False,
            f"No se pudo registrar el espejo de ledger: {espejo.mensaje}",
        )

    _registrar_actividad(
        data,
        "Registrar lote",
        f"Lote de «{producto.nombre}» — {cantidad} {producto.unidad.value} — {precio_total:.2f} €",
    )
    persist_data(data)
    return ResultadoOperacion(True, f"Lote registrado para «{producto.nombre}».")


def mapa_productos(
    data: AppData,
    *,
    es_bebida: bool | None = None,
    solo_activos: bool = True,
) -> dict[str, str]:
    """Catálogo nombre→id. Por defecto solo activos (selecciones nuevas)."""
    from app.core.application.context import build_app_context
    from app.core.application.producto_queries import mapa_productos_nombre_id
    from app.core.application.unit_of_work import InMemoryUnitOfWork

    ctx = build_app_context(uow=InMemoryUnitOfWork(data))
    return mapa_productos_nombre_id(
        ctx,
        es_bebida=es_bebida,
        solo_activos=solo_activos,
        ordenar=False,
    )

def mapa_bebidas(data: AppData) -> dict[str, str]:
    return mapa_productos(data, es_bebida=True)


def _ids_catalogo(data: AppData, *, es_bebida: bool) -> set[str]:
    return {p.id for p in data.productos if p.es_bebida == es_bebida}


def _lotes_filtrados(data: AppData, *, es_bebida: bool) -> list[LoteStock]:
    ids = _ids_catalogo(data, es_bebida=es_bebida)
    return [l for l in data.lotes if l.producto_id in ids]


def fecha_mas_antigua(*, es_bebida: bool = False) -> date | None:
    """Fecha de compra del lote más antiguo (para sembrar exportaciones
    semanales pendientes si nunca se ha exportado nada todavía)."""
    fechas = [l.fecha_compra for l in _lotes_filtrados(get_data(), es_bebida=es_bebida) if l.fecha_compra]
    return min(fechas) if fechas else None


def registros_exportables(
    inicio: date,
    hasta: datetime,
    *,
    es_bebida: bool = False,
) -> list[RegistroExportable]:
    """Un registro exportable por cada compra (lote) registrada entre
    `inicio` y `hasta`, filtrado por productos o bebidas."""
    data = get_data()
    repo = DataRepository(data)
    fin = hasta.date()
    col_producto = "Bebida" if es_bebida else "Producto"
    columnas = [
        col_producto, "Proveedor", "Lote", "Cantidad", "Unidad",
        "Precio total", "Coste unitario", "Expiración", "Tipo",
    ]
    simbolo = repo.get_simbolo_moneda()
    tipo_registro = "Bebida" if es_bebida else "Stock"
    tipo_movimiento = "Compra"

    resultado: list[RegistroExportable] = []
    for lote in sorted(
        _lotes_filtrados(data, es_bebida=es_bebida),
        key=lambda l: (l.fecha_compra or date.min, l.id),
    ):
        if not lote.fecha_compra or not (inicio <= lote.fecha_compra <= fin):
            continue
        producto = repo.get_producto(lote.producto_id)
        if not producto:
            continue
        coste_unit = round(lote.precio_total / lote.cantidad, 4) if lote.cantidad > 0 else 0.0
        resultado.append(RegistroExportable(
            fecha=lote.fecha_compra,
            hora=None,
            tipo=tipo_registro,
            identificador=lote.id,
            usuario=None,
            columnas=columnas,
            filas=[[
                repo.get_nombre_producto(lote.producto_id),
                lote.marca_proveedor or "—",
                lote.id,
                lote.cantidad,
                producto.unidad.value,
                formato_moneda(lote.precio_total, simbolo),
                formato_moneda(coste_unit, simbolo),
                formato_fecha(lote.fecha_expiracion),
                tipo_movimiento,
            ]],
            resumen=[
                ("Precio total", formato_moneda(lote.precio_total, simbolo)),
                ("Estado", "Anulado" if getattr(lote, "anulado", False) else "Activo"),
            ],
        ))
    return resultado


def _registros_exportables_stock(inicio: date, hasta: datetime) -> list[RegistroExportable]:
    return registros_exportables(inicio, hasta, es_bebida=False)


def _registros_exportables_bebidas(inicio: date, hasta: datetime) -> list[RegistroExportable]:
    return registros_exportables(inicio, hasta, es_bebida=True)


def configuracion_exportacion(*, es_bebida: bool = False) -> ConfiguracionExportacionModulo:
    if es_bebida:
        return ConfiguracionExportacionModulo(
            tipo="bebidas",
            titulo_documento="Registro de Bebidas",
            obtener_registros=_registros_exportables_bebidas,
        )
    return ConfiguracionExportacionModulo(
        tipo="stock",
        titulo_documento="Registro de Stock",
        obtener_registros=_registros_exportables_stock,
    )
