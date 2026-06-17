"""Regime section, rendered as a tab inside the Macro page."""

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

QUAD_COLORS = {
    "Goldilocks": "#4DD0A7",    # growth up, inflation easing
    "Reflation": "#FFD166",     # growth up, inflation rising
    "Stagflation": "#FF6B6B",   # growth down, inflation rising
    "Deflation": theme.CYAN,    # growth down, inflation easing
}


def render() -> None:
    st.markdown(
        "Each month is labelled from composite PMI (above or below 50) and how that "
        "reading has moved over the past three months. PMI alone decides the regime; "
        "CPI sits next to it as context so you can also see the inflation backdrop. We "
        "reference Ang et al. (2026) because their paper introduces a macro agent that "
        "sorts the economy into these same four regimes (expansion, late cycle, "
        "recession, recovery) from growth and inflation. Ours is the simple, "
        "transparent cousin of that idea: instead of a language model scoring several "
        "inputs, we apply one clear rule to PMI, which keeps it reproducible and easy "
        "to audit. CPI does not change the label today, but the natural next step is to "
        "let inflation help define the regime, which is what the macro clock below "
        "starts to do.")
    st.caption("CPI YoY is the year over year change in the Consumer Price Index: how "
               "much consumer prices have risen versus the same month a year ago, in "
               "percent. It is the standard headline gauge of inflation.")

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
    cpi_series = reg["CPI_YoY"].dropna() if "CPI_YoY" in reg.columns else []
    cpi_str = f"{cpi_series.iloc[-1]:.1f}" if len(cpi_series) else "n/a"
    k[2].markdown(theme.kpi("CPI YoY (latest)", cpi_str, "%"), unsafe_allow_html=True)
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
               "month (over our full history). Equities lead in Recovery and "
               "Expansion and fall hardest in Contraction, where bonds hold up.")

    # ── Growth × Inflation macro clock (interactive) ──
    st.divider()
    st.subheader("Growth × Inflation, the macro clock")
    st.markdown(
        "A second lens on the same months, this time using growth and inflation "
        "together. The x axis is growth, measured by composite PMI relative to the 50 "
        "line that separates expansion from contraction. The y axis is inflation "
        "momentum, the change in CPI over the past three months, so points above the "
        "middle line mean inflation is rising and points below mean it is easing. "
        "Splitting the plane at PMI 50 and at zero gives four corners, the classic "
        "macro quadrants: Goldilocks (growth up, inflation easing), Reflation (growth "
        "up, inflation rising), Stagflation (growth down, inflation rising), and "
        "Deflation (growth down, inflation easing). Each faint dot is one month, the "
        "bright line traces the window you select, and the large marker is the most "
        "recent month in that window. Use the slider to set the start and end of the "
        "window, for example the last twelve months.")

    quad = R.classify_quadrant(da.load_factors())
    qv = quad.dropna(subset=["quadrant"])
    months = list(qv.index)
    labels = [m.strftime("%b %Y") for m in months]
    default_start = labels[max(0, len(labels) - 13)]
    win = st.select_slider("Window", options=labels,
                           value=(default_start, labels[-1]))
    start_label, end_label = win
    start_idx, end_idx = labels.index(start_label), labels.index(end_label)
    if end_idx < start_idx:
        start_idx, end_idx = end_idx, start_idx
    sel = labels[end_idx]
    cur = qv.iloc[end_idx]
    cur_quad = cur["quadrant"]
    n_in = 0
    for q in qv["quadrant"].iloc[:end_idx + 1][::-1]:
        if q == cur_quad:
            n_in += 1
        else:
            break
    trail = qv.iloc[start_idx:end_idx + 1]

    pmi = qv["PMI"]; mom = qv["CPI_mom3"]
    xr = [float(pmi.min()) - 1.5, float(pmi.max()) + 1.5]
    pad = max((float(mom.max()) - float(mom.min())) * 0.1, 0.4)
    yr = [float(mom.min()) - pad, float(mom.max()) + pad]

    fig2 = go.Figure()
    for name, x0, x1, y0, y1 in [
        ("Goldilocks", 50, xr[1], yr[0], 0), ("Reflation", 50, xr[1], 0, yr[1]),
        ("Stagflation", xr[0], 50, 0, yr[1]), ("Deflation", xr[0], 50, yr[0], 0)]:
        fig2.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                       fillcolor=QUAD_COLORS[name], opacity=0.12,
                       line_width=0, layer="below")
        fig2.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=name,
                            showarrow=False, opacity=0.6,
                            font=dict(color=QUAD_COLORS[name], size=13))
    fig2.add_vline(x=50, line=dict(color=theme.SLATE, dash="dash"))
    fig2.add_hline(y=0, line=dict(color=theme.SLATE, dash="dash"))
    fig2.add_trace(go.Scatter(x=pmi, y=mom, mode="markers", hoverinfo="skip",
                              marker=dict(color="rgba(154,165,184,0.25)", size=5)))
    fig2.add_trace(go.Scatter(
        x=trail["PMI"], y=trail["CPI_mom3"], mode="lines+markers",
        line=dict(color=theme.CYAN, width=2), marker=dict(color=theme.CYAN, size=6),
        customdata=[m.strftime("%b %Y") for m in trail.index],
        hovertemplate="%{customdata}<br>PMI %{x:.1f}<br>ΔCPI %{y:.2f}<extra></extra>"))
    fig2.add_trace(go.Scatter(
        x=[cur["PMI"]], y=[cur["CPI_mom3"]], mode="markers+text",
        text=[sel], textposition="top center", textfont=dict(color="white"),
        marker=dict(color=theme.ROTUNDA_ORANGE, size=22, line=dict(color="white", width=1.5)),
        hoverinfo="skip"))
    fig2.update_layout(showlegend=False,
                       xaxis=dict(title="Composite PMI  (growth →)", range=xr),
                       yaxis=dict(title="CPI 3 month change  (inflation →)", range=yr))
    st.plotly_chart(theme.style_fig(fig2, height=460), width='stretch')

    qcond = R.quadrant_conditional_returns(da.load_returns(), quad) * 100
    cc = st.columns([1, 2])
    qc = QUAD_COLORS[cur_quad]
    cc[0].markdown(
        f"<div class='glass'><div class='kpi-label'>As of {sel}</div>"
        f"<div class='kpi-value' style='color:{qc}'>{cur_quad}</div>"
        f"<div style='color:#9AA5B8'>{n_in} mo in this quadrant</div></div>",
        unsafe_allow_html=True)
    if cur_quad in qcond.columns:
        col = qcond[cur_quad].sort_values(ascending=False)
        best = ", ".join(f"{da.ASSET_LABELS.get(a, a)} {col[a]:+.0f}%" for a in col.index[:3])
        worst = ", ".join(f"{da.ASSET_LABELS.get(a, a)} {col[a]:+.0f}%" for a in col.index[-2:])
        cc[1].markdown(
            f"<div class='glass'>Historically in <b style='color:{qc}'>{cur_quad}</b> "
            f"(annualized): strongest, {best}; weakest, {worst}.</div>",
            unsafe_allow_html=True)

    st.subheader("Asset returns by quadrant")
    qlabels = [da.ASSET_LABELS.get(a, a) for a in qcond.index]
    hm2 = go.Figure(go.Heatmap(
        z=qcond.values, x=list(qcond.columns), y=qlabels,
        colorscale=theme.DIVERGING, zmid=0,
        text=qcond.round(0).values, texttemplate="%{text}", textfont=dict(size=10),
        colorbar=dict(title="ann %"),
        hovertemplate="%{y}<br>%{x}<br>%{z:.1f}% annualized<extra></extra>"))
    st.plotly_chart(theme.style_fig(hm2, height=300), width='stretch')
    st.markdown(
        "Each cell is the average return an asset earned during the months that fell in "
        "that quadrant, scaled to an annual rate, over our full history. It describes "
        "the past, not a forecast: when the economy looked like this, here is how each "
        "asset tended to do. Commodities behave like an inflation play, strong in "
        "Reflation and Stagflation when prices are climbing and weak when they are not. "
        "Equities do best in Goldilocks, where growth is firm and inflation is fading, "
        "and they struggle most in Stagflation. Bonds tend to cushion the portfolio "
        "whenever growth is weak, regardless of inflation. One caveat: Stagflation has "
        "only a handful of months in our sample, so treat that column as directional "
        "rather than precise.")
