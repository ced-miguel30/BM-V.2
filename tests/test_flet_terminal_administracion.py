"""Tests Flet — Administración operativa (auth, responsables, integración)."""

from __future__ import annotations

import ast
import os
import re
import tempfile
import unittest
from dataclasses import fields
from datetime import date
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.permissions import Permiso
from app.core.auth.roles import ROL_RECEPCION  # noqa: F401 — documentación matriz
from app.core.auth.session import (
    clear_test_session,
    session_tiene_permiso,
)
from app.core.models import MotivoMerma, RolUsuario, Usuario
from app.core.auth.passwords import hash_password
from app.core.services import merma_service
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.admin_viewmodels import (
    AdminScreenVM,
    BackupItemVM,
    PendingChangeVM,
    ProductoAdminVM,
    RecetaAdminVM,
    ResponsableMermaVM,
    UsuarioAdminVM,
    assert_admin_sin_economia,
    assert_lote_alta_permite_solo_precio_total,
)
from app.presentation.flet.viewmodels import CAMPOS_ECONOMICOS_PROHIBIDOS
from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
)
from app.presentation.flet.presenters.terminal_inventario_presenter import (
    TerminalInventarioPresenter,
)
from app.presentation.flet.presenters.terminal_restaurante_presenter import (
    TerminalRestaurantePresenter,
)
from app.presentation.flet.viewmodels import CAMPOS_ECONOMICOS_PROHIBIDOS
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import (
    LOGIN_ADM,
    LOGIN_DIR,
    LOGIN_REST,
    PASS_ADM,
    PASS_DIR,
    PASS_REST,
    write_browser_fixture,
)

ROOT = Path(__file__).resolve().parent.parent
FLET_ROOT = ROOT / "app" / "presentation" / "flet"
_ECON = re.compile(
    r"(€|euro|euros|\bcoste\b|\bprecio\b|\bmargen\b|\bimporte\b|\bvaloraci[oó]n\b)",
    re.I,
)


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


class _AdminHarness(unittest.TestCase):
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

    def _login_adm(self) -> TerminalAdministracionPresenter:
        p = TerminalAdministracionPresenter()
        s = p.login(LOGIN_ADM, PASS_ADM)
        self.assertTrue(s.session.authenticated, s.feedback.mensaje if s.feedback else "")
        return p


class TestAdminAuth(_AdminHarness):
    def test_direccion_permitida(self) -> None:
        p = self._login_dir()
        self.assertTrue(session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION))
        self.assertGreaterEqual(len(p.screen().responsables), 1)

    def test_administracion_permitida(self) -> None:
        p = self._login_adm()
        self.assertTrue(p.screen().session.authenticated)

    def test_restaurante_denegado(self) -> None:
        p = TerminalAdministracionPresenter()
        s = p.login(LOGIN_REST, PASS_REST)
        self.assertFalse(s.session.authenticated)
        self.assertFalse(s.feedback.ok if s.feedback else True)

    def test_recepcion_denegada(self) -> None:
        data = get_container().app_data_store.get()
        data.usuarios.append(
            Usuario(
                "bu_rec",
                "Rec UI",
                RolUsuario.RECEPCION,
                True,
                "rec_ui",
                hash_password(PASS_DIR),
            )
        )
        get_container().app_data_store.persist(data)
        p = TerminalAdministracionPresenter()
        s = p.login("rec_ui", PASS_DIR)
        self.assertFalse(s.session.authenticated)

    def test_terminal_restaurante_mutacion_denegada(self) -> None:
        TerminalRestaurantePresenter().entrar()
        r = merma_service.crear_responsable_merma("Hack Rest")
        self.assertFalse(r.ok)

    def test_terminal_inventario_mutacion_denegada(self) -> None:
        TerminalInventarioPresenter().entrar()
        r = merma_service.crear_responsable_merma("Hack Inv")
        self.assertFalse(r.ok)
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION))

    def test_mutacion_sin_sesion_denegada(self) -> None:
        clear_test_session()
        r = merma_service.desactivar_responsable_merma("brm1")
        self.assertFalse(r.ok)


