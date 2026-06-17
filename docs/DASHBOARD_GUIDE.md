## What this dashboard is

This is the front end for our Global Macro Portfolio Optimizer. The heavy lifting
(pulling data, running regressions, estimating risk, optimizing the portfolio) all
happens in Python (`src/macro_portfolio/`). The dashboard loads the files the
pipeline produced and visualizes them. Every page shows a different stage of the
outcomes.

---

## Pipeline

The whole project is an end-to-end pipeline, and the following is the pipeline in
its entirety:

**Data → Macro → Optimizer → Ensemble → Risk → Policy → Findings**

The sidebar is in that exact order. Open any page and its stage lights up orange in
the bar, so you always know where you are in the flow. Read the pages in order and
the project tells itself as a story: get clean data → read the macro backdrop →
build a portfolio → compare construction methods → check the risk → check it against
our policy → write up what we learned.

A few conventions used everywhere:

- **Sub-tabs** group related views under one sidebar item (this Home page has
  Overview/About; the Macro page has Regime/Signals).
- **Glass cards** show headline numbers (KPIs); orange is our accent, cyan is the
  secondary highlight.
- Every number is computed by transparent code (statsmodels / scikit-learn /
  scipy). There's no language model deciding anything, which keeps our backtests
  honest.

---

## Page by Page

### Home
- **Overview:** the project in one screen which includes a summary of what we're
  building and descriptive stats such as the headline data counts, growth of $1 for
  every asset, the risk/return map, and a per-asset stats table.
- **About:** this guide.

### Data
Where the numbers come from and how clean they are.
- **What it shows:** when each asset's history starts, what bounds our usable
  window, and the macro panel's missing-data / cleaning log.
- **How to read it:** the coverage bars show each ETF's first available month. The
  window can only start once every asset exists, so the latest-starting asset
  (EMB, Dec 2007) sets our 2008 start. The macro table shows what we dropped
  (HY spread, 85% missing) and what we filled (dividend yield, interpolated).
- **Why it matters:** garbage in, garbage out. This page is our honesty about the
  data's limits, and it's the first thing a sponsor will poke at.

### Macro  *(sub-tabs: Regime · Signals)*
*The macro backdrop the portfolio should respond to.*
- **Regime tab**, classifies every month into **Expansion / Slowdown / Contraction
  / Recovery** from composite PMI (above/below 50) and its 3-month momentum.
  - *How to read it:* the timeline shades the cycle behind the PMI line; the
    asset×regime heatmap shows how each asset has actually performed in each regime.
  - *Why it matters:* it's the empirical case for tilting, equities rip in
    Recovery/Expansion and get hit in Contraction, where bonds hold up.
- **Signals tab**, runs a regression of every asset's return on every macro factor
  (one-month lag, Newey-West errors) and shows the grid.
  - *How to read it:* color = strength. For t-stat, **|t| > 2 ≈ statistically
    real**; orange is positive, blue negative. Use the drill-down to see the actual
    scatter + fit line behind any cell.
  - *Why it matters:* it tells us *which* macro variables actually move *which*
    assets, the basis for the expected-return model. (Early read: inflation is the
    strongest signal; PMI is weaker than you'd expect.)

### Optimizer
*Build one portfolio and see how it behaves.*
- **What it shows:** an interactive mean-variance optimizer, pick the objective
  (max-return at a vol target, or max-Sharpe with a diversification penalty), the
  covariance (sample vs Ledoit-Wolf shrinkage), and the weight box. Then weights,
  headline stats, a sensitivity chart, and a comparison vs the 60/40 benchmark.
- **How to read it:** watch **"assets at bound"** and **"effective N"**, when most
  assets sit on a constraint, the box (not the math) is driving. The sensitivity
  chart shows whether changing an asset's expected return actually moves its weight
  (right now it barely does, a key finding).
- **Why it matters:** this is the core deliverable, and the page makes its current
  weakness visible.

### Ensemble
*Don't bet on one method, run them all and combine.*
- **What it shows:** eight portfolio-construction methods (equal-weight, inverse-vol,
  min-variance, max-Sharpe, risk parity, hierarchical risk parity, max-diversification,
  inverse-variance) built on the same inputs, then blended into one ensemble.
- **How to read it:** the comparison table ranks them by Sharpe (benchmark Sharpe is
  the reference line); the heatmap shows every method's allocation at once; the bar
  is the final ensemble.
- **Why it matters:** it's the institutional move (and straight out of the Ang et al.
  2026 paper), diversify across *methodologies*, not just assets, so we're not
  hostage to one optimizer's quirks.

