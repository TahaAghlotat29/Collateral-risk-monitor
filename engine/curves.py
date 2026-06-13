"""
Yield curve utilities — discount factors, interpolation, bumped curves.

Takes the raw spot rates from ECB and converts them into discount
factors for bond pricing, with the ability to bump the curve
for DV01 and stress scenario calculations.
"""

import numpy as np
from config.settings import CURVE_TENORS, DV01_SHOCK_BPS


def interpolate_rate(curve, target_tenor):
    """
    Linear interpolation of the spot rate for a given tenor.

    Parameters
    ----------
    curve : dict
        {tenor_years: rate_pct} from the ECB OIS curve.
    target_tenor : float
        Maturity in years to interpolate.

    Returns
    -------
    float : interpolated spot rate in percent.
    """
    tenors = sorted(curve.keys())
    rates = [curve[t] for t in tenors]

    if target_tenor <= tenors[0]:
        return rates[0]
    if target_tenor >= tenors[-1]:
        return rates[-1]

    for i in range(len(tenors) - 1):
        if tenors[i] <= target_tenor <= tenors[i + 1]:
            weight = (target_tenor - tenors[i]) / (tenors[i + 1] - tenors[i])
            return rates[i] + weight * (rates[i + 1] - rates[i])

    return rates[-1]


def discount_factor(rate_pct, tenor_years):
    """
    Compute the discount factor from a spot rate.
    DF = 1 / (1 + r/100)^T
    """
    return 1.0 / (1.0 + rate_pct / 100.0) ** tenor_years


def build_discount_factors(curve):
    """
    Build a full set of discount factors from the spot curve.

    Returns a dict {tenor: discount_factor}.
    """
    dfs = {}
    for tenor in sorted(curve.keys()):
        dfs[tenor] = discount_factor(curve[tenor], tenor)
    return dfs


def bump_curve(curve, bump_bps, bucket=None):
    """
    Shift the curve by a given number of basis points.

    Parameters
    ----------
    curve : dict
        {tenor: rate_pct}
    bump_bps : float or dict
        If float: parallel shift applied to all tenors.
        If dict: {bucket_label: bps} for non-parallel scenarios.
    bucket : str, optional
        If provided with float bump_bps, only bump tenors in this bucket.

    Returns
    -------
    dict : bumped curve.
    """
    bumped = curve.copy()

    if isinstance(bump_bps, dict):
        # Non-parallel: map bucket labels to tenor ranges
        bucket_ranges = {
            "2Y": (0, 2.5),
            "5Y": (2.5, 7.5),
            "10Y": (7.5, 15),
            "30Y": (15, 50),
        }
        for tenor in bumped:
            for bkt, (lo, hi) in bucket_ranges.items():
                if lo <= tenor < hi and bkt in bump_bps:
                    bumped[tenor] += bump_bps[bkt] / 100.0
                    break
    else:
        # Parallel shift
        if bucket is not None:
            bucket_ranges = {
                "2Y": (0, 2.5),
                "5Y": (2.5, 7.5),
                "10Y": (7.5, 15),
                "30Y": (15, 50),
            }
            lo, hi = bucket_ranges.get(bucket, (0, 50))
            for tenor in bumped:
                if lo <= tenor < hi:
                    bumped[tenor] += bump_bps / 100.0
        else:
            for tenor in bumped:
                bumped[tenor] += bump_bps / 100.0

    return bumped