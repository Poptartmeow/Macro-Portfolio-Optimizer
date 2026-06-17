"""Risk report — Sharpe, VaR/CVaR, drawdown, correlation matrix."""

import sys as _sys
from pathlib import Path as _Path
for _p in (_Path(__file__).resolve().parent, _Path(__file__).resolve().parent.parent):
    if (_p / "data_access.py").exists() and str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import data_access as da
import theme

st.set_page_config(page_title="Risk", layout="wide")
theme.apply_theme()

st.markdown("# Risk")
st.markdown(theme.flow_diagram(active="Risk"), unsafe_allow_html=True)

rets = da.load_returns()
PERIODS = da.PERIODS

# ── Equal-weight portfolio as a stand-in until optimizer weights are wired in ──
port = rets.mean(axis=1)
ann_ret = port.mean() * PERIODS
ann_vol = port.std() * np.sqrt(PERIODS)
sharpe = ann_ret / ann_vol
var95 = np.percentile(port, 5)
cvar95 = port[port <= var95].mean()
cum = (1 + port).cumprod()
drawdown = cum / cum.cummax() - 1
max_dd = drawdown.min()

st.caption("Headline metrics for an equal-weight portfolio (placeholder until the "
           "optimizer weights + backtester feed in).")
k = st.columns(5)
k[0].markdown(theme.kpi("Ann. return", f"{ann_ret*100:.1f}", "%"), unsafe_allow_html=True)
k[1].markdown(theme.kpi("Ann. vol", f"{ann_vol*100:.1f}", "%"), unsafe_allow_html=True)
k[2].markdown(theme.kpi("Sharpe", f"{sharpe:.2f}"), unsafe_allow_html=True)
k[3].markdown(theme.kpi("Monthly VaR 95%", f"{var95*100:.1f}", "%"), unsafe_allow_html=True)
k[4].markdown(theme.kpi("Max drawdown", f"{max_dd*100:.1f}", "%"), unsafe_allow_html=True)

st.write("")
left, right = st.columns(2)

with left:
    st.subheader("Drawdown")
    fig = go.Figure(go.Scatter(
        x=drawdown.index, y=drawdown * 100, fill="tozeroy", mode="lines",
        line=dict(color=theme.ROTUNDA_ORANGE, width=1.5),
        fillcolor="rgba(229,114,0,0.25)"))
    fig.update_layout(yaxis_title="Drawdown (%)")
    st.plotly_chart(theme.style_fig(fig, height=380), width='stretch')

with right:
    st.subheader("Correlation matrix")
    corr = rets.corr()
    labels = [da.ASSET_LABELS.get(c, c) for c in corr.columns]
    hm = go.Figure(go.Heatmap(
        z=corr.values, x=labels, y=labels,
        colorscale=theme.DIVERGING, zmid=0,
        text=corr.round(2).values, texttemplate="%{text}", textfont=dict(size=9),
        colorbar=dict(title="ρ")))
    st.plotly_chart(theme.style_fig(hm, height=380), width='stretch')

st.subheader("Return distribution (equal-weight portfolio)")
hist = go.Figure(go.Histogram(x=port * 100, nbinsx=40,
                              marker=dict(color=theme.CYAN)))
hist.add_vline(x=var95 * 100, line=dict(color=theme.ROTUNDA_ORANGE, dash="dash"),
               annotation_text="VaR 95%")
hist.update_layout(xaxis_title="Monthly return (%)", yaxis_title="Count")
st.plotly_chart(theme.style_fig(hist, height=320), width='stretch')
