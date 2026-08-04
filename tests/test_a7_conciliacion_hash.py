"""Tests A7 — hash de intención y conciliación modelo/serializers."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import AppData, ConciliacionLineaDocumento, EstadoConciliacion
from app.core.services.contenido_hash import (
    contenido_hash_intencion,
    payload_intencion_documento,
)
from app.data.serializers import appdata_to_dict, dict_to_appdata


class TestA7HashConciliacion(unittest.TestCase):
    def test_hash_estable_e_independiente_de_totales(self) -> None:
        base = payload_intencion_documento(
            tipo="albaran",
            proveedor_id="prv1",
            referencia_externa="A-1",
            fecha_documento="2026-07-01",
            fecha_recepcion=None,
            ubicacion_entrada_id=None,
            moneda="EUR",
            descuento_cabecera_importe="0",
            lineas=[
                {
                    "client_line_key": "b",
                    "producto_id": "p1",
                    "cantidad_compra": "2",
                    "precio_unitario_compra": "20",
                    "factor_conversion": "24",
                },
                {
                    "client_line_key": "a",
                    "producto_id": "p1",
                    "cantidad_compra": "1",
                    "precio_unitario_compra": "10",
                    "factor_conversion": "1",
                },
            ],
        )
        h1 = contenido_hash_intencion(base)
        h2 = contenido_hash_intencion(base)
        self.assertEqual(h1, h2)
        # Reordenar entrada antes de canónica → mismo hash
        other = payload_intencion_documento(
            tipo="albaran",
            proveedor_id="prv1",
            referencia_externa="A-1",
            fecha_documento="2026-07-01",
            fecha_recepcion=None,
            ubicacion_entrada_id=None,
            moneda="EUR",
            descuento_cabecera_importe="0",
            lineas=list(reversed(base["lineas"])),
        )
        self.assertEqual(contenido_hash_intencion(other), h1)

    def test_conciliacion_roundtrip(self) -> None:
        data = AppData(
            conciliaciones_documento=[
                ConciliacionLineaDocumento(
                    id="con1",
                    linea_factura_id="lf1",
                    linea_albaran_id="la1",
                    cantidad_conciliada=Decimal("5"),
                    fecha=date(2026, 7, 1),
                    estado=EstadoConciliacion.ACTIVA,
                    confirmacion_id="11111111-1111-1111-1111-111111111111",
                )
            ]
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(len(back.conciliaciones_documento), 1)
        self.assertEqual(
            back.conciliaciones_documento[0].cantidad_conciliada, Decimal("5")
        )

    def test_legacy_sin_conciliaciones(self) -> None:
        data = dict_to_appdata({"productos": []})
        self.assertEqual(data.conciliaciones_documento, [])


if __name__ == "__main__":
    unittest.main()
