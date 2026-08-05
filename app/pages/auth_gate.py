"""Puerta de autenticación F16 (login, bootstrap, terminal)."""

from __future__ import annotations

import streamlit as st

from app.core.auth.session import (
    AUTH_SESSION_KEY,
    autenticar_usuario,
    get_auth_session,
    iniciar_terminal_restaurante,
    invalidate_destructive_ui_tokens,
    logout,
    necesita_bootstrap,
    save_auth_session,
)
from app.core.services.settings_service import bootstrap_direccion
from app.core.storage.session_store import get_data, persist_data
from app.ui.theme import APP_NAME, APP_VERSION


def _aplicar_login_ok(resultado) -> None:
    invalidate_destructive_ui_tokens()
    save_auth_session(resultado.session)
    data = get_data()
    if resultado.usuario is not None:
        data.usuario_actual_id = resultado.usuario.id
        if resultado.password_migrated:
            persist_data(data)
        else:
            # Solo actualizar puntero de sesión en memoria/disco
            persist_data(data)
    st.rerun()


def render_auth_gate() -> bool:
    """Devuelve True si hay sesión autenticada y se puede continuar."""
    session = get_auth_session()
    if session and session.authenticated:
        return True

    data = get_data()
    st.markdown(f"## {APP_NAME}")
    st.caption(f"Versión {APP_VERSION} · acceso restringido")

    if necesita_bootstrap(data.usuarios):
        st.warning(
            "No hay un usuario Dirección con credenciales. "
            "Configure el acceso inicial. No hay contraseña por defecto."
        )
        with st.form("form_bootstrap_f16"):
            nombre = st.text_input("Nombre visible")
            login = st.text_input("Identificador de acceso")
            password = st.text_input("Contraseña", type="password")
            password2 = st.text_input("Repetir contraseña", type="password")
            if st.form_submit_button("Crear acceso Dirección", type="primary"):
                if password != password2:
                    st.error("Las contraseñas no coinciden.")
                else:
                    res = bootstrap_direccion(
                        nombre=nombre, login=login, password=password
                    )
                    if not res.ok:
                        st.error(res.mensaje)
                    else:
                        # Auto-login tras bootstrap
                        data2 = get_data()
                        login_res = autenticar_usuario(data2.usuarios, login, password)
                        if login_res.ok:
                            _aplicar_login_ok(login_res)
                        else:
                            st.success(res.mensaje)
                            st.info("Inicie sesión con las credenciales definidas.")
                            st.rerun()
        return False

    tab_login, tab_terminal = st.tabs(["Acceso personal", "Terminal Restaurante"])
    with tab_login:
        with st.form("form_login_f16"):
            login = st.text_input("Identificador de acceso")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Entrar", type="primary")
            if submitted:
                # Anti-doble submit: token de intento
                token = st.session_state.get("_login_attempt_token")
                nuevo = f"{login}:{submitted}"
                if token == nuevo and st.session_state.get("_login_done"):
                    st.info("Inicio de sesión ya procesado.")
                else:
                    st.session_state["_login_attempt_token"] = nuevo
                    res = autenticar_usuario(get_data().usuarios, login, password)
                    if not res.ok:
                        st.error(res.mensaje)
                    else:
                        st.session_state["_login_done"] = True
                        _aplicar_login_ok(res)

    with tab_terminal:
        st.caption(
            "Modo terminal sin cuenta personal. Las operaciones se registran "
            "como identidad técnica «Restaurante»."
        )
        if st.button("Abrir Terminal Restaurante", type="primary", key="btn_terminal_f16"):
            invalidate_destructive_ui_tokens()
            save_auth_session(iniciar_terminal_restaurante())
            st.session_state["nav_section"] = "Registros"
            st.session_state["bm_espacio_trabajo"] = "registro"
            st.rerun()

    return False


def render_logout_sidebar() -> None:
    session = get_auth_session()
    if not session:
        return
    st.markdown("---")
    st.caption(f"{session.actor_label} · {session.role}")
    if st.button("Cerrar sesión", key="btn_logout_f16", use_container_width=True):
        logout()
        st.session_state.pop("_login_done", None)
        st.session_state.pop("_login_attempt_token", None)
        st.session_state.pop(AUTH_SESSION_KEY, None)
        st.rerun()
