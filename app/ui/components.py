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
            st.caption("Detalle completo en Configuración.")
        except Exception as exc:  # noqa: BLE001
            st.error("No se pudo cargar el diagnóstico.")
            st.caption(str(exc))


def render_sidebar() -> str:
    """Renderiza la barra lateral y devuelve la sección seleccionada."""
    opciones = list(NAV_SECTIONS.keys())
    # Deep-link: aplicar destino pendiente ANTES de instanciar el radio.
    pending = st.session_state.pop("nav_section_pending", None)
    if pending in opciones:
        st.session_state["nav_section"] = pending
    # Si el menú cambió (p. ej. se añadió Registros), limpia un valor obsoleto
    # para que Streamlit no oculte opciones nuevas o falle el radio.
    if st.session_state.get("nav_section") not in (None, *opciones):
        del st.session_state["nav_section"]

    with st.sidebar:
        _render_sidebar_alertas()
        st.markdown('<p class="bm-sidebar-section-label">Navegación</p>', unsafe_allow_html=True)
        section = st.radio(
            label="Sección",
            options=opciones,
            label_visibility="collapsed",
            key="nav_section",
        )
        _render_sidebar_diagnostico()

    return NAV_SECTIONS[section]


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
