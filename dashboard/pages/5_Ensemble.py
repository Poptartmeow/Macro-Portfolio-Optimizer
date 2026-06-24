"""Methods & Ensemble, compare the full PC method library and combine them."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_DASH = str(Path(__file__).resolve().parent.parent)
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)

import data_access as da
import theme

st.set_page_config(page_title="Ensemble", layout="wide")
theme.apply_theme()

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from macro_portfolio.optimizer import methods as M               # noqa: E402
from macro_portfolio.risk.covariance import (                    # noqa: E402
    sample_cov, ledoit_wolf_cov)

st.markdown("# Ensemble")
st.markdown(theme.flow_diagram(active="Ensemble"), unsafe_allow_html=True)
st.caption("Eight portfolio-construction methods built on the same inputs, then "
           "combined into one ensemble (the CIO step in Ang et al. 2026). "
           "All pure-quant, no LLM, no lookahead. The **Optimizer** page tunes a "
           "single method interactively; this page compares them all.")

rets = da.load_returns()
mu = rets.mean() * 12

# ── Controls ──
c1, c2, c3 = st.columns(3)
cov_choice = c1.selectbox("Covariance", ["Ledoit-Wolf (shrinkage)", "Sample"])
max_w = c2.slider("Max weight per asset", 0.15, 1.0, 1.0, 0.05,
                  help="Caps the optimizer-based methods; heuristics use their natural weights.")
scheme = c3.selectbox("Ensemble scheme",
                      ["inverse_te", "equal"],
                      format_func=lambda s: {"inverse_te": "Inverse tracking-error "
                                             "(toward consensus)",
                                             "equal": "Equal weight"}[s])

cov = ledoit_wolf_cov(rets)[0] if cov_choice.startswith("Ledoit") else sample_cov(rets)

ports = M.build_all(mu, cov, 0.0, max_w)
ens = M.ensemble(ports, scheme)

# ── Scores ──
rows = []
for name, w in ports.items():
    rows.append({"Method": name, "Family": M.CATEGORY[name], **M.score(w, mu, cov)})
ens_score = M.score(ens, mu, cov)
rows.append({"Method": "★ Ensemble", "Family": "Ensemble", **ens_score})
tbl = pd.DataFrame(rows).set_index("Method").sort_values("Sharpe", ascending=False)

best = tbl.drop("★ Ensemble").sort_values("Sharpe", ascending=False).index[0]

# ── KPI row ──
k = st.columns(4)
k[0].markdown(theme.kpi("Methods", str(len(ports))), unsafe_allow_html=True)
k[1].markdown(theme.kpi("Best single (Sharpe)", best), unsafe_allow_html=True)
k[2].markdown(theme.kpi("Ensemble Sharpe", f"{ens_score['Sharpe']:.2f}"),
              unsafe_allow_html=True)
k[3].markdown(theme.kpi("Ensemble Effective N", f"{ens_score['Effective N']:.1f}"),
              unsafe_allow_html=True)

# ── 1. Comparison table ──
st.subheader("Method comparison")
st.dataframe(
    tbl.style.format({"Ann. Return": "{:.2%}", "Ann. Vol": "{:.2%}",
                      "Sharpe": "{:.2f}", "Max Weight": "{:.1%}",
                      "Effective N": "{:.1f}"}),
    width='stretch')
bench = da.load_benchmark()
if bench is not None:
    b = bench["BENCH_60_40"].dropna()
    bsharpe = (b.mean() * 12) / (b.std() * np.sqrt(12))
    st.caption(f"Reference, 60/40 ACWI/IGOV benchmark Sharpe ≈ **{bsharpe:.2f}**. "
               "Effective N = how many assets effectively carry weight (higher = "
               "more diversified). Concentration rises as Sharpe is maximized.")

with st.expander("📖 What these methods are (plain English)"):
    st.markdown(
        "**The two Greg asked us to look at — they need *no* return forecasts:**\n\n"
        "- **Inverse Volatility** — weight each asset by **1 ÷ its volatility**. "
        "Calm assets (bonds) get more; jumpy ones (stocks, commodities) get less. "
        "Simple, hard to break, ignores any view on returns.\n"
        "- **Inverse Variance** — same idea but **1 ÷ volatility²**. It tilts *even "
        "harder* toward the calmest assets, so it piles into bonds and runs at very "
        "low risk.\n\n"
        "**Why they matter:** they're the **baseline**. Because they use no "
        "expected-return model, they're the yardstick — our forecast-driven "
        "optimizer (Max Sharpe, fed by the macro regression) has to **beat these** "
        "to justify the extra complexity.\n\n"
        "**The rest, in one line each:**\n\n"
        "- *Equal Weight* — same amount in everything (simplest possible).\n"
        "- *Max Sharpe* — the only one that uses **return forecasts**; chases the "
        "best risk-adjusted return.\n"
        "- *Min Variance / Risk Parity / HRP / Max Diversification* — different ways "
        "to **shape risk** (lowest risk, equal risk per asset, cluster-aware, most "
        "diversified) without forecasting returns.")

# ── 2. Weights heatmap (all methods at once) ──
st.subheader("Allocations across methods")
Wdf = pd.DataFrame({n: w for n, w in ports.items()})
Wdf["★ Ensemble"] = ens
Wdf = Wdf.reindex(mu.index)
order = list(tbl.index)                       # match table ordering
Wdf = Wdf[order]
labels = [da.ASSET_LABELS.get(a, a) for a in Wdf.index]
heat = go.Figure(go.Heatmap(
    z=(Wdf.values * 100).T, x=labels, y=order,
    colorscale=theme.SEQUENTIAL, zmin=0,
    text=[[f"{v*100:.0f}" if v >= 0.005 else "" for v in Wdf[m].values] for m in order],
    texttemplate="%{text}", textfont=dict(size=9),
    colorbar=dict(title="wt %"),
    hovertemplate="%{y}<br>%{x}<br>%{z:.1f}%<extra></extra>"))
heat.update_layout(xaxis_tickangle=-35)
st.plotly_chart(theme.style_fig(heat, height=430), width='stretch')

# ── 3. Ensemble weights ──
st.subheader("Ensemble allocation")
ew = ens.sort_values()
bar = go.Figure(go.Bar(
    x=ew.values * 100, y=[da.ASSET_LABELS.get(i, i) for i in ew.index],
    orientation="h", marker=dict(color=ew.values * 100, colorscale=theme.SEQUENTIAL),
    text=[f"{v*100:.1f}%" for v in ew.values], textposition="auto"))
bar.update_layout(xaxis_title="Weight (%)")
st.plotly_chart(theme.style_fig(bar, height=360), width='stretch')
st.caption("The ensemble blends all eight methods, diversifying across "
           "*construction methodologies*, not just across assets.")
