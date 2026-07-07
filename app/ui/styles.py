"""Inyección de estilos CSS globales."""

import streamlit as st

from app.ui.theme import (
    BORDER,
    DANGER,
    DARK_TEXT,
    FONT_FAMILY,
    GOLD,
    GOLD_LIGHT,
    INFO,
    LIGHT_GRAY,
    MID_GRAY,
    NAVY,
    NAVY_LIGHT,
    SUCCESS,
    WARNING,
    WHITE,
)


def inject_global_styles() -> None:
    """Aplica el tema visual luxury hotel a toda la aplicación."""
    st.markdown(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

            :root {{
                --navy: {NAVY};
                --navy-light: {NAVY_LIGHT};
                --gold: {GOLD};
                --gold-light: {GOLD_LIGHT};
                --white: {WHITE};
                --light-gray: {LIGHT_GRAY};
                --mid-gray: {MID_GRAY};
                --dark-text: {DARK_TEXT};
                --border: {BORDER};
                --success: {SUCCESS};
                --warning: {WARNING};
                --danger: {DANGER};
                --info: {INFO};
            }}

            #MainMenu {{ visibility: hidden; }}
            footer {{ visibility: hidden; }}
            header[data-testid="stHeader"] {{
                background: transparent;
            }}
            [data-testid="stToolbar"] a[href*="streamlit.io"],
            .stAppDeployButton,
            [data-testid="stToolbar"] [data-testid="stToolbarDeployButton"] {{
                display: none !important;
            }}

            .stApp {{
                background-color: {LIGHT_GRAY};
                font-family: {FONT_FAMILY};
            }}

            [data-testid="stSidebarNav"],
            [data-testid="stSidebarNavSeparator"],
            section[data-testid="stSidebarNav"] {{
                display: none !important;
            }}

            [data-testid="stSidebar"] > div:first-child {{
                padding-top: 1.25rem;
            }}

            [data-testid="stSidebar"] .bm-sidebar-panel {{
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
                width: 100%;
                padding: 0.5rem 0.5rem 1rem;
            }}

            [data-testid="stSidebar"] .bm-sidebar-section-label {{
                font-size: 0.72rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: {GOLD};
                margin: 0.75rem 0 0.5rem 0;
                text-align: center;
                width: 100%;
            }}

            [data-testid="stSidebar"] {{
                background: linear-gradient(180deg, {NAVY} 0%, {NAVY_LIGHT} 100%);
                border-right: 1px solid rgba(201, 162, 39, 0.25);
            }}

            [data-testid="stSidebar"] * {{
                color: {WHITE} !important;
            }}

            [data-testid="stSidebar"] .stRadio label {{
                color: rgba(255, 255, 255, 0.85) !important;
                font-weight: 500;
            }}

            [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {{
                background: transparent;
                border-radius: 8px;
                padding: 0.35rem 0.5rem;
                transition: background 0.2s ease;
            }}

            [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:hover {{
                background: rgba(201, 162, 39, 0.15);
            }}

            [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label[data-checked="true"] {{
                background: rgba(201, 162, 39, 0.22);
                border-left: 3px solid {GOLD};
            }}

            .block-container {{
                padding-top: 2rem;
                padding-bottom: 3rem;
                max-width: 1200px;
            }}

            .bm-page-header {{
                margin-bottom: 1.75rem;
            }}

            .bm-page-title {{
                color: {NAVY};
                font-size: 1.85rem;
                font-weight: 700;
                margin: 0 0 0.35rem 0;
                letter-spacing: -0.02em;
            }}

            .bm-page-subtitle {{
                color: {MID_GRAY};
                font-size: 1rem;
                margin: 0;
                font-weight: 400;
            }}

            .bm-metric-card {{
                background: {WHITE};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 1.25rem 1.35rem;
                box-shadow: 0 2px 8px rgba(11, 31, 58, 0.06);
                height: 100%;
                min-height: 120px;
            }}

            .bm-metric-label {{
                color: {MID_GRAY};
                font-size: 0.8rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                margin-bottom: 0.5rem;
            }}

            .bm-metric-value {{
                color: {NAVY};
                font-size: 1.65rem;
                font-weight: 700;
                margin: 0;
            }}

            .bm-metric-delta {{
                color: {MID_GRAY};
                font-size: 0.85rem;
                margin-top: 0.35rem;
            }}

            .bm-card {{
                background: {WHITE};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 1.5rem;
                box-shadow: 0 2px 8px rgba(11, 31, 58, 0.06);
                margin-bottom: 1rem;
            }}

            .bm-card-title {{
                color: {NAVY};
                font-size: 1.05rem;
                font-weight: 600;
                margin: 0 0 0.75rem 0;
                padding-bottom: 0.5rem;
                border-bottom: 2px solid {GOLD};
                display: inline-block;
            }}

            .bm-badge {{
                display: inline-block;
                padding: 0.25rem 0.65rem;
                border-radius: 20px;
                font-size: 0.78rem;
                font-weight: 600;
            }}

            .bm-badge-warning {{
                background: rgba(184, 134, 11, 0.15);
                color: {WARNING};
            }}

            .bm-badge-info {{
                background: rgba(58, 110, 165, 0.12);
                color: {INFO};
            }}

            .bm-empty-state {{
                text-align: center;
                padding: 2.5rem 1.5rem;
                color: {MID_GRAY};
                background: {WHITE};
                border: 1px dashed {BORDER};
                border-radius: 12px;
            }}

            .bm-empty-state-icon {{
                font-size: 2rem;
                margin-bottom: 0.75rem;
                opacity: 0.6;
            }}

            .bm-placeholder-panel {{
                background: {WHITE};
                border-left: 4px solid {GOLD};
                border-radius: 0 12px 12px 0;
                padding: 1.25rem 1.5rem;
                margin: 1rem 0;
                box-shadow: 0 2px 6px rgba(11, 31, 58, 0.04);
            }}

            .bm-placeholder-panel h4 {{
                color: {NAVY};
                margin: 0 0 0.5rem 0;
                font-size: 1rem;
            }}

            .bm-placeholder-panel p {{
                color: {MID_GRAY};
                margin: 0 0 0.75rem 0;
                font-size: 0.9rem;
            }}

            .bm-placeholder-panel ul {{
                margin: 0;
                padding-left: 1.25rem;
                color: {DARK_TEXT};
                font-size: 0.88rem;
            }}

            .bm-sidebar-alerts {{
                padding: 0.5rem 0 1rem 0;
                border-bottom: 1px solid rgba(201, 162, 39, 0.3);
                margin-bottom: 0.5rem;
                width: 100%;
                max-width: 240px;
            }}

            .bm-sidebar-alerts-title {{
                font-size: 0.72rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: {GOLD};
                margin: 0 0 0.85rem 0;
                text-align: center;
            }}

            .bm-sidebar-metric {{
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 0.15rem;
                margin-bottom: 0.65rem;
                font-size: 0.82rem;
                text-align: center;
            }}

            .bm-sidebar-metric-label {{
                color: rgba(255, 255, 255, 0.75);
            }}

            .bm-sidebar-metric-value {{
                font-weight: 700;
                color: {WHITE};
                font-size: 0.95rem;
            }}

            .bm-sidebar-alert {{
                background: rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 0.6rem 0.75rem;
                margin: 0 auto 0.5rem auto;
                border-left: none;
                border-top: 3px solid {GOLD};
                width: 100%;
                max-width: 240px;
                text-align: center;
            }}

            .bm-sidebar-alert-warning {{
                border-left-color: {WARNING};
            }}

            .bm-sidebar-alert-danger {{
                border-left-color: {DANGER};
            }}

            .bm-sidebar-alert-ok {{
                border-left-color: {SUCCESS};
            }}

            .bm-sidebar-alert-title {{
                font-size: 0.8rem;
                font-weight: 600;
                margin: 0 0 0.2rem 0;
                color: {WHITE};
            }}

            .bm-sidebar-alert-detail {{
                font-size: 0.72rem;
                margin: 0;
                color: rgba(255, 255, 255, 0.7);
                line-height: 1.35;
            }}

            .bm-chart-placeholder {{
                background: linear-gradient(135deg, {WHITE} 0%, {LIGHT_GRAY} 100%);
                border: 1px dashed {BORDER};
                border-radius: 12px;
                min-height: 280px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: {MID_GRAY};
                font-size: 0.95rem;
            }}

            .bm-basket-panel {{
                background: {WHITE};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 1.25rem;
                min-height: 320px;
            }}

            .bm-basket-title {{
                color: {NAVY};
                font-weight: 600;
                font-size: 1rem;
                margin-bottom: 1rem;
                padding-bottom: 0.5rem;
                border-bottom: 1px solid {BORDER};
            }}

            .bm-subtabs-nav {{
                margin-bottom: 1.25rem;
                padding-bottom: 0.5rem;
                border-bottom: 1px solid {BORDER};
            }}

            .bm-subtabs-nav div[role="radiogroup"] {{
                gap: 0.35rem;
                flex-wrap: wrap;
            }}

            .bm-subtabs-nav div[role="radiogroup"] label {{
                background: {WHITE};
                border: 1px solid {BORDER};
                border-radius: 8px 8px 0 0;
                padding: 0.45rem 1rem !important;
                font-weight: 500;
                color: {MID_GRAY} !important;
                transition: all 0.2s ease;
            }}

            .bm-subtabs-nav div[role="radiogroup"] label:hover {{
                border-color: {GOLD};
                color: {NAVY} !important;
            }}

            .bm-subtabs-nav div[role="radiogroup"] label[data-checked="true"] {{
                background: {WHITE};
                border-color: {BORDER};
                border-bottom: 3px solid {GOLD};
                color: {NAVY} !important;
                font-weight: 600;
            }}

            div[data-testid="stForm"] {{
                background: {WHITE};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 1rem;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )
