"""Tests Flet — launcher mínimo (routing, auth no implícita, arquitectura)."""

from __future__ import annotations

import ast
import os
import re
import tempfile
import unittest
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.permissions import Permiso
from app.core.auth.session import clear_test_session, get_auth_session, session_tiene_permiso
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet import session_bridge
from app.presentation.flet.app_shell_launcher import LauncherShell, attach_launcher
from app.presentation.flet.launcher_routing import (
    DESTINO_ADMINISTRACION,
    DESTINO_INVENTARIO,
    DESTINO_RESTAURANTE,
    DESTINOS,
    STREAMLIT_ADMIN_HINT,
    DestinoDesconocidoError,
    listar_destinos,
    resolver_destino,
)
from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
)
from app.presentation.flet.presenters.terminal_inventario_presenter import (
    TerminalInventarioPresenter,
)
from app.presentation.flet.presenters.terminal_restaurante_presenter import (
    TerminalRestaurantePresenter,
)
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import LOGIN_DIR, PASS_DIR, write_browser_fixture

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
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


class _FakePage:
    def __init__(self) -> None:
        self.width = 900
        self.title = ""
        self.theme_mode = None
        self.padding = 0
        self.bgcolor = None
        self.on_resize = None
        self.controls: list = []

    def add(self, *controls) -> None:
        self.controls.extend(controls)

    def update(self) -> None:
        return None


class _Harness(unittest.TestCase):
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


class TestLauncherRouting(_Harness):
    def test_listado_exacto_tres_destinos(self) -> None:
        ids = [d.id for d in listar_destinos()]
        self.assertEqual(
            ids,
            [DESTINO_RESTAURANTE, DESTINO_INVENTARIO, DESTINO_ADMINISTRACION],
        )
        self.assertEqual(len(DESTINOS), 3)

    def test_resolucion_destinos_y_desconocido(self) -> None:
        self.assertEqual(resolver_destino("restaurante"), DESTINO_RESTAURANTE)
        self.assertEqual(resolver_destino("inventory"), DESTINO_INVENTARIO)
        self.assertEqual(resolver_destino("admin"), DESTINO_ADMINISTRACION)
        self.assertEqual(resolver_destino("launcher"), "launcher")
        with self.assertRaises(DestinoDesconocidoError):
            resolver_destino("compras")

    def test_streamlit_hint_sin_economia(self) -> None:
        self.assertIn("Streamlit", STREAMLIT_ADMIN_HINT)
        self.assertIsNone(_ECON.search(STREAMLIT_ADMIN_HINT))
        for d in listar_destinos():
            self.assertIsNone(_ECON.search(d.descripcion))
            self.assertIsNone(_ECON.search(d.etiqueta))


class TestLauncherShell(_Harness):
    def test_construccion_y_seleccion_sin_conceder_permisos(self) -> None:
        page = _FakePage()
        shell = attach_launcher(page)
        self.assertIsInstance(shell, LauncherShell)
        sess = get_auth_session()
        self.assertTrue(sess is None or not sess.authenticated)
        # Seleccionar Inventario no autentica como terminal hasta Entrar
        shell._on_select(DESTINO_INVENTARIO)
        self.assertEqual(shell._mounted_destino, DESTINO_INVENTARIO)
        sess2 = get_auth_session()
        self.assertTrue(sess2 is None or not sess2.authenticated)
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_INVENTARIO))

    def test_seleccion_restaurante_y_admin_sin_sesion(self) -> None:
        page = _FakePage()
        shell = attach_launcher(page)
        shell._on_select(DESTINO_RESTAURANTE)
        self.assertEqual(shell._mounted_destino, DESTINO_RESTAURANTE)
        self.assertFalse(session_bridge.puede_usar_terminal())
        shell.show_launcher()
        shell._on_select(DESTINO_ADMINISTRACION)
        self.assertEqual(shell._mounted_destino, DESTINO_ADMINISTRACION)
        self.assertFalse(session_bridge.puede_usar_administracion())

    def test_destino_desconocido_error_recuperable(self) -> None:
        page = _FakePage()
        shell = attach_launcher(page)
        shell._on_select("zzz_no_existe")
        self.assertIsNone(shell._mounted_destino)
        self.assertIn("no reconocido", shell._error.lower())

    def test_logout_al_cambiar_de_destino(self) -> None:
        # Sesión admin previa no debe sobrevivir al abrir Inventario vía launcher
        admin = TerminalAdministracionPresenter()
        admin.login(LOGIN_DIR, PASS_DIR)
        self.assertTrue(session_bridge.puede_usar_administracion())
        page = _FakePage()
        shell = attach_launcher(page)
        # mount ya hace logout
        self.assertFalse(session_bridge.puede_usar_administracion())
        shell._on_select(DESTINO_INVENTARIO)
        self.assertFalse(session_bridge.puede_usar_administracion())
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION))


