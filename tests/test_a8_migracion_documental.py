"""Tests A8 — migración histórica sobre TemporaryDirectory."""

from __future__ import annotations

import json
import sys
import unittest
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    Documento,
    EstadoDocumento,
    LineaDocumento,
    TipoDocumento,
)
from app.core.services.migracion_documental_service import (
    migrar_appdata,
    migrar_json_path,
)
from app.core.services.persistencia_appdata import transactional_update_appdata
from app.data.serializers import appdata_to_dict


class TestA8Migracion(unittest.TestCase):
    def test_asigna_confirmacion_id_e_idempotente(self) -> None:
        data = AppData(
            documentos=[
                Documento(
                    id="d1",
                    tipo=TipoDocumento.ALBARAN,
                    estado=EstadoDocumento.CONFIRMADO,
                    fecha_documento=date(2026, 1, 1),
                    lineas=[
                        LineaDocumento("la1", "p1", 5.0, 10.0),
                    ],
                ),
                Documento(
                    id="d2",
                    tipo=TipoDocumento.FACTURA,
                    estado=EstadoDocumento.CONFIRMADO,
                    fecha_documento=date(2026, 1, 2),
                    lineas=[
                        LineaDocumento(
                            "lf1",
                            "p1",
                            5.0,
                            10.0,
                            linea_origen_id="la1",
                        ),
                    ],
                ),
            ]
        )
        inf1 = migrar_appdata(data)
        self.assertEqual(len(inf1.confirmacion_ids_asignados), 2)
        self.assertEqual(len(inf1.conciliaciones_creadas), 1)
        self.assertIsNotNone(data.documentos[0].confirmacion_id)
        uuid.UUID(data.documentos[0].confirmacion_id)

        inf2 = migrar_appdata(data)
        self.assertEqual(inf2.confirmacion_ids_asignados, [])
        self.assertEqual(inf2.conciliaciones_creadas, [])
        self.assertTrue(inf2.sin_cambios or not inf2.pendientes_revision)

    def test_ambiguo_no_inventa(self) -> None:
        data = AppData(
            documentos=[
                Documento(
                    id="d1",
                    tipo=TipoDocumento.ALBARAN,
                    estado=EstadoDocumento.CONFIRMADO,
                    fecha_documento=date(2026, 1, 1),
                    lineas=[LineaDocumento("la1", "p1", 5.0, 10.0)],
                ),
                Documento(
                    id="d2",
                    tipo=TipoDocumento.FACTURA,
                    estado=EstadoDocumento.CONFIRMADO,
                    fecha_documento=date(2026, 1, 2),
                    lineas=[
                        LineaDocumento(
                            "lf1",
                            "p1",
                            3.0,
                            6.0,
                            linea_origen_id="la1",
                        ),
                    ],
                ),
            ]
        )
        inf = migrar_appdata(data)
        self.assertEqual(inf.conciliaciones_creadas, [])
        self.assertTrue(inf.pendientes_revision)
        self.assertEqual(
            data.documentos[1].lineas[0].legacy_conciliacion_estado,
            "pendiente_revision",
        )

    def test_json_path_backup_dry_run_and_persist(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "datos.json"
            backup_dir = root / "backups"
            data = AppData(
                documentos=[
                    Documento(
                        id="d1",
                        tipo=TipoDocumento.ALBARAN,
                        estado=EstadoDocumento.CONFIRMADO,
                        fecha_documento=date(2026, 1, 1),
                        lineas=[],
                    )
                ]
            )
            transactional_update_appdata(json_path, lambda d: data)
            # dry-run no escribe confirmacion en disco
            before = json_path.read_text(encoding="utf-8")
            inf_dry = migrar_json_path(json_path, dry_run=True)
            self.assertTrue(inf_dry.dry_run)
            self.assertEqual(json_path.read_text(encoding="utf-8"), before)
            inf = migrar_json_path(
                json_path, backup_dir=backup_dir, dry_run=False
            )
            self.assertTrue(list(backup_dir.iterdir()))
            self.assertTrue(inf.confirmacion_ids_asignados)
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIsNotNone(loaded["documentos"][0].get("confirmacion_id"))
            # segunda pasada
            inf2 = migrar_json_path(json_path, backup_dir=backup_dir)
            self.assertEqual(inf2.confirmacion_ids_asignados, [])


if __name__ == "__main__":
    unittest.main()
