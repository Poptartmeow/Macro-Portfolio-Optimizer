"""Optimizer — compare models and show how expected returns move the weights."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ensure dashboard/ is importable whether launched via Home.py or alone
_DASH = str(Path(__file__).resolve().parent.parent)
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)

import data_access as da
import theme

st.set_page_config(page_title="Optimizer", layout="wide")
theme.apply_theme()

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from macro_portfolio.optimizer import optimizer as O          # noqa: E402
from macro_portfolio.optimizer.advanced import max_sharpe_l2   # noqa: E402
from macro_portfolio.risk.covariance import (                  # noqa: E402
    sample_cov, ledoit_wolf_cov, condition_number)

st.markdown("# Optimizer")
st.markdown(theme.flow_diagram(active="Optimizer"), unsafe_allow_html=True)
st.caption("Tune a single optimizer and see how the box constraints flatten the "
           "expected-return signal. Expected returns = historical mean (macro model "
           "swaps in next). To compare all methods at once, see **Ensemble**.")

EQUITY = ["SPY", "VXF", "EWC", "EFA", "VWO"]
rets = da.load_returns()
mu = rets.mean() * 12

# ── Controls ──
c1, c2, c3 = st.columns(3)
objective = c1.selectbox("Objective",
                         ["Max return @ target vol (baseline)",
                          "Max Sharpe + L2 (diversified)"])
cov_choice = c2.selectbox("Covariance", ["Ledoit-Wolf (shrinkage)", "Sample"])
min_w, max_w = c3.slider("Weight box per asset", 0.0, 0.50, (0.03, 0.30), 0.01)

c4, c5, c6 = st.columns(3)
target_vol = c4.slider("Target vol (baseline only)", 0.04, 0.20, 0.10, 0.005)
l2 = c5.slider("L2 diversification (Max-Sharpe only)", 0.0, 2.0, 0.5, 0.1)
eq_cap = c6.slider("Equity group cap (Max-Sharpe only)", 0.30, 1.0, 0.55, 0.05)

# ── Covariance ──
if cov_choice.startswith("Ledoit"):
    cov, shrink = ledoit_wolf_cov(rets)
    cov_note = f"Ledoit-Wolf (shrinkage {shrink:.2f})"
else:
    cov, shrink = sample_cov(rets), None
    cov_note = "Sample"
cond = condition_number(cov)


def at_bound(w):
    return int(np.sum((w.values <= min_w + 1e-4) | (w.values >= max_w - 1e-4)))


def eff_n(w):
    return float(1.0 / np.sum(w.values ** 2))


# ── Run selected model ──
try:
    if objective.startswith("Max return"):
        res = O.optimize(mu, cov, target_vol=target_vol,
                         min_weight=min_w, max_weight=max_w)
    else:
        groups = [(EQUITY, 0.0, eq_cap)]
        res = max_sharpe_l2(mu, cov, min_weight=min_w, max_weight=max_w,
                            l2=l2, group_bounds=groups)
except Exception as e:
    st.error(f"Optimization failed: {e}")
    st.stop()

w = res["weights"]

# ── KPI row ──
k = st.columns(6)
k[0].markdown(theme.kpi("Expected return", f"{res['expected_return']*100:.2f}", "%"),
              unsafe_allow_html=True)
k[1].markdown(theme.kpi("Volatility", f"{res['volatility']*100:.2f}", "%"),
              unsafe_allow_html=True)
k[2].markdown(theme.kpi("Sharpe", f"{res['sharpe_ratio']:.2f}"), unsafe_allow_html=True)
k[3].markdown(theme.kpi("Assets at bound", f"{at_bound(w)}/9"), unsafe_allow_html=True)
k[4].markdown(theme.kpi("Effective N", f"{eff_n(w):.1f}"), unsafe_allow_html=True)
k[5].markdown(theme.kpi("Cov condition #", f"{cond:,.0f}"), unsafe_allow_html=True)
st.caption(f"Covariance: {cov_note}. 'Assets at bound' near 9 = corner solution "
           "(box dominates). 'Effective N' is how many assets effectively carry "
           "weight (higher = more diversified). Condition # lower = more stable.")

st.write("")
left, right = st.columns([3, 2])

with left:
    st.subheader("Optimal weights")
    ws = w.sort_values()
    bar = go.Figure(go.Bar(
        x=ws.values * 100, y=[da.ASSET_LABELS.get(i, i) for i in ws.index],
        orientation="h",
        marker=dict(color=ws.values * 100, colorscale=theme.SEQUENTIAL),
        text=[f"{v*100:.1f}%" for v in ws.values], textposition="auto"))
    bar.update_layout(xaxis_title="Weight (%)")
    st.plotly_chart(theme.style_fig(bar, height=420), width='stretch')

with right:
    st.subheader("Sensitivity: does a macro view move the weight?")
    asset = st.selectbox("Shock this asset's expected return", list(mu.index), index=4)
    grid = np.linspace(0.0, 0.16, 17)
    weights_path = []
    for v in grid:
        m2 = mu.copy(); m2[asset] = v
        try:
            if objective.startswith("Max return"):
                r2 = O.optimize(m2, cov, target_vol=target_vol,
                                min_weight=min_w, max_weight=max_w)
            else:
                r2 = max_sharpe_l2(m2, cov, min_weight=min_w, max_weight=max_w,
                                   l2=l2, group_bounds=[(EQUITY, 0.0, eq_cap)])
            weights_path.append(r2["weights"][asset] * 100)
        except Exception:
            weights_path.append(np.nan)
    sfig = go.Figure(go.Scatter(
        x=grid * 100, y=weights_path, mode="lines+markers",
        line=dict(color=theme.ROTUNDA_ORANGE, width=3)))
    sfig.add_vline(x=mu[asset] * 100, line=dict(color=theme.CYAN, dash="dash"),
                   annotation_text="current view")
    sfig.update_layout(xaxis_title=f"{asset} expected return view (%)",
                       yaxis_title=f"{asset} weight (%)")
    st.plotly_chart(theme.style_fig(sfig, height=380), width='stretch')
    st.caption("Step-shaped = the box forces near-binary floor/cap bets, so the "
               "macro signal gets flattened. Smoother is better (→ Black-Litterman).")

# ── vs 60/40 ACWI/IGOV benchmark ──
st.write("")
st.subheader("Optimized portfolio vs 60/40 ACWI/IGOV benchmark")
bench = da.load_benchmark()
if bench is None:
    st.info("Benchmark not fetched yet. Run:  "
            "`python -m macro_portfolio.pipelines.benchmark`")
else:
    wv = w.reindex(rets.columns).fillna(0.0)
    port = (rets * wv).sum(axis=1).rename("Optimized")
    b = bench["BENCH_60_40"].rename("Benchmark 60/40")
    df = pd.concat([port, b], axis=1).dropna()
    cum = (1 + df).cumprod()

    bl, br = st.columns([3, 2])
    with bl:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=cum.index, y=cum["Optimized"], name="Optimized",
                                 line=dict(color=theme.ROTUNDA_ORANGE, width=3)))
        fig.add_trace(go.Scatter(x=cum.index, y=cum["Benchmark 60/40"],
                                 name="Benchmark 60/40",
                                 line=dict(color=theme.CYAN, width=2.5, dash="dot")))
        fig.update_layout(yaxis_title="Growth of $1", hovermode="x unified")
        st.plotly_chart(theme.style_fig(fig, height=360), width='stretch')
    with br:
        ann = df.mean() * 12
        vol = df.std() * np.sqrt(12)
        comp = pd.DataFrame({"Ann. Return": ann, "Ann. Vol": vol,
                             "Sharpe": ann / vol})
        st.dataframe(comp.style.format({"Ann. Return": "{:.2%}",
                                        "Ann. Vol": "{:.2%}", "Sharpe": "{:.2f}"}),
                     width='stretch')
        excess = (ann["Optimized"] - ann["Benchmark 60/40"]) * 100
        st.markdown(
            f"<div class='glass'>Optimized vs benchmark: "
            f"<b>{excess:+.2f}%</b>/yr return, Sharpe "
            f"<b>{ann['Optimized']/vol['Optimized']:.2f}</b> vs "
            f"<b>{ann['Benchmark 60/40']/vol['Benchmark 60/40']:.2f}</b>."
            f"<br><span style='color:#9AA5B8'>In-sample, static weights, "
            f"{cum.index.min().year}–{cum.index.max().year} overlap.</span></div>",
            unsafe_allow_html=True)
    st.caption("Current weights applied across history vs the passive 60/40. "
               "A proper train/test backtest is the next build.")
