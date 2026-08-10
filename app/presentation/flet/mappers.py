"""Traducción de resultados de dominio a mensajes de UI (sin economía)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.presentation.flet.viewmodels import FeedbackVM

_ECONOMIC_RE = re.compile(
    r"(€|euro|euros|\bcoste\b|\bprecio\b|\bmargen\b|\bimporte\b|\bvaloraci[oó]n\b)",
    re.IGNORECASE,
)
_INTERNAL_LEAK_RE = re.compile(
    r"(traceback|exception|filenotfound|permissionerror|"
    r"[A-Za-z]:\\|/home/|/Users/|\.py\b|\.pyc\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MermaLineaOperativa:
    """Datos operativos tipados para feedback (sin economía)."""

    nombre: str
    cantidad: float
    unidad: str
    lote_id: str = ""
    motivo: str = ""
    servicio: str = ""


def sanitize_mensaje(mensaje: str) -> str:
    """Bloquea textos con marcas económicas; no sustituye éxito tipado de merma."""
    text = (mensaje or "").strip()
    if not text:
        return text
    if _ECONOMIC_RE.search(text):
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
    return FeedbackVM(
        ok=False,
        mensaje=sanitize_mensaje(mensaje) or "No se pudo completar.",
        codigo=codigo,
    )


def _mensaje_error_operativo(texto: str, fallback: str) -> str:
    """Mensaje de error usable; sin economía ni fugas internas."""
    text = (texto or "").strip()
    if not text or _INTERNAL_LEAK_RE.search(text):
        return fallback
    cleaned = sanitize_mensaje(text)
    if cleaned != text and _ECONOMIC_RE.search(text):
        # sanitize genérico no aporta detalle operativo en merma.
        return fallback
    return cleaned or fallback


def map_merma_registro_feedback(
    *,
    ok: bool,
    mensaje_backend: str = "",
    codigo: str | None = None,
    lineas: tuple[MermaLineaOperativa, ...] = (),
) -> FeedbackVM:
    """Feedback de confirmación de merma desde campos operativos tipados.

    No reutiliza el mensaje de backend que incluye coste/€.
    """
    if not ok:
        texto = (mensaje_backend or "").strip()
        low = texto.lower()
        if "autoriz" in low or "permiso" in low or "no autorizado" in low:
            return FeedbackVM(
                ok=False,
                mensaje=_mensaje_error_operativo(texto, "Permiso denegado."),
                codigo=codigo or "DENEGADO",
            )
        if "idempot" in low or (codigo or "").upper() == "IDEMPOTENTE":
            return FeedbackVM(
                ok=False,
                mensaje=_mensaje_error_operativo(
                    texto, "Registro ya confirmado (idempotente)."
                ),
                codigo=codigo or "IDEMPOTENTE",
            )
        if "vacía" in low or "vacia" in low:
            return FeedbackVM(
                ok=False,
                mensaje="La cesta de merma está vacía.",
                codigo=codigo or "CESTA_VACIA",
            )
        return FeedbackVM(
            ok=False,
            mensaje=_mensaje_error_operativo(
                texto, "No se pudo registrar la merma."
            ),
            codigo=codigo,
        )

    if not lineas:
        return FeedbackVM(ok=True, mensaje="Merma registrada.", codigo=codigo)

    partes: list[str] = []
    for ln in lineas:
        trozo = f"{ln.nombre} {ln.cantidad:g} {ln.unidad}".strip()
        if ln.lote_id:
            trozo += f" (lote {ln.lote_id})"
        detalle = " · ".join(p for p in (ln.motivo, ln.servicio) if p)
        if detalle:
            trozo += f" — {detalle}"
        partes.append(trozo)
    visible = partes[:3]
    extra = f" y {len(partes) - 3} más" if len(partes) > 3 else ""
    mensaje = f"Merma registrada ({len(partes)} línea(s)): {'; '.join(visible)}{extra}."
    assert not _ECONOMIC_RE.search(mensaje), "feedback merma no debe contener economía"
    return FeedbackVM(ok=True, mensaje=mensaje, codigo=codigo)