class TestLauncherNoBypassAuth(_Harness):
    def test_cada_destino_conserva_auth(self) -> None:
        r = TerminalRestaurantePresenter()
        r.entrar()
        self.assertTrue(session_bridge.puede_usar_terminal())
        self.assertFalse(session_bridge.puede_usar_administracion())
        clear_test_session()
        i = TerminalInventarioPresenter()
        i.entrar()
        self.assertTrue(session_bridge.puede_usar_terminal_inventario())
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION))
        clear_test_session()
        a = TerminalAdministracionPresenter()
        a.login(LOGIN_DIR, PASS_DIR)
        self.assertTrue(session_bridge.puede_usar_administracion())

    def test_compose_unica(self) -> None:
        c1 = get_container()
        configure_for_flet(data_path=self.json_path)
        c2 = get_container()
        # Misma factory; no hay segundo root de tipos distintos
        self.assertIs(c1.app_data_store.__class__, c2.app_data_store.__class__)


class TestLauncherEntrypoints(_Harness):
    def test_main_launcher_y_bm_flet_terminal(self) -> None:
        from app.presentation.flet.main_launcher import build_app_handler as bl
        from app.presentation.flet import main as main_mod

        self.assertTrue(callable(bl()))
        old = os.environ.get("BM_FLET_TERMINAL")
        try:
            os.environ["BM_FLET_TERMINAL"] = "launcher"
            h = main_mod.build_app_handler()
            self.assertTrue(callable(h))
            os.environ["BM_FLET_TERMINAL"] = "restaurante"
            self.assertTrue(callable(main_mod.build_app_handler()))
            os.environ["BM_FLET_TERMINAL"] = "inventario"
            self.assertTrue(callable(main_mod.build_app_handler()))
            os.environ["BM_FLET_TERMINAL"] = "administracion"
            self.assertTrue(callable(main_mod.build_app_handler()))
        finally:
            if old is None:
                os.environ.pop("BM_FLET_TERMINAL", None)
            else:
                os.environ["BM_FLET_TERMINAL"] = old

    def test_entrypoints_especificos_operativos(self) -> None:
        from app.presentation.flet.main_inventario import build_app_handler as bi
        from app.presentation.flet.main_administracion import build_app_handler as ba

        self.assertTrue(callable(bi()))
        self.assertTrue(callable(ba()))


