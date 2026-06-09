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
│   │   ├── pmi_manufacturing.py       ISM Manufacturing PMI       -> PMI_US
│   │   ├── pmi_nonmanufacturing.py    ISM Non-Manufacturing PMI   -> PMI_NM_US
│   │   └── pmi_composite.py           Weighted composite of the two -> PMI_Composite_US
│   │
│   ├── optimizer/             ── Stage 2: portfolio construction ──
│   │   ├── optimizer.py               Mean-variance optimizer at a target volatility
│   │   └── plot_frontier.py           Efficient-frontier chart (constrained vs unconstrained)
│   │
│   └── analysis/              ── Stage 3: supporting research ──
│       └── intl_bond_splice.py        Bond-splice proxy study (why PFORX, not BWX)
│
├── data/                      Cleaned CSV outputs from the pipelines
│   └── raw/                   Raw, manually-acquired inputs (do not edit by hand except to refresh)
│
├── outputs/                   Generated charts + analysis result tables
│
└── docs/                      Documentation, methodology notes, schema diagrams
```

---

## Data flow

```
                                 ┌─────────────────────────┐
   yfinance (ETF prices) ──────► │ pipelines/data_pipeline  │ ──► data/returns_aligned.csv ─┐
                                 └─────────────────────────┘     data/prices_raw.csv        │
                                                                 data/summary_stats.csv      │
                                                                 data/data_quality.csv       │
                                                                                             │
   data/raw/PMI_Manufacturing_US.txt ──► pmi_manufacturing.py ──► data/PMI_Manufacturing_US.csv
   data/raw/PMI_Non_Manufacturing_US.txt ─► pmi_nonmanufacturing.py ─► data/PMI_NonManufacturing_US.csv
                                                  │  │                                        │
                                                  ▼  ▼                                        │
                                          pmi_composite.py ──► data/PMI_Composite_US.csv      │
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
bottom of `optimizer.py`. The PMI pipelines exist to feed that model.

---

## Files in `data/`

| File                              | Produced by              | Description |
|-----------------------------------|--------------------------|-------------|
| `returns_aligned.csv`             | data_pipeline            | ★ Main optimizer input: aligned monthly returns, no NaNs |
| `returns_full.csv`                | data_pipeline            | All returns incl. early NaNs |
| `prices_raw.csv`                  | data_pipeline            | Raw monthly adjusted-close prices |
| `summary_stats.csv`               | data_pipeline            | Annualized return / vol / Sharpe per asset |
| `data_quality.csv`                | data_pipeline            | Coverage, gaps, splice metadata |
| `PMI_Manufacturing_US.csv`        | pmi_manufacturing        | Windowed Manufacturing PMI |
| `PMI_Manufacturing_US_full.csv`   | pmi_manufacturing        | Full-history Manufacturing PMI |
| `PMI_NonManufacturing_US.csv`     | pmi_nonmanufacturing     | Windowed Non-Manufacturing PMI |
| `PMI_NonManufacturing_US_full.csv`| pmi_nonmanufacturing     | Full-history Non-Manufacturing PMI |
| `PMI_Composite_US.csv`            | pmi_composite            | Windowed composite PMI |
| `PMI_Composite_US_full.csv`       | pmi_composite            | Full-history composite PMI |
| `us_macro_2007_2026.csv`          | **external / manual**    | OECD/FRED macro panel — see Known Gaps below |

### `data/raw/` (inputs, not generated)

| File                                      | Description |
|-------------------------------------------|-------------|
| `PMI_Manufacturing_US.txt`                | Manual copy of investing.com ISM Manufacturing table |
| `PMI_Non_Manufacturing_US.txt`            | Manual copy of investing.com ISM Non-Manufacturing table |
| `ISM_Manufacturing_PMI_investing_com.html`| Saved source page for reference |

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