### Risk
*Would we sleep at night holding this?*
- **What it shows:** Sharpe, volatility, Value-at-Risk / CVaR, max drawdown, the
  drawdown path, the asset correlation matrix, and the return distribution.
- **How to read it:** the correlation matrix is the "smell test", our equity
  sleeves correlate ~0.9, so they're almost one bet; bonds/commodities are the real
  diversifiers. VaR/CVaR quantify the bad months.
- **Why it matters:** Greg asked for risk analytics, not just returns. *(Note: this
  page currently profiles an equal-weight portfolio as a stand-in until the
  optimizer weights + a full backtester feed in.)*

### Policy
*Does the portfolio obey our own rules?*
- **What it shows:** our Investment Policy Statement (IPS) and a **live compliance
  check** of the policy portfolio against it, per-asset cap, total-equity cap,
  fully-invested, volatility band, drawdown limit, with a PASS/BREACH badge.
- **How to read it:** green ✓ = within policy, red ✗ = breach. The full IPS text is
  below the check.
- **Why it matters:** the IPS is the governing document (the human sets the rules,
  every portfolio is checked against them). It's also how the same framework can run
  at different risk levels, just change the limits.

### Findings
*What we actually learned, in plain English.*
- The running write-up: the biggest findings (the corner-solution problem, the
  expected-returns-don't-move-weights problem, CPI vs PMI), what's surprising, data
  concerns, and recommended next steps. It renders `docs/FINDINGS.md`, so editing
  that file updates the page.

---

## Where the code lives

| You see (page) | Code behind it |
|---|---|
| Data | `pipelines/`, `research/curate.py` |
| Macro · Regime | `research/regime.py` |
| Macro · Signals | `data_access.univariate_sweep` (statsmodels) |
| Optimizer | `optimizer/optimizer.py`, `optimizer/advanced.py` |
| Ensemble | `optimizer/methods.py` |
| Risk | `risk/`, `risk/covariance.py` |
| Policy | `optimizer/ips.py`, `docs/IPS.md` |
| Findings | `docs/FINDINGS.md` |

- **`src/macro_portfolio/`**, the actual model (importable package).
- **`dashboard/`**, this app. `Home.py` is the entry; `pages/` are the sidebar
  pages; `sec_*.py` are sub-tab sections; `theme.py` holds all colors/styling;
  `data_access.py` is the cached loader layer.
- **`data/`**, inputs and cleaned outputs. **`docs/`**, these write-ups.

To edit a chart, find its page in `dashboard/pages/` (or `sec_*.py`); to change the
look, edit `theme.py`; to change a number, it's in `src/macro_portfolio/`.

---

## Mini-glossary

- **Sharpe ratio**, return per unit of risk (higher = better). Ours vs the 60/40 is
  the bar to beat.
- **Volatility**, annualized standard deviation of returns; our risk target is ~10%.
- **Ledoit-Wolf shrinkage**, a more stable covariance estimate; tames the noise from
  our highly-correlated equities.
- **Effective N**, roughly how many assets actually carry weight (higher = more
  diversified).
- **Risk parity / HRP / max-diversification**, portfolio methods that lean on the
  risk structure instead of return forecasts.
- **Regime**, which phase of the business cycle we're in (from PMI).
- **t-stat / Newey-West**, is a regression relationship real (|t|>2), using errors
  that account for autocorrelated monthly data.
- **IPS**, Investment Policy Statement; the rules the portfolio must obey.
- **60/40 benchmark**, 60% global stocks (ACWI) + 40% intl gov bonds (IGOV); the
  passive baseline we measure against.
- **Lookahead bias**, accidentally using future info in a backtest; why we keep any
  LLM out of the modeling loop.

*This guide also lives at `docs/DASHBOARD_GUIDE.md`, edit there and this tab updates.*
