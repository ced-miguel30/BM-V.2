"""Componentes reutilizables de interfaz."""

import streamlit as st

from app.core.services.sidebar_service import resumen_sidebar
from app.ui.theme import NAV_SECTIONS


def _render_sidebar_alertas() -> None:
    datos = resumen_sidebar()
    st.markdown('<div class="bm-sidebar-panel">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="bm-sidebar-alerts">
            <p class="bm-sidebar-alerts-title">Resumen del mes</p>
            <div class="bm-sidebar-metric">
                <span class="bm-sidebar-metric-label">Coste desayuno</span>
                <span class="bm-sidebar-metric-value">{datos["coste_consumo_mes"]}</span>
            </div>
            <div class="bm-sidebar-metric">
                <span class="bm-sidebar-metric-label">Coste total</span>
                <span class="bm-sidebar-metric-value">{datos["coste_total_mes"]}</span>
            </div>
        </div>
        <p class="bm-sidebar-section-label">Alertas</p>
        """,
        unsafe_allow_html=True,
    )
    for alerta in datos["alertas"]:
        clase = f"bm-sidebar-alert bm-sidebar-alert-{alerta.tipo}"
        st.markdown(
            f"""
            <div class="{clase}">
                <p class="bm-sidebar-alert-title">{alerta.titulo}</p>
                <p class="bm-sidebar-alert-detail">{alerta.detalle}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_sidebar_diagnostico() -> None:
    """Acceso visible al diagnóstico (solo lectura) desde la barra lateral."""
    st.markdown('<p class="bm-sidebar-section-label">Diagnóstico</p>', unsafe_allow_html=True)
    with st.expander("Diagnóstico técnico", expanded=False):
        try:
            from app.core.services.data_service import get_repository
            from app.core.services.diagnostico_service import generar_diagnostico

            r = generar_diagnostico(get_repository().data)
            st.caption(f"Productos: {r.num_productos}")
            st.caption(f"Recetas: {r.num_recetas}")
            st.caption(f"Lotes activos: {r.num_lotes_activos}")
            st.caption(f"Registros: {r.num_registros}")
            st.caption(f"Mermas: {r.num_mermas}")
            st.caption(f"Ajustes: {r.num_ajustes}")
            st.caption("Detalle completo en Configuración.")
        except Exception as exc:  # noqa: BLE001
            st.error("No se pudo cargar el diagnóstico.")
            st.caption(str(exc))


def render_sidebar() -> str:
    """Renderiza la barra lateral y devuelve la clave interna de sección.

    Fase 5: selector «Espacio de trabajo» filtra la navegación operativa.
    Configuración es global (siempre visible). No toca AppData/JSON.

    Orden: resolver deep-link / coherencia → fijar session_state → widgets
    → como máximo un ``st.rerun()`` (botón Configuración).
    """
    from app.core.application import espacios as esp

    key_esp = esp.SESSION_KEY_ESPACIO
    key_op = "nav_section_op"
    key_nav = "nav_section"

    # 1–5. Deep-link y coherencia ANTES de instanciar widgets.
    pending = st.session_state.pop("nav_section_pending", None)
    estado = esp.resolver_navegacion(
        espacio_actual=st.session_state.get(key_esp),
        seccion_actual=st.session_state.get(key_nav),
        seccion_pendiente=pending,
    )
    st.session_state[key_esp] = estado.espacio
    st.session_state[key_nav] = estado.seccion

    operativas = list(esp.secciones_operativas(estado.espacio))
    if estado.seccion in operativas:
        st.session_state[key_op] = estado.seccion
    elif st.session_state.get(key_op) not in operativas:
        st.session_state[key_op] = operativas[0]

    with st.sidebar:
        _render_sidebar_alertas()

        st.markdown(
            '<p class="bm-sidebar-section-label">Espacio de trabajo</p>',
            unsafe_allow_html=True,
        )
        st.selectbox(
            "Espacio de trabajo",
            options=list(esp.ESPACIOS_ORDEN),
            format_func=lambda e: esp.ETIQUETAS_ESPACIO[e],
            key=key_esp,
            label_visibility="collapsed",
        )

        st.markdown(
            '<p class="bm-sidebar-section-label">Navegación</p>',
            unsafe_allow_html=True,
        )

        def _al_cambiar_seccion_operativa() -> None:
            st.session_state[key_nav] = st.session_state[key_op]

        st.radio(
            label="Sección",
            options=operativas,
            label_visibility="collapsed",
            key=key_op,
            on_change=_al_cambiar_seccion_operativa,
        )

        st.markdown(
            '<p class="bm-sidebar-section-label">Global</p>',
            unsafe_allow_html=True,
        )
        config_activa = st.session_state.get(key_nav) == esp.SECCION_CONFIGURACION
        if st.button(
            "Configuración",
            key="nav_btn_configuracion",
            type="primary" if config_activa else "secondary",
            use_container_width=True,
        ):
            st.session_state[key_nav] = esp.SECCION_CONFIGURACION
            st.rerun()

        if st.session_state.get(key_nav) != esp.SECCION_CONFIGURACION:
            st.session_state[key_nav] = st.session_state[key_op]

        _render_sidebar_diagnostico()

    seccion_label = st.session_state.get(
        key_nav, esp.primera_seccion_operativa(estado.espacio),
    )
    if seccion_label not in NAV_SECTIONS:
        seccion_label = esp.primera_seccion_operativa(
            esp.normalizar_espacio(st.session_state.get(key_esp)),
        )
        st.session_state[key_nav] = seccion_label
    return NAV_SECTIONS[seccion_label]


def page_header(title: str, subtitle: str) -> None:
    """Encabezado de página con título y descripción."""
    st.markdown(
        f"""
        <div class="bm-page-header">
            <h1 class="bm-page-title">{title}</h1>
            <p class="bm-page-subtitle">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, delta: str = "", icon: str = "") -> None:
    """Card de métrica KPI."""
    icon_html = f'<span style="margin-right:0.35rem;">{icon}</span>' if icon else ""
    delta_html = f'<p class="bm-metric-delta">{delta}</p>' if delta else ""
    st.markdown(
        f"""
        <div class="bm-metric-card">
            <div class="bm-metric-label">{icon_html}{label}</div>
            <p class="bm-metric-value">{value}</p>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def placeholder_panel(title: str, description: str, items: list[str]) -> None:
    """Panel informativo de funcionalidades próximas."""
    items_html = "".join(f"<li>{item}</li>" for item in items)
    st.markdown(
        f"""
        <div class="bm-placeholder-panel">
            <h4>{title}</h4>
            <p>{description}</p>
            <ul>{items_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(message: str, icon: str = "📋") -> None:
    """Estado vacío elegante."""
    st.markdown(
        f"""
        <div class="bm-empty-state">
            <div class="bm-empty-state-icon">{icon}</div>
            <p>{message}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sub_tabs(options: list[str], key: str) -> str:
    """Navegación tipo tabs; solo se renderiza el panel activo (evita IDs duplicados)."""
    st.markdown('<div class="bm-subtabs-nav">', unsafe_allow_html=True)
    selected = st.radio(
        label="Subsección",
        options=options,
        horizontal=True,
        label_visibility="collapsed",
        key=key,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    return selected


def section_divider() -> None:
    """Separador visual sutil."""
    st.markdown(
        '<hr style="border:none;border-top:1px solid #E2E6EC;margin:1.5rem 0;">',
        unsafe_allow_html=True,
    )


def chart_placeholder(message: str) -> None:
    """Área reservada para gráficos futuros."""
    st.markdown(
        f'<div class="bm-chart-placeholder">{message}</div>',
        unsafe_allow_html=True,
    )


def card_wrapper(title: str) -> None:
    """Inicio de card con título (usar con contenido Streamlit debajo)."""
    st.markdown(
        f'<div class="bm-card"><p class="bm-card-title">{title}</p>',
        unsafe_allow_html=True,
    )


def badge_warning(text: str) -> None:
    """Badge de advertencia."""
    st.markdown(
        f'<span class="bm-badge bm-badge-warning">{text}</span>',
        unsafe_allow_html=True,
    )


def badge_info(text: str) -> None:
    """Badge informativo."""
    st.markdown(
        f'<span class="bm-badge bm-badge-info">{text}</span>',
        unsafe_allow_html=True,
    )


def basket_panel(title: str = "Cesta") -> None:
    """Panel lateral tipo cesta (estructura visual)."""
    st.markdown(
        f"""
        <div class="bm-basket-panel">
            <div class="bm-basket-title">{title}</div>
        """,
        unsafe_allow_html=True,
    )


def aviso_servicios_pendientes(*, key_prefix: str = "aviso_serv") -> None:
    """Aviso si hay productos/recetas sin servicios_disponibles + enlace a config."""
    from app.core.services.data_service import get_repository
    from app.core.services.diagnostico_service import generar_diagnostico

    r = generar_diagnostico(get_repository().data)
    n_prod = len(r.productos_sin_servicio)
    n_rec = len(r.recetas_sin_servicio)
    if n_prod == 0 and n_rec == 0:
        return

    partes = []
    if n_prod:
        partes.append(f"{n_prod} producto(s)")
    if n_rec:
        partes.append(f"{n_rec} receta(s)")
    st.warning(
        "Hay "
        + " y ".join(partes)
        + " sin servicios disponibles configurados. "
        "Lista vacía ≠ todos: no aparecen en registros nuevos ni en merma "
        "(salvo Almacén / General). Configúrelos en Stock o Recetas."
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Ir a Stock", key=f"{key_prefix}_stock", use_container_width=True):
            st.session_state["nav_section_pending"] = "Stock"
            st.rerun()
    with col_b:
        if st.button("Ir a Recetas", key=f"{key_prefix}_recetas", use_container_width=True):
            st.session_state["nav_section_pending"] = "Recetas"
            st.rerun()


def periodo_filtro_analisis(
    key: str,
    *,
    mensaje_error: str = "Revise las fechas.",
) -> tuple | None:
    """Periodo compartido de Análisis: semana / mes / rango. Sin cambiar el contrato del Dashboard."""
    from datetime import date

    from app.core.services.exportacion_semanal_service import limite_semana

    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    periodo_sel = st.radio(
        "Periodo",
        ["Esta semana", "Este mes", "Rango personalizado"],
        horizontal=True,
        key=f"{key}_periodo",
    )
    if periodo_sel == "Esta semana":
        return limite_semana(hoy)[0], hoy
    if periodo_sel == "Este mes":
        return inicio_mes, hoy
    c1, c2 = st.columns(2)
    with c1:
        desde = st.date_input("Desde", value=inicio_mes, key=f"{key}_desde")
    with c2:
        hasta = st.date_input("Hasta", value=hoy, max_value=hoy, key=f"{key}_hasta")
    if desde > hasta:
        st.error(mensaje_error)
        return None
    return desde, hasta


def render_explicacion_calculo() -> None:
    """Expander común de Análisis (texto canónico en analitica_consumo_service)."""
    from app.core.services import analitica_consumo_service as analitica

    with st.expander("Explicación del cálculo", expanded=False):
        st.markdown(analitica.TEXTO_EXPLICACION_CALCULO)


def ir_analisis(
    subtab: str = "Consumo",
    *,
    consumo_pestana: str | None = None,
    costes_pestana: str | None = None,
    merma_pestana: str | None = None,
    _st=None,
) -> None:
    """Deep-link a Análisis (aplicar nav_section_pending antes del radio del sidebar)."""
    ui = _st if _st is not None else st
    ui.session_state["nav_section_pending"] = "Análisis"
    ui.session_state["analisis_subtab"] = subtab
    if consumo_pestana:
        ui.session_state["consumo_pestana"] = consumo_pestana
    if costes_pestana:
        ui.session_state["costes_pestana"] = costes_pestana
    if merma_pestana:
        ui.session_state["merma_pestana"] = merma_pestana
    ui.rerun()


def ir_stock(subtab: str = "Inventario", *, _st=None) -> None:
    ui = _st if _st is not None else st
    ui.session_state["nav_section_pending"] = "Stock"
    ui.session_state["stock_subtab"] = subtab
    ui.rerun()


def ir_registros(subtab: str = "Desayuno", *, _st=None) -> None:
    ui = _st if _st is not None else st
    ui.session_state["nav_section_pending"] = "Registros"
    ui.session_state["registros_subtab"] = subtab
    ui.rerun()
