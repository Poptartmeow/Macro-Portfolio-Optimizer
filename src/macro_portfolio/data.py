"""
Pure data loaders for the macro portfolio: CSV → DataFrame.

No streamlit, no caching — just reads the canonical files via `paths`. The
dashboard wraps these with its own caching layer; scripts/notebooks/tests can
import them directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro_portfolio import paths

PERIODS = 12  # months per year (annualization factor)


def load_returns() -> pd.DataFrame:
    """Aligned monthly asset returns (the optimizer input), indexed by month-end."""
    return pd.read_csv(paths.MARKET_PROCESSED / "returns_aligned.csv",
                       index_col=0, parse_dates=True)


def load_benchmark() -> pd.DataFrame | None:
    """60/40 ACWI/IGOV monthly returns, or None if not fetched yet."""
    p = paths.MARKET_PROCESSED / "benchmark_returns.csv"
    return pd.read_csv(p, index_col=0, parse_dates=True) if p.exists() else None


def load_factors() -> pd.DataFrame:
    """Monthly macro factor panel (cleaned curate.py output) + composite PMI."""
    curated = paths.MACRO_PROCESSED / "macro_monthly.csv"
    if curated.exists():
        macro = pd.read_csv(curated, index_col=0, parse_dates=True)
    else:  # fallback: clean the raw panel on the fly
        macro = pd.read_csv(paths.MACRO_RAW / "us_macro_2007_2026.csv")
        macro["Month"] = pd.PeriodIndex(macro["Month"], freq="M")
        macro = macro.groupby("Month").mean(numeric_only=True)
        macro.index = macro.index.to_timestamp(how="end").normalize()

    pmi = pd.read_csv(paths.MACRO_PMI / "PMI_Composite_US.csv", parse_dates=["date"])
    pmi = pmi.set_index("date")[["PMI_Composite_US"]]
    pmi.index = pmi.index.to_period("M").to_timestamp(how="end").normalize()

    return macro.join(pmi, how="outer").sort_index()


def load_fill_log() -> pd.DataFrame | None:
    """The macro gap-filling / factor-source log written by curate.py, if present."""
    p = paths.MACRO_PROCESSED / "macro_fill_log.csv"
    return pd.read_csv(p) if p.exists() else None


def summary_stats(returns: pd.DataFrame | None = None) -> pd.DataFrame:
    """Annualized return / vol / Sharpe per asset (sorted by return)."""
    r = load_returns() if returns is None else returns
    ann_ret = r.mean() * PERIODS
    ann_vol = r.std() * np.sqrt(PERIODS)
    return pd.DataFrame({
        "Ann. Return": ann_ret,
        "Ann. Vol": ann_vol,
        "Sharpe": ann_ret / ann_vol,
    }).sort_values("Ann. Return", ascending=False)


def to_month(idx: pd.DatetimeIndex) -> pd.PeriodIndex:
    """Convert a month-end DatetimeIndex to a monthly PeriodIndex (for joins/shifts)."""
    return idx.to_period("M")
