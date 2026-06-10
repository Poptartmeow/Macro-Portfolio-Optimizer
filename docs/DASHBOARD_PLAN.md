# Macro Analytics Platform & Dashboard — Build Brief (Claude prompt)

> **Status:** DRAFT / living document. This is a prompt + design spec for a future
> Claude Code session to build the regression engine, factor risk model, backtester,
> and Streamlit dashboard. Edit freely as ideas evolve. Nothing here is built yet.
> Sections marked **[DECIDE]** are open questions for the author to lock down.
>
> This brief is written to satisfy the sponsor (Greg) and faculty mentor (Adam)
> guidance captured in the meeting notes — see **§16 Source mapping** for traceability.

---

## How to use this file

Paste this whole file (or point Claude at `docs/DASHBOARD_PLAN.md`) and say:
*"Build the platform described in this brief. Start with Phase 1 only and stop for
review."* Build it in phases — do not let it one-shot the whole thing.

---

## 1. Goal

Turn the existing optimizer into the full **Global Macro Portfolio Optimizer & Risk
Analytics Platform** the capstone is graded on: a reproducible pipeline that goes from
raw data → macro factor regressions → expected returns + factor-based covariance →
mean-variance optimizer → backtest vs a benchmark → an **interactive Streamlit
dashboard** that ties it all together with a futuristic, UVA-branded look.

The dashboard is the deliverable that communicates the whole system to Greg. It must
**cover every component** of Adam's system flow diagram (§3).

## 2. Scope decisions locked in

- **No heavyweight database required.** Organize data as tidy files in folders
  (Parquet/CSV "data lake"). SQLite is the sanctioned alternative (Adam confirmed it's
  fine at our scale, ~120k rows / 25–30 ETFs) and is a drop-in later since both are
  just local files — but folders first, per author preference.
- **Producer/consumer split:** heavy compute (regressions, factor model, backtests)
  runs in batch and writes result tables; Streamlit only *reads* them (cached).
- **Regression forms to run (ALL):** univariate sweep, multivariate per asset,
  lagged/predictive, change-based (Δ). Lagged + change combine.
