"""Fixture mínima F17 — entorno E2E aislado (sin demo real).

Uso exclusivo en tests con BM_TEST_ISOLATION + TemporaryDirectory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from app.core.auth.passwords import hash_password
from tests.auth_harness import restore_harness_session
from app.core.auth.session import (
    AuthSession,
    clear_test_session,
    set_test_session,
)
from app.core.models import (
    AppData,
    LoteStock,
    Producto,
    Proveedor,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.storage.demo_files import set_demo_file_override
from app.core.storage.json_atomic import atomic_write_json
from app.data.serializers import appdata_to_dict, dict_to_appdata

# Credenciales ficticias de fixture (solo tests; no usar en producción)
PASS_DIR = "e2e-dir-pass-99"
PASS_ADM = "e2e-adm-pass-99"
PASS_REC = "e2e-rec-pass-99"


def build_appdata_minima() -> AppData:
    """Datos operativos mínimos: 3 roles, producto, lote, proveedor."""
    ahora = datetime.now().isoformat(timespec="seconds")
    return AppData(
        productos=[
            Producto(
                "p_e2e",
                "Pan E2E",
                UnidadProducto.UD,
                codigo="E2E-01",
                servicios_disponibles=["desayuno", "comida", "cena"],
            ),
        ],
        lotes=[
            LoteStock(
                "l_e2e",
                "p_e2e",
                precio_total=20.0,
                cantidad=40.0,
                cantidad_restante=40.0,
                fecha_compra=date(2026, 7, 1),
                marca_proveedor="Prov E2E",
            ),
        ],
        proveedores=[
            Proveedor(id="prov_e2e", nombre_fiscal="Proveedor E2E", activo=True),
        ],
        usuarios=[
            Usuario(
                "u_dir_e2e",
                "Dirección E2E",
                RolUsuario.DIRECCION,
                True,
                login="dir_e2e",
                password_hash=hash_password(PASS_DIR),
                creado_en=ahora,
                modificado_en=ahora,
            ),
            Usuario(
                "u_adm_e2e",
                "Admin E2E",
                RolUsuario.ADMINISTRACION,
                True,
                login="adm_e2e",
                password_hash=hash_password(PASS_ADM),
                creado_en=ahora,
                modificado_en=ahora,
            ),
            Usuario(
                "u_rec_e2e",
                "Recepción E2E",
                RolUsuario.RECEPCION,
                True,
                login="rec_e2e",
                password_hash=hash_password(PASS_REC),
                creado_en=ahora,
                modificado_en=ahora,
            ),
        ],
        usuario_actual_id="u_dir_e2e",
    )


def session_for(
    *,
    role: str,
    actor_id: str,
    label: str,
    login: str | None = None,
    actor_type: str = "usuario",
    terminal_id: str | None = None,
    session_id: str = "e2e-sess",
) -> AuthSession:
    return AuthSession(
        authenticated=True,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=label,
        role=role,
        session_id=session_id,
        login_at=datetime.now().isoformat(timespec="seconds"),
        terminal_id=terminal_id,
        login=login,
    )


@dataclass
class E2EEnv:
    """Entorno temporal con JSON override y helpers de sesión."""

    root: Path
    json_path: Path
    data: AppData
    _tmp: object
    _patches: list

    @classmethod
    def create(cls) -> E2EEnv:
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        json_path = root / "datos_e2e.json"
        data = build_appdata_minima()
        atomic_write_json(json_path, appdata_to_dict(data))
        set_demo_file_override(json_path)
        clear_test_session()

        env = cls(root=root, json_path=json_path, data=data, _tmp=tmp, _patches=[])

        def _get():
            return env.data

        def _persist(d):
            env.data = d
            atomic_write_json(env.json_path, appdata_to_dict(d))
            return d

        for mod in (
            "app.core.services.settings_service",
            "app.core.storage.session_store",
            "app.core.services.stock_service",
            "app.core.services.ajuste_service",
            "app.core.services.backup_service",
        ):
            try:
                p = patch(f"{mod}.get_data", side_effect=_get)
                p.start()
                env._patches.append(p)
            except AttributeError:
                pass
            try:
                p = patch(f"{mod}.persist_data", side_effect=_persist)
                p.start()
                env._patches.append(p)
            except AttributeError:
                pass
        return env

    def reload_from_disk(self) -> None:
        self.data = dict_to_appdata(
            json.loads(self.json_path.read_text(encoding="utf-8"))
        )

    def as_direccion(self) -> AuthSession:
        s = session_for(
            role="direccion",
            actor_id="u_dir_e2e",
            label="Dirección E2E",
            login="dir_e2e",
            session_id="e2e-dir",
        )
        set_test_session(s)
        self.data.usuario_actual_id = "u_dir_e2e"
        return s

    def as_administracion(self) -> AuthSession:
        s = session_for(
            role="administracion",
            actor_id="u_adm_e2e",
            label="Admin E2E",
            login="adm_e2e",
            session_id="e2e-adm",
        )
        set_test_session(s)
        self.data.usuario_actual_id = "u_adm_e2e"
        return s

    def as_recepcion(self) -> AuthSession:
        s = session_for(
            role="recepcion",
            actor_id="u_rec_e2e",
            label="Recepción E2E",
            login="rec_e2e",
            session_id="e2e-rec",
        )
        set_test_session(s)
        self.data.usuario_actual_id = "u_rec_e2e"
        return s

    def as_terminal(self) -> AuthSession:
        from app.core.auth.session import iniciar_terminal_restaurante

        s = iniciar_terminal_restaurante()
        set_test_session(s)
        return s

    def cleanup(self) -> None:
        clear_test_session()
        restore_harness_session()
        for p in reversed(self._patches):
            p.stop()
        set_demo_file_override(None)
        self._tmp.cleanup()
