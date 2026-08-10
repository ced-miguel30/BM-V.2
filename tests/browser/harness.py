"""Harness Playwright + Streamlit aislado (BM_DEMO_FILE temporal)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from tests.browser.fixtures_minimos import (
    LOGIN_ADM,
    LOGIN_DIR,
    LOGIN_REST,
    PASS_ADM,
    PASS_DIR,
    PASS_REST,
    write_browser_fixture,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "tests" / "browser" / "_artifacts"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def load_appdata(json_path: Path):
    from app.data.serializers import dict_to_appdata, load_json

    return dict_to_appdata(load_json(json_path))


class BrowserE2ECase(unittest.TestCase):
    """Base: un proceso Streamlit + Chromium por clase de test."""

    base_url: str
    json_path: Path
    page: Page
    _tmp: object
    _proc: subprocess.Popen | None
    _pw: object
    _browser: object
    _log_path: Path

    @classmethod
    def setUpClass(cls) -> None:
        import tempfile

        os.environ["BM_TEST_ISOLATION"] = "1"
        cls._tmp = tempfile.TemporaryDirectory(prefix="bm_ui_")
        tmp = Path(cls._tmp.name)
        cls.json_path = tmp / "datos_hotel.json"
        write_browser_fixture(cls.json_path)
        cls._port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls._port}"
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        cls._log_path = ARTIFACTS / f"streamlit_{cls.__name__}.log"
        env = os.environ.copy()
        env["BM_TEST_ISOLATION"] = "1"
        env["BM_DEMO_FILE"] = str(cls.json_path.resolve())
        env["BM_SKIP_WEEKLY_EXPORT"] = "1"
        # Evitar que el proceso herede un override in-process accidental
        env.pop("STREAMLIT_SERVER_PORT", None)
        log_f = open(cls._log_path, "w", encoding="utf-8", errors="replace")
        cls._log_f = log_f
        cls._proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app/main.py",
                "--server.headless=true",
                f"--server.port={cls._port}",
                "--server.address=127.0.0.1",
                "--browser.gatherUsageStats=false",
            ],
            cwd=str(ROOT),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        cls._wait_ready(cls.base_url, timeout=90.0)
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(headless=True)
        cls.page = cls._browser.new_page(viewport={"width": 1400, "height": 900})

    @classmethod
    def _wait_ready(cls, url: str, timeout: float) -> None:
        import urllib.error
        import urllib.request

        deadline = time.time() + timeout
        last_err = ""
        while time.time() < deadline:
            if cls._proc and cls._proc.poll() is not None:
                raise RuntimeError(
                    f"Streamlit exited early code={cls._proc.returncode}. "
                    f"See {cls._log_path}"
                )
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if resp.status < 500:
                        return
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
            time.sleep(0.5)
        raise TimeoutError(f"Streamlit not ready at {url}: {last_err}")

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            if getattr(cls, "page", None):
                cls.page.close()
        except Exception:
            pass
        try:
            if getattr(cls, "_browser", None):
                cls._browser.close()
        except Exception:
            pass
        try:
            if getattr(cls, "_pw", None):
                cls._pw.stop()
        except Exception:
            pass
        if getattr(cls, "_proc", None) and cls._proc.poll() is None:
            cls._proc.terminate()
            try:
                cls._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls._proc.kill()
        try:
            cls._log_f.close()
        except Exception:
            pass
        try:
            cls._tmp.cleanup()
        except Exception:
            pass

    def tearDown(self) -> None:
        return

    def on_fail_screenshot(self, name: str) -> None:
        try:
            path = ARTIFACTS / f"{self.__class__.__name__}_{name}.png"
            self.page.screenshot(path=str(path), full_page=True)
        except Exception:
            pass

    def reload_app(self) -> None:
        self.page.goto(self.base_url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(800)

    def login(self, login: str, password: str) -> None:
        self.reload_app()
        tab = self.page.get_by_role("tab", name="Acceso personal")
        if tab.count():
            tab.first.click()
            self.page.wait_for_timeout(300)
        # Streamlit forms: prefer input types over labels (más estable).
        text_inputs = self.page.locator('input[type="text"]')
        pwd_inputs = self.page.locator('input[type="password"]')
        if text_inputs.count() == 0:
            # fallback labels
            self.page.get_by_label("Identificador de acceso").fill(login)
        else:
            text_inputs.first.click()
            text_inputs.first.fill(login)
        if pwd_inputs.count() == 0:
            self.page.get_by_label("Contraseña").fill(password)
        else:
            pwd_inputs.first.click()
            pwd_inputs.first.fill(password)
        self.page.get_by_role("button", name="Entrar").click()
        # Esperar puerta cerrada o error
        self.page.wait_for_timeout(2000)
        for _ in range(20):
            if self.page.get_by_role("button", name="Cerrar sesión").count():
                return
            if self.page.get_by_text("Credenciales incorrectas").count():
                return
            # Terminales también
            if "Terminal Restaurante" in self.page.content() and self.page.get_by_role(
                "button", name="Cerrar sesión"
            ).count():
                return
            self.page.wait_for_timeout(250)

    def login_dir(self) -> None:
        self.login(LOGIN_DIR, PASS_DIR)

    def login_adm(self) -> None:
        self.login(LOGIN_ADM, PASS_ADM)

    def login_rest(self) -> None:
        self.login(LOGIN_REST, PASS_REST)

    def logout(self) -> None:
        btn = self.page.get_by_role("button", name="Cerrar sesión")
        if btn.count():
            btn.first.click()
            self.page.wait_for_timeout(1000)

    def open_terminal_restaurante(self) -> None:
        self.reload_app()
        self.page.get_by_role("tab", name="Terminal Restaurante").click()
        self.page.get_by_role("button", name="Abrir Terminal Restaurante").click()
        self.page.wait_for_timeout(1500)

    def open_terminal_inventario(self) -> None:
        self.reload_app()
        self.page.get_by_role("tab", name="Terminal Inventario").click()
        self.page.get_by_role("button", name="Abrir Terminal Inventario").click()
        self.page.wait_for_timeout(1500)

    def select_espacio(self, etiqueta: str) -> None:
        """Cambia el selectbox «Espacio de trabajo» (Registro / Gestor / Inventario)."""
        sel = self.page.get_by_label("Espacio de trabajo")
        if sel.count() == 0:
            # collapsed label: localize by options text
            sel = self.page.locator("div[data-baseweb='select']").first
        try:
            self.page.get_by_text("Espacio de trabajo", exact=False).first.click(
                timeout=3000
            )
        except Exception:
            pass
        # Streamlit selectbox
        combo = self.page.locator('[data-testid="stSelectbox"]')
        if combo.count():
            combo.first.click()
            self.page.wait_for_timeout(400)
            opt = self.page.get_by_text(etiqueta, exact=True)
            if opt.count():
                opt.last.click()
                self.page.wait_for_timeout(1000)
                return
        # Fallback: keyboard / option role
        option = self.page.get_by_role("option", name=etiqueta)
        if option.count():
            option.first.click()
            self.page.wait_for_timeout(1000)

    def click_nav(self, label: str) -> None:
        # Recetas vive en espacio Inventario
        if label == "Recetas":
            self.select_espacio("Inventario")
        elif label in ("Dashboard", "Análisis"):
            self.select_espacio("Gestor")
        elif label == "Registros":
            self.select_espacio("Registro")
        elif label == "Stock":
            self.select_espacio("Inventario")
        loc = self.page.get_by_role("button", name=label)
        if loc.count() == 0:
            loc = self.page.get_by_text(label, exact=True)
        loc.first.click(timeout=15000)
        self.page.wait_for_timeout(1000)

    def click_subtab(self, label: str) -> None:
        tab = self.page.get_by_role("tab", name=label)
        if tab.count():
            tab.first.click()
        else:
            self.page.get_by_text(label, exact=True).first.click()
        self.page.wait_for_timeout(800)

    def data(self):
        return load_appdata(self.json_path)

    def assert_demo_intact(self) -> None:
        from app.core.storage.demo_files import (
            DEMO_CONTENT_SHA256_CANONICO,
            DEMO_FILE,
            sha256_demo_file,
        )

        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)
