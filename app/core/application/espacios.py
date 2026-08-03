"""Espacios de trabajo — lógica pura (Fase 5).

No importa Streamlit. No toca AppData, JSON ni persistencia.
El selector solo determina la navegación visible; no concede permisos
(seguridad real: Fase 16).
"""

from __future__ import annotations

from dataclasses import dataclass

# Identificadores estables
ESPACIO_REGISTRO = "registro"
ESPACIO_GESTOR = "gestor"
ESPACIO_INVENTARIO = "inventario"

ESPACIOS_ORDEN: tuple[str, ...] = (
    ESPACIO_REGISTRO,
    ESPACIO_GESTOR,
    ESPACIO_INVENTARIO,
)

ESPACIO_DEFAULT = ESPACIO_GESTOR

ETIQUETAS_ESPACIO: dict[str, str] = {
    ESPACIO_REGISTRO: "Registro",
    ESPACIO_GESTOR: "Gestor",
    ESPACIO_INVENTARIO: "Inventario",
}

# Etiquetas de sección (= claves de NAV_SECTIONS en theme.py)
SECCION_DASHBOARD = "Dashboard"
SECCION_REGISTROS = "Registros"
SECCION_RECETAS = "Recetas"
SECCION_STOCK = "Stock"
SECCION_ANALISIS = "Análisis"
SECCION_CONFIGURACION = "Configuración"

SECCIONES_POR_ESPACIO: dict[str, tuple[str, ...]] = {
    ESPACIO_REGISTRO: (SECCION_REGISTROS,),
    ESPACIO_GESTOR: (SECCION_DASHBOARD, SECCION_ANALISIS),
    ESPACIO_INVENTARIO: (SECCION_STOCK, SECCION_RECETAS),
}

SECCIONES_GLOBALES: tuple[str, ...] = (SECCION_CONFIGURACION,)

SESSION_KEY_ESPACIO = "bm_espacio_trabajo"


@dataclass(frozen=True)
class EstadoNavegacion:
    """Resultado de resolver espacio + sección (etiquetas de menú)."""

    espacio: str
    seccion: str
    destino_desconocido: bool = False


def normalizar_espacio(valor: str | None) -> str:
    """Devuelve un id de espacio válido; desconocido → predeterminado."""
    if valor in SECCIONES_POR_ESPACIO:
        return valor
    if valor in ETIQUETAS_ESPACIO.values():
        for espacio_id, etiqueta in ETIQUETAS_ESPACIO.items():
            if etiqueta == valor:
                return espacio_id
    return ESPACIO_DEFAULT


def secciones_operativas(espacio: str | None) -> tuple[str, ...]:
    return SECCIONES_POR_ESPACIO[normalizar_espacio(espacio)]


def secciones_visibles(espacio: str | None) -> tuple[str, ...]:
    """Operativas del espacio + globales (Configuración)."""
    return secciones_operativas(espacio) + SECCIONES_GLOBALES


def es_seccion_global(seccion: str | None) -> bool:
    return seccion in SECCIONES_GLOBALES


def es_seccion_conocida(seccion: str | None) -> bool:
    if not seccion:
        return False
    if seccion in SECCIONES_GLOBALES:
        return True
    return any(seccion in secs for secs in SECCIONES_POR_ESPACIO.values())


def espacio_para_seccion(seccion: str | None) -> str | None:
    """Espacio dueño de la sección operativa.

    Configuración (global) y destinos desconocidos → None (no fuerzan cambio).
    """
    if not seccion or seccion in SECCIONES_GLOBALES:
        return None
    for espacio_id, secs in SECCIONES_POR_ESPACIO.items():
        if seccion in secs:
            return espacio_id
    return None


def primera_seccion_operativa(espacio: str | None) -> str:
    return secciones_operativas(espacio)[0]


def _seccion_valida_en_espacio(espacio: str, seccion: str | None) -> str:
    """Elige sección permitida: global se conserva; operativa inválida → primera."""
    espacio_n = normalizar_espacio(espacio)
    if seccion and seccion in SECCIONES_GLOBALES:
        return seccion
    if seccion and seccion in secciones_operativas(espacio_n):
        return seccion
    return primera_seccion_operativa(espacio_n)


def aplicar_seccion_pendiente(
    espacio_actual: str | None,
    seccion_actual: str | None,
    pendiente: str | None,
) -> EstadoNavegacion:
    """Resuelve deep-link `nav_section_pending` + coherencia espacio/sección.

    - Pendiente global (Configuración): conserva el espacio.
    - Pendiente operativa de otro espacio: cambia el espacio.
    - Pendiente desconocida: no cambia nada; marca destino_desconocido.
    """
    espacio = normalizar_espacio(espacio_actual)
    seccion = _seccion_valida_en_espacio(espacio, seccion_actual)

    if not pendiente:
        return EstadoNavegacion(espacio=espacio, seccion=seccion)

    if not es_seccion_conocida(pendiente):
        return EstadoNavegacion(
            espacio=espacio,
            seccion=seccion,
            destino_desconocido=True,
        )

    if pendiente in SECCIONES_GLOBALES:
        return EstadoNavegacion(espacio=espacio, seccion=pendiente)

    nuevo_espacio = espacio_para_seccion(pendiente)
    if nuevo_espacio is None:
        return EstadoNavegacion(
            espacio=espacio,
            seccion=seccion,
            destino_desconocido=True,
        )
    return EstadoNavegacion(espacio=nuevo_espacio, seccion=pendiente)


def aplicar_cambio_espacio(
    espacio_nuevo: str | None,
    seccion_actual: str | None,
) -> EstadoNavegacion:
    """Al cambiar el selector de espacio manualmente.

    Si la sección actual es Configuración, se conserva.
    Si la sección no pertenece al nuevo espacio, va a la primera operativa.
    """
    espacio = normalizar_espacio(espacio_nuevo)
    seccion = _seccion_valida_en_espacio(espacio, seccion_actual)
    return EstadoNavegacion(espacio=espacio, seccion=seccion)


def resolver_navegacion(
    *,
    espacio_actual: str | None,
    seccion_actual: str | None,
    seccion_pendiente: str | None = None,
) -> EstadoNavegacion:
    """Punto único: pendiente + coherencia con el espacio en sesión."""
    base = aplicar_seccion_pendiente(
        espacio_actual, seccion_actual, seccion_pendiente,
    )
    # Si no hubo pendiente, el espacio en sesión manda (p. ej. tras cambio de selector).
    if seccion_pendiente:
        return base
    return aplicar_cambio_espacio(base.espacio, base.seccion)
