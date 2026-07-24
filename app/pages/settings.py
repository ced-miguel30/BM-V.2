"""Settings — usuarios, configuración, actividad y exportación."""

from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

from app.core.services import actividad_service
from app.core.services.data_service import get_repository
from app.core.services.export_service import EXPORTS_DIR, exportar_informe_cliente
from app.core.services.exportacion_semanal_service import exportar_semana_actual, limite_semana
from app.core.services.formatting import formato_fecha_hora
from app.core.services.settings_service import (
    MONEDAS,
    crear_usuario,
    editar_usuario,
    eliminar_usuario,
    guardar_configuracion,
    guardar_logo,
)
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider


def _render_usuarios() -> None:
    repo = get_repository()
    usuarios = repo.data.usuarios

    st.markdown("#### Usuarios del sistema")
    st.caption("Gestión de usuarios. El login se implementará en la fase final.")

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
    with st.form("form_usuario", clear_on_submit=True):
        nombre = st.text_input("Nombre", key="settings_usuario_nombre")
        rol = st.selectbox("Rol", ["Owner", "Admin"], key="settings_usuario_rol")
        if st.form_submit_button("Crear usuario", type="primary"):
            resultado = crear_usuario(nombre, rol)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    section_divider()
    st.markdown("##### Editar / eliminar")
    if usuarios:
        opciones = {u.nombre: u.id for u in usuarios}
        sel_nombre = st.selectbox(
            "Seleccionar usuario",
            list(opciones.keys()),
            key="settings_sel_usuario",
        )
        usuario_id = opciones[sel_nombre]

        with st.form("form_editar_usuario"):
            nuevo_nombre = st.text_input("Nuevo nombre", value=sel_nombre, key="settings_edit_nombre")
            if st.form_submit_button("Guardar nombre", use_container_width=True):
                resultado = editar_usuario(usuario_id, nuevo_nombre)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)

        if st.button("Eliminar usuario", use_container_width=True, key="settings_eliminar_usuario"):
            resultado = eliminar_usuario(usuario_id)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)


def _render_configuracion() -> None:
    repo = get_repository()
    config = repo.data.configuracion

    st.markdown("#### Configuración del establecimiento")
    st.caption("Los cambios se guardan en el archivo JSON local.")

    nombre = config.nombre_establecimiento if config else "Hotel Boutique"
    moneda_key = config.moneda if config else "EUR"
    moneda_labels = [v[0] for v in MONEDAS.values()]
    moneda_keys = list(MONEDAS.keys())
    idx_moneda = moneda_keys.index(moneda_key) if moneda_key in moneda_keys else 0

    with st.form("form_configuracion"):
        nuevo_nombre = st.text_input(
            "Nombre del establecimiento",
            value=nombre,
            key="settings_nombre_establecimiento",
        )
        moneda_sel = st.selectbox(
            "Moneda",
            moneda_labels,
            index=idx_moneda,
            key="settings_moneda",
        )
        if st.form_submit_button("Guardar configuración", type="primary"):
            key = moneda_keys[moneda_labels.index(moneda_sel)]
            resultado = guardar_configuracion(nuevo_nombre, key)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    section_divider()
    st.markdown("##### Logo / foto")

    if config and config.logo_path:
        logo_path = Path(config.logo_path)
        if logo_path.is_file():
            st.image(str(logo_path), width=160, caption="Logo actual")

    archivo = st.file_uploader(
        "Subir imagen (PNG o JPG)",
        type=["png", "jpg", "jpeg"],
        key="settings_logo",
    )
    if archivo is not None:
        ext = archivo.name.rsplit(".", 1)[-1].lower()
        if ext == "jpeg":
            ext = "jpg"
        if st.button("Guardar logo", type="primary", key="settings_guardar_logo"):
            resultado = guardar_logo(archivo.getvalue(), ext)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)


def _render_lista_incidencias(titulo: str, items: list[str], *, limite: int = 30) -> None:
    st.markdown(f"**{titulo}:** {len(items)}")
    if not items:
        st.caption("Ninguna.")
        return
    mostrados = items[:limite]
    for item in mostrados:
        st.caption(f"· {item}")
    if len(items) > limite:
        st.caption(f"… y {len(items) - limite} más (no se listan todos).")


def _render_diagnostico_tecnico() -> None:
    """Bloque de solo lectura. No escribe datos ni corrige incidencias."""
    st.markdown("### Diagnóstico técnico")
    st.caption(
        "Solo lectura. No modifica datos, no crea copias y no corrige incidencias."
    )

    try:
        from app.core.services.diagnostico_service import generar_diagnostico

        resumen = generar_diagnostico(get_repository().data)
    except Exception as exc:  # noqa: BLE001 — mostrar fallo en UI sin tumbar Settings
        st.error(
            "No se pudo generar el diagnóstico. "
            "Compruebe que existe app/core/services/diagnostico_service.py "
            "y reinicie Streamlit desde la carpeta del proyecto."
        )
        st.caption(f"Detalle: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Productos", resumen.num_productos)
    c2.metric("Recetas", resumen.num_recetas)
    c3.metric("Lotes activos", resumen.num_lotes_activos)
    c4.metric("Compras (lotes)", resumen.num_compras)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Registros", resumen.num_registros)
    c6.metric("— Desayuno", resumen.num_registros_desayuno)
    c7.metric("— Otros servicios", resumen.num_registros_servicio)
    c8.metric("Líneas de detalle", resumen.num_lineas_detalle)

    c9, c10, _, _ = st.columns(4)
    c9.metric("Mermas", resumen.num_mermas)
    c10.metric("Líneas de merma", resumen.num_lineas_merma)

    with st.expander("Incidencias detectadas", expanded=True):
        st.info(resumen.productos_sin_servicio_msg)
        _render_lista_incidencias("Lotes con stock negativo", resumen.lotes_stock_negativo)
        _render_lista_incidencias(
            "Productos con stock total negativo", resumen.productos_stock_negativo
        )
        _render_lista_incidencias("Referencias huérfanas", resumen.referencias_huerfanas)
        _render_lista_incidencias(
            "Recetas sin ingredientes", resumen.recetas_sin_ingredientes
        )
        _render_lista_incidencias("Productos sin unidad", resumen.productos_sin_unidad)
        _render_lista_incidencias(
            "Registros / líneas sin snapshots relevantes",
            resumen.registros_sin_snapshots,
        )
        _render_lista_incidencias("Posibles duplicidades", resumen.posibles_duplicidades)
        _render_lista_incidencias("Otras incidencias", resumen.otras_incidencias)


