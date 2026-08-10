"""Sesión de autenticación F16 (sin contraseñas en el store de sesión).

La persistencia de AuthSession se obtiene del composition root
(``AuthSessionStore``). El adaptador Streamlit vive en
``app.presentation.streamlit.adapters``.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from app.core.auth.passwords import (
    hash_password,
    migrate_legacy_if_needed,
    password_usable,
    verify_password,
)
from app.core.auth.permissions import Permiso, tiene_permiso
from app.core.auth.roles import (
    ROL_ADMINISTRACION,
    ROL_RESTAURANTE,
    es_direccion,
    rol_canonico,
)
from app.core.models import Usuario

AUTH_SESSION_KEY = "bm_auth_session"
TERMINAL_ID_DEFAULT = "terminal_restaurante"
TERMINAL_ACTOR_ID = "terminal_restaurante"
TERMINAL_LABEL = "Restaurante"
TERMINAL_INVENTARIO_ID = "terminal_inventario"
TERMINAL_INVENTARIO_ACTOR_ID = "terminal_inventario"
TERMINAL_INVENTARIO_LABEL = "Inventario"

ACTOR_TYPE_USUARIO = "usuario"
ACTOR_TYPE_TERMINAL = "terminal"
ACTOR_TYPE_SISTEMA = "sistema"

MSG_LOGIN_FALLIDO = "Credenciales incorrectas."

_DUMMY_HASH = (
    "pbkdf2_sha256$200000$"
    "AAAAAAAAAAAAAAAAAAAAAA==$"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
)

# Override harness de tests (prioridad sobre store)
_TEST_SESSION: AuthSession | None = None
_TEST_OVERRIDE: bool = False

_PERMISOS_BLOQUEADOS_TERMINAL_INVENTARIO = frozenset({
    Permiso.CONSULTAR_COSTES,
    Permiso.ACCEDER_CONFIGURACION,
    Permiso.ACCEDER_GESTOR,
    Permiso.ACCEDER_COMPRAS_DOCUMENTOS,
})


@dataclass
class AuthSession:
    authenticated: bool
    actor_type: str
    actor_id: str
    actor_label: str
    role: str
    session_id: str
    login_at: str
    terminal_id: str | None = None
    login: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> AuthSession | None:
        if not raw or not raw.get("authenticated"):
            return None
        try:
            return cls(
                authenticated=True,
                actor_type=str(raw.get("actor_type") or ACTOR_TYPE_USUARIO),
                actor_id=str(raw.get("actor_id") or ""),
                actor_label=str(raw.get("actor_label") or ""),
                role=rol_canonico(raw.get("role")),
                session_id=str(raw.get("session_id") or ""),
                login_at=str(raw.get("login_at") or ""),
                terminal_id=raw.get("terminal_id"),
                login=raw.get("login"),
            )
        except (TypeError, ValueError):
            return None


@dataclass
class ResultadoLogin:
    ok: bool
    mensaje: str
    session: AuthSession | None = None
    password_migrated: bool = False
    usuario: Usuario | None = None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_session_id() -> str:
    return secrets.token_urlsafe(24)


def _auth_store():
    from app.bootstrap import get_container

    return get_container().auth_session_store


def clear_test_session() -> None:
    global _TEST_SESSION, _TEST_OVERRIDE
    _TEST_SESSION = None
    _TEST_OVERRIDE = False
    try:
        _auth_store().set_raw(None)
    except Exception:  # noqa: BLE001
        pass


def set_test_session(session: AuthSession | None) -> None:
    """Fija sesión para tests unitarios (sin Streamlit)."""
    global _TEST_SESSION, _TEST_OVERRIDE
    _TEST_OVERRIDE = True
    _TEST_SESSION = session
    try:
        _auth_store().set_raw(session.to_dict() if session else None)
    except Exception:  # noqa: BLE001
        pass


def get_auth_session() -> AuthSession | None:
    if _TEST_OVERRIDE:
        if _TEST_SESSION is None or not _TEST_SESSION.authenticated:
            return None
        return _TEST_SESSION
    try:
        return AuthSession.from_dict(_auth_store().get_raw())
    except Exception:  # noqa: BLE001
        return None


def save_auth_session(session: AuthSession | None) -> None:
    global _TEST_SESSION
    if _TEST_OVERRIDE:
        _TEST_SESSION = session
    try:
        _auth_store().set_raw(session.to_dict() if session else None)
    except Exception:  # noqa: BLE001
        if not _TEST_OVERRIDE:
            _TEST_SESSION = session


def invalidate_destructive_ui_tokens() -> None:
    """Invalida confirmaciones C2/C3 al cambiar de actor."""
    keys = (
        "settings_danger_token",
        "settings_danger_last",
        "settings_danger_reset_chk",
        "settings_danger_reset_frase",
        "settings_restore_token",
        "settings_restore_last",
        "settings_restore_insp",
        "settings_del_user_chk",
        "settings_del_user_frase",
    )
    if _TEST_OVERRIDE:
        return
    try:
        _auth_store().clear_keys(keys)
    except Exception:  # noqa: BLE001
        pass


def logout() -> None:
    invalidate_destructive_ui_tokens()
    save_auth_session(None)
    if _TEST_OVERRIDE:
        return
    try:
        _auth_store().clear_keys((
            "nav_section",
            "nav_section_op",
            "nav_section_pending",
            "bm_espacio_trabajo",
            "bm_force_hide_costes",
        ))
    except Exception:  # noqa: BLE001
        pass


def _permiso_bloqueado_por_terminal(session: AuthSession | None, permiso: Permiso | str) -> bool:
    """Terminal Inventario: denegación real (no solo UI) de economía/config."""
    if session is None or session.terminal_id != TERMINAL_INVENTARIO_ID:
        return False
    p = Permiso(permiso) if not isinstance(permiso, Permiso) else permiso
    return p in _PERMISOS_BLOQUEADOS_TERMINAL_INVENTARIO


def session_tiene_permiso(permiso: Permiso | str) -> bool:
    s = get_auth_session()
    if s is None or not s.authenticated:
        return False
    if _permiso_bloqueado_por_terminal(s, permiso):
        return False
    return tiene_permiso(s.role, permiso)


def require_permiso(permiso: Permiso | str) -> AuthSession:
    from app.core.auth.permissions import AuthorizationError

    s = get_auth_session()
    if s is None or not s.authenticated:
        raise AuthorizationError("Sesión no autenticada.")
    if _permiso_bloqueado_por_terminal(s, permiso):
        raise AuthorizationError("No autorizado para esta operación.")
    if not tiene_permiso(s.role, permiso):
        raise AuthorizationError("No autorizado para esta operación.")
    return s


def _buscar_por_login(usuarios: list[Usuario], login: str) -> Usuario | None:
    key = login.strip().lower()
    for u in usuarios:
        ul = (getattr(u, "login", None) or "").strip().lower()
        if ul and ul == key:
            return u
    return None


def autenticar_usuario(
    usuarios: list[Usuario],
    login: str,
    password: str,
) -> ResultadoLogin:
    """Valida credenciales. Error genérico si falla."""
    login_n = (login or "").strip()
    if not login_n or not password:
        return ResultadoLogin(False, MSG_LOGIN_FALLIDO)

    usuario = _buscar_por_login(usuarios, login_n)
    if usuario is None or not usuario.activo:
        verify_password(password, _DUMMY_HASH)
        return ResultadoLogin(False, MSG_LOGIN_FALLIDO)

    stored = getattr(usuario, "password_hash", "") or ""
    if not password_usable(stored) or not verify_password(password, stored):
        return ResultadoLogin(False, MSG_LOGIN_FALLIDO)

    migrated = False
    new_hash = migrate_legacy_if_needed(password, stored)
    if new_hash and new_hash != stored:
        usuario.password_hash = new_hash
        migrated = True

    session = AuthSession(
        authenticated=True,
        actor_type=ACTOR_TYPE_USUARIO,
        actor_id=usuario.id,
        actor_label=usuario.nombre,
        role=rol_canonico(usuario.rol),
        session_id=_new_session_id(),
        login_at=_now_iso(),
        terminal_id=None,
        login=getattr(usuario, "login", None) or login_n,
    )
    return ResultadoLogin(True, "Sesión iniciada.", session, migrated, usuario)


def iniciar_terminal_restaurante() -> AuthSession:
    """Identidad técnica de terminal (sin cuenta personal)."""
    return AuthSession(
        authenticated=True,
        actor_type=ACTOR_TYPE_TERMINAL,
        actor_id=TERMINAL_ACTOR_ID,
        actor_label=TERMINAL_LABEL,
        role=ROL_RESTAURANTE,
        session_id=_new_session_id(),
        login_at=_now_iso(),
        terminal_id=TERMINAL_ID_DEFAULT,
        login=None,
    )


def iniciar_terminal_inventario() -> AuthSession:
    """Terminal de inventario: stock operativo sin costes ni configuración."""
    return AuthSession(
        authenticated=True,
        actor_type=ACTOR_TYPE_TERMINAL,
        actor_id=TERMINAL_INVENTARIO_ACTOR_ID,
        actor_label=TERMINAL_INVENTARIO_LABEL,
        role=ROL_ADMINISTRACION,
        session_id=_new_session_id(),
        login_at=_now_iso(),
        terminal_id=TERMINAL_INVENTARIO_ID,
        login=None,
    )


def necesita_bootstrap(usuarios: list[Usuario]) -> bool:
    """True si no hay Dirección activa con credencial usable."""
    for u in usuarios:
        if not u.activo:
            continue
        if not es_direccion(u.rol):
            continue
        if password_usable(getattr(u, "password_hash", None)):
            return False
    return True


def actor_snapshot_from_session(session: AuthSession | None) -> dict[str, Any]:
    if session is None:
        return {
            "actor_type": None,
            "actor_id": None,
            "actor_label": None,
            "role_snapshot": None,
            "terminal_id": None,
        }
    return {
        "actor_type": session.actor_type,
        "actor_id": session.actor_id,
        "actor_label": session.actor_label,
        "role_snapshot": session.role,
        "terminal_id": session.terminal_id,
    }
