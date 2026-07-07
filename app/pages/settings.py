"""Settings — usuarios, configuración y actividad."""

import streamlit as st

from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha_hora
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider

MONEDAS = {
    "EUR": "EUR (€)",
    "USD": "USD ($)",
    "GBP": "GBP (£)",
}


def _render_usuarios() -> None:
    repo = get_repository()
    usuarios = repo.data.usuarios

    st.markdown("#### Usuarios del sistema")
    st.caption("Gestión temporal de usuarios. El login se implementará en la fase final.")

    st.dataframe(
        {
            "Nombre": [u.nombre for u in usuarios],
            "Rol": [u.rol.value for u in usuarios],
            "Estado": ["Activo" if u.activo else "Inactivo" for u in usuarios],
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
    nombres = [u.nombre for u in usuarios]
    st.selectbox("Seleccionar usuario", nombres, disabled=True, key="settings_sel_usuario")
    col1, col2 = st.columns(2)
    with col1:
        st.button("Editar nombre", disabled=True, use_container_width=True, key="settings_editar_usuario")
    with col2:
        st.button("Eliminar usuario", disabled=True, use_container_width=True, key="settings_eliminar_usuario")


def _render_configuracion() -> None:
    repo = get_repository()
    config = repo.data.configuracion

    st.markdown("#### Configuración del establecimiento")
    st.caption("Ajustes generales del hotel. Los cambios se persistirán en fases posteriores.")

    nombre = config.nombre_establecimiento if config else "Hotel Boutique"
    moneda_key = config.moneda if config else "EUR"
    moneda_label = MONEDAS.get(moneda_key, "EUR (€)")

    st.text_input(
        "Nombre del establecimiento",
        value=nombre,
        disabled=True,
        key="settings_nombre_establecimiento",
    )
    st.selectbox(
        "Moneda",
        list(MONEDAS.values()),
        index=list(MONEDAS.values()).index(moneda_label) if moneda_label in MONEDAS.values() else 0,
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
    repo = get_repository()
    actividades = sorted(repo.data.actividades, key=lambda a: a.fecha_hora, reverse=True)

    st.markdown("#### Registro de actividad")
    st.caption("Historial de acciones realizadas en la aplicación.")

    if actividades:
        st.dataframe(
            {
                "Fecha y hora": [formato_fecha_hora(a.fecha_hora) for a in actividades],
                "Usuario": [a.usuario for a in actividades],
                "Acción": [a.accion for a in actividades],
                "Detalle": [a.detalle for a in actividades],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("No hay actividad registrada todavía.", icon="📝")

    section_divider()
    st.button(
        "Exportar actividad (desde 00:00 hasta ahora)",
        disabled=True,
        use_container_width=True,
        key="settings_exportar_actividad",
    )
    st.caption("La exportación diaria en PDF se preparará en fases posteriores.")


def _render_datos_demo() -> None:
    from app.core.storage.session_store import get_demo_path, reload_from_disk, reset_data

    repo = get_repository()
    ruta = get_demo_path()

    st.markdown("#### Datos de demostración")
    st.caption("Los cambios de Stock y otras secciones se guardan en el archivo JSON local.")

    st.code(ruta, language=None)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Productos", len(repo.data.productos))
    with col2:
        st.metric("Lotes", len(repo.data.lotes))
    with col3:
        st.metric("Actividades", len(repo.data.actividades))

    section_divider()

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Recargar desde disco", use_container_width=True, key="settings_reload_demo"):
            reload_from_disk()
            st.success("Datos recargados desde el archivo.")
            st.rerun()
    with col_b:
        if st.button("Restablecer datos mock", use_container_width=True, key="settings_reset_demo"):
            reset_data()
            st.success("Datos restablecidos al conjunto de demostración.")
            st.rerun()

    st.caption(
        "Use «Recargar» si editó el JSON manualmente. "
        "«Restablecer» vuelve a los datos de ejemplo originales."
    )


_SUBTABS = {
    "Usuarios": _render_usuarios,
    "Configuración": _render_configuracion,
    "Actividad": _render_actividad,
    "Datos demo": _render_datos_demo,
}


def render() -> None:
    page_header("Settings", "Usuarios, configuración y registro de actividad")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="settings_subtab")
    _SUBTABS[selected]()
