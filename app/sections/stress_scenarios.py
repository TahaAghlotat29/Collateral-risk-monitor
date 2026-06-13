"""
Stress Scenarios — P&L impact and margin call estimation under curve shifts.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data.loader import load_all
from engine.risk import compute_portfolio_risk
from engine.curves import bump_curve
from engine.stress import run_scenario, run_all_scenarios, stress_bond, stress_swap, estimate_margin_call
from config.settings import CHART_PALETTE, STRESS_SCENARIOS, FACE_VALUE


@st.cache_data(show_spinner="Running stress scenarios...")
def _load():
    data = load_all()
    portfolio_risk = compute_portfolio_risk(data["portfolio"], data["latest_curve"])
    summary = run_all_scenarios(portfolio_risk, data["swaps"], data["latest_curve"])
    return data, portfolio_risk, summary


def _run_custom(portfolio_risk, swaps, base_curve, custom_bumps):
    """Run a custom scenario from user-defined shifts."""
    stressed_curve = bump_curve(base_curve, custom_bumps)

    bond_results = []
    for _, bond in portfolio_risk.iterrows():
        result = stress_bond(bond, base_curve, stressed_curve)
        result["bond_id"] = bond["bond_id"]
        result["country"] = bond["country"]
        result["bucket"] = bond["bucket"]
        result["ccp"] = bond["ccp"]
        result["notional_mn"] = bond["notional_mn"]
        bond_results.append(result)

    bond_df = pd.DataFrame(bond_results)
    total_bond_pnl = bond_df["pnl_eur"].sum()

    swap_results = []
    for _, swap in swaps.iterrows():
        result = stress_swap(swap, custom_bumps)
        result["swap_id"] = swap["swap_id"]
        result["bucket"] = swap["bucket"]
        result["notional_mn"] = swap["notional_mn"]
        swap_results.append(result)

    swap_df = pd.DataFrame(swap_results)
    total_swap_pnl = swap_df["pnl_eur"].sum()
    net_pnl = total_bond_pnl + total_swap_pnl

    bond_by_bucket = bond_df.groupby("bucket")["pnl_eur"].sum().rename("bond_pnl")
    swap_by_bucket = swap_df.groupby("bucket")["pnl_eur"].sum().rename("swap_pnl")
    pnl_by_bucket = pd.concat([bond_by_bucket, swap_by_bucket], axis=1).fillna(0)
    pnl_by_bucket["net_pnl"] = pnl_by_bucket["bond_pnl"] + pnl_by_bucket["swap_pnl"]
    pnl_by_bucket = pnl_by_bucket.round(0).reset_index()

    pnl_by_ccp = bond_df.groupby("ccp")["pnl_eur"].sum().round(0).reset_index()
    pnl_by_ccp = pnl_by_ccp.rename(columns={"pnl_eur": "collateral_pnl"})

    margin_impact = estimate_margin_call(bond_df, portfolio_risk)

    return {
        "bumps": custom_bumps,
        "bond_results": bond_df,
        "swap_results": swap_df,
        "collateral_pnl": round(total_bond_pnl, 0),
        "swap_pnl": round(total_swap_pnl, 0),
        "net_pnl": round(net_pnl, 0),
        "pnl_by_ccp": pnl_by_ccp,
        "pnl_by_bucket": pnl_by_bucket,
        "margin_impact": margin_impact,
    }


def render():
    data, portfolio_risk, summary = _load()

    st.title("Stress Scenarios")
    st.markdown(
        "**P&L impact and margin call estimation under yield curve shifts.**"
    )
    st.markdown("---")

    # ================================================================
    # CUSTOM SCENARIO — interactive sliders with session state
    # ================================================================
    st.subheader("Custom scenario builder")
    st.caption(
        "Define your own curve shift per maturity bucket and see the impact in real time."
    )

    # Initialize session state
    for key in ["shift_2y", "shift_5y", "shift_10y", "shift_30y"]:
        if key not in st.session_state:
            st.session_state[key] = 0

    # Quick presets
    st.markdown("**Quick presets**")
    presets = {
        "Flat +50": {"shift_2y": 50, "shift_5y": 50, "shift_10y": 50, "shift_30y": 50},
        "Flat -50": {"shift_2y": -50, "shift_5y": -50, "shift_10y": -50, "shift_30y": -50},
        "Steepener": {"shift_2y": -10, "shift_5y": 0, "shift_10y": 25, "shift_30y": 50},
        "Flattener": {"shift_2y": 50, "shift_5y": 25, "shift_10y": 0, "shift_30y": -10},
        "Front shock": {"shift_2y": 75, "shift_5y": 25, "shift_10y": 5, "shift_30y": 0},
        "Reset": {"shift_2y": 0, "shift_5y": 0, "shift_10y": 0, "shift_30y": 0},
    }

    preset_cols = st.columns(len(presets))
    for i, (name, values) in enumerate(presets.items()):
        with preset_cols[i]:
            if st.button(name, use_container_width=True):
                for k, v in values.items():
                    st.session_state[k] = v
                st.rerun()

    # Sliders linked to session state
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        shift_2y = st.slider(
            "2Y shift (bps)", min_value=-100, max_value=100,
            value=st.session_state["shift_2y"], step=5, key="slider_2y",
        )
        st.session_state["shift_2y"] = shift_2y
    with col2:
        shift_5y = st.slider(
            "5Y shift (bps)", min_value=-100, max_value=100,
            value=st.session_state["shift_5y"], step=5, key="slider_5y",
        )
        st.session_state["shift_5y"] = shift_5y
    with col3:
        shift_10y = st.slider(
            "10Y shift (bps)", min_value=-100, max_value=100,
            value=st.session_state["shift_10y"], step=5, key="slider_10y",
        )
        st.session_state["shift_10y"] = shift_10y
    with col4:
        shift_30y = st.slider(
            "30Y shift (bps)", min_value=-100, max_value=100,
            value=st.session_state["shift_30y"], step=5, key="slider_30y",
        )
        st.session_state["shift_30y"] = shift_30y

    custom_bumps = {
        "2Y": shift_2y,
        "5Y": shift_5y,
        "10Y": shift_10y,
        "30Y": shift_30y,
    }

    # Run custom scenario
    is_active = any(v != 0 for v in custom_bumps.values())

    if is_active:
        outcome = _run_custom(
            portfolio_risk, data["swaps"], data["latest_curve"], custom_bumps,
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Collateral P&L", f"€{outcome['collateral_pnl']:,.0f}")
        col2.metric("Swap P&L", f"€{outcome['swap_pnl']:,.0f}")
        col3.metric(
            "Net P&L",
            f"€{outcome['net_pnl']:,.0f}",
            delta="loss" if outcome["net_pnl"] < 0 else "gain",
            delta_color="inverse" if outcome["net_pnl"] < 0 else "normal",
        )
        col4.metric("Margin Call", f"€{outcome['margin_impact']['total_with_buffer']:,.0f}")

        st.markdown("---")

        pnl_bucket = outcome["pnl_by_bucket"]
        bucket_order = ["2Y", "5Y", "10Y", "30Y"]
        pnl_bucket = pnl_bucket.set_index("bucket").reindex(bucket_order).fillna(0).reset_index()

        col1, col2 = st.columns(2)

        with col1:
            fig_bucket = go.Figure()
            fig_bucket.add_trace(go.Bar(
                x=pnl_bucket["bucket"], y=pnl_bucket["bond_pnl"],
                name="Collateral", marker=dict(color=CHART_PALETTE["collateral"]),
            ))
            fig_bucket.add_trace(go.Bar(
                x=pnl_bucket["bucket"], y=pnl_bucket["swap_pnl"],
                name="Swap", marker=dict(color=CHART_PALETTE["swap"]),
            ))
            fig_bucket.add_trace(go.Bar(
                x=pnl_bucket["bucket"], y=pnl_bucket["net_pnl"],
                name="Net", marker=dict(color=CHART_PALETTE["residual"]),
            ))
            fig_bucket.update_layout(
                barmode="group",
                yaxis_title="P&L (EUR)",
                height=350,
                margin=dict(t=20, b=20),
                legend=dict(orientation="h", y=-0.15),
            )
            st.plotly_chart(fig_bucket, use_container_width=True)

        with col2:
            pnl_ccp = outcome["pnl_by_ccp"]
            margin_ccp = outcome["margin_impact"]["by_ccp"]

            fig_ccp = go.Figure()
            fig_ccp.add_trace(go.Bar(
                x=pnl_ccp["ccp"], y=pnl_ccp["collateral_pnl"],
                name="Collateral P&L", marker=dict(color=CHART_PALETTE["collateral"]),
            ))
            fig_ccp.add_trace(go.Bar(
                x=margin_ccp["ccp"], y=margin_ccp["margin_call"],
                name="Margin Call", marker=dict(color=CHART_PALETTE["residual"]),
            ))
            fig_ccp.update_layout(
                barmode="group",
                yaxis_title="EUR",
                height=350,
                margin=dict(t=20, b=20),
                legend=dict(orientation="h", y=-0.15),
            )
            st.plotly_chart(fig_ccp, use_container_width=True)

    else:
        st.info("Move the sliders or click a preset to simulate a curve shift.")

    st.markdown("---")

    # ================================================================
    # PREDEFINED SCENARIOS
    # ================================================================
    st.subheader("Predefined scenarios")

    display = summary.copy()
    display = display.rename(columns={
        "scenario": "Scenario",
        "collateral_pnl": "Collateral P&L (€)",
        "swap_pnl": "Swap P&L (€)",
        "net_pnl": "Net P&L (€)",
        "margin_call": "Margin Call (€)",
    })

    for col in ["Collateral P&L (€)", "Swap P&L (€)", "Net P&L (€)", "Margin Call (€)"]:
        display[col] = display[col].apply(lambda x: f"{x:,.0f}")

    st.dataframe(display, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Net P&L comparison
    st.subheader("Net P&L comparison")

    colors = [
        CHART_PALETTE["negative"] if v < 0 else CHART_PALETTE["collateral"]
        for v in summary["net_pnl"]
    ]

    fig_net = go.Figure()
    fig_net.add_trace(go.Bar(
        x=summary["scenario"], y=summary["net_pnl"],
        marker=dict(color=colors, line=dict(color="#1A1A1A", width=0.8)),
        text=[f"€{v:,.0f}" for v in summary["net_pnl"]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Net P&L: €%{y:,.0f}<extra></extra>",
    ))
    fig_net.add_hline(y=0, line=dict(color="#1A1A1A", width=1, dash="dash"))
    fig_net.update_layout(
        yaxis_title="Net P&L (EUR)",
        height=400,
        margin=dict(t=20, b=100),
        xaxis_tickangle=-30,
        showlegend=False,
    )
    st.plotly_chart(fig_net, use_container_width=True)

    st.markdown("---")

    # Margin calls
    st.subheader("Estimated margin calls")

    fig_margin = go.Figure()
    fig_margin.add_trace(go.Bar(
        x=summary["scenario"], y=summary["margin_call"],
        marker=dict(color=CHART_PALETTE["residual"], line=dict(color="#1A1A1A", width=0.8)),
        text=[f"€{v:,.0f}" for v in summary["margin_call"]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Margin: €%{y:,.0f}<extra></extra>",
    ))
    fig_margin.update_layout(
        yaxis_title="Margin call (EUR)",
        height=400,
        margin=dict(t=20, b=100),
        xaxis_tickangle=-30,
        showlegend=False,
    )
    st.plotly_chart(fig_margin, use_container_width=True)

    st.markdown("---")

    # Drill-down
    st.subheader("Scenario drill-down")

    selected_scenario = st.selectbox(
        "Select predefined scenario",
        options=list(STRESS_SCENARIOS.keys()),
    )

    outcome = run_scenario(
        portfolio_risk, data["swaps"], data["latest_curve"], selected_scenario,
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Collateral P&L", f"€{outcome['collateral_pnl']:,.0f}")
    col2.metric("Swap P&L", f"€{outcome['swap_pnl']:,.0f}")
    col3.metric("Net P&L", f"€{outcome['net_pnl']:,.0f}")
    col4.metric("Margin Call", f"€{outcome['margin_impact']['total_with_buffer']:,.0f}")

    st.markdown("---")

    st.markdown("**Curve shift applied (bps)**")
    bumps = outcome["bumps"]
    bump_cols = st.columns(len(bumps))
    for i, (bucket, shift) in enumerate(bumps.items()):
        with bump_cols[i]:
            st.metric(bucket, f"{shift:+d} bps")

    st.markdown("---")

    # Bond detail
    st.subheader("Bond-level P&L detail")

    bond_detail = outcome["bond_results"][[
        "bond_id", "country", "bucket", "ccp", "notional_mn",
        "base_price", "stressed_price", "price_change_pct", "pnl_eur",
    ]].sort_values("pnl_eur").copy()

    bond_detail = bond_detail.rename(columns={
        "bond_id": "Bond", "country": "Country", "bucket": "Bucket",
        "ccp": "CCP", "notional_mn": "Notional (€M)",
        "base_price": "Base Price", "stressed_price": "Stressed Price",
        "price_change_pct": "Price Chg (%)", "pnl_eur": "P&L (€)",
    })
    bond_detail["P&L (€)"] = bond_detail["P&L (€)"].apply(lambda x: f"{x:,.0f}")

    st.dataframe(bond_detail, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.caption(
        f"Portfolio: {len(portfolio_risk)} bonds · "
        f"Hedges: {len(data['swaps'])} swaps"
    )