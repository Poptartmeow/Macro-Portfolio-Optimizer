"""Data, assets (left-hand side) and macro factors (right-hand side)."""

import sys as _sys
from pathlib import Path as _Path
for _p in (_Path(__file__).resolve().parent, _Path(__file__).resolve().parent.parent):
    if (_p / "data_access.py").exists() and str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import pandas as pd
import streamlit as st

import data_access as da
import theme

st.set_page_config(page_title="Data", layout="wide")
theme.apply_theme()

st.markdown("# Data")
st.markdown(theme.flow_diagram(active="Data"), unsafe_allow_html=True)

rets = da.load_returns()

st.markdown("Everything here is public and free, pulled and cleaned by our Python "
            "pipeline, with nothing proprietary.")

k = st.columns(3)
k[0].markdown(theme.kpi("Aligned window", da.window_label()), unsafe_allow_html=True)
k[1].markdown(theme.kpi("Months", str(len(rets))), unsafe_allow_html=True)
k[2].markdown(theme.kpi("Assets", str(rets.shape[1])), unsafe_allow_html=True)
st.write("")

ASSET_CLASS = {
    "SPY": "US equity", "VXF": "US equity",
    "EFA": "Intl equity", "VWO": "Intl equity", "EWC": "Intl equity",
    "AGG": "Bonds", "INTL_BOND": "Bonds", "EMB": "Bonds",
    "DBC": "Commodities",
}
FACTOR_CATEGORY = {
    "HEADLINE_CPI_USA": "Inflation", "CORE_CPI_USA": "Inflation",
    "IRSTCI_USA": "Rates", "IR3TIB_USA": "Rates", "IRLT_USA": "Rates",
    "DGS2_USA": "Rates", "DIV_YIELD_USA": "Valuation",
    "CREDIT_SPREAD_BAA_USA": "Credit", "CREDIT_SPREAD_AAA_USA": "Credit",
    "HY_SPREAD_USA": "Credit", "SPREAD_BAA_AAA_USA": "Credit",
    "SPREAD_10Y3M_USA": "Term spread", "SPREAD_10Y2Y_USA": "Term spread",
    "INFLATION_ACCEL": "Inflation", "EXCESS_DIV_YIELD": "Valuation",
    "LOG_VIX": "Volatility", "PMI_CHANGE": "Growth",
}

tab_assets, tab_factors = st.tabs(["Assets", "Macro Factors"])

# ─────────────────────────────────────────────
# ASSETS (left-hand side)
# ─────────────────────────────────────────────
with tab_assets:
    st.caption("The **left-hand side**, the nine ETFs we allocate across. In "
               "regression terms, these are the variables we model and hold.")
    st.markdown(
        "Nine liquid ETFs from Yahoo Finance: US large and mid/small-cap equity "
        "(SPY, VXF), international developed, emerging-market, and Canadian equity "
        "(EFA, VWO, EWC), US aggregate, international, and emerging-market bonds "
        "(AGG, INTL_BOND, EMB), and broad commodities (DBC), as monthly total "
        f"returns from {da.window_label().replace('–', ' to ')}. Several series are "
        "chain-linked splices — international bonds (PFORX → BNDX), EM bonds "
        "(PYEMX → EMB), commodities (PCRIX → DBC), and EM equities (VEIEX → VWO) — "
        "so each reaches back to ~2002, before its ETF existed. The aligned window "
        "is now bound by US aggregate bonds (AGG, Oct 2003). We also pull the 60/40 "
        "ACWI/IGOV benchmark for comparison.")

    uni = da.summary_stats().copy()
    uni.insert(0, "Asset", [da.ASSET_LABELS.get(i, i) for i in uni.index])
    uni.insert(1, "Class", [ASSET_CLASS.get(i, "") for i in uni.index])
    uni.index.name = "Ticker"
    uni = uni.sort_values(["Class", "Ann. Return"], ascending=[True, False])
    st.dataframe(
        uni.style.format({"Ann. Return": "{:.2%}", "Ann. Vol": "{:.2%}",
                          "Sharpe": "{:.2f}"}),
        width='stretch')

# ─────────────────────────────────────────────
# MACRO FACTORS (right-hand side)
# ─────────────────────────────────────────────
with tab_factors:
    st.caption("The **right-hand side**, the macro series we use to explain and "
               "predict asset returns. All US, all monthly.")
    st.markdown(
        "A US panel sourced from FRED and OECD: headline and core CPI, the policy "
        "rate and short-term rates, the 2-year and 10-year Treasury yields and the "
        "term/credit spreads, the dividend yield, and investment-grade and high-yield "
        "credit spreads, plus a composite ISM PMI. The usable window now starts in "
        "October 2003: emerging-market bonds, commodities, and EM equities have all "
        "been spliced to pre-ETF proxy funds (PYEMX, PCRIX, VEIEX) that reach back to "
        "2002, so US aggregate bonds (AGG, Oct 2003) are now the latest-starting "
        "series and bound the common, gap-free window. The earlier start captures the "
        "full 2008 financial crisis.")

    st.subheader("Macro Panel")
    st.markdown(
        "Each row is one macro series. **factor**, readable name; **category**, "
        "what it measures; **name**, the raw data code; **missing_pct**, share of "
        "months missing in the raw data; **action**, cleaning applied (kept as-is, "
        "interpolated, or dropped); **n_filled**, number of monthly values filled in.")
    log = da.load_fill_log()
    if log is not None:
        disp = log.rename(columns={"column": "name"}).copy()
        disp.insert(0, "factor", [da.FACTOR_LABELS.get(c, c) for c in disp["name"]])
        disp.insert(1, "category", [FACTOR_CATEGORY.get(c, "") for c in disp["name"]])
        st.dataframe(disp, width='stretch', hide_index=True)

        fac = da.load_factors()
        n_pending = int(log["action"].astype(str).str.contains("PENDING", case=False).sum())
        n_derived = int(log["source"].astype(str).str.contains("derived|yfinance|PMI", case=False).sum()) \
            if "source" in log.columns else 0
        n_fill = int((log["n_filled"] > 0).sum())
        st.markdown(
            f"<div class='glass'><code>research/curate.py</code> builds the factor panel "
            f"from the 2002 FRED/OECD source: <b>{fac.shape[0]} monthly observations × "
            f"{fac.shape[1]} factors</b> back to 2002. <b>{n_fill}</b> base series had small "
            f"interior gaps filled by interpolation; <b>{n_derived}</b> factors are derived "
            f"or fetched (inflation acceleration, excess dividend yield, log-VIX, PMI change); "
            f"<b>{n_pending}</b> are flagged <b>PENDING</b> (high-yield spread, earnings-yield "
            f"premium) until we source them. The table shows exactly what happened to each. "
            f"<br><span style='color:#9AA5B8'>Cleaning rule: only carry information "
            f"forward or interpolate between known points, never backfill the past, "
            f"so no look-ahead bias.</span></div>",
            unsafe_allow_html=True)
    else:
        st.info("Run `python -m macro_portfolio.research.curate` to generate the "
                "cleaned macro panel and fill log.")
