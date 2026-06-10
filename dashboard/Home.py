"""
UVA Macro Portfolio Optimizer — dashboard entry point (Home / Overview).

Run from the repo root:
    streamlit run dashboard/Home.py
"""

import sys as _sys
from pathlib import Path as _Path
for _p in (_Path(__file__).resolve().parent, _Path(__file__).resolve().parent.parent):
    if (_p / "data_access.py").exists() and str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import plotly.graph_objects as go
import streamlit as st

import data_access as da
import theme

st.set_page_config(page_title="UVA Macro Portfolio Optimizer", layout="wide")
theme.apply_theme()

# ── Header ──
st.markdown("# Global Macro Portfolio Optimizer")
st.markdown(
    "<span class='badge'>UVA MSDS</span> &nbsp; "
    "<span class='badge'>Vanco Global Advisors</span> &nbsp; "
    "<span class='badge'>Capstone Project</span> &nbsp; "
    "<span class='badge'>Risk Analytics Platform</span>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div style='color:#9AA5B8; margin-top:8px; font-size:0.9rem;'>"
    "Authors: Mauricio Torres, Jack Joy, Tianyin Mao, Tiandra Threat</div>",
    unsafe_allow_html=True,
)
st.markdown(theme.flow_diagram(active="Dashboard"), unsafe_allow_html=True)
st.caption("System pipeline — the dashboard is the consumer at the end of the chain.")

# ── Data ──
rets = da.load_returns()
facs = da.load_factors()

# ── KPI row ──
c1, c2, c3, c4 = st.columns(4)
span = f"{rets.index.min().year}–{rets.index.max().year}"
c1.markdown(theme.kpi("Assets", str(rets.shape[1])), unsafe_allow_html=True)
c2.markdown(theme.kpi("Macro factors", str(facs.shape[1])), unsafe_allow_html=True)
c3.markdown(theme.kpi("Months of returns", str(len(rets))), unsafe_allow_html=True)
c4.markdown(theme.kpi("Coverage", span), unsafe_allow_html=True)

st.write("")

# ── Growth of $1 across all assets ──
left, right = st.columns([3, 2])

with left:
    st.subheader("Growth of $1 — aligned window")
    cum = (1 + rets).cumprod()
    fig = go.Figure()
    for col in cum.columns:
        fig.add_trace(go.Scatter(
            x=cum.index, y=cum[col], mode="lines", name=col,
            hovertemplate=f"{col}: %{{y:.2f}}<extra></extra>"))
    fig.update_layout(yaxis_title="Growth of $1", hovermode="x unified")
    st.plotly_chart(theme.style_fig(fig, height=420), width='stretch')

with right:
    st.subheader("Risk / return")
    stats = da.summary_stats()
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=stats["Ann. Vol"] * 100, y=stats["Ann. Return"] * 100,
        mode="markers+text", text=stats.index, textposition="top center",
        marker=dict(size=13, color=theme.ROTUNDA_ORANGE,
                    line=dict(width=1, color="white")),
        hovertemplate="%{text}<br>vol %{x:.1f}%<br>ret %{y:.1f}%<extra></extra>"))
    fig2.update_layout(xaxis_title="Ann. Volatility (%)",
                       yaxis_title="Ann. Return (%)")
    st.plotly_chart(theme.style_fig(fig2, height=420), width='stretch')

st.write("")
st.subheader("Per-asset summary")
show = da.summary_stats().copy()
show.insert(0, "Asset", [da.ASSET_LABELS.get(i, i) for i in show.index])
show.index.name = "Ticker"
st.dataframe(
    show.style.format({"Ann. Return": "{:.2%}", "Ann. Vol": "{:.2%}",
                       "Sharpe": "{:.2f}"}),
    width='stretch',
)

st.caption("Use the pages in the sidebar: Macro Regressions · Optimizer · Risk Report. "
           "Reading existing data/*.csv; result tables in DASHBOARD_PLAN.md are next.")