- **Factor-based risk model** (Adam's main ask) in addition to raw historical
  covariance, so the two can be compared.
- **Backtest** with a strict train/test holdout, in both static and rolling modes.
- **Benchmark:** 60% ACWI / 40% IGOV, comparisons bounded to 2009+ (overlap window).
- **Reproducibility:** mostly static data snapshot, with a flag to switch to live
  ingestion (confirm exact expectation with Greg — open question).

## 3. Architecture — mirrors Adam's system flow diagram

```
 ┌───────────────┐   ┌────────────────────┐   ┌──────────────────────┐   ┌──────────────────┐
 │ 1. INGEST     │   │ 2. FACTOR MODEL    │   │ 3. EXPECTED RETURNS  │   │ 4. OPTIMIZER     │
 │ yfinance/FRED │──►│ regressions →      │──►│ macro-regression μ   │──►│ mean-variance    │
 │ OECD CSVs     │   │ betas → covariance │   │ (lagged) vs hist μ   │   │ target 10% vol   │
 │ → curated/    │   │ (B Σf Bᵀ + D)      │   │                      │   │ 3%–30% box       │
 └───────────────┘   └────────────────────┘   └──────────────────────┘   └──────────────────┘
         │                     │                          │                        │
         └─────────────────────┴──────────┬───────────────┴────────────────────────┘
                                           ▼
                              ┌──────────────────────────┐        ┌────────────────────────┐
                              │ 5. BACKTEST ENGINE        │───────►│ 6. STREAMLIT DASHBOARD │
                              │ static + rolling, vs bmk  │        │ UVA futuristic theme   │
                              └──────────────────────────┘        └────────────────────────┘
```

- Batch steps write to `data/curated/` and `data/results/`.
- Dashboard is fast, stateless, read-only (`@st.cache_data`), recomputes nothing.

## 4. Data inputs (already in repo or to be added)

| File | Shape | Use |
|------|-------|-----|
| `data/returns_aligned.csv` | wide: date × asset | Y: asset returns (8 assets) |
| `data/returns_full.csv` | wide, NaNs | longer history option |
| `data/us_macro_2007_2026.csv` | month × macro cols | X: macro indicators (US) |
| `data/PMI_Composite_US.csv` | month × PMI | X: PMI signal (limits factor model to its window) |
| **TODO** ACWI, IGOV | monthly | benchmark legs (add to data_pipeline universe) |
| **TODO** MSCI World, VIX, credit/HY spreads, unemployment | monthly | additional global factors (§7) |

Macro column naming convention is in the README. **Month alignment is the first thing
to get right:** macro is `YYYY-MM`, returns are month-end — resample both to a common
monthly key. **Always forward-fill macro, never backfill** (look-ahead bias).

## 5. On-disk layout (tidy long tables)

```
data/
├── curated/                       NEW — tidy, analysis-ready inputs
│   ├── returns_long.parquet            date, asset, ret
│   ├── macro_long.parquet              date, factor, country, value, transform
│   └── benchmark_long.parquet          date, ticker(ACWI/IGOV), ret
└── results/                       NEW — outputs the dashboard reads
    ├── regression_results.parquet      coefficient-level (schema §12)
    ├── factor_model.parquet            betas + idiosyncratic var per asset
    ├── covariance_matrices.parquet     historical vs factor-based (tidy: i, j, value, method)
    ├── expected_returns.parquet        per asset, per method (hist_mean vs macro_model)
    ├── optimizer_runs.parquet          weights + realized stats per config
    ├── backtest_results.parquet        date, strategy, port_ret, bmk_ret, cum, drawdown
    └── run_metadata.parquet            one row per batch run (timestamp, window, git sha, config)
```

Long format is deliberate — the dashboard filters/pivots with one `df.pivot_table()`.

## 6. The macro regression sweep (research layer)

One row per estimated coefficient (schema §12). Forms:

1. **Univariate** — `asset_ret ~ factor` for every (asset, factor) pair.
2. **Multivariate per asset** — `asset_ret ~ all factors` (one model per asset).
3. **Lagged/predictive** — `asset_ret(t) ~ factor(t−k)` for `k ∈` **[DECIDE]** (e.g. 1,3,6,12).
4. **Change-based** — same on Δ(factor). Run lagged on both levels and changes.

Use **HAC / Newey-West** standard errors (`statsmodels OLS(...).fit(cov_type="HAC",
cov_kwds={"maxlags": L})`) — monthly macro is autocorrelated and plain OLS t-stats lie.
Report an **FDR/Bonferroni-adjusted** significance flag (hundreds of regressions → false
positives). **[DECIDE]** z-score regressors for the heatmap so βs are comparable.

## 7. Factor-based risk model (Adam's main ask)

Replace/augment the raw sample covariance with a **factor model** so covariance is
parsimonious and less noisy as assets grow.

- **Two-source decomposition:**
  `Total covariance = B · Σ_f · Bᵀ + D`
  where `B` = asset×factor beta matrix (from regressions), `Σ_f` = factor covariance,
  `D` = diagonal idiosyncratic (residual) variances.
- **Systematic risk** = `B Σ_f Bᵀ`; **idiosyncratic** = `D` (assumed uncorrelated, normal).
- **Candidate global factors** (Adam's list): MSCI World, S&P Global PMI, credit
  spreads (IG and/or HY over Treasuries), unemployment, volatility (VIX), GDP (PMI proxy).
  Plus the term-structure / value factors Greg mentioned (10y−2y, 10y−3m, div yield,
  credit risk premium Baa−Aaa, 1-month cash).
- **Lag factors** when used as predictors (look-ahead). Pick **economically sensible**
  factors; don't over-engineer.
- Output both covariance matrices to `covariance_matrices.parquet` (method =
  `historical` | `factor`) so the dashboard can A/B them and show their effect on weights.

## 8. Expected returns

- **Baseline:** historical mean (the optimizer's current placeholder).
- **Macro model:** expected returns from the **lagged** macro-factor regressions
  (Greg: "lag the regression by one month… this will replace Jack's average return").
  Feed via `optimizer.set_expected_returns({asset: μ})`.
- Write both to `expected_returns.parquet` and let the dashboard compare them and show
  the resulting weight/return sensitivity (Greg: "drop down the return assumptions…
  play around with that sensitivity").

## 9. Optimizer integration

- Reuse existing `optimizer.py` (mean-variance, target 10% vol, 3%–30% box — working
  assumptions, **[DECIDE]** justify final values).
- Add a **PIMCO/INTL_BOND inclusion toggle** (include vs exclude) as a hyperparameter
  research output — run both, compare (Adam's framing).
- Persist each run's weights + realized stats to `optimizer_runs.parquet`.

## 10. Backtesting engine

- **Strict train/test:** train 2013→end-2024 (or Jan 2025); **holdout is untouched**
  during all design decisions.
- **Modes:** (1) **static** — train once, hold weights, evaluate on test; (2)
  **rolling/expanding** — each month: re-estimate (5-yr lookback), reweight, evaluate
  next month, repeat.
- Compare every strategy to the **60/40 ACWI+IGOV benchmark** (2009+ window).
- Persist to `backtest_results.parquet`.

## 11. Risk analytics & reports

Greg/Adam want risk *reporting*, not just vol: **Sharpe**, **VaR** (and CVaR),
**max drawdown**, **factor sensitivities/exposures** (market, size small-vs-large,
value-vs-growth — Fama-French style), tracking error vs benchmark, and the
correlation matrix (8×8 — "easier for debugging and smell test").

## 12. `regression_results.parquet` schema

| column | type | notes |
|--------|------|-------|
| `model_id` | str | groups rows from one fitted model |
| `model_type` | str | `univariate`\|`multivariate`\|`lagged`\|`lagged_change` |
| `asset` | str | dependent variable |
| `factor` | str | regressor (`const` for intercept) |
| `lag` | int | 0 contemporaneous; k lagged |
| `transform` | str | `level`\|`change` |
| `coef`,`std_err`,`t_stat`,`p_value` | float | HAC-based |
| `ci_low`,`ci_high` | float | 95% CI |
| `r_squared`,`adj_r_squared` | float | model-level (repeated) |
| `n_obs` | int | |
| `sig_fdr` | bool | passes FDR/Bonferroni adjustment |
| `start`,`end` | date | sample window |

## 13. New code modules

```
src/macro_portfolio/
├── research/                NEW
│   ├── transforms.py        month alignment, level/change, lagging, z-score
│   ├── curate.py            wide CSVs -> data/curated/*_long.parquet
│   └── regressions.py       all 4 forms -> results/regression_results.parquet
├── risk/                    NEW
│   ├── factor_model.py      betas + Σf + D -> factor covariance
│   └── analytics.py         Sharpe, VaR/CVaR, drawdown, exposures, tracking error
├── backtest/                NEW
│   └── engine.py            static + rolling; -> results/backtest_results.parquet
├── optimizer/optimizer.py   EXTEND: persist runs, PIMCO toggle
└── paths.py                 ADD: CURATED_DIR, RESULTS_DIR

dashboard/                   NEW (streamlit run dashboard/app.py)
├── app.py                   landing + global filters; loads theme
├── theme.py                 UVA futuristic palette, plotly template, CSS injector
├── .streamlit/config.toml   Streamlit theme (colors/fonts)
└── pages/
    ├── 1_Overview.py            system flow diagram + headline KPIs
    ├── 2_Macro_Regressions.py   asset×factor heatmap (β / t-stat), drill-downs
    ├── 3_Factor_Risk_Model.py   betas, factor vs historical covariance, exposures
    ├── 4_Expected_Returns.py    macro-model vs historical μ, sensitivity sliders
    ├── 5_Optimizer.py           weights, efficient frontier, PIMCO toggle
    ├── 6_Backtest.py            equity curve vs benchmark, drawdown, static/rolling
    └── 7_Risk_Report.py         Sharpe/VaR/CVaR, correlation matrix, tracking error
```

Reuse `macro_portfolio.paths` everywhere (no hardcoded paths — that bug is fixed).
Each batch module exposes a callable + `python -m ...` entry point.
Add deps: `statsmodels`, `streamlit`, `pyarrow`, `plotly`.

## 14. Dashboard aesthetics — UVA futuristic

**Brand palette (UVA official + futuristic accents):**

| Token | Hex | Use |
|-------|-----|-----|
| Jefferson Blue | `#232D4B` | primary background / deep navy base |
| Rotunda Orange | `#E57200` | primary accent, CTAs, key data series, highlights |
| White | `#FFFFFF` | text on dark, card surfaces in light mode |
| Cyan glow (accent) | `#3DD2FF` | "futuristic" neon highlights, hover, secondary series |
| Slate (muted) | `#5B6478` | gridlines, secondary text |
| Surface | `#1B2238` | card/panel background (slightly lighter than base) |

**Look & feel:**
- **Dark, futuristic, glassmorphism:** deep Jefferson-blue background, semi-transparent
  "glass" cards (subtle blur + 1px translucent border), soft orange/cyan glow on key
  numbers and active controls. Rounded corners (12–16px), generous spacing.
- **Typography:** a clean geometric/techy font — e.g. `Inter` or `Space Grotesk` for
  headings, `Inter` for body, monospace (`JetBrains Mono`) for numeric tables.
- **Charts:** custom **Plotly template** using the palette — Rotunda Orange as the
  primary series, cyan as secondary, white/slate gridlines on transparent paper so
  charts sit on the glass cards. Heatmap colorscale: navy → white → orange (diverging,
  centered at 0 for β/t-stat).
- **Motion (subtle):** fade-in on load, animated KPI counters, glow on hover. Keep it
  tasteful — it's a finance tool, not a game.
- **Consistency:** a small "V"/Rotunda-inspired logo mark in orange in the header; the
  system flow diagram (§3) rendered as the Overview hero with the active stage glowing.

Implement via `dashboard/.streamlit/config.toml` (base theme colors) **plus** a
`theme.py` that injects custom CSS (`st.markdown(..., unsafe_allow_html=True)`) for the
glassmorphism and registers the Plotly template. Keep all colors in one place in
`theme.py` so the palette is editable in one spot.

```toml
# dashboard/.streamlit/config.toml  (starting point)
[theme]
base = "dark"
primaryColor = "#E57200"
backgroundColor = "#232D4B"
secondaryBackgroundColor = "#1B2238"
textColor = "#FFFFFF"
font = "sans serif"
```

## 15. Build phases (do in order, STOP for review between each)

1. **Curate** — `transforms.py` + `curate.py` → `data/curated/*.parquet`. Verify
   alignment & row counts. No regressions yet.
2. **Regressions** — univariate sweep first → `regression_results.parquet`; hand-check
   a few coefficients; then add the other three forms (HAC SE, FDR flag).
3. **Factor risk model** — `factor_model.py` → betas + factor covariance; compare to
   historical covariance.
4. **Expected returns + optimizer integration** — macro-model μ, PIMCO toggle,
   persist runs.
5. **Backtest engine** — static then rolling; benchmark comparison.
6. **Dashboard skeleton + theme** — `app.py`, `theme.py`, config.toml, Overview +
   Macro Regressions pages against real data.
7. **Remaining dashboard pages** — factor model, expected returns, optimizer, backtest,
   risk report.
8. **Polish** — caching, a "run pipeline" entry point / Makefile, refresh docs.

## 16. Source mapping (traceability to meeting notes)

- **Factor risk model, two-source decomposition, factor list, lag factors, statsmodels**
  → Adam 06/03 (`Team_Adam_MeetingNotes_06_03_2026`, `Adam Meeting 06_03_2026`).
- **Backtest train/test holdout, static vs rolling, 5-yr lookback, lag regression by 1
  month, output means+covariance, return-assumption sensitivity** → Greg 4th
  (06/02) + Adam 06/03.
- **Markowitz single point @ 10% vol, sample covariance, 8×8 cov/corr matrices** → Greg
  3rd & 4th.
- **3%/30% box, PIMCO inclusion as hyperparameter, SQLite OK + Streamlit** → Adam 06/03.
- **Benchmark 60% ACWI / 40% IGOV, 2009+ window** → Greg 1st, Portfolio Allocation,
  Adam 05/20.
- **PMI as monthly GDP proxy, regional aggregation by GDP/population, credit spread /
  dividend yield / 1-month cash factors, region-by-region (Harvey)** → Greg 1st/3rd,
  Macro Data Sourcing, Adam 05/20.
- **Splice PFORX (hedged) extends to 2007; manual FX hedge via rate differential** →
  Adam 05/20 & 06/03, Portfolio Allocation.
- **Streamlit/Plotly, reproducible pipeline, static-vs-live flag** → Adam 05/20 & 06/03,
  Briefing Report.
- **Risk report contents (Sharpe, VaR, factor sensitivities, not just vol)** → Greg 1st.
- **System flow diagram of all components** → Adam 06/03 (explicit recommendation).

## 17. Open questions — **[DECIDE]**

- Lags `k` and per-factor transforms (rates as levels? CPI YoY? PMI level + Δ?).
- Sample window: full history per-pair vs common aligned window.
- z-score regressors for the heatmap (likely yes for heatmap, raw for detail).
- Multiple-testing correction method (FDR vs Bonferroni).
- US-only macro for v1 (map all assets to US factors), or wait for the multi-region
  macro panel (known-gap TODO) before regressing non-US assets.
- Final factor list to commit to (Adam asked the team to finalize this).
- Transaction-cost assumptions in the backtest (Adam raised; ask Greg).
- Reproducibility level: static snapshot vs live-ingestion flag (ask Greg).
- Where/how the dashboard is deployed (local only vs Streamlit Community Cloud).
- Keep folders/Parquet only, or also stand up the optional SQLite layer.

## 18. Notes / scratchpad

_(Add ideas here as you brainstorm.)_
-
