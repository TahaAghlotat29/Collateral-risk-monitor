"""
Hedge Monitor — DV01 collateral vs swap comparison and residual tracking.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data.loader import load_all
from engine.risk import compute_portfolio_risk
from engine.hedge import (
    compute_hedge_ratio,
    compute_total_hedge,
    compute_hedge_by_ccp,
    hedge_efficiency_score,
)
from config.settings import CHART_PALETTE


@st.cache_data(show_spinner="Analysing hedge efficiency...")
def _load():
    data = load_all()
    portfolio_risk = compute_portfolio_risk(data["portfolio"], data["latest_curve"])
    hedge_table = compute_hedge_ratio(portfolio_risk, data["swaps"])
    total_hedge = compute_total_hedge(hedge_table)
    hedge_ccp = compute_hedge_by_ccp(portfolio_risk, data["swaps"])
    efficiency = hedge_efficiency_score(hedge_table)
    return data, portfolio_risk, hedge_table, total_hedge, hedge_ccp, efficiency


def render():
    data, portfolio_risk, hedge_table, total_hedge, hedge_ccp, efficiency = _load()

    st.title("Hedge Monitor")
    st.markdown(
        "**Collateral DV01 vs IR swap hedge comparison by maturity bucket.**"
    )
    st.markdown("---")

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Hedge Efficiency", f"{efficiency:.0f} / 100")
    col2.metric(
        "Overall Hedge Ratio",
        f"{total_hedge['overall_hedge_ratio']:.2f}",
    )
    col3.metric(
        "Residual DV01",
        f"€{total_hedge['total_residual_dv01']:,.0f}",
        delta=f"{total_hedge['residual_pct']:.1f}% of gross",
        delta_color="inverse",
    )
    col4.metric(
        "Status",
        "ALERT" if total_hedge["is_alert"] else "OK",
    )

    st.markdown("---")

    # DV01 comparison by bucket  grouped bar chart
    st.subheader("DV01 by maturity bucket (collateral vs swap)")

    bucket_order = ["2Y", "5Y", "10Y", "30Y"]
    ht = hedge_table.set_index("bucket").reindex(bucket_order).reset_index()

    fig_compare = go.Figure()

    fig_compare.add_trace(go.Bar(
        x=ht["bucket"],
        y=ht["collateral_dv01"],
        name="Collateral DV01",
        marker=dict(color=CHART_PALETTE["collateral"], line=dict(color="#1A1A1A", width=0.8)),
        hovertemplate="<b>%{x}</b><br>Collateral: €%{y:,.0f}<extra></extra>",
    ))

    fig_compare.add_trace(go.Bar(
        x=ht["bucket"],
        y=ht["swap_dv01"],
        name="Swap DV01",
        marker=dict(color=CHART_PALETTE["swap"], line=dict(color="#1A1A1A", width=0.8)),
        hovertemplate="<b>%{x}</b><br>Swap: €%{y:,.0f}<extra></extra>",
    ))

    fig_compare.update_layout(
        barmode="group",
        yaxis_title="DV01 (EUR)",
        height=400,
        margin=dict(t=20, b=20),
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_compare, use_container_width=True)

    st.markdown("---")

    st.subheader("Residual DV01 by bucket")
    st.caption(
        "Positive = under-hedged (long rates risk). "
        "Negative = over-hedged (short rates risk)."
    )

    colors = [
        CHART_PALETTE["negative"] if r > 0 else CHART_PALETTE["collateral"]
        for r in ht["residual_dv01"]
    ]

    fig_residual = go.Figure()
    fig_residual.add_trace(go.Bar(
        x=ht["bucket"],
        y=ht["residual_dv01"],
        marker=dict(color=colors, line=dict(color="#1A1A1A", width=0.8)),
        text=[f"€{v:,.0f}" for v in ht["residual_dv01"]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Residual: €%{y:,.0f}<extra></extra>",
    ))
    fig_residual.add_hline(
        y=0, line=dict(color="#1A1A1A", width=1, dash="dash"),
    )
    fig_residual.update_layout(
        yaxis_title="Residual DV01 (EUR)",
        height=350,
        margin=dict(t=20, b=20),
        showlegend=False,
    )
    st.plotly_chart(fig_residual, use_container_width=True)

    st.markdown("---")

    # Hedge ratio by bucket
    st.subheader("Hedge ratio by bucket")
    st.caption(
        "1.0 = perfectly hedged. Below 1.0 = under-hedged. Above 1.0 = over-hedged."
    )

    ratio_colors = []
    for r in ht["hedge_ratio"]:
        if abs(r - 1.0) < 0.05:
            ratio_colors.append(CHART_PALETTE["collateral"])
        elif r < 1.0:
            ratio_colors.append(CHART_PALETTE["negative"])
        else:
            ratio_colors.append(CHART_PALETTE["residual"])

    fig_ratio = go.Figure()
    fig_ratio.add_trace(go.Bar(
        x=ht["bucket"],
        y=ht["hedge_ratio"],
        marker=dict(color=ratio_colors, line=dict(color="#1A1A1A", width=0.8)),
        text=[f"{v:.2f}" for v in ht["hedge_ratio"]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Ratio: %{y:.3f}<extra></extra>",
    ))
    fig_ratio.add_hline(
        y=1.0, line=dict(color="#1A1A1A", width=1.5, dash="dash"),
        annotation_text="Target (1.0)",
        annotation_position="top right",
    )
    fig_ratio.update_layout(
        yaxis_title="Hedge ratio",
        yaxis=dict(range=[0, max(1.5, ht["hedge_ratio"].max() * 1.2)]),
        height=350,
        margin=dict(t=20, b=20),
        showlegend=False,
    )
    st.plotly_chart(fig_ratio, use_container_width=True)

    st.markdown("---")

    # Hedge by CCP
    st.subheader("Residual by CCP")
    st.caption(
        "Swap DV01 is allocated proportionally to collateral per CCP."
    )

    fig_ccp = go.Figure()

    fig_ccp.add_trace(go.Bar(
        x=hedge_ccp["ccp"],
        y=hedge_ccp["collateral_dv01"],
        name="Collateral DV01",
        marker=dict(color=CHART_PALETTE["collateral"]),
    ))

    fig_ccp.add_trace(go.Bar(
        x=hedge_ccp["ccp"],
        y=hedge_ccp["swap_dv01_allocated"],
        name="Swap DV01 (allocated)",
        marker=dict(color=CHART_PALETTE["swap"]),
    ))

    fig_ccp.update_layout(
        barmode="group",
        yaxis_title="DV01 (EUR)",
        height=350,
        margin=dict(t=20, b=20),
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_ccp, use_container_width=True)

    st.markdown("---")

    # Detail table
    st.subheader("Hedge detail by bucket")

    display = hedge_table[[
        "bucket", "collateral_dv01", "swap_dv01",
        "residual_dv01", "hedge_ratio", "residual_pct", "is_alert",
    ]].copy()

    display = display.rename(columns={
        "bucket": "Bucket",
        "collateral_dv01": "Collateral DV01 (€)",
        "swap_dv01": "Swap DV01 (€)",
        "residual_dv01": "Residual DV01 (€)",
        "hedge_ratio": "Hedge Ratio",
        "residual_pct": "Residual (%)",
        "is_alert": "Alert",
    })

    for col in ["Collateral DV01 (€)", "Swap DV01 (€)", "Residual DV01 (€)"]:
        display[col] = display[col].apply(lambda x: f"{x:,.0f}")

    st.dataframe(display, use_container_width=True, hide_index=True)

    # Swap portfolio table
    st.markdown("---")
    st.subheader("IR swap hedge portfolio")

    swap_display = data["swaps"][[
        "swap_id", "bucket", "direction", "maturity_years",
        "notional_mn", "fixed_rate_pct", "dv01_eur",
    ]].copy()

    swap_display = swap_display.rename(columns={
        "swap_id": "Swap",
        "bucket": "Bucket",
        "direction": "Direction",
        "maturity_years": "Maturity (Y)",
        "notional_mn": "Notional (€M)",
        "fixed_rate_pct": "Fixed Rate (%)",
        "dv01_eur": "DV01 (€)",
    })

    swap_display["Notional (€M)"] = swap_display["Notional (€M)"].apply(lambda x: f"{x:,.1f}")
    swap_display["DV01 (€)"] = swap_display["DV01 (€)"].apply(lambda x: f"{x:,.0f}")

    st.dataframe(swap_display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.caption(
        f"Portfolio: {len(portfolio_risk)} bonds · "
        f"Hedges: {len(data['swaps'])} swaps · "
        f"Efficiency score: {efficiency:.0f}/100"
    )