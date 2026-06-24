"""
Dashboard data layer — thin, cached wrappers over the `macro_portfolio` package.

All real logic lives in src/ (loaders in `macro_portfolio.data`; regressions,
expected returns, and the backtest in `macro_portfolio.research.*`). This module
only adds Streamlit caching and keeps the dashboard's presentation helpers
(asset/factor labels). Pages import this; they never compute here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from macro_portfolio import data as _data                                  # noqa: E402
from macro_portfolio.research import regression as _regression            # noqa: E402
from macro_portfolio.research import expected_returns as _er              # noqa: E402
from macro_portfolio.research import backtest as _backtest               # noqa: E402
from macro_portfolio.research.expected_returns import DEFAULT_ER_FACTORS  # noqa: E402,F401

PERIODS = _data.PERIODS


# ── Cached loaders (logic in macro_portfolio.data) ──
@st.cache_data(show_spinner=False)
def load_returns():
    return _data.load_returns()


@st.cache_data(show_spinner=False)
def load_benchmark():
    return _data.load_benchmark()


@st.cache_data(show_spinner=False)
def load_factors():
    return _data.load_factors()


@st.cache_data(show_spinner=False)
def load_fill_log():
    return _data.load_fill_log()


@st.cache_data(show_spinner=False)
def summary_stats():
    return _data.summary_stats()


@st.cache_data(show_spinner=False)
def load_regime():
    """Monthly macro regime labels (Expansion/Slowdown/Contraction/Recovery)."""
    from macro_portfolio.research import regime as R
    return R.classify(load_factors())


def window_label() -> str:
    """Human-readable 'YYYY–YYYY' span of the aligned returns (for KPIs/captions)."""
    idx = load_returns().index
    return f"{idx.min().year}–{idx.max().year}"


# ── Cached compute wrappers (logic in macro_portfolio.research.*) ──
@st.cache_data(show_spinner=True)
def univariate_sweep(lag: int = 0, transform: str = "level",
                     hac_lags: int = 6, min_obs: int = 24):
    return _regression.univariate_sweep(
        load_returns(), load_factors(),
        lag=lag, transform=transform, hac_lags=hac_lags, min_obs=min_obs)


@st.cache_data(show_spinner=True)
def regression_expected_returns(factors, lag: int = 1, transform: str = "level",
                                hac_lags: int = 6, min_obs: int = 36,
                                train_end: str | None = None):
    return _er.regression_expected_returns(
        load_returns(), load_factors(), tuple(factors),
        lag=lag, transform=transform, hac_lags=hac_lags,
        min_obs=min_obs, train_end=train_end)


@st.cache_data(show_spinner=True)
def rolling_backtest(factors, lag, transform, train_end, objective, cov_choice,
                     min_w, max_w, target_vol, l2, eq_cap, equity,
                     hac_lags: int = 6, min_obs: int = 36):
    return _backtest.rolling_backtest(
        load_returns(), load_factors(), load_benchmark(), tuple(factors),
        lag, transform, train_end, objective, cov_choice, min_w, max_w,
        target_vol, l2, eq_cap, tuple(equity), hac_lags=hac_lags, min_obs=min_obs)


# ── Presentation helpers (dashboard-only: labels for the cryptic codes) ──
ASSET_LABELS = {
    "SPY": "US Large Cap", "VXF": "US Mid+Small", "EWC": "Canada",
    "EFA": "Intl Developed", "VWO": "Emerging Eq (VEIEX→VWO)", "AGG": "US Agg Bonds",
    "EMB": "EM Bonds (PYEMX→EMB)", "DBC": "Commodities (PCRIX→DBC)",
    "INTL_BOND": "Intl Bonds (PFORX→BNDX)",
}

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
