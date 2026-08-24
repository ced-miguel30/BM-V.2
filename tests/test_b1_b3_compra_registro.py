"""Tests B1+B3 — conversión, borrador SoT, confirmación A2 e idempotencia."""

from __future__ import annotations

import sys
import threading
import unittest
import uuid
from datetime import date
from decimal import Decimal
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
from app.core.services.contenido_hash import contenido_hash_intencion
from app.core.services.conversion_compra import (
    ConversionDesconocidaError,
    resolver_factor_conversion,
)
from app.core.services import compra_registro_service as compra
from app.core.services.persistencia_appdata import (
    read_appdata_json,
    transactional_update_appdata,
)
from app.data.serializers import appdata_to_dict


def _seed_catalog(data: AppData) -> None:
    data.productos.append(
        Producto("p1", "Agua", UnidadProducto.UD, codigo="AGUA-01")
    )
    data.proveedores.append(
        Proveedor(id="prv1", nombre_fiscal="Norte", codigo="PRV-N")
    )


class TestB1Conversion(unittest.TestCase):
    def test_misma_unidad_uno(self) -> None:
        self.assertEqual(
            resolver_factor_conversion(
                unidad_compra="Ud",
                unidad_inventario="ud",
                factor_explicito=None,
            ),
            Decimal("1"),
        )

    def test_distinta_sin_factor_bloquea(self) -> None:
        with self.assertRaises(ConversionDesconocidaError):
            resolver_factor_conversion(
                unidad_compra="Caja",
                unidad_inventario="Ud",
                factor_explicito=None,
            )

    def test_factor_explicito(self) -> None:
        self.assertEqual(
            resolver_factor_conversion(
                unidad_compra="Caja",
                unidad_inventario="Ud",
                factor_explicito="24",
            ),
            Decimal("24"),
        )


