"""Tests B2 — anulación exacta, devolución y rectificativa económica."""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    Producto,
    Proveedor,
    TipoDocumento,
    UnidadProducto,
)
from app.core.services import anulacion_documento_service as anul
from app.core.services import compra_registro_service as compra
from app.core.services.persistencia_appdata import (
    read_appdata_json,
    transactional_update_appdata,
)


def _seed_catalog(data: AppData) -> None:
    data.productos.append(Producto("p1", "Agua", UnidadProducto.UD, codigo="AGUA-01"))
    data.proveedores.append(Proveedor(id="prv1", nombre_fiscal="Norte", codigo="PRV-N"))


def _confirmar_albaran(path: Path, *, ref: str = "ALB-B2", qty: str = "10") -> str:
    def seed(data: AppData) -> AppData:
        _seed_catalog(data)
        r = compra.guardar_borrador(
            data,
            tipo=TipoDocumento.ALBARAN.value,
            proveedor_id="prv1",
            referencia_externa=ref,
            lineas=[
                {
                    "producto_id": "p1",
                    "client_line_key": "k1",
                    "cantidad_compra": qty,
                    "unidad_compra": "Ud",
                    "precio_unitario_compra": "5",
                    "impuesto_porcentaje": "0",
                }
            ],
        )
        assert r.ok, r.mensaje
        return data

    transactional_update_appdata(path, seed)
    data = read_appdata_json(path)
    doc = data.documentos[0]
    token = str(uuid.uuid4())
    h = compra.construir_hash_documento(doc)
    res = compra.confirmar_compra(
        doc.id, confirmacion_id=token, contenido_hash=h, json_path=path
    )
    assert res.ok, res.mensaje
    return doc.id


