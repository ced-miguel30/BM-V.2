"""Fase 9 — archivos documentales (hash, inmutabilidad, sin OCR).

Ejecutar:

    py -m unittest tests.test_fase9_archivos_documentales -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import AppData
from app.core.services import archivo_documental_service as ads
from app.core.storage.instance_paths import set_documentos_root_override
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui.theme import APP_VERSION


def _ctx(data: AppData):
    return build_app_context(uow=InMemoryUnitOfWork(data))


class TestFase9ArchivosDocumentales(unittest.TestCase):
    def tearDown(self) -> None:
        set_documentos_root_override(None)
    def test_01_json_antiguo(self) -> None:
        data = dict_to_appdata({"productos": []})
        self.assertEqual(data.archivos_documentales, [])

    def test_02_registrar_y_hash(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            set_documentos_root_override(base)
            r = ads.registrar_archivo(
                b"hola mundo documental",
                "albaran_demo.pdf",
                mime_type="application/pdf",
                ctx=ctx,
                base_dir=base,
            )
            self.assertTrue(r.ok, r.mensaje)
            assert r.archivo is not None
            self.assertEqual(len(r.archivo.sha256), 64)
            self.assertEqual(r.archivo.tamanio_bytes, len(b"hola mundo documental"))
            path = base / r.archivo.id / "albaran_demo.pdf"
            self.assertTrue(path.is_file())
            v = ads.verificar_integridad(r.archivo.id, ctx=ctx)
            self.assertTrue(v.ok, v.mensaje)

    def test_03_inmutable_no_sobrescribe(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            set_documentos_root_override(base)
            r1 = ads.registrar_archivo(b"AAA", "doc.txt", ctx=ctx, base_dir=base)
            self.assertTrue(r1.ok)
            # mismo contenido → rechazo por hash
            r2 = ads.registrar_archivo(b"AAA", "otro.txt", ctx=ctx, base_dir=base)
            self.assertFalse(r2.ok)
            self.assertIn("SHA-256", r2.mensaje)

    def test_04_desactivar_conserva_fichero(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            set_documentos_root_override(base)
            r = ads.registrar_archivo(b"contenido", "x.bin", ctx=ctx, base_dir=base)
            path = ads.ruta_absoluta(r.archivo)
            self.assertTrue(path.is_file())
            d = ads.desactivar_archivo(r.archivo.id, ctx=ctx)
            self.assertTrue(d.ok)
            self.assertFalse(r.archivo.activo)
            self.assertTrue(path.is_file())

    def test_05_integridad_rota(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            set_documentos_root_override(base)
            r = ads.registrar_archivo(b"original", "y.txt", ctx=ctx, base_dir=base)
            path = ads.ruta_absoluta(r.archivo)
            path.write_bytes(b"alterado")
            v = ads.verificar_integridad(r.archivo.id, ctx=ctx)
            self.assertFalse(v.ok)

    def test_06_roundtrip_metadatos(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        with tempfile.TemporaryDirectory() as tmp:
            set_documentos_root_override(Path(tmp))
            ads.registrar_archivo(
                b"meta", "z.pdf", notas="prueba", ctx=ctx, base_dir=Path(tmp)
            )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(len(back.archivos_documentales), 1)
        self.assertEqual(back.archivos_documentales[0].notas, "prueba")

    def test_07_enlazar_documento(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        with tempfile.TemporaryDirectory() as tmp:
            set_documentos_root_override(Path(tmp))
            r = ads.registrar_archivo(b"x", "a.pdf", ctx=ctx, base_dir=Path(tmp))
            e = ads.enlazar_documento(r.archivo.id, "doc_futuro_01", ctx=ctx)
            self.assertTrue(e.ok)
            self.assertEqual(r.archivo.documento_id, "doc_futuro_01")

    def test_08_leer_bytes(self) -> None:
        data = AppData()
        ctx = _ctx(data)
        payload = b"bytes-originales"
        with tempfile.TemporaryDirectory() as tmp:
            set_documentos_root_override(Path(tmp))
            r = ads.registrar_archivo(payload, "r.bin", ctx=ctx, base_dir=Path(tmp))
            bruto, err = ads.leer_bytes(r.archivo.id, ctx=ctx)
            self.assertEqual(err, "")
            self.assertEqual(bruto, payload)

    def test_09_version(self) -> None:
        self.assertIn("Ledger", APP_VERSION)
        self.assertTrue(
            "documental" in APP_VERSION.lower() or "Archivo" in APP_VERSION,
            APP_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
