"""Servicio central de exportación semanal.

Reutilizable por todos los módulos (desayuno, merma, stock, bebidas, consumo,
actividad). Cada módulo aporta una `ConfiguracionExportacionModulo` con su
título de documento y una función que traduce sus propios registros a
`RegistroExportable` (ver `excel_bloques.py`). Este servicio se encarga de:

- Calcular el rango de la semana actual / de una exportación manual.
- Detectar semanas completas todavía no exportadas (de forma idempotente).
- Generar el libro Excel (hoja "Info" + una hoja por día con registros).
- Guardar el archivo sin sobrescribir exportaciones anteriores.
- Registrar la exportación en el Registro de actividad (una sola vez).
- No propagar excepciones: cualquier fallo se devuelve como
  `ResultadoExportacion(ok=False, ...)` para no romper el arranque de la app
  ni la página que llama a esto desde un botón.

Fase 4H: actividad / reloj vía AppContext (UoW parcheable).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable

from openpyxl import Workbook

from app.core.application.clock import Clock, SystemClock
from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import Actividad, AppData
from app.core.services.excel_bloques import (
    RegistroExportable,
    escribir_hoja_dia,
    escribir_hoja_info,
    nombre_hoja_dia,
)
from app.core.storage.session_store import get_data, persist_data

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
EXPORTS_DIR = PROJECT_ROOT / "exports" / "semanal"
META_FILE = EXPORTS_DIR / "_meta_exportaciones.json"


@dataclass(frozen=True)
class ConfiguracionExportacionModulo:
    """Contrato que cada módulo implementa para conectarse al motor central.

    `obtener_registros(inicio, hasta)` debe devolver los `RegistroExportable`
    del módulo cuya fecha esté en `[inicio, hasta.date()]` (ambos inclusive).
    """

    tipo: str
    titulo_documento: str
    obtener_registros: Callable[[date, datetime], list[RegistroExportable]]
    carpeta: Path | None = None


@dataclass(frozen=True)
class ResultadoExportacion:
    ok: bool
    mensaje: str
    ruta: Path | None = None
    nombre_archivo: str | None = None
    filas_exportadas: int = 0


class _CompatSessionUow:
    def get_data(self) -> AppData:
        return get_data()

    def commit(self, data: AppData | None = None) -> AppData:
        return persist_data(data if data is not None else get_data())


def _try_ctx(ctx: AppContext | None = None) -> AppContext | None:
    if ctx is not None:
        return ctx
    try:
        from app.core.application.actor import actor_desde_appdata

        uow = _CompatSessionUow()
        app = uow.get_data()
        return AppContext(
            uow=uow,
            actor=actor_desde_appdata(app),
            clock=SystemClock(),
        )
    except Exception:
        return None


def _clock(ctx: AppContext | None = None, clock: Clock | None = None) -> Clock:
    if clock is not None:
        return clock
    if ctx is not None:
        return ctx.clock
    return SystemClock()


def limite_semana(fecha_ref: date) -> tuple[date, date]:
    """Lunes y domingo (fechas) de la semana que contiene `fecha_ref`."""
    lunes = fecha_ref - timedelta(days=fecha_ref.weekday())
    domingo = lunes + timedelta(days=6)
    return lunes, domingo


def rango_semana_actual(ahora: datetime) -> tuple[date, datetime]:
    """Lunes 00:00 → domingo 23:59:59 de la semana de `ahora`."""
    lunes, domingo = limite_semana(ahora.date())
    hasta = datetime.combine(domingo, time(23, 59, 59))
    return lunes, hasta


def rango_manual_actual(ahora: datetime) -> tuple[date, datetime]:
    """Lunes 00:00 de la semana actual → el momento exacto `ahora`."""
    lunes, _ = limite_semana(ahora.date())
    return lunes, ahora


def _carpeta_modulo(config: ConfiguracionExportacionModulo, carpeta_exports: Path | None) -> Path:
    base = carpeta_exports or EXPORTS_DIR
    return config.carpeta or (base / config.tipo)


def _leer_meta(archivo_meta: Path) -> dict:
    if not archivo_meta.exists():
        return {}
    try:
        return json.loads(archivo_meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _guardar_meta(archivo_meta: Path, meta: dict) -> None:
    archivo_meta.parent.mkdir(parents=True, exist_ok=True)
    archivo_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def ultima_semana_exportada(tipo: str, *, archivo_meta: Path | None = None) -> date | None:
    meta = _leer_meta(archivo_meta or META_FILE)
    valor = meta.get(tipo, {}).get("ultima_semana_exportada")
    return date.fromisoformat(valor) if valor else None


def _marcar_semana_exportada(
    tipo: str,
    lunes: date,
    nombre_archivo: str,
    *,
    archivo_meta: Path | None = None,
) -> None:
    ruta_meta = archivo_meta or META_FILE
    meta = _leer_meta(ruta_meta)
    entrada = meta.setdefault(tipo, {})
    entrada["ultima_semana_exportada"] = lunes.isoformat()
    entrada["ultimo_archivo"] = nombre_archivo
    historico = entrada.setdefault("exportaciones", [])
    historico.append({"semana": lunes.isoformat(), "archivo": nombre_archivo})
    _guardar_meta(ruta_meta, meta)


def semanas_pendientes(
    tipo: str,
    ahora: datetime,
    fecha_mas_antigua: date | None = None,
    *,
    archivo_meta: Path | None = None,
) -> list[date]:
    """Lunes de cada semana COMPLETA (estrictamente anterior a la semana
    actual) que todavía no se ha exportado para `tipo`.

    Si nunca se exportó nada, se usa `fecha_mas_antigua` (p. ej. la fecha del
    primer registro histórico del módulo) como punto de partida. Sin
    exportación previa ni `fecha_mas_antigua`, no hay nada pendiente: no se
    inventan semanas "desde siempre" sin una referencia real de datos.
    """
    lunes_actual, _ = limite_semana(ahora.date())
    ultima = ultima_semana_exportada(tipo, archivo_meta=archivo_meta)

    if ultima is not None:
        primer_lunes_pendiente = ultima + timedelta(days=7)
    elif fecha_mas_antigua is not None:
        primer_lunes_pendiente, _ = limite_semana(fecha_mas_antigua)
    else:
        return []

    pendientes = []
    lunes = primer_lunes_pendiente
    while lunes < lunes_actual:
        pendientes.append(lunes)
        lunes += timedelta(days=7)
    return pendientes


def _nombre_archivo_base(titulo_documento: str, fecha_exportacion: date, inicio: date, hasta: date) -> str:
    titulo_slug = titulo_documento.strip().replace(" ", "_")
    return f"{titulo_slug}_{fecha_exportacion.isoformat()}_{inicio.isoformat()}_a_{hasta.isoformat()}.xlsx"


def _nombre_archivo_seguro(
    carpeta: Path,
    base: str,
    *,
    clock: Clock | None = None,
) -> str:
    """Si `base` ya existe en `carpeta`, añade un sufijo `_HHMMSS` único
    (y un contador adicional en el improbable caso de colisión en el mismo
    segundo), para nunca sobrescribir una exportación anterior."""
    if not (carpeta / base).exists():
        return base
    raiz = base[:-5] if base.endswith(".xlsx") else base
    clk = clock or SystemClock()
    sufijo = clk.now().strftime("%H%M%S")
    candidato = f"{raiz}_{sufijo}.xlsx"
    contador = 1
    while (carpeta / candidato).exists():
        candidato = f"{raiz}_{sufijo}_{contador}.xlsx"
        contador += 1
    return candidato


def _agrupar_por_dia(registros: list[RegistroExportable]) -> dict[date, list[RegistroExportable]]:
    por_dia: dict[date, list[RegistroExportable]] = defaultdict(list)
    for registro in registros:
        por_dia[registro.fecha].append(registro)
    for lista in por_dia.values():
        lista.sort(key=lambda r: (r.hora or time.min, r.identificador))
    return por_dia


def _registrar_actividad_exportacion(
    modulo: str,
    periodo_txt: str,
    automatica: bool,
    nombre_archivo: str,
    resultado_ok: bool,
    *,
    ctx: AppContext | None = None,
) -> None:
    """Registra UNA actividad de exportación tras completarse (correcta o
    con error). No se llama nunca antes de tener el resultado final, así que
    exportar el propio Registro de actividad no puede generar un bucle."""
    context = _try_ctx(ctx)
    if context is None:
        return  # fuera de una sesión Streamlit (p. ej. en pruebas) no hay nada que registrar

    data = context.data()
    usuario = "Sistema" if automatica else context.actor.nombre

    tipo_txt = "Automática" if automatica else "Manual"
    resultado_txt = "Correcto" if resultado_ok else "Error"
    detalle = (
        f"Exportación {tipo_txt.lower()} de {modulo} — periodo {periodo_txt} — "
        f"archivo {nombre_archivo} — resultado {resultado_txt.lower()}"
    )

    data.actividades.insert(0, Actividad(
        next_id("act", [a.id for a in data.actividades]),
        context.clock.now(),
        usuario,
        "Exportación",
        detalle,
        modulo=modulo,
        resultado=resultado_txt,
        tipo_exportacion=tipo_txt,
        periodo_afectado=periodo_txt,
        archivo_generado=nombre_archivo,
    ))
    context.uow.commit(data)


def exportar_periodo(
    config: ConfiguracionExportacionModulo,
    inicio: date,
    hasta: datetime,
    *,
    automatica: bool,
    fecha_exportacion: date | None = None,
    carpeta_exports: Path | None = None,
    archivo_meta: Path | None = None,
    ctx: AppContext | None = None,
    clock: Clock | None = None,
) -> ResultadoExportacion:
    """Genera y guarda el Excel de un módulo para el periodo
    [inicio 00:00, hasta]. Nunca lanza excepciones hacia afuera."""
    periodo_txt = f"{inicio.isoformat()} a {hasta.date().isoformat()}"
    clk = _clock(ctx, clock)

    try:
        registros = config.obtener_registros(inicio, hasta)
    except Exception as exc:
        _registrar_actividad_exportacion(
            config.tipo, periodo_txt, automatica, "—", False, ctx=ctx,
        )
        return ResultadoExportacion(False, f"No se pudieron obtener los registros: {exc}")

    try:
        carpeta = _carpeta_modulo(config, carpeta_exports)
        carpeta.mkdir(parents=True, exist_ok=True)

        libro = Workbook()
        hoja_info = libro.active
        hoja_info.title = "Info"
        escribir_hoja_info(
            hoja_info,
            titulo_documento=config.titulo_documento,
            periodo_txt=periodo_txt,
            fecha_exportacion_txt=clk.now().strftime("%d/%m/%Y %H:%M"),
            tipo_exportacion="Automática" if automatica else "Manual",
            total_registros=len(registros),
        )

        por_dia = _agrupar_por_dia(registros)
        for fecha_dia in sorted(por_dia):
            nombre_hoja = nombre_hoja_dia(fecha_dia)
            hoja = libro.create_sheet(title=nombre_hoja[:31])
            escribir_hoja_dia(hoja, fecha_dia, por_dia[fecha_dia], nombre_hoja)

        base = _nombre_archivo_base(
            config.titulo_documento,
            fecha_exportacion or clk.today(),
            inicio,
            hasta.date(),
        )
        nombre_final = _nombre_archivo_seguro(carpeta, base, clock=clk)
        ruta = carpeta / nombre_final
        libro.save(ruta)
    except Exception as exc:
        _registrar_actividad_exportacion(
            config.tipo, periodo_txt, automatica, "—", False, ctx=ctx,
        )
        return ResultadoExportacion(False, f"Error al generar el archivo: {exc}")

    _registrar_actividad_exportacion(
        config.tipo, periodo_txt, automatica, nombre_final, True, ctx=ctx,
    )
    return ResultadoExportacion(
        True,
        f"Exportado correctamente: {nombre_final}",
        ruta=ruta,
        nombre_archivo=nombre_final,
        filas_exportadas=len(registros),
    )


def exportar_semana_actual(
    config: ConfiguracionExportacionModulo,
    ahora: datetime,
    *,
    carpeta_exports: Path | None = None,
    archivo_meta: Path | None = None,
    ctx: AppContext | None = None,
) -> ResultadoExportacion:
    """Exportación manual: desde el lunes 00:00 de la semana actual hasta
    `ahora`. Nunca marca ninguna semana como cerrada — una semana incompleta
    no se considera "ya exportada automáticamente" ni impide el cierre
    automático posterior de esa misma semana."""
    inicio, hasta = rango_manual_actual(ahora)
    return exportar_periodo(
        config, inicio, hasta, automatica=False,
        fecha_exportacion=ahora.date(),
        carpeta_exports=carpeta_exports, archivo_meta=archivo_meta,
        ctx=ctx,
    )


def procesar_pendientes(
    config: ConfiguracionExportacionModulo,
    ahora: datetime,
    fecha_mas_antigua: date | None = None,
    *,
    carpeta_exports: Path | None = None,
    archivo_meta: Path | None = None,
    ctx: AppContext | None = None,
) -> list[ResultadoExportacion]:
    """Exporta automáticamente cada semana completa pendiente de `config` y
    la marca como exportada. Idempotente: llamar varias veces (p. ej. varios
    arranques de la app) no genera archivos ni actividades duplicadas, porque
    cada semana ya marcada deja de aparecer en `semanas_pendientes`."""
    lunes_pendientes = semanas_pendientes(
        config.tipo, ahora, fecha_mas_antigua, archivo_meta=archivo_meta,
    )
    resultados = []
    for lunes in lunes_pendientes:
        _, domingo = limite_semana(lunes)
        hasta = datetime.combine(domingo, time(23, 59, 59))
        resultado = exportar_periodo(
            config, lunes, hasta, automatica=True,
            fecha_exportacion=ahora.date(),
            carpeta_exports=carpeta_exports, archivo_meta=archivo_meta,
            ctx=ctx,
        )
        if resultado.ok:
            _marcar_semana_exportada(
                config.tipo, lunes, resultado.nombre_archivo or "", archivo_meta=archivo_meta,
            )
        resultados.append(resultado)
    return resultados
