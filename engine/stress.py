"""
Stress scenario engine.

Simulates the impact of yield curve shifts on:
  - Collateral P&L (bonds lose value when rates rise)
  - Swap hedge P&L (pay-fixed swaps gain when rates rise)
  - Net P&L (the residual that hits the desk)
  - Margin call estimation (CCP demands more collateral)

Scenarios range from mild parallel shifts to extreme
steepening/flattening events.
"""

import pandas as pd
import numpy as np

from engine.curves import bump_curve
from engine.risk import price_bond
from config.settings import (
    STRESS_SCENARIOS,
    CCP_HAIRCUTS,
    MARGIN_BUFFER_PCT,
    FACE_VALUE,
)


def stress_bond(bond, base_curve, stressed_curve):
    """
    Compute P&L on a single bond under a stressed curve.

    P&L = (stressed_price - base_price) / 100 * notional
    Negative P&L means the bond lost value (rates went up).
    """
    base_price = price_bond(
        bond["coupon_pct"], bond["remaining_years"], base_curve,
    )
    stressed_price = price_bond(
        bond["coupon_pct"], bond["remaining_years"], stressed_curve,
    )

    price_change = stressed_price - base_price
    pnl = price_change / FACE_VALUE * bond["notional_mn"] * 1e6

    return {
        "base_price": round(base_price, 4),
        "stressed_price": round(stressed_price, 4),
        "price_change_pct": round(price_change / base_price * 100, 3),
        "pnl_eur": round(pnl, 0),
    }


def stress_swap(swap, scenario_bps):
    """
    Approximate P&L on an IR swap under a rate scenario.

    For a pay-fixed swap, when rates rise the swap gains value
    because the fixed leg becomes cheaper relative to the
    floating leg. Approximate P&L = DV01 * shift in bps.

    The shift used is the one matching the swap's bucket.
    """
    bucket = swap["bucket"]

    if isinstance(scenario_bps, dict):
        shift = scenario_bps.get(bucket, 0)
    else:
        shift = scenario_bps

    pnl = swap["dv01_eur"] * shift

    return {
        "shift_bps": shift,
        "pnl_eur": round(pnl, 0),
    }


def run_scenario(portfolio_risk, swaps, base_curve, scenario_name):
    """
    Run a full stress scenario on the collateral book and swap hedges.

    Parameters
    ----------
    portfolio_risk : pd.DataFrame
        Collateral portfolio with risk metrics.
    swaps : pd.DataFrame
        IR swap hedges.
    base_curve : dict
        Current OIS curve {tenor: rate_pct}.
    scenario_name : str
        Key from STRESS_SCENARIOS.

    Returns
    -------
    dict with:
        scenario, bumps,
        bond_results (DataFrame), swap_results (DataFrame),
        collateral_pnl, swap_pnl, net_pnl,
        pnl_by_ccp, pnl_by_bucket, margin_impact
    """
    bumps = STRESS_SCENARIOS[scenario_name]
    stressed_curve = bump_curve(base_curve, bumps)

    # Bond P&L
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

    # Swap P&L
    swap_results = []
    for _, swap in swaps.iterrows():
        result = stress_swap(swap, bumps)
        result["swap_id"] = swap["swap_id"]
        result["bucket"] = swap["bucket"]
        result["notional_mn"] = swap["notional_mn"]
        swap_results.append(result)

    swap_df = pd.DataFrame(swap_results)
    total_swap_pnl = swap_df["pnl_eur"].sum()

    net_pnl = total_bond_pnl + total_swap_pnl

    # P&L by CCP
    pnl_by_ccp = (
        bond_df
        .groupby("ccp")["pnl_eur"]
        .sum()
        .round(0)
        .reset_index()
        .rename(columns={"pnl_eur": "collateral_pnl"})
    )

    # P&L by bucket (bonds + swaps)
    bond_by_bucket = bond_df.groupby("bucket")["pnl_eur"].sum().rename("bond_pnl")
    swap_by_bucket = swap_df.groupby("bucket")["pnl_eur"].sum().rename("swap_pnl")

    pnl_by_bucket = pd.concat([bond_by_bucket, swap_by_bucket], axis=1).fillna(0)
    pnl_by_bucket["net_pnl"] = pnl_by_bucket["bond_pnl"] + pnl_by_bucket["swap_pnl"]
    pnl_by_bucket = pnl_by_bucket.round(0).reset_index()

    # Margin impact estimation
    margin_impact = estimate_margin_call(bond_df, portfolio_risk)

    return {
        "scenario": scenario_name,
        "bumps": bumps,
        "bond_results": bond_df,
        "swap_results": swap_df,
        "collateral_pnl": round(total_bond_pnl, 0),
        "swap_pnl": round(total_swap_pnl, 0),
        "net_pnl": round(net_pnl, 0),
        "pnl_by_ccp": pnl_by_ccp,
        "pnl_by_bucket": pnl_by_bucket,
        "margin_impact": margin_impact,
    }


def estimate_margin_call(bond_results, portfolio_risk):
    """
    Estimate additional margin required under stress.

    When bond prices drop, the collateral value falls below
    the required margin. The CCP demands the difference plus
    a buffer.

    Additional margin = sum of (price_drop * notional * haircut_factor)
    """
    df = bond_results.merge(
        portfolio_risk[["bond_id", "haircut_pct"]],
        on="bond_id",
        how="left",
    )

    # Price drop reduces collateral value
    df["value_loss"] = -df["pnl_eur"]  # positive when bonds lose value

    # Additional margin = value loss * (1 + haircut adjustment)
    # When prices drop, CCPs may increase haircuts
    df["margin_call"] = df["value_loss"] * (1 + df["haircut_pct"] / 100)

    # Only count positive margin calls (when bonds lose value)
    df["margin_call"] = df["margin_call"].clip(lower=0)

    total_margin_call = df["margin_call"].sum()

    # Add buffer
    buffer = total_margin_call * MARGIN_BUFFER_PCT / 100
    total_with_buffer = total_margin_call + buffer

    by_ccp = (
        df
        .groupby("ccp")["margin_call"]
        .sum()
        .round(0)
        .reset_index()
    )

    return {
        "total_margin_call": round(total_margin_call, 0),
        "buffer": round(buffer, 0),
        "total_with_buffer": round(total_with_buffer, 0),
        "by_ccp": by_ccp,
    }


def run_all_scenarios(portfolio_risk, swaps, base_curve):
    """
    Run every predefined stress scenario and return a summary table.
    """
    results = []

    for name in STRESS_SCENARIOS:
        outcome = run_scenario(portfolio_risk, swaps, base_curve, name)
        results.append({
            "scenario": name,
            "collateral_pnl": outcome["collateral_pnl"],
            "swap_pnl": outcome["swap_pnl"],
            "net_pnl": outcome["net_pnl"],
            "margin_call": outcome["margin_impact"]["total_with_buffer"],
        })

    summary = pd.DataFrame(results)

    return summary