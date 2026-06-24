# Repository Structure

This document is the map of the repo: what every file is, how data flows
through the system, and the known gaps. Start here if you're new.

---

## Directory layout

```
Macro-Portfolio-Optimizer/
├── README.md                  Project overview + quick start
├── pyproject.toml             Package metadata + dependencies (pip install -e .)
├── requirements.txt           Dependency list (pip install -r ...)
│
├── src/macro_portfolio/       The Python package — ALL computing logic lives here
│   ├── paths.py               Resolves repo-root-relative paths for every script
│   ├── data.py               Pure CSV loaders (returns, factors, benchmark, fill log)
│   │
│   ├── pipelines/             ── Stage 1: data acquisition & cleaning ──
│   │   ├── data_pipeline.py           ETF prices -> monthly returns (the main input)
│   │   ├── pmi.py                      ISM Man + Non-Man -> Man / NonMan / Composite PMI
│   │   └── benchmark.py               60/40 ACWI/IGOV benchmark returns
│   │
│   ├── research/             ── Stage 2: curation, regressions, backtest ──
│   │   ├── curate.py                  Build the cleaned macro factor panel + derived factors
│   │   ├── regime.py                  Growth×inflation regime / quadrant labels
│   │   ├── regression.py             Univariate sweep: asset_ret ~ factor(t-lag)
│   │   ├── expected_returns.py       Macro-regression μ for the optimizer (+ train cutoff)
│   │   └── backtest.py               Walk-forward rolling re-optimization
│   │
│   ├── optimizer/             ── Stage 3: portfolio construction ──
│   │   ├── optimizer.py               Mean-variance optimizer at a target volatility
│   │   ├── methods.py                8-method library + ensemble (incl. inverse vol/var)
│   │   ├── advanced.py               Max-Sharpe with L2 + group bounds
│   │   ├── ips.py                    Investment Policy Statement constraints/compliance
│   │   └── plot_frontier.py           Efficient-frontier chart (constrained vs unconstrained)
│   │
│   ├── risk/                  covariance.py — sample + Ledoit-Wolf shrinkage
│   └── analysis/             intl_bond_splice.py — bond-splice proxy study
│
├── dashboard/                 Streamlit UI — THIN: imports from src, only loads + draws
│   ├── data_access.py        Cached wrappers over macro_portfolio.* (no logic here)
│   └── pages/                Each page = one view (Data, Macro, Optimizer, Ensemble, …)
│
├── data/                      Split by domain; each domain has raw inputs vs processed outputs
│   ├── macro_data/
│   │   ├── raw/               External / manually-pasted macro inputs (incl. pmi/ table dumps)
│   │   └── processed/         Pipeline-generated factor panel + pmi/ series
│   └── market_data/
│       ├── raw/               Raw price pulls
│       └── processed/         Returns, stats, benchmark (optimizer inputs)
│
├── outputs/                   Generated charts + analysis result tables
│
└── docs/                      Documentation, methodology notes, schema diagrams
```

---

## Data flow

```
                                 ┌─────────────────────────┐  market_data/raw/prices_raw.csv
   yfinance (ETF prices) ──────► │ pipelines/data_pipeline  │ ─► market_data/processed/returns_aligned.csv ─┐
                                 └─────────────────────────┘  market_data/processed/summary_stats.csv      │
                                                                                                           │
   macro_data/raw/pmi/PMI_US_Man ──┐                       ──► macro_data/processed/pmi/PMI_Manufacturing_US.csv
   macro_data/raw/pmi/PMI_US_NonMan┼─► pipelines/pmi.py ───►   macro_data/processed/pmi/PMI_NonManufacturing_US.csv
                                   │                        ──► macro_data/processed/pmi/PMI_Composite_US.csv │
                                                                                                           ▼
                                                              ┌──────────────────────────────────┐
                                                              │ optimizer/optimizer.py            │
   (expected returns: historical mean today; macro model later) │  reads returns_aligned.csv      │
                                                              │  -> optimal weights @ target vol  │
                                                              └──────────────────────────────────┘
                                                                            │
                                                                            ▼
                                                       optimizer/plot_frontier.py
                                                       -> outputs/efficient_frontier.png
```