class TestB2Anulacion(unittest.TestCase):
    def test_anular_albaran_integro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            doc_id = _confirmar_albaran(path)
            before = read_appdata_json(path)
            n_mov = len(before.movimientos)
            r = anul.anular_documento_confirmado(
                doc_id, motivo="Error de recepción", json_path=path
            )
            self.assertTrue(r.ok, r.mensaje)
            after = read_appdata_json(path)
            doc = next(d for d in after.documentos if d.id == doc_id)
            self.assertEqual(doc.estado.value, "anulado")
            self.assertEqual(len(after.lotes), 1)
            self.assertTrue(after.lotes[0].anulado)
            self.assertEqual(after.lotes[0].cantidad_restante, 0.0)
            self.assertEqual(len(after.movimientos), n_mov + 1)
            rev = after.movimientos[-1]
            self.assertEqual(
                rev.tipo.value if hasattr(rev.tipo, "value") else rev.tipo,
                "reversion_entrada",
            )
            self.assertIsNotNone(rev.movimiento_revertido_id)

    def test_segunda_anulacion_idempotente(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            doc_id = _confirmar_albaran(path, ref="ALB-IDEM")
            r1 = anul.anular_documento_confirmado(
                doc_id, motivo="Primera", json_path=path
            )
            self.assertTrue(r1.ok)
            n_mov = len(read_appdata_json(path).movimientos)
            r2 = anul.anular_documento_confirmado(
                doc_id, motivo="Segunda", json_path=path
            )
            self.assertTrue(r2.ok)
            self.assertEqual(r2.codigo, anul.ANULACION_IDEMPOTENTE)
            self.assertEqual(len(read_appdata_json(path).movimientos), n_mov)

    def test_rechazo_si_lote_parcialmente_consumido(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            doc_id = _confirmar_albaran(path, ref="ALB-CONS", qty="10")

            def consume(data: AppData) -> AppData:
                data.lotes[0].cantidad_restante = 4.0
                return data

            transactional_update_appdata(path, consume)
            r = anul.anular_documento_confirmado(
                doc_id, motivo="Intento", json_path=path
            )
            self.assertFalse(r.ok)
            self.assertIn("parcialmente consumido", r.mensaje.lower())
            after = read_appdata_json(path)
            self.assertEqual(after.documentos[0].estado.value, "confirmado")
            self.assertEqual(after.lotes[0].cantidad_restante, 4.0)

    def test_albaran_bloqueado_con_conciliacion_activa(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            alb_id = _confirmar_albaran(path, ref="ALB-CONC")

            def factura_conc(data: AppData) -> AppData:
                r = compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.FACTURA.value,
                    proveedor_id="prv1",
                    referencia_externa="FAC-C1",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "f1",
                            "cantidad_compra": "10",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "5",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                assert r.ok, r.mensaje
                return data

            transactional_update_appdata(path, factura_conc)
            data = read_appdata_json(path)
            alb = next(d for d in data.documentos if d.id == alb_id)
            fac = next(d for d in data.documentos if d.referencia_externa == "FAC-C1")
            conc_payload = [
                {
                    "linea_factura_client_key": "f1",
                    "linea_albaran_id": alb.lineas[0].id,
                    "cantidad_conciliada": "10",
                }
            ]
            h = compra.construir_hash_documento(fac, conc_payload)
            cres = compra.confirmar_compra(
                fac.id,
                confirmacion_id=str(uuid.uuid4()),
                contenido_hash=h,
                json_path=path,
                conciliaciones_propuestas=conc_payload,
            )
            self.assertTrue(cres.ok, cres.mensaje)
            r = anul.anular_documento_confirmado(
                alb_id, motivo="No debería", json_path=path
            )
            self.assertFalse(r.ok)
            self.assertIn("conciliaciones activas", r.mensaje.lower())

    def test_devolucion_parcial_trazable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            doc_id = _confirmar_albaran(path, ref="ALB-DEV", qty="10")
            lote_id = read_appdata_json(path).lotes[0].id
            token = str(uuid.uuid4())
            r = anul.registrar_devolucion(
                documento_origen_id=doc_id,
                lineas=[{"lote_id": lote_id, "cantidad": 3}],
                json_path=path,
                motivo="Rotura",
                confirmacion_id=token,
            )
            self.assertTrue(r.ok, r.mensaje)
            after = read_appdata_json(path)
            self.assertEqual(after.lotes[0].cantidad_restante, 7.0)
            self.assertEqual(
                after.documentos[-1].tipo.value
                if hasattr(after.documentos[-1].tipo, "value")
                else after.documentos[-1].tipo,
                "devolucion",
            )
            r2 = anul.registrar_devolucion(
                documento_origen_id=doc_id,
                lineas=[{"lote_id": lote_id, "cantidad": 3}],
                json_path=path,
                motivo="Rotura",
                confirmacion_id=token,
            )
            self.assertTrue(r2.ok)
            self.assertEqual(r2.codigo, anul.ANULACION_IDEMPOTENTE)
            self.assertEqual(read_appdata_json(path).lotes[0].cantidad_restante, 7.0)

    def test_rectificativa_economica_sin_stock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            doc_id = _confirmar_albaran(path, ref="ALB-RECT")
            before = read_appdata_json(path)
            n_lot = len(before.lotes)
            n_mov = len(before.movimientos)
            rest = before.lotes[0].cantidad_restante
            token = str(uuid.uuid4())
            r = anul.registrar_rectificativa_economica(
                documento_rectificado_id=doc_id,
                motivo="Error precio documental",
                json_path=path,
                confirmacion_id=token,
            )
            self.assertTrue(r.ok, r.mensaje)
            after = read_appdata_json(path)
            self.assertEqual(len(after.lotes), n_lot)
            self.assertEqual(len(after.movimientos), n_mov)
            self.assertEqual(after.lotes[0].cantidad_restante, rest)
            orig = next(d for d in after.documentos if d.id == doc_id)
            self.assertEqual(orig.estado.value, "rectificado")
            rect = next(
                d
                for d in after.documentos
                if (d.tipo.value if hasattr(d.tipo, "value") else d.tipo)
                == "rectificativa"
            )
            self.assertIs(rect.impacto_stock, False)


if __name__ == "__main__":
    unittest.main()
