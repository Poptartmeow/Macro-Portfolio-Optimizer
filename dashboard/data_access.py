"""
Cached data loaders + a live univariate regression sweep for the dashboard.

This first version reads the existing CSVs in data/ directly (the batch result
tables described in DASHBOARD_PLAN.md don't exist yet). Once the research layer
is built, these loaders should switch to reading data/results/*.parquet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
MARKET_PROCESSED = DATA_DIR / "market_data" / "processed"
MACRO_RAW = DATA_DIR / "macro_data" / "raw"
MACRO_PROCESSED = DATA_DIR / "macro_data" / "processed"
MACRO_PMI = MACRO_PROCESSED / "pmi"
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

PERIODS = 12  # months per year


@st.cache_data(show_spinner=False)
def load_returns() -> pd.DataFrame:
    """Aligned monthly asset returns, indexed by month-end."""
    df = pd.read_csv(MARKET_PROCESSED / "returns_aligned.csv", index_col=0, parse_dates=True)
    return df


@st.cache_data(show_spinner=False)
def load_regime() -> pd.DataFrame:
    """Monthly macro regime labels (Expansion/Slowdown/Contraction/Recovery)."""
    from macro_portfolio.research import regime as R
    return R.classify(load_factors())


@st.cache_data(show_spinner=False)
def load_benchmark() -> pd.DataFrame | None:
    """60/40 ACWI/IGOV monthly returns (or None if not fetched yet)."""
    p = MARKET_PROCESSED / "benchmark_returns.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, index_col=0, parse_dates=True)


@st.cache_data(show_spinner=False)
def load_factors() -> pd.DataFrame:
    """Monthly macro factors (cleaned US macro panel + composite PMI)."""
    curated = MACRO_PROCESSED / "macro_monthly.csv"
    if curated.exists():
        macro = pd.read_csv(curated, index_col=0, parse_dates=True)
    else:  # fallback: clean on the fly
        macro = pd.read_csv(MACRO_RAW / "us_macro_2007_2026.csv")
        macro["Month"] = pd.PeriodIndex(macro["Month"], freq="M")
        macro = macro.groupby("Month").mean(numeric_only=True)
        macro.index = macro.index.to_timestamp(how="end").normalize()

    pmi = pd.read_csv(MACRO_PMI / "PMI_Composite_US.csv", parse_dates=["date"])
    pmi = pmi.set_index("date")[["PMI_Composite_US"]]
    pmi.index = pmi.index.to_period("M").to_timestamp(how="end").normalize()

    factors = macro.join(pmi, how="outer").sort_index()
    return factors


@st.cache_data(show_spinner=False)
def load_fill_log() -> pd.DataFrame | None:
    """The macro gap-filling log written by research/curate.py, if present."""
    p = MACRO_PROCESSED / "macro_fill_log.csv"
    return pd.read_csv(p) if p.exists() else None


def _to_month(idx: pd.DatetimeIndex) -> pd.PeriodIndex:
    return idx.to_period("M")


@st.cache_data(show_spinner=True)
def univariate_sweep(lag: int = 0, transform: str = "level",
                     hac_lags: int = 6, min_obs: int = 24):
    """
    Run asset_ret(t) ~ factor(t-lag) for every (asset, factor) pair.

    transform: 'level' (raw factor) or 'change' (month-over-month diff).
    Returns (beta_df, tstat_df, n_df, r2_df) as assets × factors DataFrames.
    """
    rets = load_returns().copy()
    facs = load_factors().copy()

    rets.index = _to_month(rets.index)
    facs.index = _to_month(facs.index)

    if transform == "change":
        facs = facs.diff()

    assets = list(rets.columns)
    factors = list(facs.columns)
    beta = pd.DataFrame(index=assets, columns=factors, dtype=float)
    tstat = pd.DataFrame(index=assets, columns=factors, dtype=float)
    nobs = pd.DataFrame(index=assets, columns=factors, dtype=float)
    r2 = pd.DataFrame(index=assets, columns=factors, dtype=float)

    for f in factors:
        x = facs[f].shift(lag)
        for a in assets:
            df = pd.concat([rets[a], x], axis=1, keys=["y", "x"]).dropna()
            if len(df) < min_obs or df["x"].nunique() < 3:
                continue
            X = sm.add_constant(df["x"].values)
            try:
                res = sm.OLS(df["y"].values, X).fit(
                    cov_type="HAC", cov_kwds={"maxlags": hac_lags})
            except Exception:
                continue
            beta.loc[a, f] = res.params[1]
            tstat.loc[a, f] = res.tvalues[1]
            nobs.loc[a, f] = int(res.nobs)
            r2.loc[a, f] = res.rsquared
    return beta, tstat, nobs, r2


def window_label() -> str:
    """Human-readable 'YYYY–YYYY' span of the aligned returns (for KPIs/captions)."""
    idx = load_returns().index
    return f"{idx.min().year}–{idx.max().year}"


@st.cache_data(show_spinner=True)
def regression_expected_returns(
    factors: tuple[str, ...],
    lag: int = 1,
    transform: str = "level",
    hac_lags: int = 6,
    min_obs: int = 36,
    train_end: str | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    """
    Macro-model expected returns for the optimizer.

    For each asset, fit a multivariate OLS of monthly return on the chosen
    macro factors (optionally lagged / month-over-month changes), then evaluate
    the fitted model at the *latest* observed factor values to get a forward
    monthly expected return; annualized (×12).

    `train_end` (e.g. "2020-12-31") restricts the regression fit to data on or
    before that date — the professor's train/test split — while μ is still
    evaluated at the most recent factor values (current macro state). When None,
    the full history is used.

    Falls back to the asset's historical mean when the regression can't be fit
    (too few obs, singular design, or missing latest factor values).

    Returns:
      mu_ann : annualized expected return per asset (pd.Series)
      detail : per-asset diagnostics (R², n, source) for display
    """
    rets = load_returns().copy()
    facs = load_factors().copy()
    facs = facs[[c for c in factors if c in facs.columns]]

    rets.index = _to_month(rets.index)
    facs.index = _to_month(facs.index)

    if transform == "change":
        facs = facs.diff()

    X_all = facs.shift(lag)
    # Latest factor row that is fully populated for the chosen set
    latest = X_all.dropna(how="any")
    x_latest = latest.iloc[-1] if len(latest) else None

    train_cut = pd.Period(train_end, freq="M") if train_end else None

    hist = rets.mean() * PERIODS
    mu, rows = {}, []
    for a in rets.columns:
        df = pd.concat([rets[a], X_all], axis=1).dropna()
        if train_cut is not None:
            df = df[df.index <= train_cut]
        ok = (len(df) >= min_obs and x_latest is not None
              and not facs.empty and df.iloc[:, 1:].shape[1] > 0)
        if ok:
            try:
                X = sm.add_constant(df.iloc[:, 1:].values)
                res = sm.OLS(df[a].values, X).fit(
                    cov_type="HAC", cov_kwds={"maxlags": hac_lags})
                pred_monthly = float(res.params @ np.r_[1.0, x_latest.values])
                mu[a] = pred_monthly * PERIODS
                rows.append({"Asset": a, "Source": "macro model",
                             "R²": res.rsquared, "n": int(res.nobs)})
                continue
            except Exception:
                pass
        mu[a] = hist[a]
        rows.append({"Asset": a, "Source": "historical (fallback)",
                     "R²": np.nan, "n": np.nan})

    mu_ann = pd.Series(mu).reindex(rets.columns)
    detail = pd.DataFrame(rows).set_index("Asset")
    return mu_ann, detail


# A robust default factor set for the macro expected-return model: one series per
# economic dimension (growth / inflation / rates / credit), kept small to avoid
# the collinearity that wrecks a kitchen-sink regression.
DEFAULT_ER_FACTORS = (
    "PMI_Composite_US",       # growth
    "INFLATION_ACCEL",        # inflation
    "IRSTCI_USA",             # rates / policy
    "SPREAD_BAA_AAA_USA",     # credit
)


@st.cache_data(show_spinner=True)
def rolling_backtest(
    factors: tuple[str, ...],
    lag: int,
    transform: str,
    train_end: str,
    objective: str,
    cov_choice: str,
    min_w: float,
    max_w: float,
    target_vol: float,
    l2: float,
    eq_cap: float,
    equity: tuple[str, ...],
    hac_lags: int = 6,
    min_obs: int = 36,
) -> dict:
    """
    Walk-forward monthly re-optimization (the professor's rolling scheme).

    For each out-of-sample month t (those after `train_end`):
      1. Re-fit each asset's macro regression on ALL data up to t-1 (expanding
         window) — factors are lagged so they're knowable at t.
      2. μ_t = fitted β · factor values observed at t (annualized).
      3. Σ_t from the trailing returns up to t-1 (annualized; LW or sample).
      4. Optimize → target weights w_t.
      5. Realized next-month return = w_t · r_t.
      6. Trades_t = w_t − w_{t-1} (what you'd rebalance into).

    Returns a dict of DataFrames/Series:
      perf      : monthly realized portfolio return + benchmark (if available)
      weights   : weights through time (months × assets)
      turnover  : one-way turnover per month (0.5·Σ|Δw|)
      trades    : last month's allocation change per asset
      summary   : annualized return/vol/Sharpe for portfolio vs benchmark
    """
    from macro_portfolio.optimizer import optimizer as O
    from macro_portfolio.optimizer.advanced import max_sharpe_l2
    from macro_portfolio.risk.covariance import sample_cov, ledoit_wolf_cov

    rets = load_returns().copy()
    facs = load_factors().copy()
    facs = facs[[c for c in factors if c in facs.columns]]
    rets.index = _to_month(rets.index)
    facs.index = _to_month(facs.index)
    if transform == "change":
        facs = facs.diff()
    X_all = facs.shift(lag)

    assets = list(rets.columns)
    equity = [e for e in equity if e in assets]
    train_cut = pd.Period(train_end, freq="M")
    oos_months = [t for t in rets.index if t > train_cut]

    def fit_mu(upto: pd.Period) -> pd.Series | None:
        """Expected returns using data through `upto`, evaluated at month upto's factors."""
        x_now = X_all.loc[upto] if upto in X_all.index else None
        if x_now is None or x_now.isna().any():
            return None
        hist = rets.loc[:upto].mean() * PERIODS
        out = {}
        for a in assets:
            df = pd.concat([rets[a], X_all], axis=1).dropna()
            df = df[df.index < upto]            # strictly past data
            if len(df) >= min_obs:
                try:
                    X = sm.add_constant(df.iloc[:, 1:].values)
                    res = sm.OLS(df[a].values, X).fit(
                        cov_type="HAC", cov_kwds={"maxlags": hac_lags})
                    out[a] = float(res.params @ np.r_[1.0, x_now.values]) * PERIODS
                    continue
                except Exception:
                    pass
            out[a] = hist[a]
        return pd.Series(out).reindex(assets)

    weights_rows, realized = {}, {}
    prev_w = None
    turnover = {}
    for t in oos_months:
        mu = fit_mu(t)
        if mu is None:
            continue
        train_rets = rets.loc[:t].iloc[:-1].dropna()   # returns strictly before t
        if len(train_rets) < min_obs:
            continue
        if cov_choice.startswith("Ledoit"):
            cov, _ = ledoit_wolf_cov(train_rets)
        else:
            cov = sample_cov(train_rets)
        try:
            if objective.startswith("Max return"):
                res = O.optimize(mu, cov, target_vol=target_vol,
                                 min_weight=min_w, max_weight=max_w)
            else:
                res = max_sharpe_l2(mu, cov, min_weight=min_w, max_weight=max_w,
                                    l2=l2, group_bounds=[(equity, 0.0, eq_cap)])
        except Exception:
            continue
        w = res["weights"].reindex(assets).fillna(0.0)
        weights_rows[t] = w
        realized[t] = float((w * rets.loc[t]).sum())
        turnover[t] = 0.5 * float((w - prev_w).abs().sum()) if prev_w is not None else np.nan
        prev_w = w

    if not weights_rows:
        return {"empty": True}

    weights = pd.DataFrame(weights_rows).T
    weights.index = weights.index.to_timestamp(how="end").normalize()
    port = pd.Series(realized).rename("Strategy")
    port.index = port.index.to_timestamp(how="end").normalize()
    turn = pd.Series(turnover).rename("Turnover")
    turn.index = turn.index.to_timestamp(how="end").normalize()

    perf = port.to_frame()
    bench = load_benchmark()
    if bench is not None and "BENCH_60_40" in bench.columns:
        b = bench["BENCH_60_40"].rename("Benchmark 60/40")
        perf = perf.join(b, how="left")

    ann = perf.mean() * PERIODS
    vol = perf.std() * np.sqrt(PERIODS)
    summary = pd.DataFrame({"Ann. Return": ann, "Ann. Vol": vol,
                            "Sharpe": ann / vol})

    last_w = weights.iloc[-1]
    prev = weights.iloc[-2] if len(weights) > 1 else pd.Series(0.0, index=assets)
    trades = pd.DataFrame({"Weight": last_w, "Prev weight": prev,
                           "Trade (Δw)": last_w - prev})

    return {
        "empty": False,
        "perf": perf,
        "weights": weights,
        "turnover": turn,
        "trades": trades,
        "summary": summary,
        "oos_start": port.index.min(),
        "oos_end": port.index.max(),
        "avg_turnover": float(turn.mean(skipna=True)),
    }


@st.cache_data(show_spinner=False)
def summary_stats() -> pd.DataFrame:
    """Annualized return / vol / Sharpe per asset."""
    r = load_returns()
    ann_ret = r.mean() * PERIODS
    ann_vol = r.std() * np.sqrt(PERIODS)
    out = pd.DataFrame({
        "Ann. Return": ann_ret,
        "Ann. Vol": ann_vol,
        "Sharpe": ann_ret / ann_vol,
    })
    return out.sort_values("Ann. Return", ascending=False)


ASSET_LABELS = {
    "SPY": "US Large Cap", "VXF": "US Mid+Small", "EWC": "Canada",
    "EFA": "Intl Developed", "VWO": "Emerging Eq (VEIEX→VWO)", "AGG": "US Agg Bonds",
    "EMB": "EM Bonds (PYEMX→EMB)", "DBC": "Commodities (PCRIX→DBC)",
    "INTL_BOND": "Intl Bonds (PFORX→BNDX)",
}

# Human-readable names for the cryptic macro factor codes.
FACTOR_LABELS = {
    "HEADLINE_CPI_USA": "Headline CPI",
    "CORE_CPI_USA": "Core CPI",
    "IRSTCI_USA": "Policy Rate",
    "IR3TIB_USA": "3M Interbank Rate",
    "IRLT_USA": "10Y Gov Yield",
    "DGS2_USA": "2Y Treasury Yield",
    "DIV_YIELD_USA": "Dividend Yield",
    "CREDIT_SPREAD_BAA_USA": "Baa Credit Spread",
    "CREDIT_SPREAD_AAA_USA": "Aaa Credit Spread",
    "HY_SPREAD_USA": "High-Yield Spread",
    "SPREAD_10Y3M_USA": "Term Spread 10Y–3M",
    "SPREAD_10Y2Y_USA": "Term Spread 10Y–2Y",
    "SPREAD_BAA_AAA_USA": "Baa–Aaa Spread",
    "PMI_Composite_US": "Composite PMI",
    # derived factors (per Greg's meeting)
    "INFLATION_ACCEL": "Inflation Acceleration (ΔCPI)",
    "EXCESS_DIV_YIELD": "Excess Dividend Yield",
    "LOG_VIX": "Log VIX",
    "PMI_CHANGE": "PMI Change (MoM)",
}


def factor_label(code: str) -> str:
    return FACTOR_LABELS.get(code, code)


def asset_label(code: str) -> str:
    return ASSET_LABELS.get(code, code)