The optimizer currently uses **historical-mean** expected returns as a
placeholder. The macro/PMI signal is wired in via
`PortfolioOptimizer.set_expected_returns({...})` — see the example block at the
bottom of `optimizer.py`. The PMI pipeline exists to feed that model.

---

## Files in `data/`

| File (under `data/`)                              | Produced by           | Description |
|---------------------------------------------------|-----------------------|-------------|
| `market_data/processed/returns_aligned.csv`       | data_pipeline         | ★ Main optimizer input: aligned monthly returns, no NaNs |
| `market_data/processed/summary_stats.csv`         | data_pipeline         | Annualized return / vol / Sharpe per asset (human-readable overview) |
| `market_data/processed/benchmark_returns.csv`     | benchmark             | 60/40 ACWI/IGOV monthly returns |
| `market_data/raw/prices_raw.csv`                  | data_pipeline         | Raw monthly adjusted-close prices |
| `macro_data/processed/macro_monthly.csv`          | curate                | Factor panel, 2002→present: cleaned levels + derived factors (inflation accel, excess div yield, log-VIX, PMI change) |
| `macro_data/processed/macro_fill_log.csv`         | curate                | One row per factor: source/derivation, missing %, fill action (incl. PENDING factors) |
| `macro_data/processed/pmi/PMI_Manufacturing_US.csv`    | pmi              | Manufacturing PMI (2002→present) |
| `macro_data/processed/pmi/PMI_NonManufacturing_US.csv` | pmi              | Non-Manufacturing PMI (2002→present) |
| `macro_data/processed/pmi/PMI_Composite_US.csv`        | pmi              | Weighted composite PMI (2002→present) |
| `macro_data/raw/us_macro_2002_2026.csv`           | **external / manual** | OECD/FRED macro panel (2002→2026-04), the curation source — see Known Gaps below |

### `data/macro_data/raw/pmi/` (PMI inputs, not generated)

| File              | Description |
|-------------------|-------------|
| `PMI_US_Man`      | Manual copy of investing.com ISM Manufacturing table (2002→present) |
| `PMI_US_NonMan`   | Manual copy of investing.com ISM Non-Manufacturing table (2002→present) |

Refresh procedure for the `.txt` files is documented in
[PMI_Data_Documentation.md](PMI_Data_Documentation.md).

---

## Files in `outputs/`

| File                          | Produced by         |
|-------------------------------|---------------------|
| `efficient_frontier.png`      | plot_frontier       |
| `splice_analysis_results.csv` | intl_bond_splice    |
| `splice_analysis_chart.png`   | intl_bond_splice    |

---

## Known gaps / TODOs

- **The macro panel (`us_macro_2002_2026.csv`) has no generating pipeline.** The
  OECD/FRED source is produced manually outside this repo; `curate.py` reads it,
  cleans it, and adds the derived factors. A `pipelines/macro_panel.py` to pull it
  reproducibly is still to be written. (`us_macro_2007_2026.csv` is the older,
  superseded source, kept for reference.)
- **Two factors still PENDING.** `HY_SPREAD_USA` (high-yield spread, to replace
  Baa−Aaa) and `EARNINGS_YIELD_PREMIUM` (S&P 500 E/P) aren't in any source yet —
  they're logged as PENDING in the fill log until sourced.
- **Non-US PMI coverage.** Only US PMI is implemented. The pipeline docstrings
  list Eurozone, developed-ex-US, and EM regions as planned but not yet built.
- **Macro model not yet wired in.** Expected returns are still the historical
  mean placeholder; the macro regression model output needs to be connected via
  `optimizer.set_expected_returns()`.
- **Box constraints (`MIN_WEIGHT`/`MAX_WEIGHT`) and `TARGET_VOL`** in
  `optimizer.py` are flagged as tunable — confirm final values with the sponsor.
