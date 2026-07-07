"""Componentes reutilizables de interfaz."""

import streamlit as st

from app.ui.theme import APP_NAME, APP_VERSION, HOTEL_NAME, NAV_SECTIONS


def render_sidebar() -> str:
    """Renderiza la barra lateral y devuelve la sección seleccionada."""
    with st.sidebar:
        st.markdown(
            f"""
            <div class="bm-sidebar-brand">
                <div class="bm-sidebar-logo">☕</div>
                <p class="bm-sidebar-title">{APP_NAME}</p>
                <p class="bm-sidebar-hotel">{HOTEL_NAME}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("**Navegación**")
        section = st.radio(
            label="Sección",
            options=list(NAV_SECTIONS.keys()),
            label_visibility="collapsed",
            key="nav_section",
        )

        st.markdown(
            f'<p class="bm-sidebar-version">{APP_VERSION}</p>',
            unsafe_allow_html=True,
        )

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
