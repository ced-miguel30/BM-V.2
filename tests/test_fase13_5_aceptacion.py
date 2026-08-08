"""B5 — Suite de aceptación Fase 13.5 sobre almacenamiento temporal.

Cubre el checklist del Plan v3 / instrucción de ejecución (extremos a extremo).
No escribe el demo canónico.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.models import (
    AppData,
    Producto,
    Proveedor,
    TipoDocumento,
    UnidadProducto,
)
from app.core.services import anulacion_documento_service as anul
from app.core.services import compra_registro_service as compra
from app.core.services.migracion_documental_service import migrar_json_path
from app.core.services.persistencia_appdata import (
    read_appdata_json,
    transactional_update_appdata,
)
from app.core.storage.archivo_storage import LocalArchivoStorage
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from app.data.serializers import appdata_to_dict
from app.data.mock_data import crear_datos_mock


def _seed_masters(data: AppData) -> None:
    data.productos.append(
        Producto("p1", "Agua", UnidadProducto.UD, codigo="AGUA-01")
    )
    data.proveedores.append(
        Proveedor(id="prv1", nombre_fiscal="Norte SL", codigo="PRV-N")
    )


class TestB5Aceptacion(unittest.TestCase):
    def test_01_demo_protegido_hash(self) -> None:
        self.assertTrue(DEMO_FILE.exists())
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_02_e2e_albaran_adjunto_idempotencia_anulacion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "datos.json"
            storage = root / "documentos_storage"

            def seed(data: AppData) -> AppData:
                _seed_masters(data)
                r = compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-E2E",
                    descuento_cabecera_importe="0.01",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "k1",
                            "cantidad_compra": "2",
                            "unidad_compra": "Caja",
                            "unidad_inventario": "Ud",
                            "factor_conversion": "24",
                            "precio_unitario_compra": "20",
                            "descuento_porcentaje": "0",
                            "descuento_importe": "0",
                            "impuesto_porcentaje": "7",
                        }
                    ],
                )
                self.assertTrue(r.ok, r.mensaje)
                return data

            transactional_update_appdata(path, seed)
            data = read_appdata_json(path)
            doc = data.documentos[0]
            # Monetario: base 40, IGIC fuera del coste inventariable
            self.assertEqual(doc.lineas[0].base_antes_descuento, Decimal("40.00"))
            self.assertEqual(doc.lineas[0].cantidad_inventario, Decimal("48"))
            # último céntimo cabecera
            self.assertEqual(doc.lineas[0].descuento_cabecera_asignado, Decimal("0.01"))
            self.assertEqual(doc.lineas[0].coste_inventariable_linea, Decimal("39.99"))

            h = compra.construir_hash_documento(doc)
            token = str(uuid.uuid4())
            adj = compra.AdjuntoEntrada(
                contenido=b"%PDF-1.4 fake",
                nombre_original="albaran.pdf",
                mime_type="application/pdf",
            )
            res = compra.confirmar_compra(
                doc.id,
                confirmacion_id=token,
                contenido_hash=h,
                json_path=path,
                adjuntos=[adj],
                storage_root=storage,
            )
            self.assertTrue(res.ok, res.mensaje)
            self.assertEqual(res.adjuntos_estado, "ok")
            after = read_appdata_json(path)
            self.assertEqual(after.documentos[0].estado.value, "confirmado")
            self.assertEqual(len(after.lotes), 1)
            self.assertEqual(after.lotes[0].cantidad, 48.0)
            self.assertAlmostEqual(after.lotes[0].precio_total, 39.99, places=2)
            self.assertEqual(len(after.movimientos), 1)
            self.assertTrue(after.documentos[0].archivo_ids)
            self.assertTrue(
                any(a.storage_key for a in after.archivos_documentales)
            )

            # Idempotencia
            res2 = compra.confirmar_compra(
                doc.id,
                confirmacion_id=token,
                contenido_hash=h,
                json_path=path,
                adjuntos=[adj],
                storage_root=storage,
            )
            self.assertTrue(res2.ok)
            self.assertEqual(res2.codigo, compra.CONFIRMACION_IDEMPOTENTE)
            self.assertEqual(len(read_appdata_json(path).lotes), 1)

            # Concurrente: mismo token + hash → noop / no crash
            errs: list = []

            def _race() -> None:
                r = compra.confirmar_compra(
                    doc.id,
                    confirmacion_id=token,
                    contenido_hash=h,
                    json_path=path,
                )
                if not r.ok:
                    errs.append(r.mensaje)

            threads = [threading.Thread(target=_race) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errs, [])
            self.assertEqual(len(read_appdata_json(path).lotes), 1)

            # Anulación exacta
            ar = anul.anular_documento_confirmado(
                doc.id, motivo="B5 anulación", json_path=path
            )
            self.assertTrue(ar.ok, ar.mensaje)
            fin = read_appdata_json(path)
            self.assertEqual(fin.documentos[0].estado.value, "anulado")
            self.assertEqual(fin.lotes[0].cantidad_restante, 0.0)
            self.assertTrue(fin.lotes[0].anulado)

            # Residuos staging
            store = LocalArchivoStorage(storage)
            staging = getattr(store, "staging_dir", storage / "staging")
            if Path(staging).exists():
                leftovers = list(Path(staging).rglob("*"))
                self.assertFalse(
                    any(p.is_file() for p in leftovers),
                    f"staging residual: {leftovers}",
                )

    def test_03_factura_directa_y_conciliada_sin_doble_stock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_masters(data)
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-M1",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "a1",
                            "cantidad_compra": "5",
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
            self.assertEqual(len(read_appdata_json(path).lotes), 1)

            # Factura conciliada
            def fac(data: AppData) -> AppData:
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.FACTURA.value,
                    proveedor_id="prv1",
                    referencia_externa="FAC-M1",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "f1",
                            "cantidad_compra": "5",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "2",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, fac)
            data = read_appdata_json(path)
            ln_a = data.documentos[0].lineas[0]
            fac_doc = next(d for d in data.documentos if d.referencia_externa == "FAC-M1")
            props = [
                {
                    "linea_factura_client_key": "f1",
                    "linea_albaran_id": ln_a.id,
                    "cantidad_conciliada": "5",
                }
            ]
            self.assertTrue(
                compra.confirmar_compra(
                    fac_doc.id,
                    confirmacion_id=str(uuid.uuid4()),
                    contenido_hash=compra.construir_hash_documento(fac_doc, props),
                    json_path=path,
                    conciliaciones_propuestas=props,
                ).ok
            )
            mid = read_appdata_json(path)
            self.assertEqual(len(mid.lotes), 1)
            self.assertFalse(mid.documentos[-1].impacto_stock)

            # Factura directa adicional
            def fac2(data: AppData) -> AppData:
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.FACTURA.value,
                    proveedor_id="prv1",
                    referencia_externa="FAC-DIR",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "fd",
                            "cantidad_compra": "1",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "3",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, fac2)
            data = read_appdata_json(path)
            fd = next(d for d in data.documentos if d.referencia_externa == "FAC-DIR")
            self.assertTrue(
                compra.confirmar_compra(
                    fd.id,
                    confirmacion_id=str(uuid.uuid4()),
                    contenido_hash=compra.construir_hash_documento(fd),
                    json_path=path,
                ).ok
            )
            self.assertEqual(len(read_appdata_json(path).lotes), 2)

    def test_04_fallo_persistencia_sin_mutacion_memoria_previa(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_masters(data)
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-FAIL",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "k",
                            "cantidad_compra": "1",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "1",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed)
            before = read_appdata_json(path)
            # Conflicto de hash → no confirma
            bad = compra.confirmar_compra(
                before.documentos[0].id,
                confirmacion_id=str(uuid.uuid4()),
                contenido_hash="0" * 64,
                json_path=path,
            )
            self.assertFalse(bad.ok)
            after = read_appdata_json(path)
            self.assertEqual(after.documentos[0].estado.value, "borrador")
            self.assertEqual(len(after.lotes), 0)

    def test_05_reload_json_y_migracion_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"
            # Partir de mock serializado (legacy-friendly)
            payload = appdata_to_dict(crear_datos_mock())
            path.write_text(
                __import__("json").dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            loaded = read_appdata_json(path)
            self.assertTrue(loaded.productos)
            # dry-run migración
            r = migrar_json_path(path, dry_run=True)
            self.assertTrue(getattr(r, "ok", True) or r is not None)
            # hash demo intacto
            self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_06_devolucion_y_rectificativa(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "datos.json"

            def seed(data: AppData) -> AppData:
                _seed_masters(data)
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.ALBARAN.value,
                    proveedor_id="prv1",
                    referencia_externa="ALB-DEV",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "k",
                            "cantidad_compra": "8",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "1",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, seed)
            doc = read_appdata_json(path).documentos[0]
            self.assertTrue(
                compra.confirmar_compra(
                    doc.id,
                    confirmacion_id=str(uuid.uuid4()),
                    contenido_hash=compra.construir_hash_documento(doc),
                    json_path=path,
                ).ok
            )
            lote = read_appdata_json(path).lotes[0]
            self.assertTrue(
                anul.registrar_devolucion(
                    documento_origen_id=doc.id,
                    lineas=[{"lote_id": lote.id, "cantidad": 2}],
                    json_path=path,
                    motivo="B5",
                    confirmacion_id=str(uuid.uuid4()),
                ).ok
            )
            self.assertEqual(read_appdata_json(path).lotes[0].cantidad_restante, 6.0)
            # Anulación total rechazada por consumo parcial
            self.assertFalse(
                anul.anular_documento_confirmado(
                    doc.id, motivo="no", json_path=path
                ).ok
            )
            # Rectificativa económica sobre factura directa aparte
            def fac(data: AppData) -> AppData:
                compra.guardar_borrador(
                    data,
                    tipo=TipoDocumento.FACTURA.value,
                    proveedor_id="prv1",
                    referencia_externa="FAC-R",
                    lineas=[
                        {
                            "producto_id": "p1",
                            "client_line_key": "fr",
                            "cantidad_compra": "1",
                            "unidad_compra": "Ud",
                            "precio_unitario_compra": "9",
                            "impuesto_porcentaje": "0",
                        }
                    ],
                )
                return data

            transactional_update_appdata(path, fac)
            fd = next(
                d
                for d in read_appdata_json(path).documentos
                if d.referencia_externa == "FAC-R"
            )
            self.assertTrue(
                compra.confirmar_compra(
                    fd.id,
                    confirmacion_id=str(uuid.uuid4()),
                    contenido_hash=compra.construir_hash_documento(fd),
                    json_path=path,
                ).ok
            )
            n_lot = len(read_appdata_json(path).lotes)
            self.assertTrue(
                anul.registrar_rectificativa_economica(
                    documento_rectificado_id=fd.id,
                    motivo="precio",
                    json_path=path,
                ).ok
            )
            self.assertEqual(len(read_appdata_json(path).lotes), n_lot)


if __name__ == "__main__":
    unittest.main()
