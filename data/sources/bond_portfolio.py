"""
Simulated collateral book posted to CCPs.

In production, this comes from the desk's position management system.
Here we generate a realistic portfolio of EUR sovereign bonds
allocated across LCH and Eurex, with varying maturities, coupons,
and notional amounts.

The portfolio reflects CCM desk behavior:
  - Bunds dominate (lowest haircut, most accepted)
  - OATs as secondary collateral
  - BTPs and Bonos in smaller size (higher haircuts)
  - Mix of maturities across 2Y to 30Y
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta

from config.settings import (
    COUNTRIES,
    CCPS,
    CCP_HAIRCUTS,
    DOWNLOADS_DIR,
)


def _generate_bonds(seed=42):
    """
    Generate a realistic set of sovereign bonds with
    ISIN-like identifiers, coupons, maturities, and notionals.
    """
    rng = np.random.RandomState(seed)

    bonds = []
    bond_id = 1

    # Allocation weights: Bund heavy, periphery light
    country_weights = {
        "DE": {"n_bonds": 8, "notional_range": (200, 800)},
        "FR": {"n_bonds": 6, "notional_range": (150, 500)},
        "IT": {"n_bonds": 4, "notional_range": (100, 300)},
        "ES": {"n_bonds": 3, "notional_range": (80, 250)},
    }

    # Maturity dates spread across the curve
    maturity_years = [2, 3, 5, 7, 10, 15, 20, 30]
    today = date.today()

    for country, params in country_weights.items():
        issuer = COUNTRIES[country]["issuer"]

        for i in range(params["n_bonds"]):
            # Pick a maturity
            mat_years = rng.choice(maturity_years)
            maturity_date = today + timedelta(days=int(mat_years * 365.25))

            # Realistic coupon based on vintage
            # Recent issuance = low coupon, older = higher
            if mat_years <= 3:
                coupon = round(rng.uniform(0.0, 1.5), 3)
            elif mat_years <= 10:
                coupon = round(rng.uniform(0.5, 3.0), 3)
            else:
                coupon = round(rng.uniform(1.0, 3.5), 3)

            # Notional in EUR millions
            notional_mn = rng.randint(
                params["notional_range"][0],
                params["notional_range"][1],
            )

            # Assign to CCP (LCH gets more, Eurex less)
            ccp = rng.choice(CCPS, p=[0.6, 0.4])

            # Approximate remaining maturity
            remaining_years = round(mat_years + rng.uniform(-0.5, 0.5), 2)
            remaining_years = max(0.5, remaining_years)

            bonds.append({
                "bond_id": f"BOND_{bond_id:03d}",
                "country": country,
                "issuer": issuer,
                "coupon_pct": coupon,
                "maturity_date": maturity_date.isoformat(),
                "remaining_years": remaining_years,
                "notional_mn": notional_mn,
                "ccp": ccp,
                "haircut_pct": CCP_HAIRCUTS[ccp][country],
            })

            bond_id += 1

    return pd.DataFrame(bonds)


def load_portfolio():
    """
    Load the collateral portfolio.
    Returns a DataFrame with one row per bond position.
    """
    portfolio = _generate_bonds()

    # Compute net collateral value after haircut
    portfolio["collateral_value_mn"] = (
        portfolio["notional_mn"] * (1 - portfolio["haircut_pct"] / 100)
    ).round(2)

    # Assign maturity bucket
    def _bucket(years):
        if years <= 2.5:
            return "2Y"
        elif years <= 7.5:
            return "5Y"
        elif years <= 15:
            return "10Y"
        return "30Y"

    portfolio["bucket"] = portfolio["remaining_years"].apply(_bucket)

    output_path = DOWNLOADS_DIR / "collateral_portfolio.csv"
    portfolio.to_csv(output_path, index=False)
    print(f"[portfolio] Saved {len(portfolio)} positions -> {output_path}")

    # Summary stats
    total_notional = portfolio["notional_mn"].sum()
    total_collateral = portfolio["collateral_value_mn"].sum()
    print(f"[portfolio] Total notional: €{total_notional:,.0f}M")
    print(f"[portfolio] Total collateral value: €{total_collateral:,.0f}M")

    return portfolio


def portfolio_summary(portfolio):
    """
    Aggregate portfolio by CCP, country, and bucket.
    Returns three summary DataFrames.
    """
    by_ccp = (
        portfolio
        .groupby("ccp")
        .agg(
            n_bonds=("bond_id", "count"),
            notional_mn=("notional_mn", "sum"),
            collateral_mn=("collateral_value_mn", "sum"),
        )
        .round(1)
        .reset_index()
    )

    by_country = (
        portfolio
        .groupby(["ccp", "country"])
        .agg(
            n_bonds=("bond_id", "count"),
            notional_mn=("notional_mn", "sum"),
        )
        .round(1)
        .reset_index()
    )

    by_bucket = (
        portfolio
        .groupby(["ccp", "bucket"])
        .agg(
            n_bonds=("bond_id", "count"),
            notional_mn=("notional_mn", "sum"),
        )
        .round(1)
        .reset_index()
    )

    return by_ccp, by_country, by_bucket