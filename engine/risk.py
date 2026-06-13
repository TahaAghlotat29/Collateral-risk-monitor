"""
Bond risk engine — pricing, DV01, and convexity.

For each bond in the collateral portfolio:
  - Compute clean price from discounted cash flows
  - Compute DV01 (price sensitivity to +1bp parallel shift)
  - Compute modified duration
  - Aggregate risk by CCP, country, and maturity bucket
"""

import pandas as pd
import numpy as np

from engine.curves import interpolate_rate, discount_factor, bump_curve
from config.settings import (
    COUPON_FREQUENCY,
    FACE_VALUE,
    DV01_SHOCK_BPS,
    MATURITY_BUCKETS,
)


def price_bond(coupon_pct, remaining_years, curve):
    """
    Price a bond from its cash flows and the spot curve.

    Generates annual coupon payments + final principal,
    discounts each flow at the interpolated spot rate.

    Parameters
    ----------
    coupon_pct : float
        Annual coupon in percent.
    remaining_years : float
        Time to maturity in years.
    curve : dict
        {tenor: rate_pct} spot curve.

    Returns
    -------
    float : clean price per 100 face value.
    """
    coupon = coupon_pct / 100.0 * FACE_VALUE

    # Generate cash flow schedule
    n_flows = max(1, int(np.ceil(remaining_years * COUPON_FREQUENCY)))
    times = []
    flows = []

    for i in range(1, n_flows + 1):
        t = remaining_years - (n_flows - i) / COUPON_FREQUENCY
        if t <= 0:
            continue
        times.append(t)
        if i == n_flows:
            flows.append(coupon + FACE_VALUE)
        else:
            flows.append(coupon)

    # Discount each flow
    price = 0.0
    for t, cf in zip(times, flows):
        rate = interpolate_rate(curve, t)
        df = discount_factor(rate, t)
        price += cf * df

    return price


def compute_bond_dv01(coupon_pct, remaining_years, curve):
    """
    DV01 per 100 face value: price change for a +1bp parallel shift.

    DV01 = P(base) - P(bumped)

    Convention: positive DV01 means the bond loses value when rates rise
    (which is always true for a fixed coupon bond).
    """
    price_base = price_bond(coupon_pct, remaining_years, curve)
    curve_up = bump_curve(curve, DV01_SHOCK_BPS)
    price_up = price_bond(coupon_pct, remaining_years, curve_up)

    dv01_per_100 = price_base - price_up

    return price_base, dv01_per_100


def compute_modified_duration(coupon_pct, remaining_years, curve):
    """
    Modified duration = DV01 / Price * 10000.
    Expressed in years.
    """
    price, dv01 = compute_bond_dv01(coupon_pct, remaining_years, curve)
    if price == 0:
        return 0.0
    mod_dur = (dv01 / price) * 10000
    return mod_dur


def compute_portfolio_risk(portfolio, curve):
    """
    Compute price, DV01, and duration for every bond in the portfolio.

    Returns the portfolio DataFrame enriched with:
        clean_price, dv01_per_100, dv01_eur, modified_duration
    """
    df = portfolio.copy()

    prices = []
    dv01s_per_100 = []
    dv01s_eur = []
    durations = []

    for _, bond in df.iterrows():
        price, dv01_100 = compute_bond_dv01(
            bond["coupon_pct"],
            bond["remaining_years"],
            curve,
        )

        # DV01 in EUR for the full position
        # notional_mn * 1e6 / 100 face * dv01_per_100
        dv01_position = dv01_100 * bond["notional_mn"] * 1e6 / FACE_VALUE

        mod_dur = compute_modified_duration(
            bond["coupon_pct"],
            bond["remaining_years"],
            curve,
        )

        prices.append(round(price, 4))
        dv01s_per_100.append(round(dv01_100, 6))
        dv01s_eur.append(round(dv01_position, 0))
        durations.append(round(mod_dur, 2))

    df["clean_price"] = prices
    df["dv01_per_100"] = dv01s_per_100
    df["dv01_eur"] = dv01s_eur
    df["modified_duration"] = durations

    return df


def aggregate_risk(portfolio_risk):
    """
    Aggregate DV01 by CCP, country, and maturity bucket.

    Returns three DataFrames for dashboard display.
    """
    by_ccp = (
        portfolio_risk
        .groupby("ccp")
        .agg(
            n_bonds=("bond_id", "count"),
            notional_mn=("notional_mn", "sum"),
            total_dv01=("dv01_eur", "sum"),
            avg_duration=("modified_duration", "mean"),
        )
        .round(1)
        .reset_index()
    )

    by_country = (
        portfolio_risk
        .groupby(["ccp", "country"])
        .agg(
            notional_mn=("notional_mn", "sum"),
            total_dv01=("dv01_eur", "sum"),
        )
        .round(0)
        .reset_index()
    )

    by_bucket = (
        portfolio_risk
        .groupby(["ccp", "bucket"])
        .agg(
            notional_mn=("notional_mn", "sum"),
            total_dv01=("dv01_eur", "sum"),
        )
        .round(0)
        .reset_index()
    )

    return by_ccp, by_country, by_bucket