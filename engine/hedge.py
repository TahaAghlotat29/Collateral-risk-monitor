"""
Hedge efficiency engine.

Compares collateral DV01 against swap hedge DV01 by maturity bucket.
Computes:
  - Hedge ratio per bucket (swap DV01 / collateral DV01)
  - Residual risk (unhedged DV01)
  - Hedge efficiency score
  - Alerts when residual exceeds threshold
"""

import pandas as pd
import numpy as np

from config.settings import (
    HEDGE_RATIO_TARGET,
    HEDGE_ALERT_THRESHOLD,
)


def compute_hedge_ratio(portfolio_risk, swaps):
    """
    Compare collateral DV01 vs swap DV01 by maturity bucket.

    Parameters
    ----------
    portfolio_risk : pd.DataFrame
        Collateral portfolio with dv01_eur and bucket columns.
    swaps : pd.DataFrame
        Swap hedges with dv01_eur and bucket columns.

    Returns
    -------
    pd.DataFrame with columns:
        bucket, collateral_dv01, swap_dv01, residual_dv01,
        hedge_ratio, is_alert
    """
    # Aggregate collateral DV01 by bucket
    coll_dv01 = (
        portfolio_risk
        .groupby("bucket")["dv01_eur"]
        .sum()
        .rename("collateral_dv01")
    )

    # Aggregate swap DV01 by bucket
    swap_dv01 = (
        swaps
        .groupby("bucket")["dv01_eur"]
        .sum()
        .rename("swap_dv01")
    )

    # Merge
    comparison = pd.concat([coll_dv01, swap_dv01], axis=1).fillna(0)

    # Residual = collateral - swap (positive = under-hedged, long risk)
    comparison["residual_dv01"] = comparison["collateral_dv01"] - comparison["swap_dv01"]

    # Hedge ratio = swap / collateral (1.0 = perfect)
    comparison["hedge_ratio"] = np.where(
        comparison["collateral_dv01"] != 0,
        comparison["swap_dv01"] / comparison["collateral_dv01"],
        0.0,
    )
    comparison["hedge_ratio"] = comparison["hedge_ratio"].round(4)

    # Alert flag: residual exceeds threshold
    gross_dv01 = comparison["collateral_dv01"].abs()
    residual_pct = np.where(
        gross_dv01 > 0,
        comparison["residual_dv01"].abs() / gross_dv01,
        0.0,
    )
    comparison["residual_pct"] = (residual_pct * 100).round(1)
    comparison["is_alert"] = residual_pct > HEDGE_ALERT_THRESHOLD

    comparison = comparison.reset_index()

    return comparison


def compute_total_hedge(hedge_table):
    """
    Compute aggregate hedge metrics across all buckets.

    Returns a dict with total collateral DV01, swap DV01,
    residual, overall hedge ratio, and alert status.
    """
    total_coll = hedge_table["collateral_dv01"].sum()
    total_swap = hedge_table["swap_dv01"].sum()
    total_residual = hedge_table["residual_dv01"].sum()

    overall_ratio = total_swap / total_coll if total_coll != 0 else 0.0

    residual_pct = abs(total_residual) / abs(total_coll) * 100 if total_coll != 0 else 0.0

    return {
        "total_collateral_dv01": round(total_coll, 0),
        "total_swap_dv01": round(total_swap, 0),
        "total_residual_dv01": round(total_residual, 0),
        "overall_hedge_ratio": round(overall_ratio, 4),
        "residual_pct": round(residual_pct, 1),
        "is_alert": residual_pct > HEDGE_ALERT_THRESHOLD * 100,
    }


def compute_hedge_by_ccp(portfolio_risk, swaps):
    """
    Hedge comparison at CCP level.

    The desk posts different collateral to different CCPs,
    but hedges with a single swap book. This shows which
    CCP has the most residual risk.
    """
    coll_by_ccp = (
        portfolio_risk
        .groupby("ccp")["dv01_eur"]
        .sum()
        .rename("collateral_dv01")
    )

    # Swaps are not CCP-specific, so we allocate proportionally
    total_swap_dv01 = swaps["dv01_eur"].sum()
    total_coll_dv01 = coll_by_ccp.sum()

    result = pd.DataFrame({"collateral_dv01": coll_by_ccp})

    if total_coll_dv01 != 0:
        result["swap_dv01_allocated"] = (
            result["collateral_dv01"] / total_coll_dv01 * total_swap_dv01
        ).round(0)
    else:
        result["swap_dv01_allocated"] = 0

    result["residual_dv01"] = result["collateral_dv01"] - result["swap_dv01_allocated"]
    result["residual_dv01"] = result["residual_dv01"].round(0)

    result = result.reset_index()

    return result


def hedge_efficiency_score(hedge_table):
    """
    Composite hedge efficiency score (0-100).

    100 = all buckets perfectly hedged (ratio = 1.0)
    0 = completely unhedged

    Score = weighted average of per-bucket efficiency,
    weighted by collateral DV01 (bigger buckets matter more).
    """
    df = hedge_table.copy()

    # Per-bucket efficiency: 100 * (1 - |ratio - 1|), floored at 0
    df["bucket_efficiency"] = (100 * (1 - (df["hedge_ratio"] - 1.0).abs())).clip(lower=0)

    # Weight by collateral DV01
    total_dv01 = df["collateral_dv01"].abs().sum()
    if total_dv01 == 0:
        return 0.0

    weighted = (df["bucket_efficiency"] * df["collateral_dv01"].abs()).sum()
    score = weighted / total_dv01

    return round(score, 1)