class TestLauncherArquitectura(_Harness):
    def test_sin_streamlit_pages_json_y_sin_cruzados(self) -> None:
        paths = [
            FLET_ROOT / "launcher_routing.py",
            FLET_ROOT / "app_shell_launcher.py",
            FLET_ROOT / "main_launcher.py",
            FLET_ROOT / "views" / "launcher_view.py",
        ]
        for path in paths:
            imports = _imports_of(path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("streamlit", imports)
            self.assertFalse(any(i.startswith("app.pages") for i in imports))
            self.assertNotIn("save_demo_files", text)
            self.assertNotIn("json.dump", text)
        # Verticales no importan launcher
        for name in (
            "app_shell.py",
            "app_shell_inventario.py",
            "app_shell_administracion.py",
        ):
            imports = _imports_of(FLET_ROOT / name)
            self.assertFalse(any("launcher" in i for i in imports))

    def test_asgi_smoke_launcher(self) -> None:
        from app.presentation.flet.main_launcher import build_app_handler

        handler = build_app_handler()
        page = _FakePage()
        handler(page)
        self.assertTrue(page.controls)


def _collect_texts(control) -> list[str]:
    out: list[str] = []
    if control is None:
        return out
    if isinstance(control, str):
        if control.strip():
            out.append(control.strip())
        return out
    text = getattr(control, "text", None)
    if isinstance(text, str) and text.strip():
        out.append(text.strip())
    if control.__class__.__name__ == "Text":
        value = getattr(control, "value", None)
        if isinstance(value, str) and value.strip():
            out.append(value.strip())
    content = getattr(control, "content", None)
    if content is not None:
        out.extend(_collect_texts(content))
    controls = getattr(control, "controls", None) or []
    for c in controls:
        out.extend(_collect_texts(c))
    return out


def _has_label(control, label: str) -> bool:
    return any(label == t or label in t for t in _collect_texts(control))


class TestVolverAlMenu(_Harness):
    def _assert_launcher_ui(self, shell: LauncherShell) -> None:
        self.assertIsNone(shell._mounted_destino)
        texts = _collect_texts(shell._root.content)
        joined = " ".join(texts)
        self.assertIn("Restaurante", joined)
        self.assertIn("Inventario", joined)
        self.assertIn("Administración", joined)
        self.assertIn("Streamlit", joined)
        self.assertIsNone(_ECON.search(joined))
        self.assertNotIn("streamlit.runtime", joined.lower())

    def _roundtrip(self, destino: str, authenticate) -> None:
        page = _FakePage()
        shell = attach_launcher(page)
        n_controls = len(page.controls)
        self._assert_launcher_ui(shell)

        shell._on_select(destino)
        self.assertEqual(shell._mounted_destino, destino)
        self.assertIs(shell._root, page.controls[0])
        active = shell._active_shell
        self.assertIsNotNone(active)
        self.assertTrue(_has_label(active._root.content, "Volver al menú"))

        authenticate(active)
        self.assertTrue(
            session_bridge.puede_usar_terminal()
            or session_bridge.puede_usar_terminal_inventario()
            or session_bridge.puede_usar_administracion()
        )
        active.refresh()
        self.assertTrue(_has_label(active._root.content, "Volver al menú"))

        shell.volver_al_menu()
        self.assertEqual(len(page.controls), n_controls)
        self._assert_launcher_ui(shell)
        sess = get_auth_session()
        self.assertTrue(sess is None or not sess.authenticated)
        self.assertFalse(session_bridge.puede_usar_terminal())
        self.assertFalse(session_bridge.puede_usar_terminal_inventario())
        self.assertFalse(session_bridge.puede_usar_administracion())
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION))
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_INVENTARIO))

        # Reentrar exige auth normal (sin sesión residual)
        shell._on_select(destino)
        self.assertEqual(shell._mounted_destino, destino)
        self.assertFalse(
            session_bridge.puede_usar_terminal()
            or session_bridge.puede_usar_terminal_inventario()
            or session_bridge.puede_usar_administracion()
        )

    def test_restaurante_volver_launcher(self) -> None:
        def auth(active) -> None:
            active.presenter.entrar()

        self._roundtrip(DESTINO_RESTAURANTE, auth)

    def test_inventario_volver_launcher(self) -> None:
        def auth(active) -> None:
            active.presenter.entrar()

        self._roundtrip(DESTINO_INVENTARIO, auth)

    def test_administracion_volver_launcher(self) -> None:
        def auth(active) -> None:
            active.presenter.login(LOGIN_DIR, PASS_DIR)

        self._roundtrip(DESTINO_ADMINISTRACION, auth)

    def test_volver_ejecuta_logout_explícito(self) -> None:
        page = _FakePage()
        shell = attach_launcher(page)
        shell._on_select(DESTINO_RESTAURANTE)
        active = shell._active_shell
        active.presenter.entrar()
        self.assertTrue(session_bridge.puede_usar_terminal())
        shell.volver_al_menu()
        self.assertFalse(session_bridge.puede_usar_terminal())
        self.assertIsNone(shell._mounted_destino)

    def test_entrypoints_directos_sin_volver_menu(self) -> None:
        from app.presentation.flet.app_shell import TerminalRestauranteShell
        from app.presentation.flet.app_shell_administracion import (
            TerminalAdministracionShell,
        )
        from app.presentation.flet.app_shell_inventario import TerminalInventarioShell

        for Shell in (
            TerminalRestauranteShell,
            TerminalInventarioShell,
            TerminalAdministracionShell,
        ):
            page = _FakePage()
            sh = Shell(page)
            sh.mount()
            self.assertEqual(len(page.controls), 1)
            self.assertFalse(_has_label(sh._root.content, "Volver al menú"))


if __name__ == "__main__":
    unittest.main()
