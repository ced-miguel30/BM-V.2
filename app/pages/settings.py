"""Settings — usuarios, configuración y actividad."""

import streamlit as st

from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider


def _render_usuarios() -> None:
    st.markdown("#### Usuarios del sistema")
    st.caption("Gestión temporal de usuarios. El login se implementará en la fase final.")

    st.dataframe(
        {
            "Nombre": ["Usuario Owner"],
            "Rol": ["Owner"],
            "Estado": ["Activo"],
        },
        use_container_width=True,
        hide_index=True,
    )

    section_divider()
    st.markdown("##### Crear usuario")
    with st.form("form_usuario", clear_on_submit=False):
        st.text_input("Nombre", disabled=True, key="settings_usuario_nombre")
        st.selectbox("Rol", ["Owner", "Admin"], disabled=True, key="settings_usuario_rol")
        st.form_submit_button("Crear usuario", disabled=True)

    section_divider()
    st.markdown("##### Editar / eliminar")
    st.selectbox("Seleccionar usuario", ["Usuario Owner"], disabled=True, key="settings_sel_usuario")
    col1, col2 = st.columns(2)
    with col1:
        st.button("Editar nombre", disabled=True, use_container_width=True, key="settings_editar_usuario")
    with col2:
        st.button("Eliminar usuario", disabled=True, use_container_width=True, key="settings_eliminar_usuario")


def _render_configuracion() -> None:
    st.markdown("#### Configuración del establecimiento")
    st.caption("Ajustes generales del hotel. Los cambios se persistirán en fases posteriores.")

    st.text_input(
        "Nombre del establecimiento",
        value="Hotel Boutique",
        disabled=True,
        key="settings_nombre_establecimiento",
    )
    st.selectbox(
        "Moneda",
        ["EUR (€)", "USD ($)", "GBP (£)"],
        disabled=True,
        key="settings_moneda",
    )

    section_divider()
    st.markdown("##### Logo / foto")
    st.info("Placeholder — podrá subir el logo del hotel en una fase posterior.")
    st.file_uploader(
        "Subir imagen",
        disabled=True,
        type=["png", "jpg", "jpeg"],
        key="settings_logo",
    )

    section_divider()
    st.button("Guardar configuración", disabled=True, type="primary", key="settings_guardar")


def _render_actividad() -> None:
    st.markdown("#### Registro de actividad")
    st.caption("Historial de acciones realizadas en la aplicación.")

    empty_state(
        "No hay actividad registrada todavía.",
        icon="📝",
    )

    section_divider()
    st.button(
        "Exportar actividad (desde 00:00 hasta ahora)",
        disabled=True,
        use_container_width=True,
        key="settings_exportar_actividad",
    )
    st.caption("La exportación diaria en PDF se preparará en fases posteriores.")


_SUBTABS = {
    "Usuarios": _render_usuarios,
    "Configuración": _render_configuracion,
    "Actividad": _render_actividad,
}


def render() -> None:
    page_header("Settings", "Usuarios, configuración y registro de actividad")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="settings_subtab")
    _SUBTABS[selected]()