class TestB3CompraRegistro(unittest.TestCase):
    def test_confirmar_albaran_crea_lote_sin_igic_en_coste(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_catalog(data)
                r = compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-1",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "k1",
                            "cantidad_compra": "2",
                            "unidad_compra": "Caja",
                            "unidad_inventario": "Ud",
                            "factor_conversion": "24",
                            "precio_unitario_compra": "20",
                            "impuesto_porcentaje": "7",
                        }
                    ],
                )
                self.assertTrue(r.ok, r.mensaje)
                return data

            transactional_update_appdata(path, seed)
            data = read_appdata_json(path)
            doc = data.documentos[0]
            self.assertEqual(doc.lineas[0].base_antes_descuento, Decimal("40.00"))
            self.assertEqual(doc.lineas[0].cantidad_inventario, Decimal("48"))
            h = compra.construir_hash_documento(doc)
            token = str(uuid.uuid4())
            res = compra.confirmar_compra(
                doc.id,
                confirmacion_id=token,
                contenido_hash=h,
                json_path=path,
            )
            self.assertTrue(res.ok, res.mensaje)
            after = read_appdata_json(path)
            self.assertEqual(after.documentos[0].estado.value, "confirmado")
            self.assertEqual(len(after.lotes), 1)
            self.assertEqual(after.lotes[0].cantidad, 48.0)
            self.assertEqual(after.lotes[0].precio_total, 40.0)  # sin IGIC
            self.assertEqual(after.lotes[0].documento_origen_id, doc.id)
            self.assertEqual(len(after.movimientos), 1)
            # Idempotencia
            res2 = compra.confirmar_compra(
                doc.id,
                confirmacion_id=token,
                contenido_hash=h,
                json_path=path,
            )
            self.assertTrue(res2.ok)
            self.assertEqual(res2.codigo, compra.CONFIRMACION_IDEMPOTENTE)
            after2 = read_appdata_json(path)
            self.assertEqual(len(after2.lotes), 1)

    def test_conflicto_hash_y_token_duplicado(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_catalog(data)
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-2",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "k1",
                            "cantidad_compra": "1",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "5",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-3",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "k2",
                            "cantidad_compra": "1",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "5",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed)
            data = read_appdata_json(path)
            d1, d2 = data.documentos[0], data.documentos[1]
            token = str(uuid.uuid4())
            h1 = compra.construir_hash_documento(d1)
            self.assertTrue(
                compra.confirmar_compra(
                    d1.id, confirmacion_id=token, contenido_hash=h1, json_path=path
                ).ok
            )
            bad = compra.confirmar_compra(
                d1.id,
                confirmacion_id=token,
                contenido_hash=contenido_hash_intencion({"x": 1}),
                json_path=path,
            )
            self.assertFalse(bad.ok)
            self.assertEqual(bad.codigo, compra.CONFIRMACION_CONFLICTO)
            h2 = compra.construir_hash_documento(read_appdata_json(path).documentos[1])
            dup = compra.confirmar_compra(
                d2.id, confirmacion_id=token, contenido_hash=h2, json_path=path
            )
            self.assertFalse(dup.ok)
            self.assertEqual(dup.codigo, compra.CONFIRMACION_ID_DUPLICADO)

    def test_conversion_desconocida_bloquea(self) -> None:
        data = AppData()
        _seed_catalog(data)
        r = compra.guardar_borrador(
            data,
            proveedor_id="prv1",
            lineas=[
                {
                    "producto_id": "p1",
                    "cantidad_compra": "1",
                    "unidad_compra": "Caja",
                    "unidad_inventario": "Ud",
                    "precio_unitario_compra": "10",
                }
            ],
        )
        self.assertFalse(r.ok)
        self.assertIn("Conversión", r.mensaje)

    def test_concurrencia_dos_confirmaciones(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            barrier = threading.Barrier(2)
            results: list = []

            def seed(data: AppData) -> AppData:
                _seed_catalog(data)
                compra.guardar_borrador(
                    data,
                    proveedor_id="prv1",
                    referencia_externa="ALB-C",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "kc",
                            "cantidad_compra": "1",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "8",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed)
            doc = read_appdata_json(path).documentos[0]
            h = compra.construir_hash_documento(doc)
            t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())

            def worker(token: str) -> None:
                barrier.wait()
                results.append(
                    compra.confirmar_compra(
                        doc.id,
                        confirmacion_id=token,
                        contenido_hash=h,
                        json_path=path,
                    )
                )

            th1 = threading.Thread(target=worker, args=(t1,))
            th2 = threading.Thread(target=worker, args=(t2,))
            th1.start()
            th2.start()
            th1.join()
            th2.join()
            oks = [r for r in results if r.ok and r.codigo == compra.CONFIRMACION_OK]
            self.assertEqual(len(oks), 1)
            after = read_appdata_json(path)
            self.assertEqual(len(after.lotes), 1)

    def test_confirmacion_con_adjunto_y_compensacion(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "datos.json"
            storage = root / "docs"

            def seed(data: AppData) -> AppData:
                _seed_catalog(data)
                compra.guardar_borrador(
                    data,
                    proveedor_id="prv1",
                    referencia_externa="ALB-ADJ",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "kad",
                            "cantidad_compra": "1",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "3",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed)
            doc = read_appdata_json(path).documentos[0]
            h = compra.construir_hash_documento(doc)
            res = compra.confirmar_compra(
                doc.id,
                confirmacion_id=str(uuid.uuid4()),
                contenido_hash=h,
                json_path=path,
                adjuntos=[
                    compra.AdjuntoEntrada(b"%PDF-demo", "albaran.pdf", "application/pdf")
                ],
                storage_root=storage,
            )
            self.assertTrue(res.ok, res.mensaje)
            self.assertEqual(res.adjuntos_estado, "ok")
            self.assertTrue(res.adjuntos_publicados)
            after = read_appdata_json(path)
            self.assertEqual(len(after.archivos_documentales), 1)
            self.assertTrue(after.archivos_documentales[0].storage_key)
            key = after.archivos_documentales[0].storage_key
            self.assertTrue((storage / key).exists())

            # Compensación: forzar fallo de JSON tras publish mockeando atomic_write
            def seed2(data: AppData) -> AppData:
                compra.guardar_borrador(
                    data,
                    proveedor_id="prv1",
                    referencia_externa="ALB-ADJ2",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "kad2",
                            "cantidad_compra": "1",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "3",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed2)
            doc2 = next(
                d for d in read_appdata_json(path).documentos if d.referencia_externa == "ALB-ADJ2"
            )
            h2 = compra.construir_hash_documento(doc2)
            from unittest.mock import patch

            with patch(
                "app.core.storage.json_atomic.atomic_write_json",
                side_effect=RuntimeError("boom"),
            ):
                bad = compra.confirmar_compra(
                    doc2.id,
                    confirmacion_id=str(uuid.uuid4()),
                    contenido_hash=h2,
                    json_path=path,
                    adjuntos=[
                        compra.AdjuntoEntrada(b"%PDF-x", "x.pdf", "application/pdf")
                    ],
                    storage_root=storage,
                )
            self.assertFalse(bad.ok)
            self.assertEqual(bad.adjuntos_estado, "compensado")
            # JSON intacto: doc2 sigue borrador
            still = next(
                d for d in read_appdata_json(path).documentos if d.id == doc2.id
            )
            self.assertEqual(still.estado.value, "borrador")

    def test_factura_conciliada_sin_doble_stock(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_catalog(data)
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-X",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "ka",
                            "cantidad_compra": "10",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "2",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed)
            alb = read_appdata_json(path).documentos[0]
            h_a = compra.construir_hash_documento(alb)
            self.assertTrue(
                compra.confirmar_compra(
                    alb.id,
                    confirmacion_id=str(uuid.uuid4()),
                    contenido_hash=h_a,
                    json_path=path,
                ).ok
            )
            after_a = read_appdata_json(path)
            ln_alb = after_a.documentos[0].lineas[0]

            def seed_fac(data: AppData) -> AppData:
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.FACTURA.value,
                    proveedor_id="prv1",
                    referencia_externa="FAC-X",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "kf",
                            "cantidad_compra": "10",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "2",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed_fac)
            data = read_appdata_json(path)
            fac = next(d for d in data.documentos if d.referencia_externa == "FAC-X")
            props = [
                {
                    "linea_factura_client_key": "kf",
                    "linea_albaran_id": ln_alb.id,
                    "cantidad_conciliada": "10",
                }
            ]
            h_f = compra.construir_hash_documento(fac, props)
            res = compra.confirmar_compra(
                fac.id,
                confirmacion_id=str(uuid.uuid4()),
                contenido_hash=h_f,
                json_path=path,
                conciliaciones_propuestas=props,
            )
            self.assertTrue(res.ok, res.mensaje)
            final = read_appdata_json(path)
            self.assertEqual(len(final.lotes), 1)  # sin doble stock
            self.assertEqual(len(final.conciliaciones_documento), 1)
            self.assertFalse(final.documentos[-1].impacto_stock)

    def test_factura_mixta_stock_solo_lineas_directas(self) -> None:
        """Factura con línea conciliada + línea directa: stock solo en la directa."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_catalog(data)
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-MIX",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "ka",
                            "cantidad_compra": "10",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "2",
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
            ln_alb = read_appdata_json(path).documentos[0].lineas[0]
            lotes_tras_alb = len(read_appdata_json(path).lotes)

            def seed_fac(data: AppData) -> AppData:
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.FACTURA.value,
                    proveedor_id="prv1",
                    referencia_externa="FAC-MIX",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "kf_conc",
                            "cantidad_compra": "10",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "2",
                            "impuesto_porcentaje": "0",
                        },
                        {
                            "producto_id": "p1",
                            "client_line_key": "kf_dir",
                            "cantidad_compra": "3",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "2",
                            "impuesto_porcentaje": "0",
                        },
                    ],
                )
                return data

            transactional_update_appdata(path, seed_fac)
            data = read_appdata_json(path)
            fac = next(d for d in data.documentos if d.referencia_externa == "FAC-MIX")
            props = [
                {
                    "linea_factura_client_key": "kf_conc",
                    "linea_albaran_id": ln_alb.id,
                    "cantidad_conciliada": "10",
                }
            ]
            res = compra.confirmar_compra(
                fac.id,
                confirmacion_id=str(uuid.uuid4()),
                contenido_hash=compra.construir_hash_documento(fac, props),
                json_path=path,
                conciliaciones_propuestas=props,
            )
            self.assertTrue(res.ok, res.mensaje)
            final = read_appdata_json(path)
            self.assertEqual(len(final.lotes), lotes_tras_alb + 1)
            fac_f = next(d for d in final.documentos if d.referencia_externa == "FAC-MIX")
            self.assertTrue(fac_f.impacto_stock)
            ln_conc = next(x for x in fac_f.lineas if x.client_line_key == "kf_conc")
            ln_dir = next(x for x in fac_f.lineas if x.client_line_key == "kf_dir")
            self.assertIsNone(ln_conc.lote_id)
            self.assertIsNotNone(ln_dir.lote_id)


if __name__ == "__main__":
    unittest.main()
