"""C3 — protección de operaciones destructivas de datos.

Todo el I/O usa TemporaryDirectory + set_demo_file_override.
BM_TEST_ISOLATION protege el demo canónico.

    python -m unittest tests.test_c3_destructive_ops -v
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BM_TEST_ISOLATION"] = "1"

from app.core.models import AppData, ArchivoDocumental, Producto, UnidadProducto
from app.core.services import backup_service as bak
from app.core.services import destructive_ops_service as dop
from app.core.services import restore_backup_service as rst
from app.core.storage.demo_files import DEMO_FILE, set_demo_file_override
from app.core.storage.json_atomic import atomic_write_json
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.pages import settings as settings_page
from app.pages import stock

DEMO_HASH = "7EE7A94468E9B57766D803E4529C4F7E9DE2CB39A11701363AA5D58820385A30"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _data_basica(*, nombre: str = "Producto A") -> AppData:
    data = AppData()
    data.productos.append(Producto("p1", nombre, UnidadProducto.UD, codigo="P-01"))
    return data


class TestC3DestructiveOps(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.json_path = self.root / "datos.json"
        atomic_write_json(self.json_path, appdata_to_dict(_data_basica()))
        set_demo_file_override(self.json_path)
        dop.clear_consumed_tokens()
        self.addCleanup(set_demo_file_override, None)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(dop.clear_consumed_tokens)

    # --- 1 inventario ---
    def test_01_inventario_acciones_destructivas(self) -> None:
        inv = dop.inventario_acciones_destructivas_visibles()
        ids = {a["id"] for a in inv}
        self.assertIn("restablecer_mock", ids)
        self.assertIn("restaurar_backup", ids)
        self.assertIn("eliminar_usuario", ids)
        self.assertIn("recargar_desde_disco", ids)
        self.assertIn("reset_data_legacy_un_clic", ids)
        reset = next(a for a in inv if a["id"] == "restablecer_mock")
        self.assertEqual(reset["clasificacion"], "B")
        self.assertEqual(reset["frase"], dop.FRASE_RESET_TOTAL)
        legacy = next(a for a in inv if a["id"] == "reset_data_legacy_un_clic")
        self.assertEqual(legacy["clasificacion"], "C")
        self.assertEqual(legacy["expuesta_en"], "oculto")

    # --- 2 acción inocua ---
    def test_02_accion_inocua_sin_barrera(self) -> None:
        src = Path(settings_page.__file__).read_text(encoding="utf-8")
        self.assertIn("settings_reload_demo", src)
        self.assertNotIn("settings_reset_demo", src)
        # Recargar no usa FRASE_RESET_TOTAL
        inocua = next(
            a
            for a in dop.inventario_acciones_destructivas_visibles()
            if a["id"] == "recargar_desde_disco"
        )
        self.assertIsNone(inocua["frase"])
        self.assertEqual(inocua["clasificacion"], "A")
        self.assertIn("settings_descargar_backup_zip", src)

    # --- 3-7 barrera ---
    def test_03_boton_deshabilitado_sin_checkbox(self) -> None:
        self.assertFalse(
            dop.boton_destructivo_habilitado(
                dop.FRASE_RESET_TOTAL, dop.FRASE_RESET_TOTAL, False
            )
        )
        r = dop.validar_confirmacion(dop.FRASE_RESET_TOTAL, dop.FRASE_RESET_TOTAL, False)
        self.assertFalse(r.ok)

    def test_04_boton_deshabilitado_frase_incorrecta(self) -> None:
        self.assertFalse(
            dop.boton_destructivo_habilitado(
                dop.FRASE_RESET_TOTAL, "borrar todos los datos", True
            )
        )

    def test_05_coincidencias_parciales_rechazadas(self) -> None:
        self.assertFalse(
            dop.boton_destructivo_habilitado(
                dop.FRASE_RESET_TOTAL, "BORRAR TODOS", True
            )
        )
        self.assertFalse(
            dop.boton_destructivo_habilitado(
                dop.FRASE_RESET_TOTAL, "BORRAR TODOS LOS DATOS Y MAS", True
            )
        )

    def test_06_frase_con_espacios_rechazada(self) -> None:
        self.assertFalse(
            dop.boton_destructivo_habilitado(
                dop.FRASE_RESET_TOTAL, " BORRAR TODOS LOS DATOS", True
            )
        )
        self.assertFalse(
            dop.boton_destructivo_habilitado(
                dop.FRASE_RESET_TOTAL, "BORRAR TODOS LOS DATOS ", True
            )
        )

    def test_07_frase_exacta_y_checkbox_permiten(self) -> None:
        self.assertTrue(
            dop.boton_destructivo_habilitado(
                dop.FRASE_RESET_TOTAL, dop.FRASE_RESET_TOTAL, True
            )
        )
        r = dop.validar_confirmacion(
            dop.FRASE_RESET_TOTAL, dop.FRASE_RESET_TOTAL, True
        )
        self.assertTrue(r.ok)
        self.assertEqual(r.estado, dop.OP_OK)

    # --- 8-10 backup preventivo ---
    def test_08_backup_preventivo_obligatorio(self) -> None:
        before = json.loads(self.json_path.read_text(encoding="utf-8"))
        res = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="tok-ok-1",
        )
        self.assertTrue(res.ok, res.mensaje)
        self.assertTrue(res.backup_preventivo)
        pre_dir = self.json_path.parent / "backups" / "pre_reset"
        files = list(pre_dir.glob("*.zip"))
        self.assertTrue(files)
        insp = rst.inspeccionar_backup(files[0].read_bytes())
        self.assertTrue(insp.ok, insp.mensaje)
        # Estado cambió respecto al previo
        after = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.assertNotEqual(before.get("productos"), after.get("productos"))

    def test_09_fallo_crear_backup_impide_modificacion(self) -> None:
        before = self.json_path.read_bytes()
        with patch.object(
            dop, "crear_backup_preventivo_pre_reset", return_value=(None, "boom")
        ):
            res = dop.restablecer_a_datos_mock(
                confirmacion_escrita=dop.FRASE_RESET_TOTAL,
                checkbox_aceptado=True,
                destino_json=self.json_path,
                operation_token="tok-fail-bak",
            )
        self.assertFalse(res.ok)
        self.assertEqual(res.estado, dop.OP_FALLIDO_SIN_CAMBIOS)
        self.assertFalse(res.muto_estado)
        self.assertEqual(self.json_path.read_bytes(), before)

    def test_10_backup_preventivo_invalido_impide(self) -> None:
        before = self.json_path.read_bytes()

        def _bad_pre(data, *, destino_json, operacion_id):
            folder = destino_json.parent / "backups" / "pre_reset"
            folder.mkdir(parents=True, exist_ok=True)
            bad = folder / f"{operacion_id}_bad.zip"
            bad.write_bytes(b"not-a-zip")
            # El servicio real valida; aquí simulamos fallo de validación
            return None, "manifest inválido"

        with patch.object(dop, "crear_backup_preventivo_pre_reset", side_effect=_bad_pre):
            res = dop.restablecer_a_datos_mock(
                confirmacion_escrita=dop.FRASE_RESET_TOTAL,
                checkbox_aceptado=True,
                destino_json=self.json_path,
                operation_token="tok-bad-pre",
            )
        self.assertFalse(res.ok)
        self.assertEqual(res.estado, dop.OP_FALLIDO_SIN_CAMBIOS)
        self.assertEqual(self.json_path.read_bytes(), before)

    # --- 11 operation_id ---
    def test_11_resultado_contiene_operation_id(self) -> None:
        res = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="tok-opid",
        )
        self.assertTrue(res.operacion_id)
        self.assertEqual(len(res.operacion_id), 36)

    # --- 12 anti rerun ---
    def test_12_doble_ejecucion_no_repite(self) -> None:
        res1 = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="tok-idem",
        )
        self.assertTrue(res1.ok)
        mid = self.json_path.read_bytes()
        # Mutar a propósito el JSON
        atomic_write_json(self.json_path, appdata_to_dict(_data_basica(nombre="Hacked")))
        res2 = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="tok-idem",
        )
        self.assertTrue(res2.ok)
        self.assertIn("token_ya_consumido", res2.advertencias)
        # No re-aplicó mock: permanece el "Hacked" que escribimos
        after = dict_to_appdata(json.loads(self.json_path.read_text(encoding="utf-8")))
        self.assertEqual(after.productos[0].nombre, "Hacked")
        self.assertNotEqual(mid, self.json_path.read_bytes())

    # --- 13-14 demo ---
    def test_13_destino_demo_rechazado_ui(self) -> None:
        src = Path(settings_page.__file__).read_text(encoding="utf-8")
        self.assertIn("Zona de peligro", settings_page._SUBTABS)
        self.assertIn("destino_es_demo_protegido", src)
        self.assertIn("settings_danger_reset_run", src)
        self.assertIn("disabled=not can_run", src)
        self.assertIn("dop.FRASE_RESET_TOTAL", src)
        self.assertEqual(dop.FRASE_RESET_TOTAL, "BORRAR TODOS LOS DATOS")

    def test_14_destino_demo_rechazado_servicio(self) -> None:
        self.assertTrue(rst.destino_es_demo_protegido(DEMO_FILE))
        before = DEMO_FILE.read_bytes()
        res = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=DEMO_FILE,
            operation_token="tok-demo",
        )
        self.assertFalse(res.ok)
        self.assertEqual(res.estado, dop.OP_RECHAZADO)
        self.assertIn("demo", res.mensaje.lower())
        self.assertEqual(DEMO_FILE.read_bytes(), before)

    # --- 15 estado cargable ---
    def test_15_estado_cargable_tras_ok(self) -> None:
        res = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="tok-load",
        )
        self.assertTrue(res.ok, res.mensaje)
        loaded = dict_to_appdata(
            json.loads(self.json_path.read_text(encoding="utf-8"))
        )
        self.assertTrue(loaded.productos)
        self.assertTrue(hasattr(loaded, "lotes"))

    # --- 16-19 fallos / recuperación ---
    def test_16_fallo_previo_sin_cambios(self) -> None:
        before = self.json_path.read_bytes()
        res = dop.restablecer_a_datos_mock(
            confirmacion_escrita="MAL",
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="tok-rej",
        )
        self.assertEqual(res.estado, dop.OP_RECHAZADO)
        self.assertFalse(res.muto_estado)
        self.assertEqual(self.json_path.read_bytes(), before)

        with patch.object(
            dop, "crear_backup_preventivo_pre_reset", return_value=(None, "x")
        ):
            res2 = dop.restablecer_a_datos_mock(
                confirmacion_escrita=dop.FRASE_RESET_TOTAL,
                checkbox_aceptado=True,
                destino_json=self.json_path,
                operation_token="tok-prefail",
            )
        self.assertEqual(res2.estado, dop.OP_FALLIDO_SIN_CAMBIOS)
        self.assertEqual(self.json_path.read_bytes(), before)

    def test_17_18_fallo_posterior_recupera(self) -> None:
        before = self.json_path.read_bytes()

        def _fail_write(dest, payload):
            # Simula mutación parcial + fallo
            Path(dest).write_bytes(b'{"productos":[]}')
            raise OSError("escritura interrumpida")

        with patch.object(dop, "_escribir_payload_mock", side_effect=_fail_write):
            res = dop.restablecer_a_datos_mock(
                confirmacion_escrita=dop.FRASE_RESET_TOTAL,
                checkbox_aceptado=True,
                destino_json=self.json_path,
                operation_token="tok-rec",
            )
        self.assertFalse(res.ok)
        self.assertTrue(res.intento_recuperacion)
        self.assertEqual(res.estado, dop.OP_FALLIDO_RECUPERADO)
        self.assertTrue(res.recuperacion_ok)
        after = dict_to_appdata(json.loads(self.json_path.read_text(encoding="utf-8")))
        self.assertEqual(after.productos[0].nombre, "Producto A")
        # Preventivo sigue disponible
        pre_dir = self.json_path.parent / "backups" / "pre_reset"
        self.assertTrue(list(pre_dir.glob("*.zip")))

    def test_19_incierto_si_recuperacion_falla(self) -> None:
        def _fail_write(dest, payload):
            Path(dest).write_bytes(b"CORRUPT")
            raise OSError("boom")

        with patch.object(dop, "_escribir_payload_mock", side_effect=_fail_write), patch.object(
            dop, "_recuperar_desde_pre_reset", return_value=False
        ):
            res = dop.restablecer_a_datos_mock(
                confirmacion_escrita=dop.FRASE_RESET_TOTAL,
                checkbox_aceptado=True,
                destino_json=self.json_path,
                operation_token="tok-inc",
            )
        self.assertEqual(res.estado, dop.OP_INCIERTO)
        self.assertTrue(res.intento_recuperacion)
        self.assertFalse(res.recuperacion_ok)

    # --- 20 preventivo permanece ---
    def test_20_backup_preventivo_permanece(self) -> None:
        res = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="tok-keep",
        )
        self.assertTrue(res.ok)
        pre = self.json_path.parent / "backups" / "pre_reset" / res.backup_preventivo
        self.assertTrue(pre.is_file())
        self.assertTrue(rst.inspeccionar_backup(pre.read_bytes()).ok)

    # --- 21-22 temporales ---
    def test_21_22_temporales_limpios(self) -> None:
        dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="tok-tmp-ok",
        )
        self.assertEqual(list(self.root.rglob("*.tmp.*")), [])
        self.assertEqual(list(self.root.rglob("bm_restore_*")), [])

        with patch.object(
            dop, "crear_backup_preventivo_pre_reset", return_value=(None, "fail")
        ):
            dop.restablecer_a_datos_mock(
                confirmacion_escrita=dop.FRASE_RESET_TOTAL,
                checkbox_aceptado=True,
                destino_json=self.json_path,
                operation_token="tok-tmp-fail",
            )
        self.assertEqual(list(self.root.rglob("*.tmp.*")), [])

    # --- 23 adjuntos ---
    def test_23_adjuntos_no_borrados_por_reset(self) -> None:
        docs = self.root / "data" / "documentos"
        docs.mkdir(parents=True)
        rel = "data/documentos/c3_keep.pdf"
        target = self.root / rel
        target.write_bytes(b"%PDF-c3")
        data = _data_basica()
        data.archivos_documentales.append(
            ArchivoDocumental(
                id="adoc1",
                nombre_original="c3_keep.pdf",
                mime_type="application/pdf",
                tamanio_bytes=7,
                sha256=_sha(b"%PDF-c3"),
                ruta_relativa=rel,
            )
        )
        atomic_write_json(self.json_path, appdata_to_dict(data))
        with patch.object(bak, "PROJECT_ROOT", self.root):
            res = dop.restablecer_a_datos_mock(
                confirmacion_escrita=dop.FRASE_RESET_TOTAL,
                checkbox_aceptado=True,
                destino_json=self.json_path,
                operation_token="tok-att",
            )
        self.assertTrue(res.ok, res.mensaje)
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), b"%PDF-c3")

    # --- 24 legacy oculto ---
    def test_24_legacy_reset_oculto(self) -> None:
        src = Path(settings_page.__file__).read_text(encoding="utf-8")
        self.assertNotIn("settings_reset_demo", src)
        self.assertNotIn("reset_data()", src)
        # Servicio legacy sigue existiendo
        from app.core.storage import session_store

        self.assertTrue(callable(session_store.reset_data))

    # --- 25 C2 sigue ---
    def test_25_restauracion_c2_sigue(self) -> None:
        zip_bytes = bak.generar_backup_zip(_data_basica(nombre="C2ok")).contenido
        atomic_write_json(self.json_path, appdata_to_dict(_data_basica(nombre="Viejo")))
        res = rst.restaurar_desde_bytes(
            zip_bytes, destino_json=self.json_path, project_root=self.root
        )
        self.assertTrue(res.ok, res.mensaje)
        after = dict_to_appdata(json.loads(self.json_path.read_text(encoding="utf-8")))
        self.assertEqual(after.productos[0].nombre, "C2ok")

    # --- 26 C1 ---
    def test_26_navegacion_c1(self) -> None:
        self.assertIn(stock.TAB_COMPRAS_DOCUMENTOS, stock._SUBTABS)
        self.assertNotIn("Albaranes", stock._SUBTABS)

    # --- 27 aislamiento ---
    def test_27_bm_test_isolation(self) -> None:
        self.assertEqual(os.environ.get("BM_TEST_ISOLATION"), "1")
        self.assertTrue(rst.destino_es_demo_protegido(DEMO_FILE))
        self.assertFalse(rst.destino_es_demo_protegido(self.json_path))

    # --- 28 hash demo ---
    def test_28_demo_hash_intacto(self) -> None:
        h = hashlib.sha256(DEMO_FILE.read_bytes()).hexdigest().upper()
        self.assertEqual(h, DEMO_HASH)

    def test_ui_separa_zonas(self) -> None:
        self.assertIn("Restauración de datos", settings_page._SUBTABS)
        self.assertIn("Zona de peligro", settings_page._SUBTABS)
        self.assertIn("Datos demo", settings_page._SUBTABS)
        src = Path(settings_page.__file__).read_text(encoding="utf-8")
        self.assertIn("FRASE_ELIMINAR_USUARIO", src)
        self.assertEqual(dop.FRASE_ELIMINAR_USUARIO, "ELIMINAR USUARIO")
        self.assertNotIn("borrado rápido", src.lower())
        self.assertNotIn("restaurar_rapido", src.lower())


if __name__ == "__main__":
    unittest.main()