def _boton_exportar_actividad() -> None:
    """Exportación manual: desde el lunes 00:00 de la semana actual hasta el
    momento del clic. Mismo patrón que desayuno/merma/stock/consumo."""
    col_btn, _ = st.columns([1, 2])
    with col_btn:
        if st.button("Exportar semana actual", use_container_width=True, key="actividad_exportar_semana"):
            resultado = exportar_semana_actual(actividad_service.configuracion_exportacion(), datetime.now())
            if resultado.ok:
                st.session_state["actividad_export_dl"] = (
                    resultado.ruta.read_bytes(), resultado.nombre_archivo,
                )
                st.success(resultado.mensaje)
            else:
                st.error(resultado.mensaje)

    dl = st.session_state.get("actividad_export_dl")
    if dl:
        contenido, nombre = dl
        st.download_button(
            "Descargar Excel",
            data=contenido,
            file_name=nombre,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="actividad_descargar_excel",
        )


def _render_actividad() -> None:
    repo = get_repository()
    lunes, _ = limite_semana(date.today())
    actividades = sorted(
        (a for a in repo.data.actividades if a.fecha_hora.date() >= lunes),
        key=lambda a: a.fecha_hora, reverse=True,
    )

    st.markdown("#### Registro de actividad")
    st.caption(
        "Historial de acciones de la semana actual. El histórico completo "
        "se conserva y sigue disponible en las exportaciones semanales."
    )

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
        empty_state("No hay actividad registrada esta semana.", icon="📝")

    section_divider()
    st.markdown("##### Exportar registro de actividad")
    _boton_exportar_actividad()


def _render_exportacion() -> None:
    st.markdown("#### Exportación para cliente")
    st.caption(
        "Genera un informe Excel con resumen de costes, desayunos, mermas, inventario y alertas. "
        "Se guarda automáticamente en la carpeta `exports/`."
    )

    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    col1, col2, col3 = st.columns(3)
    with col1:
        desde = st.date_input("Desde", value=inicio_mes, key="export_cliente_desde")
    with col2:
        hasta = st.date_input("Hasta", value=hoy, key="export_cliente_hasta")
    with col3:
        huespedes = st.number_input("Huéspedes (KPI)", min_value=1, value=30, key="export_cliente_huespedes")

    if st.button("Generar informe cliente", type="primary", use_container_width=True, key="export_cliente_btn"):
        if desde > hasta:
            st.error("La fecha «Desde» no puede ser posterior a «Hasta».")
        else:
            contenido, nombre = exportar_informe_cliente(desde, hasta, int(huespedes))
            st.session_state["settings_dl_cliente"] = (contenido, nombre)
            st.success(f"Informe generado: exports/{nombre}")

    if "settings_dl_cliente" in st.session_state:
        data, fname = st.session_state["settings_dl_cliente"]
        st.download_button(
            "Descargar informe cliente (Excel)",
            data=data,
            file_name=fname,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="settings_dl_cliente_btn",
        )

    section_divider()
    st.markdown("##### Acceso rápido")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Últimos 7 días", use_container_width=True, key="export_7d"):
            hasta = hoy
            desde = hoy - timedelta(days=6)
            contenido, nombre = exportar_informe_cliente(desde, hasta, 30)
            st.session_state["settings_dl_cliente"] = (contenido, nombre)
            st.rerun()
    with col_b:
        if st.button("Mes en curso", use_container_width=True, key="export_mes"):
            contenido, nombre = exportar_informe_cliente(inicio_mes, hoy, 30)
            st.session_state["settings_dl_cliente"] = (contenido, nombre)
            st.rerun()

    st.caption(f"Carpeta de exportaciones: `{EXPORTS_DIR}`")


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
    "Exportación": _render_exportacion,
    "Datos demo": _render_datos_demo,
}


def render() -> None:
    page_header(
        "Configuración",
        "Diagnóstico técnico, usuarios, establecimiento, actividad y exportación",
    )

    st.success(
        "DIAGNÓSTICO TÉCNICO — si ve este mensaje verde, está usando el código actualizado."
    )

    # Siempre visible al entrar en Configuración (no depende de pestañas).
    _render_diagnostico_tecnico()
    section_divider()

    opciones = list(_SUBTABS.keys())
    # Evita que un valor antiguo de session_state oculte opciones nuevas.
    if st.session_state.get("settings_subtab") not in (None, *opciones):
        del st.session_state["settings_subtab"]

    selected = render_sub_tabs(opciones, key="settings_subtab")
    _SUBTABS[selected]()
