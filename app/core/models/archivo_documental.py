"""Archivo documental digital (Fase 9).

Original inmutable en disco; metadatos en AppData.
Sin OCR ni parseo automático.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ArchivoDocumental:
    """Registro de un archivo original almacenado.

    El contenido en disco no se modifica tras el alta.
    ``documento_id`` queda opcional para enlazar albarán/factura en F10+.
    """

    id: str
    nombre_original: str
    mime_type: str
    tamanio_bytes: int
    sha256: str
    ruta_relativa: str  # relativa a PROJECT_ROOT (p.ej. data/documentos/…)
    usuario_id: str | None = None
    creado_en: datetime | None = None
    documento_id: str | None = None  # enlace futuro a cabecera documental
    notas: str | None = None
    activo: bool = True  # soft: no borra el fichero
