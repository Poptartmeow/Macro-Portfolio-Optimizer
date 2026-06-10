"""Data Quality — coverage, the binding window, and the macro gap-fill log."""

import sys as _sys
from pathlib import Path as _Path
for _p in (_Path(__file__).resolve().parent, _Path(__file__).resolve().parent.parent):
    if (_p / "data_access.py").exists() and str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_access as da
import theme

st.set_page_config(page_title="Data Quality", layout="wide")
theme.apply_theme()

st.markdown("# Data Quality")
st.markdown(theme.flow_diagram(active="Ingest"), unsafe_allow_html=True)

# ── Coverage of each asset (full history) ──
full = pd.read_csv(da.DATA_DIR / "returns_full.csv", index_col=0, parse_dates=True)
rets = da.load_returns()
first = full.apply(lambda c: c.first_valid_index()).map(pd.Timestamp)
binder = first.idxmax()
binder_start = pd.Timestamp(first[binder])

k = st.columns(3)
k[0].markdown(theme.kpi("Aligned window", "2008–2026"), unsafe_allow_html=True)
k[1].markdown(theme.kpi("Months", str(len(rets))), unsafe_allow_html=True)
k[2].markdown(theme.kpi("Assets", str(rets.shape[1])), unsafe_allow_html=True)

st.subheader("Asset coverage (first available month)")
order = first.sort_values()
cfig = go.Figure(go.Bar(
    x=[pd.Timestamp(d).year + pd.Timestamp(d).month / 12 for d in order.values],
    y=[da.ASSET_LABELS.get(i, i) for i in order.index], orientation="h",
    marker=dict(color=theme.CYAN),
    text=[pd.Timestamp(d).date().isoformat() for d in order.values],
    textposition="auto"))
cfig.update_layout(xaxis_title="First available (year)")
st.plotly_chart(theme.style_fig(cfig, height=320), width='stretch')
st.caption(f"The aligned window can only start once every asset has data, so the "
           f"latest-starting asset sets it — here **{binder}** "
           f"({binder_start.strftime('%b %Y')}). Splicing {binder} with a pre-2008 "
           f"proxy would reclaim ~2007 (incl. the GFC onset).")

# ── Macro factor missingness + fill log ──
st.subheader("Macro panel — cleaning & gap-fill log")
log = da.load_fill_log()
if log is not None:
    st.dataframe(log, width='stretch', hide_index=True)
    st.caption("From research/curate.py. Rule: only carry information forward or "
               "interpolate between known points — never backfill the past "
               "(no look-ahead bias).")
else:
    st.info("Run `python -m macro_portfolio.research.curate` to generate the "
            "cleaned macro panel and fill log.")

# ── Raw vs cleaned row counts ──
raw = pd.read_csv(da.DATA_DIR / "us_macro_2007_2026.csv")
st.markdown(
    f"<div class='glass'>Raw macro file: <b>{len(raw):,} rows</b> "
    f"(~23 duplicate rows per month) → cleaned to "
    f"<b>{da.load_factors().shape[0]} monthly rows</b>. The panel is currently "
    f"assembled manually; with fewer time constraints a programmatic FRED/OECD "
    f"pull would make it fully reproducible and easy to refresh.</div>",
    unsafe_allow_html=True)
