"""Exportación semanal del Registro de actividad — Fase 6.

El Registro de actividad no tiene un "servicio de dominio" propio: sus
entradas (`Actividad`) las crean todos los demás módulos. Este archivo solo
aporta el conector con el motor central de exportación semanal
(`exportacion_semanal_service.py`), igual que hacen desayuno/merma/stock/
consumo.

Importante contra bucles: `exportar_periodo()` llama primero a
`obtener_registros()` (aquí abajo) para construir el Excel, y solo *después*
de guardarlo registra la actividad de "Exportación" correspondiente. Por eso
esa nueva entrada nunca puede aparecer en el propio archivo que la originó.
"""

from __future__ import annotations

from datetime import date, datetime

from app.core.services.excel_bloques import RegistroExportable
from app.core.services.exportacion_semanal_service import ConfiguracionExportacionModulo
from app.core.storage.session_store import get_data

_COLUMNAS = [
    "Módulo", "Descripción", "Resultado", "Tipo de exportación",
    "Periodo afectado", "Archivo generado",
]


def fecha_mas_antigua() -> date | None:
    """Fecha de la actividad más antigua registrada (para sembrar
    exportaciones pendientes si nunca se ha exportado nada todavía)."""
    fechas = [a.fecha_hora.date() for a in get_data().actividades]
    return min(fechas) if fechas else None


def registros_exportables(inicio: date, hasta: datetime) -> list[RegistroExportable]:
    """Un `RegistroExportable` por cada entrada de actividad entre `inicio`
    y `hasta`. Los campos estructurados (módulo, resultado, tipo de
    exportación, periodo afectado, archivo generado) solo están disponibles
    para actividades creadas por el propio motor de exportación; el resto
    los deja vacíos, tal como pide la Fase 6 ("cuando esté disponible")."""
    data = get_data()
    fin = hasta.date()

    resultado: list[RegistroExportable] = []
    for actividad in data.actividades:
        fecha = actividad.fecha_hora.date()
        if not (inicio <= fecha <= fin):
            continue

        resultado.append(RegistroExportable(
            fecha=fecha,
            hora=actividad.fecha_hora.time(),
            tipo=actividad.accion,
            identificador=actividad.id,
            usuario=actividad.usuario or None,
            columnas=_COLUMNAS,
            filas=[[
                actividad.modulo or "",
                actividad.detalle,
                actividad.resultado or "",
                actividad.tipo_exportacion or "",
                actividad.periodo_afectado or "",
                actividad.archivo_generado or "",
            ]],
        ))
    return resultado


def configuracion_exportacion() -> ConfiguracionExportacionModulo:
    return ConfiguracionExportacionModulo(
        tipo="actividad",
        titulo_documento="Registro de Actividad",
        obtener_registros=registros_exportables,
    )
