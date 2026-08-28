"""Unidades por envase (Ud de catálogo = caja/paquete, no pieza).

En desayuno/buffet las cantidades operativas son piezas individuales;
hay que convertir a Ud nativa = piezas / unidades_por_paquete.
"""

from __future__ import annotations

# producto_id → piezas por 1 Ud de inventario (caja/bandeja/bolsa)
UNIDADES_POR_PAQUETE: dict[str, float] = {
    # Pan molde (rebanadas)
    "p09": 31.0,  # MOLDE COMUN S/C 800GRS
    "p11": 31.0,  # MOLDE INTEGRAL S/C 1000 GRS
    # Pan sin gluten (panecillos por caja)
    "p04": 45.0,  # PANECILLO S/GLUTEN BETINA 55GRS 45 UND
    # Panes / bollería buffet (piezas por caja)
    "p05": 20.0,  # PAN GALLEGO BARRA 280GR 20 UND
    "p357": 10.0,  # PAN MAIZ 350GRS BERLYS 10UN
    "p276": 20.0,  # PAN MONTAÑEZ CENTENO 20UD 320G
    "p252": 66.0,  # BAGUETTINA 120GRS 66UN
    "p251": 100.0,  # MINI NAPOLITANA CACAO CREMA 100UND
    "p294": 325.0,  # CHIC CREMA 325UN 20GRS
    "p250": 194.0,  # MINI LAZO VITALCEREAL 194UD 18GRS
    "p249": 280.0,  # MINI CROISSANT RECTO MANTQUILLA 280UN
    "b01": 198.0,  # CROISSANT MINI CHOCOLATE CREMOSO 198UD
}


def piezas_a_ud_paquete(producto_id: str, piezas: float) -> float:
    """Convierte N piezas individuales → fracción de Ud de inventario."""
    pack = UNIDADES_POR_PAQUETE.get(producto_id)
    if not pack or pack <= 0:
        return float(piezas)
    return round(float(piezas) / pack, 6)


def ud_paquete_a_piezas(producto_id: str, ud: float) -> float:
    pack = UNIDADES_POR_PAQUETE.get(producto_id)
    if not pack or pack <= 0:
        return float(ud)
    return round(float(ud) * pack, 6)
