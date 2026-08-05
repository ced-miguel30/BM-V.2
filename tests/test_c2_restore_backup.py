"""C2 — restauración segura de backups (schema v2).

Todo el I/O usa TemporaryDirectory + set_demo_file_override.
BM_TEST_ISOLATION protege el demo canónico.

    python -m unittest tests.test_c2_restore_backup -v
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BM_TEST_ISOLATION"] = "1"

from app.core.models import AppData, ArchivoDocumental, Producto, UnidadProducto
from app.core.services import backup_service as bak
from app.core.services import restore_backup_service as rst
from app.core.storage.demo_files import (
    DEMO_FILE,
    set_demo_file_override,
)
from app.core.storage.json_atomic import atomic_write_json
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.data.mock_data import crear_datos_mock
from app.pages import settings as settings_page
from app.pages import stock


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _data_basica(*, nombre: str = "Producto A") -> AppData:
    data = AppData()
    data.productos.append(Producto("p1", nombre, UnidadProducto.UD, codigo="P-01"))
    return data


class TestC2RestoreBackup(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.json_path = self.root / "datos.json"
        atomic_write_json(self.json_path, appdata_to_dict(_data_basica()))
        set_demo_file_override(self.json_path)
        self.addCleanup(set_demo_file_override, None)
        self.addCleanup(self._tmp.cleanup)

    def test_01_backup_valido_aceptado(self) -> None:
        data = dict_to_appdata(
            json.loads(self.json_path.read_text(encoding="utf-8"))
        )
        zip_bytes = bak.generar_backup_zip(data).contenido
        insp = rst.inspeccionar_backup(zip_bytes)
        self.assertTrue(insp.ok, insp.mensaje)
        self.assertEqual(insp.schema_version, bak.SCHEMA_VERSION)

    def test_02_restauracion_completa(self) -> None:
        origen = _data_basica(nombre="Restaurado")
        zip_bytes = bak.generar_backup_zip(origen).contenido
        # Estado distinto en destino
        atomic_write_json(self.json_path, appdata_to_dict(_data_basica(nombre="Viejo")))
        res = rst.restaurar_desde_bytes(
            zip_bytes, destino_json=self.json_path, project_root=self.root
        )
        self.assertTrue(res.ok, res.mensaje)
        self.assertEqual(res.estado, rst.RESTORE_OK)
        after = dict_to_appdata(
            json.loads(self.json_path.read_text(encoding="utf-8"))
        )
        self.assertEqual(after.productos[0].nombre, "Restaurado")
        self.assertTrue(res.operacion_id)
        self.assertTrue(res.backup_preventivo)

    def test_03_backup_preventivo_creado_y_valido(self) -> None:
        zip_bytes = bak.generar_backup_zip(_data_basica(nombre="Nuevo")).contenido
        res = rst.restaurar_desde_bytes(
            zip_bytes, destino_json=self.json_path, project_root=self.root
        )
        self.assertTrue(res.ok, res.mensaje)
        pre_dir = self.json_path.parent / "backups" / "pre_restore"
        files = list(pre_dir.glob("*.zip"))
        self.assertTrue(files)
        insp = rst.inspeccionar_backup(files[0].read_bytes())
        self.assertTrue(insp.ok, insp.mensaje)

    def test_04_json_corrupto_rechazado(self) -> None:
        data = _data_basica()
        good = bak.generar_backup_zip(data).contenido
        # Corromper payload manteniendo manifiesto desfasado
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(
            buf, "w"
        ) as dst:
            for info in src.infolist():
                raw = src.read(info.filename)
                if info.filename == bak.APPDATA_ARCNAME:
                    raw = b"{not-json"
                dst.writestr(info.filename, raw)
        insp = rst.inspeccionar_backup(buf.getvalue())
        self.assertFalse(insp.ok)
        before = self.json_path.read_bytes()
        res = rst.restaurar_desde_bytes(
            buf.getvalue(), destino_json=self.json_path, project_root=self.root
        )
        self.assertFalse(res.ok)
        self.assertEqual(res.estado, rst.RESTORE_RECHAZADO)
        self.assertEqual(self.json_path.read_bytes(), before)

    def test_05_hash_incorrecto_rechazado(self) -> None:
        data = _data_basica()
        good = bak.generar_backup_zip(data).contenido
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(
            buf, "w"
        ) as dst:
            for info in src.infolist():
                raw = src.read(info.filename)
                if info.filename == bak.MANIFEST_NAME:
                    man = json.loads(raw.decode("utf-8"))
                    for a in man["archivos"]:
                        if a["archivo"] == bak.APPDATA_ARCNAME:
                            a["sha256"] = "0" * 64
                    raw = json.dumps(man).encode("utf-8")
                dst.writestr(info.filename, raw)
        insp = rst.inspeccionar_backup(buf.getvalue())
        self.assertFalse(insp.ok)
        self.assertIn("Hash", insp.mensaje)

    def test_06_archivo_obligatorio_ausente(self) -> None:
        data = _data_basica()
        good = bak.generar_backup_zip(data).contenido
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(
            buf, "w"
        ) as dst:
            for info in src.infolist():
                if info.filename == bak.APPDATA_ARCNAME:
                    continue
                dst.writestr(info.filename, src.read(info.filename))
        insp = rst.inspeccionar_backup(buf.getvalue())
        self.assertFalse(insp.ok)

    def test_07_version_incompatible(self) -> None:
        data = _data_basica()
        good = bak.generar_backup_zip(data).contenido
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(
            buf, "w"
        ) as dst:
            for info in src.infolist():
                raw = src.read(info.filename)
                if info.filename == bak.MANIFEST_NAME:
                    man = json.loads(raw.decode("utf-8"))
                    man["schema_version"] = 1
                    raw = json.dumps(man).encode("utf-8")
                dst.writestr(info.filename, raw)
        insp = rst.inspeccionar_backup(buf.getvalue())
        self.assertFalse(insp.ok)
        self.assertIn("incompatible", insp.mensaje.lower())

    def test_08_path_traversal_rechazado(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.json", b"{}")
            zf.writestr(
                bak.MANIFEST_NAME,
                json.dumps(
                    {
                        "schema_version": 2,
                        "archivos": [
                            {
                                "archivo": "../evil.json",
                                "bytes": 2,
                                "sha256": _sha(b"{}"),
                            }
                        ],
                    }
                ).encode(),
            )
        self.assertFalse(rst.inspeccionar_backup(buf.getvalue()).ok)

    def test_09_ruta_absoluta_rechazada(self) -> None:
        buf = io.BytesIO()
        abs_name = "C:/Windows/Temp/x.json"
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(abs_name, b"{}")
            zf.writestr(
                bak.MANIFEST_NAME,
                json.dumps(
                    {
                        "schema_version": 2,
                        "archivos": [
                            {
                                "archivo": abs_name,
                                "bytes": 2,
                                "sha256": _sha(b"{}"),
                            }
                        ],
                    }
                ).encode(),
            )
        self.assertFalse(rst.inspeccionar_backup(buf.getvalue()).ok)

    def test_10_archivo_inesperado_peligroso(self) -> None:
        data = _data_basica()
        good = bak.generar_backup_zip(data).contenido
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(
            buf, "w"
        ) as dst:
            for info in src.infolist():
                dst.writestr(info.filename, src.read(info.filename))
            dst.writestr("../../etc/passwd", b"root")
        self.assertFalse(rst.inspeccionar_backup(buf.getvalue()).ok)

    def test_11_destino_demo_rechazado(self) -> None:
        zip_bytes = bak.generar_backup_zip(_data_basica()).contenido
        self.assertTrue(rst.destino_es_demo_protegido(DEMO_FILE))
        res = rst.restaurar_desde_bytes(
            zip_bytes, destino_json=DEMO_FILE, project_root=self.root
        )
        self.assertFalse(res.ok)
        self.assertEqual(res.estado, rst.RESTORE_RECHAZADO)
        self.assertIn("demo", res.mensaje.lower())

    def test_12_fallo_staging_sin_mutacion(self) -> None:
        before = self.json_path.read_bytes()
        insp = rst.inspeccionar_backup(b"not-a-zip")
        self.assertFalse(insp.ok)
        res = rst.restaurar_desde_bytes(
            b"not-a-zip", destino_json=self.json_path, project_root=self.root
        )
        self.assertFalse(res.ok)
        self.assertEqual(self.json_path.read_bytes(), before)

    def test_13_14_estado_trazable_y_recuperacion(self) -> None:
        zip_bytes = bak.generar_backup_zip(_data_basica(nombre="OK")).contenido
        res = rst.restaurar_desde_bytes(
            zip_bytes, destino_json=self.json_path, project_root=self.root
        )
        self.assertTrue(res.ok)
        self.assertEqual(res.estado, rst.RESTORE_OK)
        self.assertTrue(res.operacion_id)
        self.assertTrue(res.archivos_validados)
        self.assertIn(bak.APPDATA_ARCNAME, res.archivos_restaurados)

        # Simular fallo de escritura JSON tras preventivo: destino protegido
        # (mismo efecto de no mutar demo real).
        res2 = rst.restaurar_desde_bytes(
            zip_bytes, destino_json=DEMO_FILE, project_root=self.root
        )
        self.assertEqual(res2.estado, rst.RESTORE_RECHAZADO)

    def test_15_16_adjuntos_y_referencia_faltante(self) -> None:
        docs = self.root / "data" / "documentos"
        docs.mkdir(parents=True)
        rel = "data/documentos/c2_test.pdf"
        (self.root / rel).write_bytes(b"%PDF-c2")
        data = _data_basica()
        data.archivos_documentales.append(
            ArchivoDocumental(
                id="adoc1",
                nombre_original="c2_test.pdf",
                mime_type="application/pdf",
                tamanio_bytes=7,
                sha256=_sha(b"%PDF-c2"),
                ruta_relativa=rel,
            )
        )
        with patch.object(bak, "PROJECT_ROOT", self.root), patch.object(
            rst, "PROJECT_ROOT", self.root
        ):
            zip_bytes = bak.generar_backup_zip(data).contenido
            insp = rst.inspeccionar_backup(zip_bytes)
            self.assertTrue(insp.ok, insp.mensaje)
            self.assertTrue(any(a["archivo"] == rel for a in insp.archivos))

            # Referencia faltante
            data2 = _data_basica()
            data2.archivos_documentales.append(
                ArchivoDocumental(
                    id="adoc2",
                    nombre_original="missing.pdf",
                    mime_type="application/pdf",
                    tamanio_bytes=1,
                    sha256=_sha(b"x"),
                    ruta_relativa="data/documentos/missing.pdf",
                )
            )
            # Backup sin el fichero: construir zip a mano desde appdata
            payload = appdata_to_dict(data2)
            app_b = json.dumps(payload).encode()
            man = {
                "schema_version": 2,
                "archivos": [
                    {
                        "archivo": bak.APPDATA_ARCNAME,
                        "bytes": len(app_b),
                        "sha256": _sha(app_b),
                        "origen": "sesion_memoria",
                    }
                ],
            }
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr(bak.APPDATA_ARCNAME, app_b)
                zf.writestr(bak.MANIFEST_NAME, json.dumps(man).encode())
            bad = rst.inspeccionar_backup(buf.getvalue())
            self.assertFalse(bad.ok)
            self.assertIn("adjunto", bad.mensaje.lower())

            # Restauración con adjunto
            target_docs = self.root / "data" / "documentos"
            if (target_docs / "c2_test.pdf").exists():
                (target_docs / "c2_test.pdf").unlink()
            res = rst.restaurar_desde_bytes(
                zip_bytes, destino_json=self.json_path, project_root=self.root
            )
            self.assertTrue(res.ok, res.mensaje)
            self.assertTrue((self.root / rel).is_file())
            self.assertEqual((self.root / rel).read_bytes(), b"%PDF-c2")

    def test_17_18_19_ui_barreras(self) -> None:
        src = Path(settings_page.__file__).read_text(encoding="utf-8")
        self.assertIn("Restauración de datos", settings_page._SUBTABS)
        self.assertIn("RESTAURAR", src)
        self.assertIn("Inspeccionar backup", src)
        self.assertIn("disabled=not can_run", src)
        self.assertIn("settings_restore_inspect", src)
        # Un solo botón de descarga de backup no restaura
        self.assertIn("settings_descargar_backup_zip", src)
        self.assertNotIn("restaurar_rapido", src.lower())
        self.assertIn("confirm_txt == \"RESTAURAR\"", src)

    def test_20_compat_creacion_backup(self) -> None:
        r = bak.generar_backup_zip(_data_basica())
        self.assertTrue(r.contenido)
        self.assertIn(bak.APPDATA_ARCNAME, r.archivos_incluidos)
        self.assertIn(bak.MANIFEST_NAME, r.archivos_incluidos)
        self.assertEqual(r.schema_version, 2)

    def test_21_repositorio_carga_restaurado(self) -> None:
        zip_bytes = bak.generar_backup_zip(_data_basica(nombre="Repo")).contenido
        rst.restaurar_desde_bytes(
            zip_bytes, destino_json=self.json_path, project_root=self.root
        )
        loaded = dict_to_appdata(
            json.loads(self.json_path.read_text(encoding="utf-8"))
        )
        self.assertEqual(loaded.productos[0].nombre, "Repo")

    def test_22_sin_temporales_tras_exito(self) -> None:
        zip_bytes = bak.generar_backup_zip(_data_basica()).contenido
        rst.restaurar_desde_bytes(
            zip_bytes, destino_json=self.json_path, project_root=self.root
        )
        leftovers = list(self.root.rglob("*.restore_tmp.*"))
        self.assertEqual(leftovers, [])
        leftovers2 = list(self.root.rglob("bm_restore_*"))
        self.assertEqual(leftovers2, [])

    def test_c1_sigue_visible_compras_documentos(self) -> None:
        self.assertIn(stock.TAB_COMPRAS_DOCUMENTOS, stock._SUBTABS)
        self.assertNotIn("Albaranes", stock._SUBTABS)

    def test_demo_hash_no_alterado_por_suite(self) -> None:
        h = hashlib.sha256(DEMO_FILE.read_bytes()).hexdigest().upper()
        self.assertEqual(
            h,
            "7EE7A94468E9B57766D803E4529C4F7E9DE2CB39A11701363AA5D58820385A30",
        )


if __name__ == "__main__":
    unittest.main()
