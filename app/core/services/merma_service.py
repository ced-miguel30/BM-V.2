"""Servicio de registro de merma — con selección de lote."""

from dataclasses import dataclass
from datetime import date, datetime

from app.core.models import AppData, LineaMerma, LoteStock, MotivoMerma, RegistroMerma
from app.core.repositories.data_repository import DataRepository
from app.core.services.excel_bloques import RegistroExportable
from app.core.services.exportacion_semanal_service import ConfiguracionExportacionModulo
from app.core.services.formatting import formato_fecha
from app.core.services.text_search import coincide_busqueda
from app.core.storage.session_store import get_data, persist_data

CESTA_MERMA_KEY = "bm_cesta_merma"
MOTIVOS = [m.value for m in MotivoMerma]


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
    comentario: str | None = None


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


def get_cesta_merma() -> list[LineaCestaMerma]:
    import streamlit as st

    if CESTA_MERMA_KEY not in st.session_state:
        st.session_state[CESTA_MERMA_KEY] = []
    return st.session_state[CESTA_MERMA_KEY]


def limpiar_cesta_merma() -> None:
    import streamlit as st

    st.session_state[CESTA_MERMA_KEY] = []


def quitar_de_cesta_merma(lote_id: str, motivo: str) -> None:
    import streamlit as st

    cesta = get_cesta_merma()
    st.session_state[CESTA_MERMA_KEY] = [
        l for l in cesta if not (l.lote_id == lote_id and l.motivo == motivo)
    ]


def productos_con_stock(buscar: str = "") -> list[dict]:
    data = get_data()
    termino = buscar.strip()
    resultado = []

    for producto in sorted(data.productos, key=lambda p: p.nombre):
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


def _cantidad_en_cesta(lote_id: str, motivo: str) -> float:
    return sum(
        l.cantidad for l in get_cesta_merma()
        if l.lote_id == lote_id and l.motivo == motivo
    )


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
    comentario: str | None = None,
) -> ResultadoOperacion:
    if cantidad <= 0:
        return ResultadoOperacion(False, "La cantidad debe ser mayor que 0.")
    if motivo not in MOTIVOS:
        return ResultadoOperacion(False, "Seleccione un motivo válido.")

    data = get_data()
    lote = _get_lote(data, lote_id)
    if not lote:
        return ResultadoOperacion(False, "El lote seleccionado no existe.")
    if lote.cantidad_restante <= 0:
        return ResultadoOperacion(False, "El lote no tiene stock disponible.")

    repo = DataRepository(data)
    producto = repo.get_producto(lote.producto_id)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    ya_en_cesta = _cantidad_en_cesta(lote_id, motivo)
    if ya_en_cesta + cantidad > lote.cantidad_restante:
        return ResultadoOperacion(
            False,
            f"Cantidad superior al stock del lote ({lote.cantidad_restante:g} {producto.unidad.value}).",
        )

    comentario_limpio = comentario.strip() if comentario else None
    cesta = get_cesta_merma()

    for linea in cesta:
        if linea.lote_id == lote_id and linea.motivo == motivo:
            linea.cantidad = round(linea.cantidad + cantidad, 4)
            if comentario_limpio:
                linea.comentario = comentario_limpio
            return ResultadoOperacion(True, f"Línea actualizada en la cesta de merma.")

    cesta.append(LineaCestaMerma(
        lote_id=lote_id,
        producto_id=lote.producto_id,
        nombre=producto.nombre,
        unidad=producto.unidad.value,
        fecha_compra_txt=formato_fecha(lote.fecha_compra),
        cantidad=cantidad,
        motivo=motivo,
        comentario=comentario_limpio,
    ))
    return ResultadoOperacion(True, f"«{producto.nombre}» (lote {lote_id}) añadido a la cesta.")


def coste_total_cesta_merma() -> float:
    cesta = get_cesta_merma()
    return sum(calcular_coste_lote(l.lote_id, l.cantidad) for l in cesta)


def _descontar_lote(data: AppData, lote_id: str, cantidad: float) -> float:
    lote = _get_lote(data, lote_id)
    if not lote:
        return 0.0
    coste = round(cantidad * _coste_unidad_lote(lote), 2)
    lote.cantidad_restante = round(lote.cantidad_restante - cantidad, 4)
    return coste


def registrar_merma(fecha: date) -> ResultadoOperacion:
    cesta = get_cesta_merma()
    if not cesta:
        return ResultadoOperacion(False, "La cesta está vacía. Añada líneas antes de registrar.")

    if fecha > date.today():
        return ResultadoOperacion(False, "No puede registrar mermas en fechas futuras.")

    data = get_data()
    lineas: list[LineaMerma] = []

    for item in cesta:
        lote = _get_lote(data, item.lote_id)
        if not lote or item.cantidad > lote.cantidad_restante:
            return ResultadoOperacion(
                False,
                f"Stock insuficiente en el lote {item.lote_id} al registrar.",
            )

    for item in cesta:
        coste = _descontar_lote(data, item.lote_id, item.cantidad)
        lineas.append(LineaMerma(
            item.producto_id,
            item.cantidad,
            coste,
            MotivoMerma(item.motivo),
            item.comentario,
            item.lote_id,
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
    """Desglose completo (producto, lote, cantidad, unidad, motivo, coste) de
    cada merma registrada entre `inicio` y `hasta`, para la exportación semanal."""
    data = get_data()
    repo = DataRepository(data)
    fin = hasta.date()
    columnas = ["Producto", "Lote", "Cantidad", "Unidad", "Motivo", "Coste", "Comentario"]

    resultado: list[RegistroExportable] = []
    for m in data.mermas:
        if not (inicio <= m.fecha <= fin):
            continue

        filas: list[list] = []
        for ln in m.lineas:
            nombre = repo.get_nombre_producto(ln.producto_id)
            producto = repo.get_producto(ln.producto_id)
            unidad = producto.unidad.value if producto else ""
            filas.append([
                nombre,
                ln.lote_id or "—",
                ln.cantidad,
                unidad,
                ln.motivo.value,
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
            resumen=[("Coste total", repo.formato_precio(m.coste_total))],
        ))
    return resultado


def configuracion_exportacion() -> ConfiguracionExportacionModulo:
    return ConfiguracionExportacionModulo(
        tipo="merma",
        titulo_documento="Registro de Merma",
        obtener_registros=registros_exportables,
    )
