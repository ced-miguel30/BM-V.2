"""Servicio de registro de merma — lote, servicio, turno y responsable."""

from dataclasses import dataclass
from datetime import date, datetime

from app.core.models import (
    AppData,
    LineaMerma,
    LoteStock,
    MotivoMerma,
    ORIGEN_SERVICIO_MERMA_LABEL,
    ORIGEN_SERVICIO_MERMA_VALORES,
    OrigenServicioMerma,
    RegistroMerma,
    ResponsableMerma,
    TURNO_MERMA_LABEL,
    TURNO_MERMA_VALORES,
    TurnoMerma,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services.excel_bloques import RegistroExportable
from app.core.services.exportacion_semanal_service import ConfiguracionExportacionModulo
from app.core.services.formatting import formato_fecha
from app.core.services.stock_service import disponible_en_servicio
from app.core.services.text_search import coincide_busqueda
from app.core.storage.session_store import get_data, persist_data

CESTA_MERMA_KEY = "bm_cesta_merma"
MOTIVOS = [m.value for m in MotivoMerma]
PLACEHOLDER_SERVICIO = "Selecciona un servicio"
PLACEHOLDER_TURNO = "Selecciona un turno"
PLACEHOLDER_RESPONSABLE = "Selecciona un responsable"
OPCIONES_SERVICIO_UI = [PLACEHOLDER_SERVICIO] + [
    ORIGEN_SERVICIO_MERMA_LABEL[m] for m in OrigenServicioMerma
]
OPCIONES_TURNO_UI = [PLACEHOLDER_TURNO] + [
    TURNO_MERMA_LABEL[t] for t in TurnoMerma
]
_LABEL_A_VALOR_SERVICIO = {v: k.value for k, v in ORIGEN_SERVICIO_MERMA_LABEL.items()}
_LABEL_A_VALOR_TURNO = {v: k.value for k, v in TURNO_MERMA_LABEL.items()}


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


@dataclass
class LineaCestaMerma:
    lote_id: str
    producto_id: str
    nombre: str
    unidad: str
    fecha_compra_txt: str
    cantidad: float
    motivo: str
    tipo_servicio_snapshot: str
    turno_snapshot: str
    responsable_id: str
    responsable_nombre: str
    comentario: str | None = None


def etiqueta_servicio_merma(valor: str | None) -> str:
    if not valor:
        return "Sin desglose histórico"
    try:
        return ORIGEN_SERVICIO_MERMA_LABEL[OrigenServicioMerma(valor)]
    except ValueError:
        return valor


def etiqueta_turno_merma(valor: str | None) -> str:
    if not valor:
        return "Dato no disponible"
    try:
        return TURNO_MERMA_LABEL[TurnoMerma(valor)]
    except ValueError:
        return valor


def etiqueta_responsable_merma(nombre: str | None) -> str:
    if not nombre:
        return "Dato no disponible"
    return nombre


def valor_servicio_desde_ui(etiqueta: str) -> str | None:
    """Devuelve el valor persistible o None si es el placeholder."""
    if not etiqueta or etiqueta == PLACEHOLDER_SERVICIO:
        return None
    return _LABEL_A_VALOR_SERVICIO.get(etiqueta)


def valor_turno_desde_ui(etiqueta: str) -> str | None:
    if not etiqueta or etiqueta == PLACEHOLDER_TURNO:
        return None
    return _LABEL_A_VALOR_TURNO.get(etiqueta)


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


def _get_lote(data: AppData, lote_id: str) -> LoteStock | None:
    return next((l for l in data.lotes if l.id == lote_id), None)


def _coste_unidad_lote(lote: LoteStock) -> float:
    if lote.cantidad <= 0:
        return 0.0
    return lote.precio_total / lote.cantidad


def _etiqueta_lote(lote: LoteStock, repo: DataRepository) -> str:
    nombre = repo.get_nombre_producto(lote.producto_id)
    compra = formato_fecha(lote.fecha_compra)
    producto = repo.get_producto(lote.producto_id)
    unidad = producto.unidad.value if producto else "Ud"
    return (
        f"{nombre} — lote {lote.id} — compra {compra} — "
        f"{lote.cantidad_restante:g} {unidad} restantes"
    )


def _clave_linea(
    lote_id: str,
    motivo: str,
    tipo_servicio_snapshot: str,
    turno_snapshot: str,
    responsable_id: str,
) -> tuple[str, str, str, str, str]:
    return (lote_id, motivo, tipo_servicio_snapshot, turno_snapshot, responsable_id)


def _misma_clave(linea: LineaCestaMerma, clave: tuple[str, str, str, str, str]) -> bool:
    return _clave_linea(
        linea.lote_id,
        linea.motivo,
        linea.tipo_servicio_snapshot,
        linea.turno_snapshot,
        linea.responsable_id,
    ) == clave


# --- Catálogo responsables (Configuración) ---

def listar_responsables_merma(*, solo_activos: bool = False) -> list[ResponsableMerma]:
    data = get_data()
    items = list(data.responsables_merma)
    if solo_activos:
        items = [r for r in items if r.activo]
    return sorted(items, key=lambda r: r.nombre.lower())


def crear_responsable_merma(nombre: str) -> ResultadoOperacion:
    texto = (nombre or "").strip()
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de responsable.")
    data = get_data()
    if any(r.nombre.lower() == texto.lower() for r in data.responsables_merma):
        return ResultadoOperacion(False, "Ya existe un responsable con ese nombre.")
    nuevo = ResponsableMerma(
        _next_id("rm", [r.id for r in data.responsables_merma]),
        texto,
        True,
    )
    data.responsables_merma.append(nuevo)
    _registrar_actividad(data, "Responsable merma", f"Alta: {texto}")
    persist_data(data)
    return ResultadoOperacion(True, f"Responsable «{texto}» creado.")


def renombrar_responsable_merma(responsable_id: str, nombre: str) -> ResultadoOperacion:
    texto = (nombre or "").strip()
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de responsable.")
    data = get_data()
    actual = next((r for r in data.responsables_merma if r.id == responsable_id), None)
    if not actual:
        return ResultadoOperacion(False, "Responsable no encontrado.")
    if any(
        r.id != responsable_id and r.nombre.lower() == texto.lower()
        for r in data.responsables_merma
    ):
        return ResultadoOperacion(False, "Ya existe un responsable con ese nombre.")
    anterior = actual.nombre
    actual.nombre = texto
    _registrar_actividad(
        data, "Responsable merma", f"Renombrado: {anterior} → {texto}",
    )
    persist_data(data)
    return ResultadoOperacion(
        True,
        f"Nombre actualizado a «{texto}». "
        "El histórico de merma conserva el nombre capturado en cada línea.",
    )


def desactivar_responsable_merma(responsable_id: str) -> ResultadoOperacion:
    data = get_data()
    actual = next((r for r in data.responsables_merma if r.id == responsable_id), None)
    if not actual:
        return ResultadoOperacion(False, "Responsable no encontrado.")
    if not actual.activo:
        return ResultadoOperacion(False, "El responsable ya está inactivo.")
    actual.activo = False
    _registrar_actividad(data, "Responsable merma", f"Desactivado: {actual.nombre}")
    persist_data(data)
    return ResultadoOperacion(True, f"Responsable «{actual.nombre}» desactivado.")


def reactivar_responsable_merma(responsable_id: str) -> ResultadoOperacion:
    data = get_data()
    actual = next((r for r in data.responsables_merma if r.id == responsable_id), None)
    if not actual:
        return ResultadoOperacion(False, "Responsable no encontrado.")
    if actual.activo:
        return ResultadoOperacion(False, "El responsable ya está activo.")
    actual.activo = True
    _registrar_actividad(data, "Responsable merma", f"Reactivado: {actual.nombre}")
    persist_data(data)
    return ResultadoOperacion(True, f"Responsable «{actual.nombre}» reactivado.")


def get_cesta_merma() -> list[LineaCestaMerma]:
    import streamlit as st

    if CESTA_MERMA_KEY not in st.session_state:
        st.session_state[CESTA_MERMA_KEY] = []
    cesta = st.session_state[CESTA_MERMA_KEY]
    # Compat: líneas antiguas de sesión sin turno/responsable → vaciar.
    if cesta and (
        not hasattr(cesta[0], "turno_snapshot")
        or not hasattr(cesta[0], "responsable_id")
    ):
        st.session_state[CESTA_MERMA_KEY] = []
    return st.session_state[CESTA_MERMA_KEY]


def limpiar_cesta_merma() -> None:
    import streamlit as st

    st.session_state[CESTA_MERMA_KEY] = []


def quitar_de_cesta_merma(
    lote_id: str,
    motivo: str,
    tipo_servicio_snapshot: str,
    turno_snapshot: str,
    responsable_id: str,
) -> None:
    import streamlit as st

    clave = _clave_linea(
        lote_id, motivo, tipo_servicio_snapshot, turno_snapshot, responsable_id,
    )
    cesta = get_cesta_merma()
    st.session_state[CESTA_MERMA_KEY] = [
        l for l in cesta if not _misma_clave(l, clave)
    ]


def productos_con_stock(buscar: str = "", *, servicio: str | None = None) -> list[dict]:
    data = get_data()
    termino = buscar.strip()
    resultado = []

    for producto in sorted(data.productos, key=lambda p: p.nombre):
        if servicio is not None and not disponible_en_servicio(
            producto.servicios_disponibles, servicio,
        ):
            continue
        lotes = [l for l in data.lotes if l.producto_id == producto.id and l.cantidad_restante > 0]
        if not lotes:
            continue
        if termino and not coincide_busqueda(producto.nombre, termino):
            continue
        stock = sum(l.cantidad_restante for l in lotes)
        resultado.append({
            "id": producto.id,
            "nombre": producto.nombre,
            "unidad": producto.unidad.value,
            "stock": stock,
            "etiqueta": f"{producto.nombre} ({stock:g} {producto.unidad.value})",
        })
    return resultado


def lotes_disponibles(producto_id: str) -> list[dict]:
    data = get_data()
    repo = DataRepository(data)
    lotes = [
        l for l in data.lotes
        if l.producto_id == producto_id and l.cantidad_restante > 0
    ]
    lotes = sorted(lotes, key=lambda l: (l.fecha_compra or date.min, l.id))
    return [
        {
            "id": l.id,
            "restante": l.cantidad_restante,
            "etiqueta": _etiqueta_lote(l, repo),
            "fecha_compra_txt": formato_fecha(l.fecha_compra),
        }
        for l in lotes
    ]


def _cantidad_en_cesta(
    lote_id: str,
    motivo: str,
    tipo_servicio_snapshot: str,
    turno_snapshot: str,
    responsable_id: str,
) -> float:
    clave = _clave_linea(
        lote_id, motivo, tipo_servicio_snapshot, turno_snapshot, responsable_id,
    )
    return sum(l.cantidad for l in get_cesta_merma() if _misma_clave(l, clave))


def calcular_coste_lote(lote_id: str, cantidad: float) -> float:
    data = get_data()
    lote = _get_lote(data, lote_id)
    if not lote:
        return 0.0
    return round(cantidad * _coste_unidad_lote(lote), 2)


def anadir_a_cesta_merma(
    lote_id: str,
    cantidad: float,
    motivo: str,
    tipo_servicio_snapshot: str | None,
    comentario: str | None = None,
    *,
    turno_snapshot: str | None = None,
    responsable_id: str | None = None,
    responsable_nombre: str | None = None,
) -> ResultadoOperacion:
    if cantidad <= 0:
        return ResultadoOperacion(False, "La cantidad debe ser mayor que 0.")
    if motivo not in MOTIVOS:
        return ResultadoOperacion(False, "Seleccione un motivo válido.")
    if not tipo_servicio_snapshot or tipo_servicio_snapshot not in ORIGEN_SERVICIO_MERMA_VALORES:
        return ResultadoOperacion(
            False,
            "Seleccione dónde se produjo la merma (Desayuno, Comida, Cena, Bebidas o Almacén / General).",
        )
    if not turno_snapshot or turno_snapshot not in TURNO_MERMA_VALORES:
        return ResultadoOperacion(False, "Seleccione el turno (Mañana, Tarde o Noche).")
    if not responsable_id or not (responsable_nombre or "").strip():
        return ResultadoOperacion(False, "Seleccione un responsable activo.")

    data = get_data()
    responsable = next(
        (r for r in data.responsables_merma if r.id == responsable_id and r.activo),
        None,
    )
    if not responsable:
        return ResultadoOperacion(
            False,
            "El responsable no está activo. Gestionelos en Configuración.",
        )
    # Snapshot de texto al añadir (no se altera si luego se renombra el catálogo).
    nombre_resp = (responsable_nombre or responsable.nombre).strip()

    lote = _get_lote(data, lote_id)
    if not lote:
        return ResultadoOperacion(False, "El lote seleccionado no existe.")
    if lote.cantidad_restante <= 0:
        return ResultadoOperacion(False, "El lote no tiene stock disponible.")

    repo = DataRepository(data)
    producto = repo.get_producto(lote.producto_id)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    ya_en_cesta = _cantidad_en_cesta(
        lote_id, motivo, tipo_servicio_snapshot, turno_snapshot, responsable_id,
    )
    if ya_en_cesta + cantidad > lote.cantidad_restante:
        return ResultadoOperacion(
            False,
            f"Cantidad superior al stock del lote ({lote.cantidad_restante:g} {producto.unidad.value}).",
        )

    comentario_limpio = comentario.strip() if comentario else None
    cesta = get_cesta_merma()
    clave = _clave_linea(
        lote_id, motivo, tipo_servicio_snapshot, turno_snapshot, responsable_id,
    )

    for linea in cesta:
        if _misma_clave(linea, clave):
            linea.cantidad = round(linea.cantidad + cantidad, 4)
            if comentario_limpio:
                linea.comentario = comentario_limpio
            return ResultadoOperacion(True, "Línea actualizada en la cesta de merma.")

    cesta.append(LineaCestaMerma(
        lote_id=lote_id,
        producto_id=lote.producto_id,
        nombre=producto.nombre,
        unidad=producto.unidad.value,
        fecha_compra_txt=formato_fecha(lote.fecha_compra),
        cantidad=cantidad,
        motivo=motivo,
        tipo_servicio_snapshot=tipo_servicio_snapshot,
        turno_snapshot=turno_snapshot,
        responsable_id=responsable_id,
        responsable_nombre=nombre_resp,
        comentario=comentario_limpio,
    ))
    return ResultadoOperacion(True, f"«{producto.nombre}» (lote {lote_id}) añadido a la cesta.")


def coste_total_cesta_merma() -> float:
    cesta = get_cesta_merma()
    return sum(calcular_coste_lote(l.lote_id, l.cantidad) for l in cesta)


def _descontar_lote(data: AppData, lote_id: str, cantidad: float) -> float:
    lote = _get_lote(data, lote_id)
    if not lote:
        raise ValueError(f"Lote {lote_id} no encontrado.")
    if cantidad > lote.cantidad_restante + 1e-9:
        raise ValueError(
            f"Stock insuficiente en lote {lote_id}: "
            f"pide {cantidad:g}, queda {lote.cantidad_restante:g}."
        )
    coste = round(cantidad * _coste_unidad_lote(lote), 2)
    lote.cantidad_restante = round(lote.cantidad_restante - cantidad, 4)
    return coste


def registrar_merma(fecha: date) -> ResultadoOperacion:
    cesta = get_cesta_merma()
    if not cesta:
        return ResultadoOperacion(False, "La cesta está vacía. Añada líneas antes de registrar.")

    if fecha > date.today():
        return ResultadoOperacion(False, "No puede registrar mermas en fechas futuras.")

    for item in cesta:
        if item.tipo_servicio_snapshot not in ORIGEN_SERVICIO_MERMA_VALORES:
            return ResultadoOperacion(
                False,
                "Hay líneas sin servicio válido. Quite y vuelva a añadirlas eligiendo el servicio.",
            )
        if item.turno_snapshot not in TURNO_MERMA_VALORES:
            return ResultadoOperacion(
                False,
                "Hay líneas sin turno válido. Quite y vuelva a añadirlas eligiendo el turno.",
            )
        if not item.responsable_id or not item.responsable_nombre:
            return ResultadoOperacion(
                False,
                "Hay líneas sin responsable. Quite y vuelva a añadirlas.",
            )

    data = get_data()
    lineas: list[LineaMerma] = []

    # Validación acumulada por lote (varias líneas del mismo lote).
    restante_sim: dict[str, float] = {}
    for item in cesta:
        lote = _get_lote(data, item.lote_id)
        if not lote:
            return ResultadoOperacion(
                False,
                f"Stock insuficiente en el lote {item.lote_id} al registrar. "
                "No se ha modificado nada.",
            )
        rem = restante_sim.get(item.lote_id, lote.cantidad_restante)
        if item.cantidad > rem + 1e-9:
            return ResultadoOperacion(
                False,
                f"Stock insuficiente en el lote {item.lote_id} al registrar. "
                "No se ha modificado nada.",
            )
        restante_sim[item.lote_id] = round(rem - item.cantidad, 4)

    from app.core.services.inventory_batch_service import (
        restaurar_cantidades_restantes,
        snapshot_cantidades_restantes,
    )

    snap = snapshot_cantidades_restantes(data)
    n_mermas = len(data.mermas)
    n_actividades = len(data.actividades)
    try:
        for item in cesta:
            coste = _descontar_lote(data, item.lote_id, item.cantidad)
            lineas.append(LineaMerma(
                item.producto_id,
                item.cantidad,
                coste,
                MotivoMerma(item.motivo),
                item.comentario,
                item.lote_id,
                item.tipo_servicio_snapshot,
                item.turno_snapshot,
                item.responsable_id,
                item.responsable_nombre,
                item.nombre,
                item.unidad,
            ))

        coste_total = round(sum(l.coste for l in lineas), 2)
        registro = RegistroMerma(
            _next_id("m", [m.id for m in data.mermas]),
            fecha,
            lineas,
            coste_total,
            _nombre_usuario(data),
            hora=datetime.now().time(),
        )
        data.mermas.append(registro)
        _registrar_actividad(
            data,
            "Registro merma",
            f"Merma del {fecha.strftime('%d/%m/%Y')} — {coste_total:.2f} €",
        )
        persist_data(data)
    except Exception:
        restaurar_cantidades_restantes(data, snap)
        del data.mermas[n_mermas:]
        del data.actividades[: max(0, len(data.actividades) - n_actividades)]
        raise

    limpiar_cesta_merma()

    from app.core.services.alert_service import sincronizar_alertas
    sincronizar_alertas()

    return ResultadoOperacion(
        True,
        f"Merma registrada — {coste_total:.2f} € ({len(lineas)} línea(s)).",
    )


def fecha_mas_antigua() -> date | None:
    """Fecha de la primera merma registrada (para sembrar exportaciones
    semanales pendientes si nunca se ha exportado nada todavía)."""
    fechas = [m.fecha for m in get_data().mermas]
    return min(fechas) if fechas else None


def registros_exportables(inicio: date, hasta: datetime) -> list[RegistroExportable]:
    """Desglose completo de cada merma entre `inicio` y `hasta`."""
    data = get_data()
    repo = DataRepository(data)
    fin = hasta.date()
    columnas = [
        "Producto", "Lote", "Cantidad", "Unidad", "Motivo",
        "Servicio", "Turno", "Responsable", "Coste", "Comentario",
    ]

    resultado: list[RegistroExportable] = []
    for m in data.mermas:
        if not (inicio <= m.fecha <= fin):
            continue

        filas: list[list] = []
        for ln in m.lineas:
            nombre = ln.producto_nombre_snapshot or repo.get_nombre_producto(ln.producto_id)
            producto = repo.get_producto(ln.producto_id)
            unidad = ln.unidad_snapshot or (producto.unidad.value if producto else "")
            filas.append([
                nombre,
                ln.lote_id or "—",
                ln.cantidad,
                unidad,
                ln.motivo.value,
                etiqueta_servicio_merma(ln.tipo_servicio_snapshot),
                etiqueta_turno_merma(ln.turno_snapshot),
                etiqueta_responsable_merma(ln.responsable_nombre),
                ln.coste,
                ln.comentario or "",
            ])

        resultado.append(RegistroExportable(
            fecha=m.fecha,
            hora=m.hora,
            tipo="Merma",
            identificador=m.id,
            usuario=m.registrado_por or None,
            columnas=columnas,
            filas=filas,
            resumen=[
                ("Coste total", repo.formato_precio(m.coste_total)),
                ("Estado", "Anulado" if getattr(m, "anulado", False) else "Activo"),
            ],
        ))
    return resultado


def configuracion_exportacion() -> ConfiguracionExportacionModulo:
    return ConfiguracionExportacionModulo(
        tipo="merma",
        titulo_documento="Registro de Merma",
        obtener_registros=registros_exportables,
    )
