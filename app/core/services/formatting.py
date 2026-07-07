"""Formateo de valores para la interfaz."""

from datetime import date, datetime


def formato_moneda(valor: float, simbolo: str = "€") -> str:
    """Formatea un valor monetario al estilo español."""
    entero, decimal = f"{valor:.2f}".split(".")
    entero_fmt = f"{int(entero):,}".replace(",", ".")
    return f"{entero_fmt},{decimal} {simbolo}"


def formato_fecha(fecha: date | datetime | None) -> str:
    """Formatea una fecha a dd/mm/aaaa."""
    if fecha is None:
        return "—"
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    return fecha.strftime("%d/%m/%Y")


def formato_fecha_hora(fecha: datetime) -> str:
    """Formatea fecha y hora."""
    return fecha.strftime("%d/%m/%Y %H:%M")
