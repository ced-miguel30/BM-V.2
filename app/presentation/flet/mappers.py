"""Traducción de resultados de dominio a mensajes de UI (sin economía)."""

from __future__ import annotations

import re

from app.presentation.flet.viewmodels import FeedbackVM

_ECONOMIC_RE = re.compile(
    r"(€|euro|euros|\bcoste\b|\bprecio\b|\bmargen\b|\bimporte\b|\bvaloraci[oó]n\b)",
    re.IGNORECASE,
)


def sanitize_mensaje(mensaje: str) -> str:
    """Elimina referencias económicas accidentales del texto mostrado."""
    text = (mensaje or "").strip()
    if not text:
        return text
    if _ECONOMIC_RE.search(text):
        # Mensaje genérico operativo: no filtramos carácter a carácter.
        return "Operación registrada. Consulte el módulo de costes en otra interfaz."
    return text


def map_resultado(ok: bool, mensaje: str, codigo: str | None = None) -> FeedbackVM:
    return FeedbackVM(ok=ok, mensaje=sanitize_mensaje(mensaje), codigo=codigo)


def map_acceso_denegado(detalle: str | None = None) -> FeedbackVM:
    base = "Acceso denegado al Terminal Restaurante."
    if detalle:
        return FeedbackVM(ok=False, mensaje=f"{base} {sanitize_mensaje(detalle)}")
    return FeedbackVM(ok=False, mensaje=base)


def map_error_recuperable(mensaje: str, codigo: str | None = None) -> FeedbackVM:
    return FeedbackVM(ok=False, mensaje=sanitize_mensaje(mensaje) or "No se pudo completar.", codigo=codigo)
