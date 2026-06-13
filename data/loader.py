"""
Unified data loader.

Fetches curve data, generates collateral portfolio and swap hedges,
and exposes one entry point for the rest of the project.
"""

import pandas as pd

from data.sources.ecb_curves import load_ois_curve, load_estr, get_latest_curve
from data.sources.bond_portfolio import load_portfolio, portfolio_summary
from data.sources.swap_hedges import generate_swap_hedges, swap_summary
from config.settings import DOWNLOADS_DIR


def load_all():
    """
    Fetch and assemble all data sources.

    Returns a dict with:
        curve       : DataFrame with full OIS curve history
        estr        : Series with €STR overnight rate
        latest_curve: dict {tenor: rate} for the most recent date
        portfolio   : DataFrame with collateral positions
        port_by_ccp, port_by_country, port_by_bucket : summary tables
        swaps       : DataFrame with IR swap hedges
        swap_by_bucket : summary table
    """
    # EUR OIS curve
    curve = load_ois_curve()
    estr = load_estr()
    latest_curve = get_latest_curve(curve)

    # Collateral portfolio
    portfolio = load_portfolio()
    by_ccp, by_country, by_bucket = portfolio_summary(portfolio)

    # Swap hedges (sized from portfolio)
    swaps = generate_swap_hedges(portfolio)
    swp_by_bucket = swap_summary(swaps)


    return {
        "curve": curve,
        "estr": estr,
        "latest_curve": latest_curve,
        "portfolio": portfolio,
        "port_by_ccp": by_ccp,
        "port_by_country": by_country,
        "port_by_bucket": by_bucket,
        "swaps": swaps,
        "swap_by_bucket": swp_by_bucket,
    }


