"""
Risk Overview — DV01 exposure by CCP, country, and maturity bucket.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data.loader import load_all
from engine.risk import compute_portfolio_risk, aggregate_risk
from config.settings import CHART_PALETTE, COUNTRIES


@st.cache_data(show_spinner="Computing portfolio risk...")
def _load():
    data = load_all()
    portfolio_risk = compute_portfolio_risk(data["portfolio"], data["latest_curve"])
    by_ccp, by_country, by_bucket = aggregate_risk(portfolio_risk)
    return data, portfolio_risk, by_ccp, by_country, by_bucket


def render():
    data, portfolio_risk, by_ccp, by_country, by_bucket = _load()

    st.title("Risk Overview")
    st.markdown(
        "**DV01 exposure of the collateral book by CCP, country, and maturity bucket.**"
    )
    st.markdown("---")

    # KPIs
    total_notional = portfolio_risk["notional_mn"].sum()
    total_dv01 = portfolio_risk["dv01_eur"].sum()
    avg_duration = portfolio_risk["modified_duration"].mean()
    n_bonds = len(portfolio_risk)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Notional", f"€{total_notional:,.0f}M")
    col2.metric("Total DV01", f"€{total_dv01:,.0f}")
    col3.metric("Avg Duration", f"{avg_duration:.1f}Y")
    col4.metric("Positions", n_bonds)

    st.markdown("---")

    # DV01 by CCP
    st.subheader("DV01 by CCP")

    col1, col2 = st.columns(2)

    with col1:
        fig_ccp = go.Figure()
        fig_ccp.add_trace(go.Bar(
            x=by_ccp["ccp"],
            y=by_ccp["total_dv01"],
            marker=dict(
                color=[CHART_PALETTE.get(c, CHART_PALETTE["neutral"]) for c in by_ccp["ccp"]],
                line=dict(color="#1A1A1A", width=0.8),
            ),
            text=[f"€{v:,.0f}" for v in by_ccp["total_dv01"]],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>DV01: €%{y:,.0f}<extra></extra>",
        ))
        fig_ccp.update_layout(
            yaxis_title="DV01 (EUR)",
            height=350,
            margin=dict(t=20, b=20),
            showlegend=False,
        )
        st.plotly_chart(fig_ccp, use_container_width=True)

    with col2:
        fig_ccp_not = go.Figure()
        fig_ccp_not.add_trace(go.Bar(
            x=by_ccp["ccp"],
            y=by_ccp["notional_mn"],
            marker=dict(
                color=[CHART_PALETTE.get(c, CHART_PALETTE["neutral"]) for c in by_ccp["ccp"]],
                line=dict(color="#1A1A1A", width=0.8),
            ),
            text=[f"€{v:,.0f}M" for v in by_ccp["notional_mn"]],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Notional: €%{y:,.0f}M<extra></extra>",
        ))
        fig_ccp_not.update_layout(
            yaxis_title="Notional (EUR M)",
            height=350,
            margin=dict(t=20, b=20),
            showlegend=False,
        )
        st.plotly_chart(fig_ccp_not, use_container_width=True)

    st.markdown("---")

    # DV01 heatmap (bucket x country)
    st.subheader("DV01 heatmap (maturity bucket × country)")

    heatmap_data = (
        portfolio_risk
        .groupby(["bucket", "country"])["dv01_eur"]
        .sum()
        .unstack(fill_value=0)
    )

    # Ensure consistent order
    bucket_order = ["2Y", "5Y", "10Y", "30Y"]
    country_order = ["DE", "FR", "IT", "ES"]
    heatmap_data = heatmap_data.reindex(index=bucket_order, columns=country_order, fill_value=0)

    fig_heat = go.Figure(data=go.Heatmap(
        z=heatmap_data.values,
        x=[COUNTRIES[c]["issuer"] for c in heatmap_data.columns],
        y=heatmap_data.index,
        colorscale=[[0, "#F5F6F5"], [0.5, "#7FAF92"], [1, "#0F6644"]],
        text=[[f"€{v:,.0f}" for v in row] for row in heatmap_data.values],
        texttemplate="%{text}",
        hovertemplate="<b>%{y} %{x}</b><br>DV01: €%{z:,.0f}<extra></extra>",
    ))
    fig_heat.update_layout(
        height=350,
        margin=dict(t=20, b=20),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    st.markdown("---")

    # DV01 by country (stacked by CCP)
    st.subheader("DV01 by country")

    ccp_selector = st.selectbox("Filter by CCP", options=["All"] + list(by_ccp["ccp"]))

    if ccp_selector == "All":
        country_data = portfolio_risk.groupby("country")["dv01_eur"].sum().reset_index()
    else:
        country_data = (
            portfolio_risk[portfolio_risk["ccp"] == ccp_selector]
            .groupby("country")["dv01_eur"]
            .sum()
            .reset_index()
        )

    country_data["name"] = country_data["country"].map(lambda c: COUNTRIES[c]["issuer"])
    country_data = country_data.sort_values("dv01_eur", ascending=True)

    fig_country = go.Figure()
    fig_country.add_trace(go.Bar(
        x=country_data["dv01_eur"],
        y=country_data["name"],
        orientation="h",
        marker=dict(
            color=[CHART_PALETTE.get(c, CHART_PALETTE["neutral"]) for c in country_data["country"]],
            line=dict(color="#1A1A1A", width=0.8),
        ),
        text=[f"€{v:,.0f}" for v in country_data["dv01_eur"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>DV01: €%{x:,.0f}<extra></extra>",
    ))
    fig_country.update_layout(
        xaxis_title="DV01 (EUR)",
        height=300,
        margin=dict(t=20, b=20, l=20, r=60),
        showlegend=False,
    )
    st.plotly_chart(fig_country, use_container_width=True)

    st.markdown("---")

    # Position detail table
    st.subheader("Position detail")

    display = portfolio_risk[[
        "bond_id", "issuer", "country", "ccp", "bucket",
        "coupon_pct", "remaining_years", "notional_mn",
        "clean_price", "modified_duration", "dv01_eur",
    ]].sort_values("dv01_eur", ascending=False).copy()

    display = display.rename(columns={
        "bond_id": "Bond",
        "issuer": "Issuer",
        "country": "Country",
        "ccp": "CCP",
        "bucket": "Bucket",
        "coupon_pct": "Coupon (%)",
        "remaining_years": "Maturity (Y)",
        "notional_mn": "Notional (€M)",
        "clean_price": "Price",
        "modified_duration": "Mod Dur",
        "dv01_eur": "DV01 (€)",
    })

    display["DV01 (€)"] = display["DV01 (€)"].apply(lambda x: f"{x:,.0f}")

    st.dataframe(display, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Current curve
    st.subheader("EUR OIS curve ")

    curve = data["latest_curve"]
    tenors = sorted(curve.keys())
    rates = [curve[t] for t in tenors]

    fig_curve = go.Figure()
    fig_curve.add_trace(go.Scatter(
        x=[f"{t}Y" for t in tenors],
        y=rates,
        mode="lines+markers",
        line=dict(color=CHART_PALETTE["collateral"], width=2),
        marker=dict(size=6),
        hovertemplate="%{x}<br>%{y:.3f}%<extra></extra>",
    ))
    fig_curve.update_layout(
        yaxis_title="Rate (%)",
        height=300,
        margin=dict(t=20, b=20),
        showlegend=False,
    )
    st.plotly_chart(fig_curve, use_container_width=True)

    st.markdown("---")
    st.caption(
        f"Data sources: ECB Statistical Data Warehouse · "
        f"Portfolio: {n_bonds} positions, €{total_notional:,.0f}M notional"
    )