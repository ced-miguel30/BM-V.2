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
    from app.core.auth.permissions import Permiso
    from app.core.auth.roles import ETIQUETAS_ROL, etiqueta_rol, rol_canonico, roles_asignables
    from app.core.auth.session import session_tiene_permiso
    from app.core.services.settings_service import (
        cambiar_rol_usuario,
        restablecer_password,
        set_usuario_activo,
    )

    if not session_tiene_permiso(Permiso.GESTIONAR_USUARIOS):
        st.error("No autorizado para gestionar usuarios.")
        return

    repo = get_repository()
    usuarios = repo.data.usuarios
    puede_dir = session_tiene_permiso(Permiso.CREAR_USUARIO_DIRECCION)

    st.markdown("#### Usuarios del sistema")
    st.caption("Gestión F16. Nunca se muestran contraseñas ni hashes.")

    st.dataframe(
        {
            "Nombre": [u.nombre for u in usuarios],
            "Acceso": [getattr(u, "login", "") or "—" for u in usuarios],
            "Rol": [etiqueta_rol(u.rol) for u in usuarios],
            "Estado": ["Activo" if u.activo else "Inactivo" for u in usuarios],
        },
        use_container_width=True,
        hide_index=True,
    )

    section_divider()
    st.markdown("##### Crear usuario")
    roles_ui = roles_asignables(incluye_direccion=puede_dir)
    with st.form("form_usuario", clear_on_submit=True):
        nombre = st.text_input("Nombre", key="settings_usuario_nombre")
        login = st.text_input("Identificador de acceso", key="settings_usuario_login")
        rol = st.selectbox(
            "Rol",
            roles_ui,
            format_func=lambda r: ETIQUETAS_ROL.get(r, r),
            key="settings_usuario_rol",
        )
        password = st.text_input(
            "Contraseña inicial", type="password", key="settings_usuario_password"
        )
        if st.form_submit_button("Crear usuario", type="primary"):
            resultado = crear_usuario(nombre, rol, login=login, password=password)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    section_divider()
    st.markdown("##### Editar / eliminar")
    if usuarios:
        opciones = {f"{u.nombre} ({getattr(u, 'login', '') or u.id})": u.id for u in usuarios}
        sel_label = st.selectbox(
            "Seleccionar usuario",
            list(opciones.keys()),
            key="settings_sel_usuario",
        )
        usuario_id = opciones[sel_label]
        sel_u = next(u for u in usuarios if u.id == usuario_id)

        with st.form("form_editar_usuario"):
            nuevo_nombre = st.text_input(
                "Nuevo nombre", value=sel_u.nombre, key="settings_edit_nombre"
            )
            if st.form_submit_button("Guardar nombre", use_container_width=True):
                resultado = editar_usuario(usuario_id, nuevo_nombre)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)

        roles_edit = roles_asignables(incluye_direccion=puede_dir)
        rol_actual = rol_canonico(sel_u.rol)
        idx_rol = roles_edit.index(rol_actual) if rol_actual in roles_edit else 0
        nuevo_rol = st.selectbox(
            "Rol",
            roles_edit,
            index=idx_rol,
            format_func=lambda r: ETIQUETAS_ROL.get(r, r),
            key="settings_edit_rol",
        )
        if st.button("Cambiar rol", key="settings_btn_rol"):
            r = cambiar_rol_usuario(usuario_id, nuevo_rol)
            st.success(r.mensaje) if r.ok else st.error(r.mensaje)
            if r.ok:
                st.rerun()

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Activar", key="settings_btn_act"):
                r = set_usuario_activo(usuario_id, True)
                st.success(r.mensaje) if r.ok else st.error(r.mensaje)
                if r.ok:
                    st.rerun()
        with col_b:
            if st.button("Desactivar", key="settings_btn_deact"):
                r = set_usuario_activo(usuario_id, False)
                st.success(r.mensaje) if r.ok else st.error(r.mensaje)
                if r.ok:
                    st.rerun()

        nueva_pw = st.text_input(
            "Nueva contraseña", type="password", key="settings_reset_pw"
        )
        if st.button("Restablecer contraseña", key="settings_btn_pw"):
            r = restablecer_password(usuario_id, nueva_pw)
            st.success(r.mensaje) if r.ok else st.error(r.mensaje)

        st.markdown("###### Eliminar usuario (confirmación + autorización)")
        from app.core.services.destructive_ops_service import (
            FRASE_ELIMINAR_USUARIO,
            validar_confirmacion,
        )

        chk = st.checkbox(
            f"Confirmo eliminar al usuario «{sel_u.nombre}»",
            key="settings_del_user_chk",
        )
        frase = st.text_input(
            f"Escriba exactamente {FRASE_ELIMINAR_USUARIO}",
            key="settings_del_user_frase",
        )
        barrera = validar_confirmacion(FRASE_ELIMINAR_USUARIO, frase, chk)
        if st.button(
            "Eliminar usuario",
            use_container_width=True,
            key="settings_eliminar_usuario",
            disabled=not barrera.ok,
            type="secondary",
        ):
            if not barrera.ok:
                st.error(barrera.mensaje)
            else:
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

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Mermas", resumen.num_mermas)
    c10.metric("Líneas de merma", resumen.num_lineas_merma)
    c11.metric("Ajustes", resumen.num_ajustes)
    c12.metric("Líneas de ajuste", resumen.num_lineas_ajuste)

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
        _render_lista_incidencias(
            "Catálogos / tipos de artículo",
            getattr(resumen, "incidencias_catalogo", []),
        )

    st.markdown("##### Ledger y stock (Fase 7B)")
    modo = getattr(resumen, "ledger_balance_mode", "shadow")
    aviso = getattr(resumen, "aviso_modo_hibrido", "") or ""
    if aviso:
        st.warning(aviso)
    st.caption(
        getattr(
            resumen,
            "nota_ledger",
            "Ledger configurable; cantidad_restante conservada.",
        )
    )
    lm1, lm2, lm3 = st.columns(3)
    lm1.metric("Modo saldo", modo)
    lm2.metric(
        "Frontera activación",
        getattr(resumen, "ledger_activation_iso", None) or "—",
    )
    lm3.metric("Movimientos", getattr(resumen, "num_movimientos", 0))
    lc1, lc2, lc3 = st.columns(3)
    lc1.metric("Lotes ledger", getattr(resumen, "lotes_ledger", 0))
    lc2.metric("Lotes legacy/parcial", getattr(resumen, "lotes_legacy", 0))
    lc3.metric("Traslados", getattr(resumen, "num_traslados", 0))
    lr1, lr2, lr3 = st.columns(3)
    lr1.metric("Consumos", getattr(resumen, "num_movimientos_consumo", 0))
    lr2.metric("Mermas", getattr(resumen, "num_movimientos_merma", 0))
    lr3.metric(
        "Recuentos pendientes",
        getattr(resumen, "num_recuentos_pendientes", 0),
    )
    cob = getattr(resumen, "ledger_cobertura", {}) or {}
    if cob:
        st.caption("Cobertura: " + ", ".join(f"{k}={v}" for k, v in cob.items()))
    with st.expander("Ledger — incidencias y diferencias", expanded=False):
        _render_lista_incidencias(
            "Incidencias de movimientos",
            getattr(resumen, "incidencias_movimientos", []),
        )
        _render_lista_incidencias(
            "Diferencias posteriores a activación",
            getattr(resumen, "ledger_diferencias_post", []),
        )
        _render_lista_incidencias(
            "Saldos por ubicación (muestra)",
            getattr(resumen, "saldos_ubicacion_muestra", []),
        )
        st.caption(
            "No hay reparación automática destructiva desde este panel."
        )

    st.markdown("##### Trazabilidad por lote (Fase 10.5)")
    st.metric(
        "Líneas con trazabilidad por lote",
        getattr(resumen, "num_lineas_con_trazabilidad_lote", 0),
    )
    st.caption(getattr(resumen, "nota_trazabilidad_lote", ""))
    with st.expander("Trazabilidad por lote — detalle", expanded=False):
        _render_lista_incidencias(
            "Sin trazabilidad histórica por lote",
            getattr(resumen, "sin_trazabilidad_historica_lote", []),
        )
        _render_lista_incidencias(
            "Incidencias de trazabilidad por lote",
            getattr(resumen, "incidencias_trazabilidad_lote", []),
        )

    st.markdown("##### Invariantes JSON / anulaciones (Fase 1B)")
    st.caption(
        "Solo lectura. Módulo `diagnostico_invariantes` (separado de los tests 1A). "
        "Detalle en docs/invariantes_json_fase1b.md."
    )
    i1, i2, i3 = st.columns(3)
    i1.metric("Registros anulados", getattr(resumen, "num_registros_anulados", 0))
    i2.metric("Mermas anuladas", getattr(resumen, "num_mermas_anuladas", 0))
    i3.metric("Compras anuladas", getattr(resumen, "num_compras_anuladas", 0))
    j1, j2, j3 = st.columns(3)
    j1.metric(
        "Activos con trazabilidad",
        getattr(resumen, "num_registros_activos_con_traza", 0),
    )
    j2.metric(
        "Activos sin trazabilidad",
        getattr(resumen, "num_registros_activos_sin_traza", 0),
        help="Históricos o incompletos: anulación automática bloqueada.",
    )
    j3.metric(
        "Mermas activas sin lote",
        getattr(resumen, "num_mermas_activas_sin_lote", 0),
    )
    with st.expander("Invariantes — detalle", expanded=False):
        for nota in getattr(resumen, "notas_invariantes", []) or []:
            st.caption(f"· {nota}")
        _render_lista_incidencias(
            "Incidencias de invariantes",
            getattr(resumen, "incidencias_invariantes", []),
        )

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
        "Descarga un ZIP restaurable (schema v2) con appdata.json, "
        "hashes SHA-256, adjuntos referenciados bajo data/documentos/ y manifest.json. "
        "Solo descarga: no restaura ni borra datos. "
        "La restauración está en «Restauración de datos»; "
        "el restablecimiento total en «Zona de peligro»."
    )
    from app.core.auth.permissions import Permiso
    from app.core.auth.session import session_tiene_permiso

    if not session_tiene_permiso(Permiso.EXPORTAR_BACKUP):
        st.warning("No autorizado para exportar copias de seguridad.")
        return
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
    st.caption(
        f"Schema {backup.schema_version} · "
        + ", ".join(backup.archivos_incluidos[:8])
        + ("…" if len(backup.archivos_incluidos) > 8 else "")
    )


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
    from app.core.storage.session_store import get_demo_path, reload_from_disk

    repo = get_repository()
    ruta = get_demo_path()

    st.markdown("#### Datos de demostración")
    st.caption(
        "Los cambios de Stock y otras secciones se guardan en el archivo JSON local. "
        "El restablecimiento total está en «Zona de peligro» (no hay borrado de un clic)."
    )

    st.code(ruta, language=None)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Productos", len(repo.data.productos))
    with col2:
        st.metric("Lotes", len(repo.data.lotes))
    with col3:
        st.metric("Actividades", len(repo.data.actividades))

    section_divider()
    if st.button("Recargar desde disco", use_container_width=True, key="settings_reload_demo"):
        reload_from_disk()
        st.success("Datos recargados desde el archivo.")
        st.rerun()

    st.caption(
        "«Recargar» lee el JSON de disco a la sesión. "
        "Para sustituir todo por datos mock use Configuración → Zona de peligro."
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


def _render_catalogos_inventario() -> None:
    """Fases 6A–6B — departamentos, categorías, subcategorías y ubicaciones."""
    from app.core.services import catalogo_service as cat

    st.markdown("#### Catálogos de inventario")
    st.caption(
        "Departamentos: ámbitos de uso del producto (no son ubicaciones ni stock). "
        "Ubicaciones: lugares físicos/lógicos donde puede almacenarse "
        "(sin cantidades ni stock por ubicación). "
        "Categorías y subcategorías: clasificación estructurada. "
        "Sin borrado físico: active o desactive."
    )
    st.info(
        "**Tipos de artículo (taxonomía fija, sin CRUD)**  \n"
        "- **Consumible:** se utiliza o agota en la operación.  \n"
        "- **Reutilizable:** permanece en el hotel y puede usarse varias veces.  \n"
        "Tipos adicionales (préstamo, textil, activo) se diseñarán más adelante.  \n"
        "«Reutilizable» aún **no** activa préstamo, retorno ni stock por ubicación.  \n"
        "`es_bebida` es independiente del tipo de artículo."
    )

    apartado = st.radio(
        "Apartado",
        ["Departamentos", "Categorías", "Subcategorías", "Ubicaciones"],
        horizontal=True,
        key="settings_catalogo_apartado",
        label_visibility="collapsed",
    )

    if apartado == "Departamentos":
        _render_crud_departamento(cat)
    elif apartado == "Categorías":
        _render_crud_categoria(cat)
    elif apartado == "Subcategorías":
        _render_crud_subcategoria(cat)
    else:
        _render_crud_ubicacion(cat)


def _render_crud_departamento(cat) -> None:
    st.markdown("##### Departamentos")
    todos = cat.listar_departamentos(solo_activos=False)
    if todos:
        st.dataframe(
            {
                "Nombre": [d.nombre for d in todos],
                "Estado": ["Activo" if d.activo else "Inactivo" for d in todos],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Todavía no hay departamentos. Cree el primero abajo.", icon="📁")

    section_divider()
    st.markdown("##### Añadir departamento")
    with st.form("form_crear_departamento", clear_on_submit=True):
        nombre = st.text_input("Nombre", key="settings_dep_nombre")
        if st.form_submit_button("Crear departamento", type="primary"):
            resultado = cat.crear_departamento(nombre)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    if not todos:
        return
    section_divider()
    st.markdown("##### Editar departamento")
    opciones = {f"{d.nombre} ({'activo' if d.activo else 'inactivo'})": d.id for d in todos}
    sel = st.selectbox("Departamento", list(opciones.keys()), key="settings_dep_sel")
    dep_id = opciones[sel]
    actual = next(d for d in todos if d.id == dep_id)
    with st.form("form_edit_departamento"):
        nuevo = st.text_input("Nombre", value=actual.nombre, key="settings_edit_dep_nombre")
        if st.form_submit_button("Guardar nombre", use_container_width=True):
            resultado = cat.renombrar_departamento(dep_id, nuevo)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)
    col_a, col_b = st.columns(2)
    with col_a:
        if actual.activo:
            if st.button("Desactivar", use_container_width=True, key="settings_desact_dep"):
                resultado = cat.desactivar_departamento(dep_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        else:
            if st.button("Reactivar", use_container_width=True, key="settings_react_dep"):
                resultado = cat.reactivar_departamento(dep_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)


def _render_crud_categoria(cat) -> None:
    st.markdown("##### Categorías")
    todos = cat.listar_categorias(solo_activos=False)
    if todos:
        st.dataframe(
            {
                "Nombre": [c.nombre for c in todos],
                "Estado": ["Activo" if c.activo else "Inactivo" for c in todos],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Todavía no hay categorías. Cree la primera abajo.", icon="📁")

    section_divider()
    st.markdown("##### Añadir categoría")
    with st.form("form_crear_categoria", clear_on_submit=True):
        nombre = st.text_input("Nombre", key="settings_cat_nombre")
        if st.form_submit_button("Crear categoría", type="primary"):
            resultado = cat.crear_categoria(nombre)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    if not todos:
        return
    section_divider()
    st.markdown("##### Editar categoría")
    opciones = {f"{c.nombre} ({'activo' if c.activo else 'inactivo'})": c.id for c in todos}
    sel = st.selectbox("Categoría", list(opciones.keys()), key="settings_cat_sel")
    cat_id = opciones[sel]
    actual = next(c for c in todos if c.id == cat_id)
    with st.form("form_edit_categoria"):
        nuevo = st.text_input("Nombre", value=actual.nombre, key="settings_edit_cat_nombre")
        if st.form_submit_button("Guardar nombre", use_container_width=True):
            resultado = cat.renombrar_categoria(cat_id, nuevo)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)
    col_a, col_b = st.columns(2)
    with col_a:
        if actual.activo:
            if st.button("Desactivar", use_container_width=True, key="settings_desact_cat"):
                resultado = cat.desactivar_categoria(cat_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        else:
            if st.button("Reactivar", use_container_width=True, key="settings_react_cat"):
                resultado = cat.reactivar_categoria(cat_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)


def _render_crud_subcategoria(cat) -> None:
    st.markdown("##### Subcategorías")
    categorias = cat.listar_categorias(solo_activos=False)
    if not categorias:
        st.warning("Cree primero al menos una categoría.")
        return

    mapa_cat = {c.id: c.nombre for c in categorias}
    todos = cat.listar_subcategorias(solo_activos=False)
    if todos:
        st.dataframe(
            {
                "Nombre": [s.nombre for s in todos],
                "Categoría": [mapa_cat.get(s.categoria_id, "Referencia no encontrada") for s in todos],
                "Estado": ["Activo" if s.activo else "Inactivo" for s in todos],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Todavía no hay subcategorías.", icon="📁")

    section_divider()
    st.markdown("##### Añadir subcategoría")
    cat_opts = {c.nombre: c.id for c in categorias}
    with st.form("form_crear_subcategoria", clear_on_submit=True):
        cat_sel = st.selectbox("Categoría padre", list(cat_opts.keys()), key="settings_sub_padre")
        nombre = st.text_input("Nombre", key="settings_sub_nombre")
        if st.form_submit_button("Crear subcategoría", type="primary"):
            resultado = cat.crear_subcategoria(nombre, cat_opts[cat_sel])
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    if not todos:
        return
    section_divider()
    st.markdown("##### Editar subcategoría")
    opciones = {
        f"{s.nombre} · {mapa_cat.get(s.categoria_id, '?')} "
        f"({'activo' if s.activo else 'inactivo'})": s.id
        for s in todos
    }
    sel = st.selectbox("Subcategoría", list(opciones.keys()), key="settings_sub_sel")
    sub_id = opciones[sel]
    actual = next(s for s in todos if s.id == sub_id)
    with st.form("form_edit_subcategoria"):
        nuevo = st.text_input("Nombre", value=actual.nombre, key="settings_edit_sub_nombre")
        if st.form_submit_button("Guardar nombre", use_container_width=True):
            resultado = cat.renombrar_subcategoria(sub_id, nuevo)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)
    col_a, col_b = st.columns(2)
    with col_a:
        if actual.activo:
            if st.button("Desactivar", use_container_width=True, key="settings_desact_sub"):
                resultado = cat.desactivar_subcategoria(sub_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        else:
            if st.button("Reactivar", use_container_width=True, key="settings_react_sub"):
                resultado = cat.reactivar_subcategoria(sub_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)


def _render_crud_ubicacion(cat) -> None:
    st.markdown("##### Ubicaciones")
    st.caption(
        "Lugares donde puede existir inventario. "
        "No representan cantidad ni la ubicación actual de cada lote."
    )
    todos = cat.listar_ubicaciones(solo_activos=False)
    if todos:
        st.dataframe(
            {
                "Código": [getattr(u, "codigo", None) or "—" for u in todos],
                "Nombre": [u.nombre for u in todos],
                "Estado": ["Activo" if u.activo else "Inactivo" for u in todos],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Todavía no hay ubicaciones. Cree la primera abajo.", icon="📁")

    section_divider()
    st.markdown("##### Añadir ubicación")
    with st.form("form_crear_ubicacion", clear_on_submit=True):
        codigo = st.text_input("Código *", key="settings_ubi_codigo")
        nombre = st.text_input("Nombre", key="settings_ubi_nombre")
        if st.form_submit_button("Crear ubicación", type="primary"):
            resultado = cat.crear_ubicacion(nombre, codigo=codigo)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    if not todos:
        return
    section_divider()
    st.markdown("##### Editar ubicación")
    opciones = {f"{u.nombre} ({'activo' if u.activo else 'inactivo'})": u.id for u in todos}
    sel = st.selectbox("Ubicación", list(opciones.keys()), key="settings_ubi_sel")
    ubi_id = opciones[sel]
    actual = next(u for u in todos if u.id == ubi_id)
    with st.form("form_edit_ubicacion"):
        nuevo = st.text_input("Nombre", value=actual.nombre, key="settings_edit_ubi_nombre")
        if st.form_submit_button("Guardar nombre", use_container_width=True):
            resultado = cat.renombrar_ubicacion(ubi_id, nuevo)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)
    col_a, col_b = st.columns(2)
    with col_a:
        if actual.activo:
            if st.button("Desactivar", use_container_width=True, key="settings_desact_ubi"):
                resultado = cat.desactivar_ubicacion(ubi_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        else:
            if st.button("Reactivar", use_container_width=True, key="settings_react_ubi"):
                resultado = cat.reactivar_ubicacion(ubi_id)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)


def _render_proveedores_impuestos() -> None:
    """Fase 8 — maestros de proveedor, impuesto y vínculo producto–proveedor."""
    from app.core.services import proveedor_service as prv
    from app.core.services.data_service import get_repository

    st.markdown("#### Proveedores e impuestos")
    st.caption(
        "Catálogo comercial (Fase 8). Sin facturas ni albaranes. "
        "El texto «marca_proveedor» de lotes históricos no se reescribe. "
        "Los snapshots del vínculo producto–proveedor quedan congelados al crear el vínculo."
    )
    apartado = st.radio(
        "Apartado comercial",
        ["Proveedores", "Impuestos", "Vínculos producto–proveedor"],
        horizontal=True,
        key="settings_prv_apartado",
        label_visibility="collapsed",
    )
    if apartado == "Proveedores":
        _render_crud_proveedores(prv)
    elif apartado == "Impuestos":
        _render_crud_impuestos(prv)
    else:
        _render_crud_vinculos(prv, get_repository())


def _render_crud_proveedores(prv) -> None:
    st.markdown("##### Proveedores")
    todos = prv.listar_proveedores(solo_activos=False)
    if todos:
        st.dataframe(
            {
                "Código": [getattr(p, "codigo", None) or "—" for p in todos],
                "Fiscal": [p.nombre_fiscal for p in todos],
                "Comercial": [p.nombre_comercial or "—" for p in todos],
                "NIF/CIF": [p.nif_cif or "—" for p in todos],
                "Estado": ["Activo" if p.activo else "Inactivo" for p in todos],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Todavía no hay proveedores.", icon="🏢")

    section_divider()
    st.markdown("##### Añadir proveedor")
    with st.form("form_crear_proveedor", clear_on_submit=True):
        codigo = st.text_input("Código *")
        nombre = st.text_input("Nombre fiscal *")
        comercial = st.text_input("Nombre comercial")
        nif = st.text_input("NIF/CIF")
        direccion = st.text_input("Dirección")
        contacto = st.text_input("Contacto")
        telefono = st.text_input("Teléfono")
        email = st.text_input("Email")
        condiciones = st.text_input("Condiciones de pago")
        observaciones = st.text_area("Observaciones")
        if st.form_submit_button("Crear proveedor", type="primary"):
            r = prv.crear_proveedor(
                nombre,
                codigo=codigo,
                nombre_comercial=comercial or None,
                nif_cif=nif or None,
                direccion=direccion or None,
                contacto=contacto or None,
                telefono=telefono or None,
                email=email or None,
                condiciones_pago=condiciones or None,
                observaciones=observaciones or None,
            )
            if r.ok:
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)

    if not todos:
        return
    section_divider()
    st.markdown("##### Editar / activar")
    opts = {
        f"{p.nombre_fiscal} ({'activo' if p.activo else 'inactivo'})": p.id
        for p in todos
    }
    sel = st.selectbox("Proveedor", list(opts.keys()), key="settings_prv_sel")
    pid = opts[sel]
    prov = next(p for p in todos if p.id == pid)
    with st.form("form_edit_proveedor"):
        nuevo_codigo = st.text_input(
            "Código",
            value=getattr(prov, "codigo", None) or "",
            key="settings_prv_codigo",
        )
        nuevo = st.text_input(
            "Nombre fiscal", value=prov.nombre_fiscal, key="settings_prv_nom"
        )
        nuevo_com = st.text_input(
            "Nombre comercial",
            value=prov.nombre_comercial or "",
            key="settings_prv_com",
        )
        nuevo_nif = st.text_input(
            "NIF/CIF", value=prov.nif_cif or "", key="settings_prv_nif"
        )
        nuevo_dir = st.text_input(
            "Dirección", value=prov.direccion or "", key="settings_prv_dir"
        )
        nuevo_contacto = st.text_input(
            "Contacto", value=prov.contacto or "", key="settings_prv_contacto"
        )
        nuevo_tel = st.text_input(
            "Teléfono", value=prov.telefono or "", key="settings_prv_tel"
        )
        nuevo_email = st.text_input(
            "Email", value=prov.email or "", key="settings_prv_email"
        )
        nuevo_cond = st.text_input(
            "Condiciones de pago",
            value=prov.condiciones_pago or "",
            key="settings_prv_cond",
        )
        nuevo_obs = st.text_area(
            "Observaciones",
            value=getattr(prov, "observaciones", None) or "",
            key="settings_prv_obs",
        )
        if st.form_submit_button("Guardar cambios"):
            kwargs = {
                "nombre_fiscal": nuevo,
                "nombre_comercial": nuevo_com or None,
                "nif_cif": nuevo_nif or None,
                "direccion": nuevo_dir or None,
                "contacto": nuevo_contacto or None,
                "telefono": nuevo_tel or None,
                "email": nuevo_email or None,
                "condiciones_pago": nuevo_cond or None,
                "observaciones": nuevo_obs or None,
            }
            if (nuevo_codigo or "").strip():
                kwargs["codigo"] = nuevo_codigo
            r = prv.editar_proveedor(pid, **kwargs)
            if r.ok:
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)
    c1, c2 = st.columns(2)
    with c1:
        if prov.activo and st.button("Desactivar", key="settings_prv_off"):
            r = prv.desactivar_proveedor(pid)
            st.success(r.mensaje) if r.ok else st.error(r.mensaje)
            if r.ok:
                st.rerun()
    with c2:
        if not prov.activo and st.button("Reactivar", key="settings_prv_on"):
            r = prv.reactivar_proveedor(pid)
            st.success(r.mensaje) if r.ok else st.error(r.mensaje)
            if r.ok:
                st.rerun()


def _render_crud_impuestos(prv) -> None:
    st.markdown("##### Impuestos")
    todos = prv.listar_impuestos(solo_activos=False)
    if todos:
        st.dataframe(
            {
                "Nombre": [i.nombre for i in todos],
                "%": [str(i.porcentaje) for i in todos],
                "Desde": [i.vigencia_desde or "—" for i in todos],
                "Hasta": [i.vigencia_hasta or "—" for i in todos],
                "Estado": ["Activo" if i.activo else "Inactivo" for i in todos],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Todavía no hay impuestos.", icon="%")

    section_divider()
    with st.form("form_crear_impuesto", clear_on_submit=True):
        nombre = st.text_input("Nombre *", placeholder="IVA general")
        pct = st.text_input("Porcentaje *", placeholder="21")
        if st.form_submit_button("Crear impuesto", type="primary"):
            r = prv.crear_impuesto(nombre, pct)
            if r.ok:
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)

    if not todos:
        return
    section_divider()
    opts = {f"{i.nombre} ({i.porcentaje}%)": i.id for i in todos}
    sel = st.selectbox("Impuesto", list(opts.keys()), key="settings_imp_sel")
    iid = opts[sel]
    imp = next(i for i in todos if i.id == iid)
    c1, c2 = st.columns(2)
    with c1:
        if imp.activo and st.button("Desactivar impuesto", key="settings_imp_off"):
            r = prv.desactivar_impuesto(iid)
            if r.ok:
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)
    with c2:
        if not imp.activo and st.button("Reactivar impuesto", key="settings_imp_on"):
            r = prv.reactivar_impuesto(iid)
            if r.ok:
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)


def _render_crud_vinculos(prv, repo) -> None:
    st.markdown("##### Vínculos producto – proveedor")
    data = repo.data
    rels = prv.listar_relaciones(solo_activas=False)
    if rels:
        st.dataframe(
            {
                "Producto": [
                    next((p.nombre for p in data.productos if p.id == r.producto_id), r.producto_id)
                    for r in rels
                ],
                "Proveedor (snapshot)": [
                    r.proveedor_nombre_snapshot or r.proveedor_id for r in rels
                ],
                "Código": [r.codigo_proveedor or "—" for r in rels],
                "Preferente": ["Sí" if r.preferente else "No" for r in rels],
                "Estado": ["Activo" if r.activo else "Inactivo" for r in rels],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Sin vínculos todavía.", icon="🔗")

    section_divider()
    prods = {p.nombre: p.id for p in data.productos}
    provs = {
        (p.nombre_comercial or p.nombre_fiscal): p.id
        for p in prv.listar_proveedores(solo_activos=True)
    }
    if not prods or not provs:
        st.warning("Se necesitan productos y proveedores activos para vincular.")
        return
    with st.form("form_vincular_pp", clear_on_submit=True):
        pl = st.selectbox("Producto", list(prods.keys()))
        vl = st.selectbox("Proveedor", list(provs.keys()))
        codigo = st.text_input("Código proveedor")
        pref = st.checkbox("Preferente")
        if st.form_submit_button("Vincular", type="primary"):
            r = prv.vincular_producto_proveedor(
                prods[pl],
                provs[vl],
                codigo_proveedor=codigo or None,
                preferente=pref,
            )
            if r.ok:
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)

    activas = [r for r in rels if r.activo]
    if activas:
        section_divider()
        opts = {
            f"{r.id} · {r.proveedor_nombre_snapshot}": r.id for r in activas
        }
        sel = st.selectbox("Vínculo activo", list(opts.keys()), key="settings_ppv_sel")
        rid = opts[sel]
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Marcar preferente", key="settings_ppv_pref"):
                r = prv.marcar_preferente(rid)
                st.success(r.mensaje) if r.ok else st.error(r.mensaje)
                if r.ok:
                    st.rerun()
        with c2:
            if st.button("Desactivar vínculo", key="settings_ppv_off"):
                r = prv.desactivar_relacion(rid)
                st.success(r.mensaje) if r.ok else st.error(r.mensaje)
                if r.ok:
                    st.rerun()


def _render_archivos_documentales() -> None:
    """Fase 9 — originales inmutables con SHA-256 (sin OCR)."""
    from app.core.services import archivo_documental_service as ads

    st.markdown("#### Archivos documentales")
    st.caption(
        "Almacena el original en disco una sola vez, con SHA-256. "
        "No hay OCR ni confirmación automática. "
        "Desactivar no borra el fichero. El enlace a albarán/factura llega en F10+."
    )

    subidos = ads.listar_archivos(solo_activos=False)
    if subidos:
        st.dataframe(
            {
                "ID": [a.id for a in subidos],
                "Nombre": [a.nombre_original for a in subidos],
                "MIME": [a.mime_type for a in subidos],
                "Bytes": [a.tamanio_bytes for a in subidos],
                "SHA-256": [a.sha256[:16] + "…" for a in subidos],
                "Documento": [a.documento_id or "—" for a in subidos],
                "Estado": ["Activo" if a.activo else "Inactivo" for a in subidos],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Todavía no hay archivos documentales.", icon="📄")

    section_divider()
    st.markdown("##### Subir original")
    fichero = st.file_uploader(
        "Archivo",
        type=None,
        key="settings_adoc_upload",
    )
    notas = st.text_input("Notas (opcional)", key="settings_adoc_notas")
    if st.button("Registrar archivo", type="primary", key="settings_adoc_reg"):
        if fichero is None:
            st.error("Seleccione un archivo.")
        else:
            bruto = fichero.getvalue()
            r = ads.registrar_archivo(
                bruto,
                fichero.name or "archivo.bin",
                mime_type=getattr(fichero, "type", None),
                notas=notas or None,
            )
            if r.ok:
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)

    activos = [a for a in subidos if a.activo]
    if activos:
        section_divider()
        st.markdown("##### Verificar / desactivar")
        opts = {f"{a.id} · {a.nombre_original}": a.id for a in activos}
        sel = st.selectbox("Archivo", list(opts.keys()), key="settings_adoc_sel")
        aid = opts[sel]
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Verificar integridad", key="settings_adoc_ver"):
                v = ads.verificar_integridad(aid)
                if v.ok:
                    st.success(v.mensaje)
                else:
                    st.error(v.mensaje)
        with c2:
            bruto, err = ads.leer_bytes(aid)
            if bruto is not None:
                arch = next(a for a in activos if a.id == aid)
                st.download_button(
                    "Descargar original",
                    data=bruto,
                    file_name=arch.nombre_original,
                    mime=arch.mime_type,
                    key="settings_adoc_dl",
                )
            elif err:
                st.caption(err)
        with c3:
            if st.button("Desactivar", key="settings_adoc_off"):
                d = ads.desactivar_archivo(aid)
                if d.ok:
                    st.success(d.mensaje)
                    st.rerun()
                else:
                    st.error(d.mensaje)


def _render_restauracion_datos() -> None:
    """C2 — restauración con inspección previa y confirmación RESTAURAR."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.session import session_tiene_permiso
    from app.core.services import restore_backup_service as rst
    from app.core.storage.demo_files import DEMO_FILE, get_demo_file

    if not session_tiene_permiso(Permiso.RESTAURAR_BACKUP):
        st.error("Solo Dirección puede restaurar backups.")
        return

    st.markdown("### Restauración de datos")
    st.warning(
        "Operación destructiva. Se creará un backup preventivo "
        "(`pre_restore`) antes de sustituir los datos activos. "
        "Requiere inspección previa y confirmación explícita. "
        "Solo Dirección (F16) puede ejecutar la restauración."
    )
    dest = get_demo_file()
    if rst.destino_es_demo_protegido(dest):
        st.error(
            "Destino demo protegido (BM_TEST_ISOLATION). "
            "La restauración está bloqueada en este entorno."
        )
        return
    if dest.resolve() == DEMO_FILE.resolve():
        st.caption(
            f"Destino activo: almacén canónico `{dest.name}` "
            "(mismo path que el demo de desarrollo; no ejecutar en tests)."
        )
    else:
        st.caption(f"Destino activo (override): `{dest}`")

    uploaded = st.file_uploader(
        "Seleccionar backup ZIP (schema v2)",
        type=["zip"],
        key="settings_restore_upload",
    )
    if uploaded is None:
        st.info("Suba un backup para inspeccionarlo. Sin inspección no hay restauración.")
        return

    raw = uploaded.getvalue()
    if st.button("Inspeccionar backup", key="settings_restore_inspect"):
        insp = rst.inspeccionar_backup(raw, nombre=uploaded.name)
        st.session_state["settings_restore_insp"] = {
            "ok": insp.ok,
            "mensaje": insp.mensaje,
            "schema_version": insp.schema_version,
            "fecha": insp.fecha,
            "version_app": insp.version_app,
            "kind": insp.kind,
            "archivos": insp.archivos,
            "advertencias": insp.advertencias,
            "nombre": uploaded.name,
            "sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "nbytes": len(raw),
        }
        st.session_state["settings_restore_bytes"] = raw

    insp_state = st.session_state.get("settings_restore_insp")
    if not insp_state:
        st.caption("Pulse «Inspeccionar backup» antes de restaurar.")
        return

    st.markdown("#### Resultado de inspección")
    st.write(
        {
            "válido": insp_state.get("ok"),
            "mensaje": insp_state.get("mensaje"),
            "schema": insp_state.get("schema_version"),
            "fecha": insp_state.get("fecha"),
            "versión": insp_state.get("version_app"),
            "kind": insp_state.get("kind"),
            "archivos": len(insp_state.get("archivos") or []),
            "advertencias": insp_state.get("advertencias") or [],
        }
    )
    if not insp_state.get("ok"):
        st.error("Validación fallida: restauración deshabilitada.")
        return

    # Evitar un solo clic: exige texto exacto + checkbox + botón
    st.markdown("#### Confirmación")
    st.caption("Se creará un backup preventivo del estado actual.")
    confirm_txt = st.text_input(
        "Escriba exactamente RESTAURAR para habilitar la acción",
        key="settings_restore_confirm_txt",
    )
    accept = st.checkbox(
        "Entiendo que los datos activos serán sustituidos",
        key="settings_restore_accept",
    )
    can_run = confirm_txt == "RESTAURAR" and accept and insp_state.get("ok")
    if st.button(
        "Ejecutar restauración",
        type="primary",
        disabled=not can_run,
        key="settings_restore_run",
    ):
        payload = st.session_state.get("settings_restore_bytes") or raw
        res = rst.restaurar_desde_bytes(
            payload,
            nombre_backup=insp_state.get("nombre") or uploaded.name,
            recargar_sesion=True,
        )
        st.session_state["settings_restore_result"] = {
            "ok": res.ok,
            "estado": res.estado,
            "mensaje": res.mensaje,
            "operacion_id": res.operacion_id,
            "backup_preventivo": res.backup_preventivo,
            "archivos_restaurados": res.archivos_restaurados,
            "advertencias": res.advertencias,
            "error": res.error,
        }
        if res.ok:
            st.success(res.mensaje)
            st.info(
                f"Operación `{res.operacion_id}`. "
                "Recargue la aplicación (o navegue de nuevo) para ver los datos."
            )
        else:
            st.error(f"{res.mensaje} [{res.estado}]")
        st.json(st.session_state["settings_restore_result"])

    prev = st.session_state.get("settings_restore_result")
    if prev and not st.session_state.get("settings_restore_run"):
        st.caption(f"Último resultado: {prev.get('estado')} · {prev.get('operacion_id')}")


def _render_zona_peligro() -> None:
    """C3 — restablecimiento total con barrera y backup preventivo."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.session import session_tiene_permiso
    from app.core.services import destructive_ops_service as dop
    from app.core.services.restore_backup_service import destino_es_demo_protegido
    from app.core.storage.demo_files import DEMO_FILE, get_demo_file

    if not session_tiene_permiso(Permiso.EJECUTAR_OPERACION_DESTRUCTIVA):
        st.error("Solo Dirección puede ejecutar operaciones destructivas.")
        return

    st.markdown("### Zona de peligro")
    st.error(
        "Acciones que sustituyen o destruyen datos operativos. "
        "No son mantenimiento rutinario. No equivalen a restaurar un backup "
        "ni a reiniciar preferencias."
    )
    st.caption(
        "Reservado a Dirección. Confirmación reforzada + backup preventivo + autorización F16."
    )
    st.markdown(
        """
**Restablecer a datos mock** sustituye **todo** el AppData activo:

productos, lotes, stock, movimientos, consumos, mermas, compras, documentos,
usuarios de datos mock, configuración de ejemplo, etc.

Se creará un backup preventivo (`pre_reset`) validado **antes** de escribir.
Los ficheros adjuntos previos bajo `data/documentos/` no se borran automáticamente
(pueden quedar huérfanos respecto al nuevo JSON).
"""
    )

    dest = get_demo_file()
    if destino_es_demo_protegido(dest):
        st.error("Destino demo protegido (BM_TEST_ISOLATION). Operación bloqueada.")
        return
    if dest.resolve() == DEMO_FILE.resolve():
        st.caption("Destino: almacén canónico de la app (mismo path que el demo de desarrollo).")

    # Anti-rerun: token único por intento
    if "settings_danger_token" not in st.session_state:
        st.session_state["settings_danger_token"] = str(__import__("uuid").uuid4())

    chk = st.checkbox(
        "Entiendo que se sustituirán todos los datos operativos",
        key="settings_danger_reset_chk",
    )
    frase = st.text_input(
        f"Escriba exactamente {dop.FRASE_RESET_TOTAL}",
        key="settings_danger_reset_frase",
    )
    barrera = dop.validar_confirmacion(dop.FRASE_RESET_TOTAL, frase, chk)
    can_run = barrera.ok

    if st.button(
        "Restablecer a datos mock",
        type="primary",
        disabled=not can_run,
        key="settings_danger_reset_run",
    ):
        token = st.session_state["settings_danger_token"]
        res = dop.restablecer_a_datos_mock(
            confirmacion_escrita=frase,
            checkbox_aceptado=chk,
            operation_token=token,
            recargar_sesion=True,
        )
        st.session_state["settings_danger_last"] = {
            "ok": res.ok,
            "estado": res.estado,
            "mensaje": res.mensaje,
            "operacion_id": res.operacion_id,
            "backup_preventivo": res.backup_preventivo,
            "advertencias": res.advertencias,
            "error": res.error,
        }
        # Nuevo token tras intento para no repetir el mismo
        st.session_state["settings_danger_token"] = str(__import__("uuid").uuid4())
        if res.ok:
            st.success(res.mensaje)
            st.info(
                f"Operación `{res.operacion_id}`. "
                f"Preventivo: `{res.backup_preventivo}`. Recargue la app si es necesario."
            )
        else:
            st.error(f"{res.mensaje} [{res.estado}]")
        st.json(st.session_state["settings_danger_last"])

    last = st.session_state.get("settings_danger_last")
    if last:
        st.caption(
            f"Último resultado: {last.get('estado')} · id={last.get('operacion_id')}"
        )


_SUBTABS = {
    "Usuarios": _render_usuarios,
    "Configuración": _render_configuracion,
    "Catálogos de inventario": _render_catalogos_inventario,
    "Proveedores e impuestos": _render_proveedores_impuestos,
    "Archivos documentales": _render_archivos_documentales,
    "Responsables merma": _render_responsables_merma,
    "Actividad": _render_actividad,
    "Exportación": _render_exportacion,
    "Restauración de datos": _render_restauracion_datos,
    "Zona de peligro": _render_zona_peligro,
    "Datos demo": _render_datos_demo,
}


def render() -> None:
    from app.core.auth.permissions import Permiso
    from app.core.auth.session import session_tiene_permiso
    from app.ui.theme import APP_VERSION

    if not session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION):
        st.error("No autorizado para Configuración.")
        return

    page_header(
        "Configuración",
        "Diagnóstico, usuarios, catálogos de inventario, responsables de merma y exportación",
    )

    st.success(
        "DIAGNÓSTICO TÉCNICO — si ve este mensaje verde, está usando el código actualizado "
        f"(versión {APP_VERSION})."
    )

    # Siempre visible al entrar en Configuración (no depende de pestañas).
    _render_diagnostico_tecnico()
    section_divider()

    opciones = []
    for name in _SUBTABS:
        if name == "Usuarios" and not session_tiene_permiso(Permiso.GESTIONAR_USUARIOS):
            continue
        if name == "Restauración de datos" and not session_tiene_permiso(
            Permiso.VER_RESTAURACION
        ):
            continue
        if name == "Zona de peligro" and not session_tiene_permiso(Permiso.VER_ZONA_PELIGRO):
            continue
        if name == "Exportación" and not session_tiene_permiso(Permiso.EXPORTAR_BACKUP):
            # Admin tiene EXPORTAR_BACKUP; if somehow not, still show other export?
            # Keep Exportación visible for ACCEDER_CONFIGURACION; backup button checks separately
            pass
        opciones.append(name)

    pending = st.session_state.pop("settings_subtab_pending", None)
    if pending in opciones:
        st.session_state["settings_subtab"] = pending
    # Evita que un valor antiguo de session_state oculte opciones nuevas.
    if st.session_state.get("settings_subtab") not in (None, *opciones):
        del st.session_state["settings_subtab"]

    st.markdown("#### Sección")
    selected = st.selectbox(
        "Sección de configuración",
        opciones,
        key="settings_subtab",
        label_visibility="collapsed",
    )
    _SUBTABS[selected]()
