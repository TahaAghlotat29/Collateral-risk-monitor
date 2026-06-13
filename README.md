# Collateral Book Risk Monitor — DV01 Hedging & Margin Stress Simulation

A cleared derivatives desk posts billions of euros in sovereign bonds as collateral to CCPs (LCH, Eurex). This collateral generates interest rate risk that the desk does not want. A portfolio of €7.2B in Bunds, OATs, BTPs, and Bonos moves by roughly €5M for every basis point of yield curve shift. The desk hedges this exposure with IR swaps (pay fixed, receive €STR), but the hedge is never perfect. This project monitors the mismatch in real time, identifies which maturity buckets are over or under hedged, and simulates the P&L and margin call impact of arbitrary yield curve scenarios.

The EUR OIS curve is fetched daily from the ECB Statistical Data Warehouse (spot rates from 1Y to 30Y). Each bond in the collateral book is priced by discounting its cash flows against this curve, and the DV01 is computed by bumping the curve by 1 basis point and measuring the price change. Bunds dominate the book (64% of total DV01) because they carry the lowest CCP haircuts (1.5% at LCH vs 4% for BTPs). LCH holds 68% of the total exposure across 14 positions, Eurex the remaining 32% across 7 positions. The DV01 heatmap reveals a sharp concentration on the Bund 30Y bucket at €2M, roughly 40% of the entire book risk on a single point of the curve.

The hedge monitor compares collateral DV01 against swap DV01 bucket by bucket. A ratio of 1.0 means the swap perfectly offsets the collateral. The current book shows the 2Y bucket at 0.99 (essentially perfect), the 5Y at 1.06 (tolerable), the 10Y at 1.25 (over hedged by 25%), and the 30Y at 1.28 (over hedged by 28%). The 30Y alone accounts for €642k of residual DV01, roughly 70% of the total mismatch. The overall hedge ratio sits at 1.18 with an efficiency score of 82/100. The desk is implicitly net short rates: it profits when rates rise and loses when they fall, which is a directional position it does not intend to carry.

The stress engine reprices the entire book (bonds and swaps) under eight predefined scenarios and any custom combination of per bucket shifts via interactive sliders. A parallel +100 bps shock produces €469M of collateral losses, €589M of swap gains, and a net profit of +€120M (the over hedge working in the desk's favour) but triggers a €502M margin call from the CCPs. A bull flattening (short end down 10 bps, long end down 75 bps) produces a net loss of €50M, the worst scenario for this book because the over hedged 30Y bucket loses more on the swap side than the collateral gains. The margin call in that case is zero because the bonds have appreciated. The custom scenario builder lets the trader test any curve shape before adjusting positions.

The logical action from the dashboard is to reduce the 30Y swap notional by roughly 22% (about €260M) and the 10Y by roughly 20% (about €150M). This would bring all bucket ratios within a 0.95 to 1.05 band, push the efficiency score above 95, and eliminate the directional bias that currently exposes the book to bull flattening risk.

## Project structure

```text

collateral-risk-monitor/
├── config/
│   └── settings.py                # Curve tenors, CCP definitions, thresholds
├── data/
│   ├── sources/
│   │   ├── ecb_curves.py          # EUR OIS curve from ECB SDMX API
│   │   ├── bond_portfolio.py      # Collateral book per CCP
│   │   └── swap_hedges.py         # IR swap hedge portfolio
│   ├── downloads/                 # Local CSV cache
│   └── loader.py                  # Unified data assembler
├── engine/
│   ├── curves.py                  # Interpolation, discount factors, curve bumping
│   ├── risk.py                    # Bond pricing, DV01, modified duration
│   ├── hedge.py                   # Hedge ratio, residual risk, efficiency score
│   └── stress.py                  # Scenario simulation, margin call estimation
├── app/
│   ├── dashboard.py               # Streamlit entry point + navigation
│   └── sections/
│       ├── risk_overview.py       # DV01 by CCP, country, bucket, heatmap
│       ├── hedge_monitor.py       # Hedge ratio, residual, efficiency
│       └── stress_scenarios.py    # Custom builder, predefined scenarios, drill-down
└── tests/
└── test_risk.py

```


## Quick start

```bash
uv sync
uv run streamlit run app/dashboard.py
Live dashboard: https://collateral-risk-monitor-3amuqmdu53wgruejwfxjgg.streamlit.app/
```