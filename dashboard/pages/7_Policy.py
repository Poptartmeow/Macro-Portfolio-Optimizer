"""Investment Policy, the governing IPS + a live compliance check."""

import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

_DASH = str(Path(__file__).resolve().parent.parent)
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)

import data_access as da
import theme

st.set_page_config(page_title="Policy", layout="wide")
theme.apply_theme()

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from macro_portfolio.optimizer import optimizer as O          # noqa: E402
from macro_portfolio.optimizer import ips as IPS              # noqa: E402
from macro_portfolio.risk.covariance import ledoit_wolf_cov   # noqa: E402

st.markdown("# Policy")
st.markdown(theme.flow_diagram(active="Policy"), unsafe_allow_html=True)
st.caption("The IPS is the governing document, we set the rules, every portfolio "
           "is checked against them (the role it plays in Ang et al. 2026).")

# ── Compliance check of the policy portfolio ──
st.subheader("Live compliance check")
st.caption("Portfolio = the optimizer run under the IPS (max-return at the 10% vol "
           "target, 3–30% per-asset box), on Ledoit-Wolf covariance.")

rets = da.load_returns()
mu = rets.mean() * 12
cov, _ = ledoit_wolf_cov(rets)
try:
    res = O.optimize(mu, cov, target_vol=IPS.DEFAULT_IPS.target_vol,
                     min_weight=0.03, max_weight=IPS.DEFAULT_IPS.max_weight)
    w = res["weights"]
    port = (rets * w.reindex(rets.columns).fillna(0.0)).sum(axis=1)
    cum = (1 + port).cumprod()
    max_dd = float((cum / cum.cummax() - 1).min())
    checks = IPS.check_compliance(w, vol=res["volatility"], max_drawdown=max_dd)
    compliant = IPS.is_compliant(checks)
except Exception as e:
    st.error(f"Could not build the policy portfolio: {e}")
    st.stop()

badge = ("<span class='badge' style='background:#4DD0A733;color:#4DD0A7;"
         "border-color:#4DD0A7'>✓ COMPLIANT</span>" if compliant else
         "<span class='badge' style='background:#FF6B6B33;color:#FF6B6B;"
         "border-color:#FF6B6B'>✗ BREACH</span>")
st.markdown(f"### Status: {badge}", unsafe_allow_html=True)

left, right = st.columns([3, 2])
with left:
    for c in checks:
        mark = "✓" if c["ok"] else "✗"
        color = "#4DD0A7" if c["ok"] else "#FF6B6B"
        st.markdown(
            f"<div class='glass' style='margin-bottom:8px'>"
            f"<span style='color:{color};font-weight:800;font-size:1.1rem'>{mark}</span> "
            f"&nbsp;<b>{c['rule']}</b><br>"
            f"<span style='color:#9AA5B8;font-size:0.85rem'>{c['detail']}</span></div>",
            unsafe_allow_html=True)
with right:
    ws = w.sort_values()
    bar = go.Figure(go.Bar(
        x=ws.values * 100, y=[da.ASSET_LABELS.get(i, i) for i in ws.index],
        orientation="h", marker=dict(color=ws.values * 100, colorscale=theme.SEQUENTIAL),
        text=[f"{v*100:.0f}%" for v in ws.values], textposition="auto"))
    bar.update_layout(xaxis_title="Weight (%)", title="Policy portfolio")
    st.plotly_chart(theme.style_fig(bar, height=360), width='stretch')

# ── The policy itself ──
st.divider()
ips_md = da.REPO_ROOT / "docs" / "IPS.md"
if ips_md.exists():
    st.markdown(ips_md.read_text())
