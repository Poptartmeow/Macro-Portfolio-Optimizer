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
    "EFA": "Intl Developed", "VWO": "Emerging Eq", "AGG": "US Agg Bonds",
    "EMB": "EM Bonds", "DBC": "Commodities", "INTL_BOND": "Intl Bonds (PFORX→BNDX)",
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
}


def factor_label(code: str) -> str:
    return FACTOR_LABELS.get(code, code)


def asset_label(code: str) -> str:
    return ASSET_LABELS.get(code, code)