class TestAdminResponsables(_AdminHarness):
    def test_listado_filtro_crear_validacion_duplicado(self) -> None:
        p = self._login_dir()
        n0 = len(p.screen().responsables)
        p.set_filtro("Cocina")
        self.assertEqual(len(p.screen().responsables), 1)
        p.set_filtro("")
        p.proponer_creacion("")
        self.assertEqual(p.screen().feedback.codigo, "VALIDACION")
        p.proponer_creacion("Cocina UI")
        p.confirmar_pendiente()
        self.assertEqual(p.screen().feedback.codigo, "DUPLICADO")
        p.proponer_creacion("Nuevo Responsable UX")
        self.assertIsNotNone(p.screen().pending)
        p.confirmar_pendiente()
        self.assertTrue(p.screen().feedback.ok)
        self.assertEqual(len(p.screen().responsables), n0 + 1)

    def test_edicion_desactivar_reactivar_idempotente(self) -> None:
        p = self._login_adm()
        rid = p.screen().responsables[0].id
        nombre_hist = p.screen().responsables[0].nombre
        p.proponer_renombre(rid, "Cocina Renombrada")
        p.confirmar_pendiente()
        self.assertTrue(p.screen().feedback.ok)
        actual = next(r for r in p.screen().responsables if r.id == rid)
        self.assertEqual(actual.nombre, "Cocina Renombrada")
        p.proponer_desactivacion(rid)
        p.confirmar_pendiente()
        self.assertFalse(next(r for r in p.screen().responsables if r.id == rid).activo)
        # segunda desactivación → idempotente
        r = merma_service.desactivar_responsable_merma(rid)
        self.assertFalse(r.ok)
        p.proponer_reactivacion(rid)
        p.confirmar_pendiente()
        self.assertTrue(next(r for r in p.screen().responsables if r.id == rid).activo)
        self.assertNotEqual(nombre_hist, "Cocina Renombrada")

    def test_doble_confirmacion_no_duplica(self) -> None:
        p = self._login_dir()
        p.proponer_creacion("Unico DX")
        p.confirmar_pendiente()
        self.assertTrue(p.screen().feedback.ok)
        n = len([r for r in p.screen().responsables if r.nombre == "Unico DX"])
        p.confirmar_pendiente()  # sin pending
        self.assertEqual(
            len([r for r in p.screen().responsables if r.nombre == "Unico DX"]), n
        )


class TestAdminIntegracion(_AdminHarness):
    def test_activo_visible_inactivo_excluido_inventario(self) -> None:
        admin = self._login_dir()
        admin.proponer_creacion("Solo Merma")
        admin.confirmar_pendiente()
        nuevos = [
            r for r in merma_service.listar_responsables_merma(solo_activos=True)
            if r.nombre == "Solo Merma"
        ]
        self.assertEqual(len(nuevos), 1)
        rid = nuevos[0].id
        # snapshot histórico: añadir linea merma con nombre congelado
        clear_test_session()
        inv = TerminalInventarioPresenter()
        inv.entrar()
        inv.seleccionar_espacio("merma")
        inv.anadir_merma("bl_pan", 1.0, MotivoMerma.MERMA.value, responsable_id=rid)
        cesta = inv.screen().cesta_merma
        self.assertTrue(cesta)
        snap_nombre = cesta[0].responsable
        self.assertEqual(snap_nombre, "Solo Merma")
        # desactivar desde admin
        clear_test_session()
        admin = self._login_dir()
        admin.proponer_desactivacion(rid)
        admin.confirmar_pendiente()
        activos_ids = {r.id for r in merma_service.listar_responsables_merma(solo_activos=True)}
        self.assertNotIn(rid, activos_ids)
        # snapshot en memoria de cesta sigue con nombre
        clear_test_session()
        inv2 = TerminalInventarioPresenter()
        inv2.entrar()
        self.assertNotIn(
            rid, {r.id for r in inv2.screen().responsables_merma}
        )

    def test_persistencia_tras_recrear_composicion(self) -> None:
        admin = self._login_dir()
        admin.proponer_creacion("Persiste ADM")
        admin.confirmar_pendiente()
        self.assertTrue(admin.screen().feedback.ok)
        reset_container()
        clear_test_session()
        configure_for_flet(data_path=self.json_path)
        names = [
            r.nombre for r in merma_service.listar_responsables_merma(solo_activos=True)
        ]
        self.assertIn("Persiste ADM", names)

    def test_terminales_sin_permiso_admin(self) -> None:
        TerminalRestaurantePresenter().entrar()
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION))
        clear_test_session()
        TerminalInventarioPresenter().entrar()
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION))

    def test_motivos_fijos_informativos(self) -> None:
        p = self._login_dir()
        for m in MotivoMerma:
            self.assertIn(m.value, p.screen().motivos_fijos)


