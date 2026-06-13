"""
Simulated IR swap hedge portfolio.

In production, this comes from the desk's booking system.
Here we generate a set of EUR IR swaps (pay fixed, receive €STR)
designed to offset the DV01 of the collateral book.

The hedges are intentionally imperfect:
  - Some buckets are slightly over-hedged
  - Some are slightly under-hedged
  - This creates realistic residual risk for the monitor to track
"""

import pandas as pd
import numpy as np

from config.settings import (
    MATURITY_BUCKETS,
    DOWNLOADS_DIR,
)


def _approximate_swap_dv01_per_mn(maturity_years):
    """
    Approximate DV01 per €1M notional for a par swap.
    Rule of thumb: DV01 ~ maturity * 0.01% * notional.
    A 10Y swap on €1M has DV01 ~ €1,000 (10 * 100).
    """
    return maturity_years * 100  # EUR per 1M notional per 1bp


def generate_swap_hedges(portfolio, seed=42):
    """
    Generate IR swap hedges that approximately offset the
    DV01 of the collateral portfolio by maturity bucket.

    Each swap is:
      - Pay fixed / receive €STR (standard EUR OIS swap)
      - Maturity matching the collateral bucket midpoint
      - Notional sized to offset ~90-110% of bucket DV01

    Parameters
    ----------
    portfolio : pd.DataFrame
        Collateral portfolio with columns: notional_mn, remaining_years, bucket.
    """
    rng = np.random.RandomState(seed)

    # Estimate collateral DV01 per bucket
    # Approximate bond DV01: modified duration ~ remaining_years * 0.95
    portfolio_dv01 = portfolio.copy()
    portfolio_dv01["bond_dv01_per_mn"] = portfolio_dv01["remaining_years"] * 95  # EUR per 1M per 1bp
    portfolio_dv01["bond_dv01"] = portfolio_dv01["bond_dv01_per_mn"] * portfolio_dv01["notional_mn"]

    bucket_dv01 = (
        portfolio_dv01
        .groupby("bucket")["bond_dv01"]
        .sum()
        .to_dict()
    )

    # Bucket midpoint maturities for swap tenor
    bucket_maturities = {
        "2Y": 2,
        "5Y": 5,
        "10Y": 10,
        "30Y": 25,
    }

    swaps = []
    swap_id = 1

    for bucket, target_dv01 in bucket_dv01.items():
        if target_dv01 == 0:
            continue

        swap_maturity = bucket_maturities.get(bucket, 5)
        dv01_per_mn = _approximate_swap_dv01_per_mn(swap_maturity)

        # Target notional to offset collateral DV01
        # Add intentional mismatch: 85% to 115% of perfect hedge
        hedge_ratio = rng.uniform(0.85, 1.15)
        target_notional = (target_dv01 * hedge_ratio) / dv01_per_mn

        # Split into 1-3 swaps per bucket (realistic, desk doesn't do one giant swap)
        n_swaps = rng.randint(1, 4)
        notionals = np.array([rng.uniform(0.3, 0.7) for _ in range(n_swaps)])
        notionals = notionals / notionals.sum() * target_notional

        for i in range(n_swaps):
            # Fixed rate: approximate par swap rate from bucket
            par_rate = {
                "2Y": rng.uniform(2.2, 2.8),
                "5Y": rng.uniform(2.4, 3.0),
                "10Y": rng.uniform(2.6, 3.2),
                "30Y": rng.uniform(2.8, 3.4),
            }.get(bucket, 2.5)

            swap_notional = round(notionals[i], 1)
            swap_dv01 = round(dv01_per_mn * swap_notional, 0)

            swaps.append({
                "swap_id": f"SWAP_{swap_id:03d}",
                "bucket": bucket,
                "direction": "pay_fixed",
                "maturity_years": swap_maturity,
                "notional_mn": swap_notional,
                "fixed_rate_pct": round(par_rate, 3),
                "dv01_eur": swap_dv01,
            })

            swap_id += 1

    result = pd.DataFrame(swaps)

    output_path = DOWNLOADS_DIR / "swap_hedges.csv"
    result.to_csv(output_path, index=False)
    print(f"[swaps] Saved {len(result)} swaps -> {output_path}")

    total_notional = result["notional_mn"].sum()
    total_dv01 = result["dv01_eur"].sum()
    print(f"[swaps] Total notional: €{total_notional:,.0f}M")
    print(f"[swaps] Total DV01: €{total_dv01:,.0f}")

    return result


def swap_summary(swaps):
    """
    Aggregate swap portfolio by bucket.
    """
    summary = (
        swaps
        .groupby("bucket")
        .agg(
            n_swaps=("swap_id", "count"),
            notional_mn=("notional_mn", "sum"),
            total_dv01=("dv01_eur", "sum"),
            avg_rate=("fixed_rate_pct", "mean"),
        )
        .round(1)
        .reset_index()
    )

    return summary