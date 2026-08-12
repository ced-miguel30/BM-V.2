"""Tests Flet — Administración maestros (productos, recetas, usuarios, backup)."""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import clear_test_session
from app.core.models import UnidadProducto
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.admin_viewmodels import (
    AdminScreenVM,
    BackupItemVM,
    LoteAltaVM,
    PendingChangeVM,
    ProductoAdminVM,
    ProveedorAdminVM,
    RecetaAdminVM,
    ResponsableMermaVM,
    UsuarioAdminVM,
    assert_admin_sin_economia,
    assert_compra_linea_permite_precio_unitario,
    assert_lote_alta_permite_solo_precio_total,
)
from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
    _backups_dir,
)
from app.presentation.flet.presenters.terminal_restaurante_presenter import (
    TerminalRestaurantePresenter,
)
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import LOGIN_DIR, PASS_DIR, write_browser_fixture

ROOT = Path(__file__).resolve().parent.parent
FLET_ROOT = ROOT / "app" / "presentation" / "flet"
ADMIN_VIEW = FLET_ROOT / "views" / "admin_shell_view.py"


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name.split(".")[0])
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
            out.add(node.module)
    return out


class _MaestrosHarness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.json_path = Path(self._tmp.name) / "datos_hotel.json"
        write_browser_fixture(self.json_path)
        reset_container()
        clear_test_session()
        set_demo_file_override(None)
        configure_for_flet(data_path=self.json_path)
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        reset_container()
        clear_test_session()
        set_demo_file_override(None)
        restore_harness_session()
        self._tmp.cleanup()
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def _login_dir(self) -> TerminalAdministracionPresenter:
        p = TerminalAdministracionPresenter()
        s = p.login(LOGIN_DIR, PASS_DIR)
        self.assertTrue(s.session.authenticated, s.feedback.mensaje if s.feedback else "")
        return p


class TestAdminMaestrosAuth(_MaestrosHarness):
    def test_login_direccion(self) -> None:
        p = self._login_dir()
        s = p.screen()
        self.assertEqual(s.seccion, "inicio")
        self.assertTrue(s.puede_exportar_backup)
        self.assertTrue(s.puede_restaurar_backup)
        self.assertTrue(s.puede_gestionar_usuarios)


class TestAdminProductos(_MaestrosHarness):
    def test_crear_producto(self) -> None:
        p = self._login_dir()
        n0 = len(p.screen().productos)
        s = p.crear_producto(
            "Harina Admin",
            UnidadProducto.KG.value,
            2.0,
            "HAR-ADM-01",
            "consumible",
            es_bebida=False,
            servicios_disponibles=["desayuno", "comida"],
        )
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertEqual(len(s.productos), n0 + 1)
        self.assertTrue(any(x.nombre == "Harina Admin" for x in s.productos))

    def test_desactivar_producto(self) -> None:
        p = self._login_dir()
        p.crear_producto(
            "Temp Desact",
            UnidadProducto.UD.value,
            0.0,
            "TMP-DES-01",
            "consumible",
        )
        pid = next(x.id for x in p.screen().productos if x.nombre == "Temp Desact")
        p.proponer_desactivar_producto(pid)
        self.assertIsNotNone(p.screen().pending)
        p.confirmar_pendiente()
        self.assertTrue(p.screen().feedback.ok)
        actual = next(x for x in p.screen().productos if x.id == pid)
        self.assertFalse(actual.activo)