class TestAdminArquitectura(_AdminHarness):
    def test_viewmodels_sin_economia(self) -> None:
        assert_admin_sin_economia(
            ResponsableMermaVM,
            PendingChangeVM,
            ProductoAdminVM,
            RecetaAdminVM,
            UsuarioAdminVM,
            BackupItemVM,
            AdminScreenVM,
        )
        assert_lote_alta_permite_solo_precio_total()
        for cls in (
            ResponsableMermaVM,
            PendingChangeVM,
            ProductoAdminVM,
            RecetaAdminVM,
            UsuarioAdminVM,
            BackupItemVM,
            AdminScreenVM,
        ):
            for f in fields(cls):
                self.assertNotIn(f.name.lower(), CAMPOS_ECONOMICOS_PROHIBIDOS)

    def test_sin_streamlit_pages_json_directo(self) -> None:
        for path in FLET_ROOT.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if "admin" not in path.name and "administracion" not in path.name:
                # revisar presenters/views admin + shell + session_bridge login
                if path.name not in {
                    "session_bridge.py",
                    "mappers.py",
                    "main.py",
                }:
                    continue
            imports = _imports_of(path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("streamlit", imports)
            self.assertFalse(any(i.startswith("app.pages") for i in imports))
            if "views" in path.parts or "presenters" in path.parts:
                self.assertNotIn("json.dump", text)
                self.assertNotIn("save_demo_files", text)

    def test_sin_acoplamiento_entre_verticales(self) -> None:
        admin_view = FLET_ROOT / "views" / "admin_shell_view.py"
        imports = _imports_of(admin_view)
        self.assertFalse(any("inventario_shell" in i for i in imports))
        self.assertFalse(any("registro_servicio" in i for i in imports))
        inv = FLET_ROOT / "views" / "inventario_shell_view.py"
        self.assertFalse(any("admin" in i for i in _imports_of(inv)))

    def test_smoke_import_build_asgi(self) -> None:
        from app.presentation.flet.main_administracion import build_app_handler

        handler = build_app_handler()
        self.assertTrue(callable(handler))

        class _FakePage:
            def __init__(self) -> None:
                self.width = 900
                self.title = ""
                self.theme_mode = None
                self.padding = 0
                self.bgcolor = None
                self.on_resize = None

            def add(self, *a):
                return None

            def update(self):
                return None

        from app.presentation.flet.app_shell_administracion import (
            attach_terminal_administracion,
        )

        attach_terminal_administracion(_FakePage())

    def test_feedback_sin_economia_textual(self) -> None:
        p = self._login_dir()
        p.proponer_creacion("Eco Check")
        p.confirmar_pendiente()
        msg = p.screen().feedback.mensaje
        self.assertIsNone(_ECON.search(msg))


if __name__ == "__main__":
    unittest.main()
