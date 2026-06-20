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
├── src/macro_portfolio/       The Python package (all source code lives here)
│   ├── paths.py               Resolves repo-root-relative paths for every script
│   │
│   ├── pipelines/             ── Stage 1: data acquisition & cleaning ──
│   │   ├── data_pipeline.py           ETF prices -> monthly returns (the main input)
│   │   └── pmi.py                      ISM Manufacturing + Non-Manufacturing -> Man / NonMan / Composite PMI
│   │
│   ├── optimizer/             ── Stage 2: portfolio construction ──
│   │   ├── optimizer.py               Mean-variance optimizer at a target volatility
│   │   └── plot_frontier.py           Efficient-frontier chart (constrained vs unconstrained)
│   │
│   └── analysis/              ── Stage 3: supporting research ──
│       └── intl_bond_splice.py        Bond-splice proxy study (why PFORX, not BWX)
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
                                                              market_data/processed/data_quality.csv       │
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
| `market_data/processed/returns_full.csv`          | data_pipeline         | All returns incl. early NaNs |
| `market_data/processed/summary_stats.csv`         | data_pipeline         | Annualized return / vol / Sharpe per asset |
| `market_data/processed/data_quality.csv`          | data_pipeline         | Coverage, gaps, splice metadata |
| `market_data/processed/benchmark_returns.csv`     | benchmark             | 60/40 ACWI/IGOV monthly returns |
| `market_data/raw/prices_raw.csv`                  | data_pipeline         | Raw monthly adjusted-close prices |
| `macro_data/processed/macro_monthly.csv`          | curate                | Cleaned, gap-filled monthly factor panel |
| `macro_data/processed/macro_fill_log.csv`         | curate                | Gap-filling log (one row per column) |
| `macro_data/processed/pmi/PMI_Manufacturing_US.csv`    | pmi              | Manufacturing PMI (2002→present) |
| `macro_data/processed/pmi/PMI_NonManufacturing_US.csv` | pmi              | Non-Manufacturing PMI (2002→present) |
| `macro_data/processed/pmi/PMI_Composite_US.csv`        | pmi              | Weighted composite PMI (2002→present) |
| `macro_data/raw/us_macro_2007_2026.csv`           | **external / manual** | OECD/FRED macro panel — see Known Gaps below |

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

- **`us_macro_2007_2026.csv` has no generating pipeline.** The OECD/FRED macro
  panel was produced manually or by code outside this repo. A
  `pipelines/macro_panel.py` to reproduce it reproducibly is still to be written.
- **Non-US PMI coverage.** Only US PMI is implemented. The pipeline docstrings
  list Eurozone, developed-ex-US, and EM regions as planned but not yet built.
- **Macro model not yet wired in.** Expected returns are still the historical
  mean placeholder; the macro regression model output needs to be connected via
  `optimizer.set_expected_returns()`.
- **Box constraints (`MIN_WEIGHT`/`MAX_WEIGHT`) and `TARGET_VOL`** in
  `optimizer.py` are flagged as tunable — confirm final values with the sponsor.
