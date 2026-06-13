"""
Project-wide settings: curve tenors, CCP definitions, stress scenarios, thresholds.
"""

from pathlib import Path
from datetime import date

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = ROOT_DIR / "data" / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Date range
DATA_START = date(2019, 10, 1)    # €STR inception
DATA_END = date.today()

# ECB SDMX API
ECB_BASE_URL = "https://data-api.ecb.europa.eu/service/data"

# EUR OIS curve tenors (years) and corresponding ECB yield curve keys
CURVE_TENORS = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]

# €STR (overnight anchor)
ESTR_SERIES = "EST/B.EU000A2X2A25.WT"

# EUR AAA yield curve from ECB (proxy for OIS)
OIS_CURVE_KEY = "YC/B.U2.EUR.4F.G_N_A.SV_C_YM"

# CCPs
CCPS = ["LCH", "Eurex"]

# Countries and their sovereign issuers
COUNTRIES = {
    "DE": {"name": "Germany", "issuer": "Bund"},
    "FR": {"name": "France", "issuer": "OAT"},
    "IT": {"name": "Italy", "issuer": "BTP"},
    "ES": {"name": "Spain", "issuer": "Bonos"},
}

# Maturity buckets for DV01 reporting
MATURITY_BUCKETS = {
    "2Y": (0, 2.5),
    "5Y": (2.5, 7.5),
    "10Y": (7.5, 15),
    "30Y": (15, 50),
}

# Bond coupon conventions
COUPON_FREQUENCY = 1          # annual for EUR sovereigns
DAY_COUNT = 365.25
FACE_VALUE = 100

# DV01 shock size
DV01_SHOCK_BPS = 1

# Hedge efficiency thresholds
HEDGE_RATIO_TARGET = 1.0      # perfect hedge
HEDGE_ALERT_THRESHOLD = 0.10  # alert if residual > 10% of gross DV01

# Stress scenarios (parallel shift in bps)
STRESS_SCENARIOS = {
    "Parallel +25 bps": {"2Y": 25, "5Y": 25, "10Y": 25, "30Y": 25},
    "Parallel +50 bps": {"2Y": 50, "5Y": 50, "10Y": 50, "30Y": 50},
    "Parallel +100 bps": {"2Y": 100, "5Y": 100, "10Y": 100, "30Y": 100},
    "Parallel -50 bps": {"2Y": -50, "5Y": -50, "10Y": -50, "30Y": -50},
    "Bear steepening": {"2Y": 10, "5Y": 25, "10Y": 50, "30Y": 75},
    "Bear flattening": {"2Y": 75, "5Y": 50, "10Y": 25, "30Y": 10},
    "Bull steepening": {"2Y": -75, "5Y": -50, "10Y": -25, "30Y": -10},
    "Bull flattening": {"2Y": -10, "5Y": -25, "10Y": -50, "30Y": -75},
}

# CCP haircuts by country (approximate, in %)
CCP_HAIRCUTS = {
    "LCH": {"DE": 1.5, "FR": 2.0, "IT": 4.0, "ES": 3.5},
    "Eurex": {"DE": 1.0, "FR": 1.8, "IT": 3.5, "ES": 3.0},
}

# Margin buffer (additional margin above minimum, in %)
MARGIN_BUFFER_PCT = 5.0

CHART_PALETTE = {
    "DE": "#1A1A1A",
    "FR": "#0F6644",
    "IT": "#B22222",
    "ES": "#D97706",
    "LCH": "#0F6644",
    "Eurex": "#1A1A1A",
    "collateral": "#0F6644",
    "swap": "#B22222",
    "residual": "#D97706",
    "neutral": "#6B7280",
    "positive": "#0F6644",
    "negative": "#B22222",
}