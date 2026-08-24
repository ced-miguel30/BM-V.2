"""Tests API pendientes de facturar y estados derivados."""

from __future__ import annotations

import sys
import unittest
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import AppData, Producto, Proveedor, TipoDocumento, UnidadProducto
from app.core.services import compra_registro_service as compra
from app.core.services.compra_pendientes_service import (
    cantidad_pendiente_facturar,
    situacion_facturacion_albaran,
)
from app.core.services.persistencia_appdata import (
    read_appdata_json,
    transactional_update_appdata,
)
from app.ui.compra_grid_helpers import lineas_libres_albaran


def _seed(data: AppData) -> None:
    data.productos.append(Producto("p1", "Agua", UnidadProducto.UD, codigo="A"))
    data.proveedores.append(Proveedor(id="prv1", nombre_fiscal="Norte", codigo="N"))


class TestCompraPendientes(unittest.TestCase):
    def test_pendiente_parcial_tras_conciliacion(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.json"

            def seed(data: AppData) -> AppData:
                _seed(data)
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-P",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "ka",
                            "cantidad_compra": "10",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "1",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed)
            alb = read_appdata_json(path).documentos[0]
            self.assertTrue(
                compra.confirmar_compra(
                    alb.id,
                    confirmacion_id=str(uuid.uuid4()),
                    contenido_hash=compra.construir_hash_documento(alb),
                    json_path=path,
                ).ok
            )
            data = read_appdata_json(path)
            ln = data.documentos[0].lineas[0]
            self.assertEqual(cantidad_pendiente_facturar(data, ln.id), Decimal("10"))
            self.assertEqual(situacion_facturacion_albaran(data, data.documentos[0]), "sin_facturar")

            def seed_fac(data: AppData) -> AppData:
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.FACTURA.value,
                    proveedor_id="prv1",
                    referencia_externa="FAC-P",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "kf",
                            "cantidad_compra": "4",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "1",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed_fac)
            data = read_appdata_json(path)
            fac = next(d for d in data.documentos if d.referencia_externa == "FAC-P")
            props = [
                {
                    "linea_factura_client_key": "kf",
                    "linea_albaran_id": ln.id,
                    "cantidad_conciliada": "4",
                }
            ]
            self.assertTrue(
                compra.confirmar_compra(
                    fac.id,
                    confirmacion_id=str(uuid.uuid4()),
                    contenido_hash=compra.construir_hash_documento(fac, props),
                    json_path=path,
                    conciliaciones_propuestas=props,
                ).ok
            )
            data = read_appdata_json(path)
            alb = next(d for d in data.documentos if d.referencia_externa == "ALB-P")
            ln = alb.lineas[0]
            self.assertEqual(cantidad_pendiente_facturar(data, ln.id), Decimal("6"))
            self.assertEqual(situacion_facturacion_albaran(data, alb), "parcial")
            libres = lineas_libres_albaran(data, alb)
            self.assertEqual(len(libres), 1)
            self.assertEqual(libres[0].id, ln.id)


if __name__ == "__main__":
    unittest.main()