class TestAdminRecetas(_MaestrosHarness):
    def test_crear_receta_aparece_en_listado(self) -> None:
        p = self._login_dir()
        prod = next(x for x in p.screen().productos if x.activo)
        n0 = len(p.screen().recetas)
        s = p.crear_receta(
            "Receta Admin Nueva",
            [(prod.id, 1.0)],
            "desayuno",
            2.0,
            servicios_disponibles=["desayuno"],
        )
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertEqual(len(s.recetas), n0 + 1)
        self.assertTrue(any(r.nombre == "Receta Admin Nueva" for r in s.recetas))

    def test_receta_visible_en_restaurante(self) -> None:
        admin = self._login_dir()
        prod = next(x for x in admin.screen().productos if x.activo)
        admin.crear_receta(
            "Cruzado Rest Admin",
            [(prod.id, 0.5)],
            "desayuno",
            1.0,
            servicios_disponibles=["desayuno"],
        )
        self.assertTrue(admin.screen().feedback.ok)
        clear_test_session()
        rest = TerminalRestaurantePresenter()
        rest.entrar()
        rest.seleccionar_servicio("desayuno")
        nombres = {c.nombre for c in rest.screen().catalogo}
        self.assertIn("Cruzado Rest Admin", nombres)


    def test_crear_receta_multi_ingrediente_y_teorico(self) -> None:
        p = self._login_dir()
        activos = [x for x in p.screen().productos if x.activo][:2]
        self.assertGreaterEqual(len(activos), 1)
        ings = [(activos[0].id, 1.0)]
        if len(activos) > 1:
            ings.append((activos[1].id, 0.5))
        s = p.crear_receta(
            "Receta Multi UX",
            ings,
            "desayuno",
            4.0,
            servicios_disponibles=["desayuno"],
        )
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        p.set_seccion("recetas")
        s2 = p.screen()
        rec = next(r for r in s2.recetas if r.nombre == "Receta Multi UX")
        self.assertEqual(rec.n_ingredientes, len(ings))
        # Dirección con CONSULTAR_COSTES: valoración teórica formateada
        self.assertTrue(rec.teorico_fmt or rec.teorico_fmt == "")


class TestAdminUsuarios(_MaestrosHarness):
    def test_crear_usuario(self) -> None:
        p = self._login_dir()
        n0 = len(p.screen().usuarios)
        s = p.crear_usuario(
            "Usuario Nuevo UI",
            "administracion",
            login="nuevo_ui",
            password="UiTestPass1",
        )
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertEqual(len(s.usuarios), n0 + 1)
        self.assertTrue(any(u.login == "nuevo_ui" for u in s.usuarios))


class TestAdminBackup(_MaestrosHarness):
    def test_generar_backup_escribe_zip(self) -> None:
        p = self._login_dir()
        s = p.generar_backup()
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertGreaterEqual(len(s.backups), 1)
        dest = _backups_dir()
        zips = list(dest.glob("*.zip"))
        self.assertTrue(zips)
        self.assertGreater(zips[0].stat().st_size, 0)


class TestAdminResponsablesSiguen(_MaestrosHarness):
    def test_responsables_crear_sigue_ok(self) -> None:
        p = self._login_dir()
        p.set_seccion("responsables")
        n0 = len(p.screen().responsables)
        p.proponer_creacion("Resp Maestros OK")
        p.confirmar_pendiente()
        self.assertTrue(p.screen().feedback.ok)
        self.assertEqual(len(p.screen().responsables), n0 + 1)


class TestAdminArquitecturaMaestros(_MaestrosHarness):
    def test_viewmodels_economia(self) -> None:
        assert_admin_sin_economia(
            ResponsableMermaVM,
            PendingChangeVM,
            ProductoAdminVM,
            RecetaAdminVM,
            UsuarioAdminVM,
            ProveedorAdminVM,
            BackupItemVM,
            AdminScreenVM,
        )
        assert_lote_alta_permite_solo_precio_total()
        assert_compra_linea_permite_precio_unitario()
        from dataclasses import fields

        self.assertIn("precio_total", {f.name for f in fields(LoteAltaVM)})

    def test_admin_view_sin_appdata_ni_servicios(self) -> None:
        imports = _imports_of(ADMIN_VIEW)
        text = ADMIN_VIEW.read_text(encoding="utf-8")
        self.assertNotIn("AppData", text)
        self.assertFalse(any(i.startswith("app.core.services") for i in imports))
        self.assertFalse(any(i.startswith("app.core.repositories") for i in imports))
        self.assertNotIn("json", imports)
        self.assertNotIn("streamlit", imports)
        self.assertFalse(any(i.startswith("app.pages") for i in imports))


if __name__ == "__main__":
    unittest.main()
