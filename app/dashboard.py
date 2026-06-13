"""
Collateral Book Risk Monitor — Dashboard.

Launch with:
    uv run streamlit run app/dashboard.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from streamlit_option_menu import option_menu
from app.sections import risk_overview, hedge_monitor, stress_scenarios


st.set_page_config(
    page_title="Collateral Risk Monitor",
    layout="wide",
    initial_sidebar_state="collapsed",
)

selected = option_menu(
    menu_title=None,
    options=["Risk Overview", "Hedge Monitor", "Stress Scenarios"],
    icons=["shield-check", "arrow-left-right", "lightning"],
    orientation="horizontal",
    default_index=0,
    styles={
        "container": {
            "padding": "0!important",
            "background-color": "#FFFFFF",
            "border-bottom": "2px solid #0F6644",
        },
        "icon": {"color": "#0F6644", "font-size": "16px"},
        "nav-link": {
            "font-size": "14px",
            "font-weight": "500",
            "text-align": "center",
            "margin": "0px",
            "padding": "12px 20px",
            "color": "#1A1A1A",
            "--hover-color": "#F5F6F5",
        },
        "nav-link-selected": {
            "background-color": "#0F6644",
            "color": "#FFFFFF",
            "font-weight": "600",
        },
    },
)

if selected == "Risk Overview":
    risk_overview.render()
elif selected == "Hedge Monitor":
    hedge_monitor.render()
elif selected == "Stress Scenarios":
    stress_scenarios.render()