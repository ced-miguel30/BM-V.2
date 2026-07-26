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
    """Bloque de solo lectura + descarga de backup (no restaura ni escribe en disco)."""
    st.markdown("### Diagnóstico técnico")
    st.caption(
        "Solo lectura. El diagnóstico no modifica datos. "
        "La descarga de copia genera un ZIP en memoria sin alterar los JSON originales."
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
        _render_lista_incidencias(
            "Productos sin servicios disponibles", resumen.productos_sin_servicio
        )
        _render_lista_incidencias(
            "Recetas sin servicios disponibles", resumen.recetas_sin_servicio
        )
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

    st.markdown("##### Formato por unidad (comprobación)")
    try:
        from app.core.services.unidad_service import ejemplos_formato_unidades

        st.dataframe(
            ejemplos_formato_unidades(),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Ud/paquete/botella paso 1 · Kg/L paso 0,01 · gr paso 1 · ml paso 10. "
            "0,02 kg es válido; no se aceptan negativos al normalizar."
        )
    except Exception as exc:  # noqa: BLE001
        st.caption(f"No se pudo mostrar la tabla de unidades: {exc}")

    st.markdown("##### Simulador de recetas (solo lectura)")
    st.caption(
        "Calcula factor, ingredientes y coste teórico sin guardar ni descontar stock. "
        "Configure «porciones estándar» en Recetas. Análisis y registros reales no cambian."
    )
    try:
        from app.core.services.receta_service import (
            etiqueta_porciones_estandar,
            listar_recetas,
            simular_receta,
        )

        recetas_sim = listar_recetas()
        if not recetas_sim:
            st.info("No hay recetas para simular.")
        else:
            mapa = {r.nombre: r.id for r in recetas_sim}
            nombre_sel = st.selectbox(
                "Receta",
                list(mapa.keys()),
                key="diag_sim_receta",
            )
            receta_sel = next(r for r in recetas_sim if r.id == mapa[nombre_sel])
            st.caption(
                f"Porciones estándar: "
                f"{etiqueta_porciones_estandar(receta_sel.porciones_estandar)}"
            )
            porciones_sim = st.number_input(
                "Porciones a simular",
                min_value=0.0,
                value=float(receta_sel.porciones_estandar or 0) or 10.0,
                step=1.0,
                format="%.0f",
                key="diag_sim_porciones",
            )
            if st.button("Simular", key="diag_sim_btn", type="secondary"):
                resultado = simular_receta(mapa[nombre_sel], porciones_sim)
                st.session_state["diag_sim_resultado"] = resultado

            resultado = st.session_state.get("diag_sim_resultado")
            if resultado is not None:
                if not resultado.ok:
                    st.warning(resultado.mensaje)
                else:
                    st.success(resultado.mensaje)
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Estándar", f"{resultado.porciones_estandar:g}")
                    m2.metric("Simuladas", f"{resultado.porciones_simuladas:g}")
                    m3.metric("Factor", f"{resultado.factor:g}")
                    m4.metric(
                        "Coste teórico",
                        get_repository().formato_precio(resultado.coste_total),
                    )
                    if resultado.lineas:
                        st.dataframe(
                            {
                                "Producto": [ln.nombre for ln in resultado.lineas],
                                "Cantidad": [
                                    f"{ln.cantidad_mostrar:g} {ln.unidad_mostrar}"
                                    for ln in resultado.lineas
                                ],
                                "Nativa": [
                                    f"{ln.cantidad_nativa:g} {ln.unidad_nativa}"
                                    for ln in resultado.lineas
                                ],
                                "Coste est.": [
                                    get_repository().formato_precio(ln.coste_estimado)
                                    for ln in resultado.lineas
                                ],
                                "Stock actual": [
                                    f"{ln.stock_actual:g} {ln.unidad_nativa}"
                                    for ln in resultado.lineas
                                ],
                            },
                            use_container_width=True,
                            hide_index=True,
                        )
                    st.caption("La simulación no se guarda. Stock y Análisis intactos.")
                    st.caption(
                        "Fase 8: al registrar con las mismas porciones, el descuento de stock "
                        "usa este factor. Compruebe factor y costes en el detalle del historial "
                        "del registro (no en Análisis)."
                    )
    except Exception as exc:  # noqa: BLE001
        st.caption(f"No se pudo cargar el simulador: {exc}")

    st.markdown("##### Copia de seguridad")
    st.caption(
        "Descarga un ZIP con los JSON de disco (sin transformar), "
        "el estado actual en memoria y manifest.json. No hay restauración automática."
    )
    try:
        from app.core.services.backup_service import generar_backup_zip

        backup = generar_backup_zip(get_repository().data)
    except Exception as exc:  # noqa: BLE001
        st.error("No se pudo generar la copia de seguridad.")
        st.caption(f"Detalle: {exc}")
        return

    st.download_button(
        label="Descargar copia de seguridad de datos",
        data=backup.contenido,
        file_name=backup.nombre_archivo,
        mime="application/zip",
        type="primary",
        use_container_width=True,
        key="settings_descargar_backup_zip",
    )
    st.caption("Incluye: " + ", ".join(backup.archivos_incluidos))


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


def _render_responsables_merma() -> None:
    from app.core.services.merma_service import (
        crear_responsable_merma,
        desactivar_responsable_merma,
        listar_responsables_merma,
        reactivar_responsable_merma,
        renombrar_responsable_merma,
    )

    st.markdown("#### Responsables de merma")
    st.caption(
        "Catálogo para el registro de merma. No se borran: desactive o reactive. "
        "Renombrar no cambia el texto ya guardado en el histórico."
    )

    todos = listar_responsables_merma(solo_activos=False)
    if todos:
        st.dataframe(
            {
                "Nombre": [r.nombre for r in todos],
                "Estado": ["Activo" if r.activo else "Inactivo" for r in todos],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Todavía no hay responsables. Cree el primero abajo.", icon="👤")

    section_divider()
    st.markdown("##### Añadir responsable")
    with st.form("form_responsable_merma", clear_on_submit=True):
        nombre = st.text_input("Nombre", key="settings_resp_merma_nombre")
        if st.form_submit_button("Crear responsable", type="primary"):
            resultado = crear_responsable_merma(nombre)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    if not todos:
        return

    section_divider()
    st.markdown("##### Editar / activar")
    opciones = {f"{r.nombre} ({'activo' if r.activo else 'inactivo'})": r.id for r in todos}
    sel = st.selectbox(
        "Seleccionar responsable",
        list(opciones.keys()),
        key="settings_sel_resp_merma",
    )
    resp_id = opciones[sel]
    actual = next(r for r in todos if r.id == resp_id)

    with st.form("form_edit_resp_merma"):
        nuevo = st.text_input("Nombre", value=actual.nombre, key="settings_edit_resp_nombre")
        if st.form_submit_button("Guardar nombre", use_container_width=True):
            resultado = renombrar_responsable_merma(resp_id, nuevo)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    col_a, col_b = st.columns(2)
    with col_a:
        if actual.activo:
            if st.button("Desactivar", use_container_width=True, key="settings_desact_resp"):
                resultado = desactivar_responsable_merma(resp_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        else:
            if st.button("Reactivar", use_container_width=True, key="settings_react_resp"):
                resultado = reactivar_responsable_merma(resp_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)


_SUBTABS = {
    "Usuarios": _render_usuarios,
    "Configuración": _render_configuracion,
    "Responsables merma": _render_responsables_merma,
    "Actividad": _render_actividad,
    "Exportación": _render_exportacion,
    "Datos demo": _render_datos_demo,
}


def render() -> None:
    from app.ui.theme import APP_VERSION

    page_header(
        "Configuración",
        "Diagnóstico técnico, usuarios, responsables de merma y exportación",
    )

    st.success(
        "DIAGNÓSTICO TÉCNICO — si ve este mensaje verde, está usando el código actualizado "
        f"(versión {APP_VERSION})."
    )

    # Siempre visible al entrar en Configuración (no depende de pestañas).
    _render_diagnostico_tecnico()
    section_divider()

    opciones = list(_SUBTABS.keys())
    pending = st.session_state.pop("settings_subtab_pending", None)
    if pending in opciones:
        st.session_state["settings_subtab"] = pending
    # Evita que un valor antiguo de session_state oculte opciones nuevas.
    if st.session_state.get("settings_subtab") not in (None, *opciones):
        del st.session_state["settings_subtab"]

    selected = render_sub_tabs(opciones, key="settings_subtab")
    _SUBTABS[selected]()
