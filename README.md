# Macro-Portfolio-Optimizer

**Global Macro Portfolio Optimizer & Risk Analytics Platform**

Authors: Mauricio Torres, Tianyin Mao, Jack Joy, Tiandra Threat

A research project that builds a globally diversified, mean-variance-optimized
portfolio from a fixed universe of ETFs, using monthly macro indicators (PMI)
as a forward-looking signal. The pipeline pulls and cleans market + macro data,
the optimizer solves for the best risk-adjusted weights at a target volatility,
and the analysis scripts back the methodology decisions.

---

## What's in here

```
src/macro_portfolio/      All Python, as an installable package
  pipelines/              Data acquisition & cleaning (ETF prices, PMI series)
  optimizer/              Mean-variance optimizer + efficient-frontier plot
  analysis/               Research scripts (bond-splice proxy study)
  paths.py                Single source of truth for data/output locations
data/                     Cleaned CSV outputs (+ raw/ for raw inputs)
outputs/                  Generated charts and analysis artifacts
docs/                     Documentation, schema diagrams, methodology notes
```

See **[docs/STRUCTURE.md](docs/STRUCTURE.md)** for a full file-by-file map and
the data-flow diagram.

---

## Quick start

```bash
# 1. Install dependencies (Python 3.10+)
pip install -e .          # installs the package + deps from pyproject.toml
#   ...or: pip install -r requirements.txt   (deps only)

# 2. Build the market data (ETF prices -> aligned monthly returns)
python -m macro_portfolio.pipelines.data_pipeline

# 3. Build the PMI macro series (run in this order)
python -m macro_portfolio.pipelines.pmi_manufacturing
python -m macro_portfolio.pipelines.pmi_nonmanufacturing
python -m macro_portfolio.pipelines.pmi_composite

# 4. Run the optimizer and plot the efficient frontier
python -m macro_portfolio.optimizer.optimizer
python -m macro_portfolio.optimizer.plot_frontier
```

All scripts resolve paths relative to the repo root (via `paths.py`), so they
work from any working directory once the package is installed.

---

## Asset universe

| Ticker      | Exposure                                   |
|-------------|--------------------------------------------|
| SPY         | US Large Cap (S&P 500)                      |
| VXF         | US Mid + Small Cap                          |
| EWC         | Canadian Equities                          |
| EFA         | Intl Developed Equities (ex-US)            |
| VWO         | Emerging Market Equities                   |
| AGG         | US Aggregate Bonds                         |
| EMB         | Emerging Market Bonds                      |
| DBC         | Broad Commodities                          |
| `INTL_BOND` | Intl Bonds ex-US — spliced **PFORX → BNDX** (PFORX pre-2013, BNDX from 2013) |

The `INTL_BOND` series is chain-linked because BNDX only starts in 2013. PFORX
(PIMCO Intl Bond, USD-hedged) extends it back to 2007 — see the splice study in
[src/macro_portfolio/analysis/intl_bond_splice.py](src/macro_portfolio/analysis/intl_bond_splice.py)
for why PFORX was chosen over the original BWX baseline.

---

## Macro data column conventions

The `data/us_macro_2007_2026.csv` file holds the broader OECD/FRED macro panel
used as model inputs. Column naming:

```
REAL_GDP_<COUNTRY>        Real GDP, PPP-adjusted USD (OECD, quarterly -> monthly ffill)
HEADLINE_CPI_<COUNTRY>    Headline CPI, % change year-on-year (OECD)
IRSTCI_<COUNTRY>          Central bank policy rate, % per annum (OECD)
IRLT_<COUNTRY>            10-year government bond yield, % per annum (OECD)
IR3TIB_<COUNTRY>          3-month interbank rate, % per annum (OECD)
CORE_CPI_USA              US Core CPI ex food & energy, index (FRED)
DGS2_USA                  US 2-year Treasury yield, % (FRED)
SPREAD_10Y3M_<COUNTRY>    10yr yield minus 3-month rate (computed)
SPREAD_10Y2Y_USA          US 10yr minus 2yr yield (computed, US only)
CREDIT_SPREAD_BAA_USA     Moody's Baa corporate yield minus 10yr Treasury (investment-grade spread)
CREDIT_SPREAD_AAA_USA     Moody's Aaa minus 10yr (tighter end)
DIV_YIELD_USA             S&P 500 dividend yield proxy (FRED)
```

> ⚠ **Known gap:** `data/us_macro_2007_2026.csv` does **not** yet have a
> generating pipeline in this repo — it was produced manually/externally. A
> `pipelines/macro_panel.py` to reproduce it is a TODO. See
> [docs/STRUCTURE.md](docs/STRUCTURE.md#known-gaps--todos).

---

## Documentation

- [docs/STRUCTURE.md](docs/STRUCTURE.md) — repository layout & data flow
- [docs/PMI_Data_Documentation.md](docs/PMI_Data_Documentation.md) — what PMI is, sources, refresh procedure, composite weighting
- [docs/architecture_diagram.html](docs/architecture_diagram.html) — database architecture diagram
- [docs/schema_documentation.docx](docs/schema_documentation.docx) / [docs/schema_diagram.xlsx](docs/schema_diagram.xlsx) — schema reference
