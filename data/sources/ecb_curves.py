"""
Retrieve EUR OIS swap curve from ECB Statistical Data Warehouse.

The ECB publishes daily zero-coupon yield curves for the euro area.
We use the AAA-rated curve as OIS proxy, pulling spot rates at
standard tenors from 3M to 30Y.

These rates are used to:
  - Discount bond cash flows for clean price calculation
  - Compute DV01 (sensitivity to a 1bp parallel shift)
  - Price IR swap hedges
"""

import pandas as pd
import numpy as np
import requests
from io import StringIO

from config.settings import (
    ECB_BASE_URL,
    ESTR_SERIES,
    OIS_CURVE_KEY,
    CURVE_TENORS,
    DATA_START,
    DATA_END,
    DOWNLOADS_DIR,
)


def _fetch_ecb_series(series_key, label):
    """Pull a single time series from the ECB SDMX API."""
    url = f"{ECB_BASE_URL}/{series_key}"
    params = {
        "startPeriod": DATA_START.isoformat(),
        "endPeriod": DATA_END.isoformat(),
        "format": "csvdata",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    raw = pd.read_csv(StringIO(response.text))
    series = (
        raw[["TIME_PERIOD", "OBS_VALUE"]]
        .rename(columns={"TIME_PERIOD": "date", "OBS_VALUE": label})
        .assign(date=lambda df: pd.to_datetime(df["date"]))
        .set_index("date")
        [label]
        .astype(float)
        .sort_index()
    )
    return series


# ECB yield curve tenor codes
TENOR_CODES = {
    0.25: "SR_0.25Y",
    0.5: "SR_0.5Y",
    1: "SR_1Y",
    2: "SR_2Y",
    3: "SR_3Y",
    5: "SR_5Y",
    7: "SR_7Y",
    10: "SR_10Y",
    15: "SR_15Y",
    20: "SR_20Y",
    30: "SR_30Y",
}


def load_ois_curve():
    """
    Fetch the full EUR OIS curve (spot rates by tenor) from ECB.
    Returns a DataFrame with dates as index and tenors as columns.
    """
    print("[ecb_curves] Fetching EUR OIS curve...")

    frames = {}
    for tenor, code in TENOR_CODES.items():
        series_key = f"{OIS_CURVE_KEY}.{code}"
        label = f"ois_{tenor}y"
        try:
            s = _fetch_ecb_series(series_key, label)
            frames[label] = s
            print(f"  [curve] {tenor}Y: {len(s)} obs")
        except Exception as e:
            print(f"  [curve] {tenor}Y: FAILED ({e})")

    if not frames:
        print("[ecb_curves] No curve data, building flat fallback")
        return _build_fallback_curve()

    combined = pd.concat(frames.values(), axis=1).sort_index()
    combined = combined.resample("B").ffill()
    combined = combined.ffill().bfill()

    output_path = DOWNLOADS_DIR / "ois_curve.csv"
    combined.to_csv(output_path)
    print(f"[ecb_curves] Saved {len(combined)} rows -> {output_path}")

    return combined


def load_estr():
    """€STR overnight rate, in percent."""
    print("[ecb_curves] Fetching €STR...")
    try:
        estr = _fetch_ecb_series(ESTR_SERIES, "estr")
        print(f"  [estr] {len(estr)} obs")
        return estr
    except Exception as e:
        print(f"  [estr] FAILED ({e})")
        return pd.Series(dtype=float, name="estr")


def get_latest_curve(curve_df):
    """
    Extract the most recent curve as a dict {tenor_years: rate_pct}.
    This is what the risk engine uses for pricing.
    """
    latest = curve_df.iloc[-1]

    curve = {}
    for tenor in CURVE_TENORS:
        col = f"ois_{tenor}y"
        if col in latest.index and pd.notna(latest[col]):
            curve[tenor] = latest[col]

    return curve


def _build_fallback_curve():
    """
    Flat curve fallback at 2.5% if ECB API fails.
    Allows the pipeline to continue with degraded precision.
    """
    dates = pd.bdate_range(DATA_START, DATA_END)
    data = {}
    for tenor in CURVE_TENORS:
        data[f"ois_{tenor}y"] = 2.5
    fallback = pd.DataFrame(data, index=dates)
    fallback.index.name = "date"
    print("[ecb_curves] Built flat fallback curve at 2.5%")
    return fallback