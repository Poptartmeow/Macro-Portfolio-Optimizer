"""Regime section — rendered as a tab inside the Macro page."""

import sys
from pathlib import Path

_DASH = str(Path(__file__).resolve().parent)
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)
_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import data_access as da
import theme
from macro_portfolio.research import regime as R

REGIME_COLORS = {
    "Expansion": "#4DD0A7",     # growth strong & rising
    "Slowdown": "#FFD166",      # late-cycle: strong but decelerating
    "Contraction": "#FF6B6B",   # recession
    "Recovery": theme.CYAN,     # turning up from a trough
}


def render() -> None:
    st.caption("Each month is labelled from composite PMI (above/below 50) and its "
               "3-month momentum, with CPI as context — a transparent rules-based "
               "version of the macro agent in Ang et al. (2026).")

    reg = da.load_regime()
    cur = R.current(reg)

    last = reg.dropna(subset=["regime"]).iloc[-1]
    k = st.columns(4)
    rc = REGIME_COLORS.get(cur["regime"], theme.WHITE)
    k[0].markdown(
        f"<div class='glass'><div class='kpi-label'>Current regime</div>"
        f"<div class='kpi-value' style='color:{rc}'>{cur['regime']}</div></div>",
        unsafe_allow_html=True)
    k[1].markdown(theme.kpi("Composite PMI", f"{last['PMI']:.1f}"), unsafe_allow_html=True)
    cpi = last.get("CPI_YoY")
    k[2].markdown(theme.kpi("CPI YoY", f"{cpi:.1f}" if cpi == cpi else "n/a", "%"),
                  unsafe_allow_html=True)
    k[3].markdown(theme.kpi("Months in regime", str(cur["months_in_regime"])),
                  unsafe_allow_html=True)

    st.subheader("PMI & regime timeline")
    r = reg.dropna(subset=["regime"])
    fig = go.Figure()
    seg_start = r.index[0]
    prev = r["regime"].iloc[0]
    idx = list(r.index)
    for i in range(1, len(idx) + 1):
        if i == len(idx) or r["regime"].iloc[i] != prev:
            x1 = idx[i] if i < len(idx) else idx[-1]
            fig.add_vrect(x0=seg_start, x1=x1, fillcolor=REGIME_COLORS[prev],
                          opacity=0.16, line_width=0, layer="below")
            if i < len(idx):
                seg_start = idx[i]
                prev = r["regime"].iloc[i]
    fig.add_trace(go.Scatter(x=r.index, y=r["PMI"], mode="lines",
                             line=dict(color=theme.WHITE, width=2),
                             name="Composite PMI"))
    fig.add_hline(y=50, line=dict(color=theme.SLATE, dash="dash"),
                  annotation_text="50 = expansion line")
    fig.update_layout(yaxis_title="Composite PMI", hovermode="x unified")
    st.plotly_chart(theme.style_fig(fig, height=380), width='stretch')
    legend = "  ".join(
        f"<span class='badge' style='background:{c}33;color:{c};border-color:{c}'>{n}</span>"
        for n, c in REGIME_COLORS.items())
    st.markdown(legend, unsafe_allow_html=True)

    st.write("")
    left, right = st.columns([2, 3])
    with left:
        st.subheader("Time spent in each regime")
        counts = reg["regime"].value_counts().reindex(R.REGIMES).dropna()
        pie = go.Figure(go.Bar(
            x=counts.values, y=counts.index, orientation="h",
            marker=dict(color=[REGIME_COLORS[i] for i in counts.index]),
            text=[f"{v} mo" for v in counts.values], textposition="auto"))
        pie.update_layout(xaxis_title="Months")
        st.plotly_chart(theme.style_fig(pie, height=300), width='stretch')
    with right:
        st.subheader("How each asset behaves by regime")
        rets = da.load_returns()
        cond = R.conditional_returns(rets, reg) * 100
        labels = [da.ASSET_LABELS.get(a, a) for a in cond.index]
        hm = go.Figure(go.Heatmap(
            z=cond.values, x=list(cond.columns), y=labels,
            colorscale=theme.DIVERGING, zmid=0,
            text=cond.round(0).values, texttemplate="%{text}", textfont=dict(size=10),
            colorbar=dict(title="ann %"),
            hovertemplate="%{y}<br>%{x}<br>%{z:.1f}% annualized<extra></extra>"))
        st.plotly_chart(theme.style_fig(hm, height=300), width='stretch')

    st.caption("Annualized mean return per asset, conditioned on the regime that "
               "month (in-sample). Equities lead in Recovery/Expansion and fall "
               "hardest in Contraction, where bonds hold up — the case for the tilt.")
