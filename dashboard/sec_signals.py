"""Signals section (macro regression sweep), rendered as a tab inside Macro."""

import sys
from pathlib import Path

_DASH = str(Path(__file__).resolve().parent)
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_access as da
import theme


def render() -> None:
    st.caption("Univariate OLS: asset return ~ factor, with HAC (Newey-West) standard "
               "errors. The live preview of the macro regression sweep.")

    c1, c2, c3 = st.columns(3)
    metric = c1.selectbox("Color by", ["t-stat", "beta", "R²"], index=0)
    transform = c2.selectbox("Factor transform", ["level", "change"], index=0)
    lag = c3.slider("Lag (months)", 0, 12, 1,
                    help="Regress return(t) on factor(t-lag). Lag>0 = predictive.")

    beta, tstat, nobs, r2 = da.univariate_sweep(lag=lag, transform=transform)

    if metric == "t-stat":
        Z, scale, zmid = tstat, theme.DIVERGING, 0
        title = f"t-statistic (|t|>2 ≈ significant) · lag {lag} · {transform}"
    elif metric == "beta":
        Z, scale, zmid = beta, theme.DIVERGING, 0
        title = f"Beta · lag {lag} · {transform}"
    else:
        Z, scale, zmid = r2, theme.SEQUENTIAL, None
        title = f"R² · lag {lag} · {transform}"

    Zv = Z.astype(float)
    Zlab = Zv.rename(index=da.ASSET_LABELS, columns=da.FACTOR_LABELS)
    txt = [["" if np.isnan(v) else f"{v:.2f}" for v in row] for row in Zv.values]
    heat = go.Figure(go.Heatmap(
        z=Zlab.values, x=list(Zlab.columns), y=list(Zlab.index),
        colorscale=scale, zmid=zmid,
        text=txt, texttemplate="%{text}", textfont=dict(size=10),
        hovertemplate="%{y}<br>%{x}<br>value %{z:.3f}<extra></extra>",
        colorbar=dict(title=metric)))
    heat.update_layout(title=title, xaxis_tickangle=-40)
    st.plotly_chart(theme.style_fig(heat, height=460), width='stretch')

    st.subheader("Drill-down")
    d1, d2 = st.columns(2)
    asset = d1.selectbox("Asset", list(beta.index), format_func=da.asset_label)
    factor = d2.selectbox("Factor", list(beta.columns), format_func=da.factor_label)

    rets = da.load_returns()
    facs = da.load_factors()
    rm = rets.copy(); rm.index = rm.index.to_period("M")
    fm = facs.copy(); fm.index = fm.index.to_period("M")
    if transform == "change":
        fm = fm.diff()
    xy = pd.concat([rm[asset], fm[factor].shift(lag)], axis=1,
                   keys=["ret", "fac"]).dropna()

    if len(xy) >= 12:
        sc = go.Figure()
        sc.add_trace(go.Scatter(x=xy["fac"], y=xy["ret"] * 100, mode="markers",
                                marker=dict(color=theme.CYAN, size=7,
                                            line=dict(width=0.5, color="white")),
                                name="months"))
        b, a = np.polyfit(xy["fac"], xy["ret"] * 100, 1)
        xs = np.linspace(xy["fac"].min(), xy["fac"].max(), 50)
        sc.add_trace(go.Scatter(x=xs, y=a + b * xs, mode="lines",
                                line=dict(color=theme.ROTUNDA_ORANGE, width=3),
                                name="OLS fit"))
        sc.update_layout(
            title=f"{da.asset_label(asset)} vs {da.factor_label(factor)} "
                  f"({transform}, lag {lag})",
            xaxis_title=da.factor_label(factor),
            yaxis_title=f"{da.asset_label(asset)} monthly return (%)")
        st.plotly_chart(theme.style_fig(sc, height=380), width='stretch')
        tval = tstat.loc[asset, factor]
        st.markdown(
            f"<div class='glass'>β = <b>{beta.loc[asset, factor]:.4f}</b> &nbsp;·&nbsp; "
            f"t = <b>{tval:.2f}</b> &nbsp;·&nbsp; R² = <b>{r2.loc[asset, factor]:.3f}</b> "
            f"&nbsp;·&nbsp; n = <b>{int(nobs.loc[asset, factor])}</b> &nbsp; "
            f"{'<span class=badge>significant</span>' if abs(tval) > 2 else ''}</div>",
            unsafe_allow_html=True)
    else:
        st.info("Not enough overlapping observations for this pair.")
