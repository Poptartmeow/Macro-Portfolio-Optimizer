"""
UVA Macro Portfolio Optimizer — dashboard entry point (Home: Overview / About).

Run from the repo root:
    streamlit run dashboard/Home.py
"""

import sys as _sys
from pathlib import Path as _Path
for _p in (_Path(__file__).resolve().parent, _Path(__file__).resolve().parent.parent):
    if (_p / "data_access.py").exists() and str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import streamlit as st
from streamlit_echarts import st_echarts

import data_access as da
import theme

st.set_page_config(page_title="UVA Macro Portfolio Optimizer", layout="wide")
theme.apply_theme()

# ── Header (shown above both tabs) ──
st.markdown("# Global Macro Portfolio Optimizer")
st.markdown(
    "<span class='badge'>UVA MSDS</span> &nbsp; "
    "<span class='badge'>Capstone Project</span>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div style='color:#9AA5B8; margin-top:8px; font-size:0.9rem;'>"
    "Authors: Mauricio Torres, Jack Joy, Tianyin Mao, Tiandra Threat</div>"
    "<div style='color:#9AA5B8; font-size:0.9rem;'>"
    "Sponsor: Greg van Inwegen</div>",
    unsafe_allow_html=True,
)
st.write("")

tab_overview, tab_about = st.tabs(["Overview", "About"])

# ─────────────────────────────────────────────
# OVERVIEW
# ─────────────────────────────────────────────
with tab_overview:
    st.markdown(
        "A research platform that turns public market & macro data into a globally "
        "diversified, risk controlled portfolio that measures it against a passive "
        "60/40 benchmark. The pipeline below runs end to end; each stage is a page "
        "in the sidebar."
    )
    st.markdown(theme.flow_diagram(), unsafe_allow_html=True)
    st.caption("Open any page and its stage lights up. New here? See the **About** tab.")

    rets = da.load_returns()
    facs = da.load_factors()

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    span = f"{rets.index.min().year}–{rets.index.max().year}"
    c1.markdown(theme.kpi("Assets", str(rets.shape[1])), unsafe_allow_html=True)
    c2.markdown(theme.kpi("Macro factors", str(facs.shape[1])), unsafe_allow_html=True)
    c3.markdown(theme.kpi("Months of returns", str(len(rets))), unsafe_allow_html=True)
    c4.markdown(theme.kpi("Coverage", span), unsafe_allow_html=True)

    st.write("")
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Growth of $1 — aligned window")
        cum = (1 + rets).cumprod()
        dates = [d.strftime("%Y-%m") for d in cum.index]
        series = [{
            "name": col, "type": "line", "smooth": True, "showSymbol": False,
            "emphasis": {"focus": "series"}, "lineStyle": {"width": 2},
            "data": [round(v, 3) for v in cum[col]],
        } for col in cum.columns]
        opt = {**theme.echarts_base(),
               "tooltip": {**theme.echarts_base()["tooltip"], "trigger": "axis"},
               "legend": {**theme.echarts_base()["legend"], "data": list(cum.columns)},
               "xAxis": {**theme.echarts_axis(value=False), "data": dates,
                         "boundaryGap": False},
               "yAxis": {**theme.echarts_axis("Growth of $1"), "scale": True},
               "dataZoom": [{"type": "inside"}, {"type": "slider", "height": 16,
                            "bottom": 8, "borderColor": "rgba(91,100,120,0.3)"}],
               "series": series}
        st_echarts(opt, height="420px")

    with right:
        st.subheader("Risk / return")
        stats = da.summary_stats()
        pts = [{"value": [round(stats.loc[a, "Ann. Vol"] * 100, 2),
                          round(stats.loc[a, "Ann. Return"] * 100, 2)], "name": a}
               for a in stats.index]
        opt2 = {**theme.echarts_base(),
                "tooltip": {**theme.echarts_base()["tooltip"], "trigger": "item",
                            "formatter": "{b}: vol {c0}%"},
                "legend": {"show": False},
                "xAxis": {**theme.echarts_axis("Ann. Volatility (%)"), "scale": True},
                "yAxis": {**theme.echarts_axis("Ann. Return (%)"), "scale": True},
                "series": [{
                    "type": "scatter", "symbolSize": 18, "data": pts,
                    "itemStyle": {"color": theme.ROTUNDA_ORANGE, "borderColor": "#fff",
                                  "borderWidth": 1, "shadowBlur": 12,
                                  "shadowColor": "rgba(229,114,0,0.5)"},
                    "label": {"show": True, "formatter": "{b}", "position": "top",
                              "color": theme.SLATE, "fontSize": 10},
                }]}
        st_echarts(opt2, height="420px")

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

# ─────────────────────────────────────────────
# ABOUT
# ─────────────────────────────────────────────
with tab_about:
    guide = da.REPO_ROOT / "docs" / "DASHBOARD_GUIDE.md"
    if guide.exists():
        st.markdown(guide.read_text(), unsafe_allow_html=False)
    else:
        st.warning("docs/DASHBOARD_GUIDE.md not found.")
