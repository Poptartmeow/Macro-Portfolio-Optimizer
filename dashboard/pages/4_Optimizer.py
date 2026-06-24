"""Optimizer, compare models and show how expected returns move the weights."""

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
           "expected-return signal. Expected returns can be the historical mean or "
           "a live macro-regression model (toggle below). To compare all methods at "
           "once, see **Ensemble**.")

EQUITY = ["SPY", "VXF", "EWC", "EFA", "VWO"]
rets = da.load_returns()

# ── Expected returns: historical mean vs macro-regression model ──
er_detail = None
with st.expander("Expected returns — historical mean vs macro-regression model",
                 expanded=False):
    er_mode = st.radio(
        "Source of expected returns (μ) fed to the optimizer",
        ["Historical mean", "Macro regression model"],
        horizontal=True,
        help="The macro model fits each asset's return on the selected macro "
             "factors and evaluates the fit at the latest factor values, so a "
             "current macro view drives μ instead of the long-run average.")
    if er_mode.startswith("Macro"):
        ec1, ec2, ec3 = st.columns([3, 1, 1])
        all_factors = list(da.load_factors().columns)
        defaults = [f for f in da.DEFAULT_ER_FACTORS if f in all_factors]
        chosen = ec1.multiselect(
            "Macro factors (regressors)", all_factors, default=defaults,
            format_func=da.factor_label)
        er_lag = ec2.slider("Factor lag (months)", 0, 6, 1)
        er_transform = ec3.selectbox("Transform", ["level", "change"])
        use_split = st.checkbox(
            "Train/test split — fit only through cutoff (reserve recent data)",
            value=True,
            help="Per the professor's scheme: fit the regression on data up to the "
                 "cutoff and hold out everything after it as out-of-sample.")
        train_end = None
        if use_split:
            train_end = st.text_input("Train cutoff (fit ≤ this month)", "2020-12-31")

if er_mode.startswith("Macro") and chosen:
    mu, er_detail = da.regression_expected_returns(
        tuple(chosen), lag=er_lag, transform=er_transform, train_end=train_end)
    mu = mu.reindex(rets.columns)
else:
    if er_mode.startswith("Macro"):
        st.warning("Select at least one macro factor — using historical mean for now.")
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

if er_detail is not None:
    with st.expander("Macro-model expected returns (μ fed to the optimizer)",
                     expanded=False):
        tbl = er_detail.copy()
        tbl.insert(0, "Asset", [da.asset_label(i) for i in tbl.index])
        tbl.insert(2, "Exp. Return (ann)", mu.reindex(tbl.index))
        st.dataframe(
            tbl.style.format({"Exp. Return (ann)": "{:.2%}", "R²": "{:.2f}",
                              "n": "{:.0f}"}),
            width='stretch')
        n_fallback = int((er_detail["Source"] == "historical (fallback)").sum())
        if n_fallback:
            st.caption(f"{n_fallback} asset(s) fell back to historical mean "
                       "(regression couldn't be fit on the chosen factors).")

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
               "For the proper walk-forward backtest, see below.")

# ── Walk-forward monthly rolling re-optimization ──
st.write("")
st.subheader("Walk-forward backtest — monthly rolling re-optimization")
st.caption("The professor's scheme: each out-of-sample month we re-fit the macro "
           "regressions on all prior data, build μ from the lagged factors, "
           "re-optimize, and trade the difference in weights. Uses the objective, "
           "covariance, and weight box selected above.")

# Factor config falls back to the defaults when the page is in historical-mean mode.
_bt_factors = tuple(chosen) if (er_mode.startswith("Macro") and chosen) \
    else tuple(f for f in da.DEFAULT_ER_FACTORS if f in da.load_factors().columns)
_bt_lag = er_lag if er_mode.startswith("Macro") else 1
_bt_transform = er_transform if er_mode.startswith("Macro") else "level"
_bt_cut = train_end if (er_mode.startswith("Macro") and train_end) else "2020-12-31"

bc1, bc2 = st.columns([2, 1])
bt_cut = bc1.text_input("Out-of-sample starts after (train cutoff)", _bt_cut,
                        key="bt_cut")
run_bt = bc2.button("Run walk-forward backtest", type="primary")

if run_bt:
    bt = da.rolling_backtest(
        _bt_factors, _bt_lag, _bt_transform, bt_cut,
        objective, cov_choice, min_w, max_w, target_vol, l2, eq_cap,
        tuple(EQUITY))
    if bt.get("empty", True):
        st.warning("Backtest produced no months — try an earlier cutoff or fewer factors.")
    else:
        m = st.columns(4)
        s = bt["summary"]
        m[0].markdown(theme.kpi("OOS window",
                      f"{bt['oos_start'].year}–{bt['oos_end'].year}"),
                      unsafe_allow_html=True)
        m[1].markdown(theme.kpi("Strategy Sharpe", f"{s.loc['Strategy','Sharpe']:.2f}"),
                      unsafe_allow_html=True)
        m[2].markdown(theme.kpi("Strategy ann. return",
                      f"{s.loc['Strategy','Ann. Return']*100:.2f}", "%"),
                      unsafe_allow_html=True)
        m[3].markdown(theme.kpi("Avg monthly turnover",
                      f"{bt['avg_turnover']*100:.1f}", "%"), unsafe_allow_html=True)

        bl2, br2 = st.columns([3, 2])
        with bl2:
            cum = (1 + bt["perf"]).cumprod()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=cum.index, y=cum["Strategy"], name="Strategy",
                                     line=dict(color=theme.ROTUNDA_ORANGE, width=3)))
            if "Benchmark 60/40" in cum.columns:
                fig.add_trace(go.Scatter(
                    x=cum.index, y=cum["Benchmark 60/40"], name="Benchmark 60/40",
                    line=dict(color=theme.CYAN, width=2.5, dash="dot")))
            fig.update_layout(yaxis_title="Growth of $1 (out-of-sample)",
                              hovermode="x unified")
            st.plotly_chart(theme.style_fig(fig, height=360), width='stretch')
        with br2:
            st.markdown("**Out-of-sample performance**")
            st.dataframe(
                s.style.format({"Ann. Return": "{:.2%}", "Ann. Vol": "{:.2%}",
                                "Sharpe": "{:.2f}"}), width='stretch')
            st.markdown("**Latest rebalance — trades (Δw)**")
            tr = bt["trades"].copy()
            tr.index = [da.asset_label(i) for i in tr.index]
            st.dataframe(
                tr.style.format("{:.1%}").background_gradient(
                    subset=["Trade (Δw)"], cmap="RdYlGn"),
                width='stretch')

        st.subheader("Weights through time")
        wfig = go.Figure()
        for col in bt["weights"].columns:
            wfig.add_trace(go.Scatter(
                x=bt["weights"].index, y=bt["weights"][col] * 100,
                name=da.asset_label(col), stackgroup="one", mode="lines"))
        wfig.update_layout(yaxis_title="Weight (%)", hovermode="x unified")
        st.plotly_chart(theme.style_fig(wfig, height=360), width='stretch')
        st.caption("Each month's allocation. The month-to-month change in these "
                   "lines is exactly what the strategy trades.")
