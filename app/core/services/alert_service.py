"""Servicio de alertas operativas de stock."""

from dataclasses import dataclass
from datetime import date, datetime

from app.core.models import AlertaOperativa, AppData, TipoAlerta
from app.core.repositories.data_repository import DataRepository
from app.core.storage.session_store import get_data, persist_data

DIAS_EXPIRACION_DEFECTO = 5

_TIPOS_STOCK_AUTO = {
    TipoAlerta.STOCK_BAJO,
    TipoAlerta.STOCK_CERO,
    TipoAlerta.EXPIRACION_PROXIMA,
    TipoAlerta.EXPIRADO,
}

_TIPOS_DESAYUNO_AUTO = {TipoAlerta.DESAYUNO_NO_REGISTRADO}


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


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


def _conservar_alertas(data: AppData) -> list[AlertaOperativa]:
    """Mantiene alertas manuales y las que no se regeneran automáticamente."""
    return [
        a for a in data.alertas
        if a.tipo not in _TIPOS_STOCK_AUTO and a.tipo not in _TIPOS_DESAYUNO_AUTO
    ]


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

    for lote in data.lotes:
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
            ))
            contador += 1

    return nuevas


def _generar_alerta_desayuno(data: AppData, repo: DataRepository, hoy: date) -> list[AlertaOperativa]:
    if repo.desayuno_registrado_hoy():
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


def sincronizar_alertas() -> AppData:
    """Regenera alertas automáticas de stock y desayuno; conserva las manuales."""
    data = get_data()
    repo = DataRepository(data)
    hoy = date.today()

    conservadas = _conservar_alertas(data)
    auto_stock = _generar_alertas_stock(data, repo, hoy)
    auto_desayuno = _generar_alerta_desayuno(data, repo, hoy)

    data.alertas = conservadas + auto_stock + auto_desayuno
    _reasignar_ids(data.alertas)
    return persist_data(data)


def crear_alerta_manual(
    titulo: str,
    mensaje: str,
    producto_id: str | None = None,
) -> ResultadoOperacion:
    titulo = titulo.strip()
    mensaje = mensaje.strip()
    if not titulo:
        return ResultadoOperacion(False, "El título es obligatorio.")
    if not mensaje:
        return ResultadoOperacion(False, "El mensaje es obligatorio.")

    data = get_data()
    if producto_id and not DataRepository(data).get_producto(producto_id):
        return ResultadoOperacion(False, "El producto seleccionado no existe.")

    alerta = AlertaOperativa(
        _next_id("a", [a.id for a in data.alertas]),
        TipoAlerta.MANUAL,
        titulo,
        mensaje,
        date.today(),
        producto_id=producto_id,
    )
    data.alertas.append(alerta)
    _registrar_actividad(data, "Alerta manual", f"«{titulo}» creada")
    persist_data(data)
    return ResultadoOperacion(True, "Alerta manual creada correctamente.")


def resolver_alerta(alerta_id: str) -> ResultadoOperacion:
    data = get_data()
    for alerta in data.alertas:
        if alerta.id == alerta_id:
            alerta.activa = False
            _registrar_actividad(data, "Resolver alerta", f"Alerta «{alerta.titulo}» marcada como resuelta")
            persist_data(data)
            return ResultadoOperacion(True, "Alerta resuelta.")
    return ResultadoOperacion(False, "No se encontró la alerta.")


def alertas_stock_activas(data: AppData) -> list[AlertaOperativa]:
    """Alertas de stock visibles en la pestaña Alertas stock."""
    tipos = _TIPOS_STOCK_AUTO | {TipoAlerta.MANUAL}
    return [a for a in data.alertas if a.activa and a.tipo in tipos]
