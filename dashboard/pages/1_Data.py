"""Data Quality — coverage, the binding window, and the macro gap-fill log."""

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

k = st.columns(3)
k[0].markdown(theme.kpi("Aligned window", "2008–2026"), unsafe_allow_html=True)
k[1].markdown(theme.kpi("Months", str(len(rets))), unsafe_allow_html=True)
k[2].markdown(theme.kpi("Assets", str(rets.shape[1])), unsafe_allow_html=True)

# ── Data sources (prose) ──
st.subheader("Data sources")
st.markdown(
    "Everything here is public and free, pulled and cleaned by our Python pipeline, "
    "with nothing proprietary. The market data is nine liquid ETFs from Yahoo "
    "Finance: US large and mid/small-cap equity (SPY, VXF), international developed, "
    "emerging-market, and Canadian equity (EFA, VWO, EWC), US aggregate, "
    "international, and emerging-market bonds (AGG, INTL_BOND, EMB), and broad "
    "commodities (DBC) — as monthly total returns from 2008 to 2026. International "
    "bonds are a chain-linked splice (PFORX → BNDX) so the series reaches back before "
    "BNDX existed, and we also pull the 60/40 ACWI/IGOV benchmark for comparison.")
st.markdown(
    "The macro data is a US panel sourced from FRED and OECD: headline and core CPI, "
    "the policy rate and short-term rates, the 2-year and 10-year Treasury yields and "
    "the term/credit spreads, the dividend yield, and investment-grade and high-yield "
    "credit spreads, plus a composite ISM PMI, all at monthly frequency. The usable "
    "window starts in January 2008 because emerging-market bonds (EMB) only launched "
    "as an ETF in late 2007; it's the latest-starting series, so it bounds the "
    "common, gap-free window. Splicing it to a pre 2008 proxy would reclaim roughly a "
    "year and the onset of the financial crisis.")

# ── Macro panel — cleaning & gap-fill log ──
st.subheader("Macro panel — cleaning & gap-fill log")
log = da.load_fill_log()
if log is not None:
    st.dataframe(log, width='stretch', hide_index=True)

    raw = pd.read_csv(da.DATA_DIR / "us_macro_2007_2026.csv")
    fac = da.load_factors()
    n_drop = int(log["action"].astype(str).str.contains("DROP", case=False).sum())
    n_fill = int((log["n_filled"] > 0).sum())
    n_clean = len(log) - n_drop - n_fill
    st.markdown(
        f"<div class='glass'>The raw macro file arrives messy — <b>{len(raw):,} rows</b> "
        f"with ~23 duplicate rows per month. <code>research/curate.py</code> collapses "
        f"it to <b>{fac.shape[0]} monthly observations × {fac.shape[1]} factors</b>: "
        f"<b>{n_clean}</b> series came through clean, <b>{n_fill}</b> were gap-filled "
        f"by interpolation, and <b>{n_drop}</b> was dropped as too sparse to trust "
        f"(the table above shows exactly what happened to each). "
        f"<br><span style='color:#9AA5B8'>Cleaning rule: only carry information "
        f"forward or interpolate between known points — never backfill the past, so "
        f"no look-ahead bias. The panel is assembled manually today; a programmatic "
        f"FRED/OECD pull is the next step to make refreshing it a one-command job."
        f"</span></div>",
        unsafe_allow_html=True)
else:
    st.info("Run `python -m macro_portfolio.research.curate` to generate the "
            "cleaned macro panel and fill log.")
