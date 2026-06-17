"""
UVA-futuristic theme: palette, Plotly template, and CSS injection.

All colors live here so the look is editable in one place. Import `apply_theme()`
once at the top of every page, and use `style_fig()` on every Plotly figure.
"""

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ── UVA official + futuristic accents ──
JEFFERSON_BLUE = "#232D4B"   # deep navy base
ROTUNDA_ORANGE = "#E57200"   # primary accent
WHITE          = "#FFFFFF"
CYAN           = "#3DD2FF"    # futuristic neon highlight
SLATE          = "#5B6478"    # muted gridlines / secondary text
SURFACE        = "#1B2238"    # card/panel background

# Categorical series colorway (orange + cyan lead)
PALETTE = [ROTUNDA_ORANGE, CYAN, "#F2A65A", "#7FB0FF", "#FFD166",
           "#9D8DF1", "#4DD0A7", "#FF6B6B", "#A0AEC0"]

# Diverging scale centered on 0 (navy → white → orange) for betas / t-stats
DIVERGING = [[0.0, "#1f6feb"], [0.5, "#0e1424"], [1.0, ROTUNDA_ORANGE]]
# Sequential (navy → orange) for magnitudes
SEQUENTIAL = [[0.0, SURFACE], [0.5, "#7a4a12"], [1.0, ROTUNDA_ORANGE]]


def _register_template() -> None:
    # Only our overrides; composed on top of plotly_dark via "plotly_dark+uva".
    tmpl = go.layout.Template()
    tmpl.layout.paper_bgcolor = "rgba(0,0,0,0)"
    tmpl.layout.plot_bgcolor = "rgba(0,0,0,0)"
    tmpl.layout.font = dict(color=WHITE, family="Inter, Segoe UI, sans-serif")
    tmpl.layout.colorway = PALETTE
    tmpl.layout.xaxis = dict(gridcolor="rgba(91,100,120,0.22)",
                             zerolinecolor="rgba(91,100,120,0.45)")
    tmpl.layout.yaxis = dict(gridcolor="rgba(91,100,120,0.22)",
                             zerolinecolor="rgba(91,100,120,0.45)")
    tmpl.layout.legend = dict(bgcolor="rgba(0,0,0,0)")
    tmpl.layout.title = dict(font=dict(size=16, color=WHITE), x=0.0, xanchor="left")
    pio.templates["uva"] = tmpl
    pio.templates.default = "plotly_dark+uva"


def style_fig(fig: go.Figure, height: int | None = None) -> go.Figure:
    # NOTE: do not set title_font here — that creates an empty title object that
    # Plotly renders as the literal "undefined". Title styling lives in the template.
    fig.update_layout(
        template="plotly_dark+uva",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    if height:
        fig.update_layout(height=height)
    return fig


_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@500&display=swap');

html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}

.stApp {{
    background:
        radial-gradient(900px 500px at 12% -8%, rgba(229,114,0,0.16), transparent 60%),
        radial-gradient(900px 600px at 100% 0%, rgba(61,210,255,0.12), transparent 55%),
        {JEFFERSON_BLUE};
}}

section[data-testid="stSidebar"] {{
    background: rgba(27,34,56,0.85);
    backdrop-filter: blur(10px);
    border-right: 1px solid rgba(61,210,255,0.15);
}}

h1, h2, h3 {{ letter-spacing: -0.01em; font-weight: 800; }}
h1 {{ background: linear-gradient(92deg, {WHITE} 30%, {ROTUNDA_ORANGE} 75%, {CYAN});
      -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}

.glass {{
    background: rgba(255,255,255,0.045);
    border: 1px solid rgba(61,210,255,0.18);
    border-radius: 16px;
    padding: 18px 22px;
    box-shadow: 0 0 28px rgba(229,114,0,0.07), inset 0 0 0 1px rgba(255,255,255,0.02);
    backdrop-filter: blur(6px);
}}

.kpi-label {{ color: {SLATE}; font-size: 0.78rem; text-transform: uppercase;
              letter-spacing: 0.12em; font-weight: 600; }}
.kpi-value {{ color: {WHITE}; font-size: 1.9rem; font-weight: 800; line-height: 1.1;
              text-shadow: 0 0 18px rgba(229,114,0,0.35); }}
.kpi-value .unit {{ color: {ROTUNDA_ORANGE}; font-size: 1.0rem; font-weight: 600; }}

[data-testid="stMetricValue"] {{ color: {ROTUNDA_ORANGE}; font-weight: 800; }}

/* Flow diagram pills */
.flow {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin: 4px 0 6px; }}
.pill {{ padding:8px 14px; border-radius:999px; font-weight:600; font-size:0.82rem;
         border:1px solid rgba(61,210,255,0.25); color:{WHITE};
         background: rgba(35,45,75,0.6); white-space:nowrap; }}
.pill.active {{ border-color:{ROTUNDA_ORANGE}; color:{WHITE};
               background: linear-gradient(120deg, rgba(229,114,0,0.30), rgba(61,210,255,0.10));
               box-shadow: 0 0 18px rgba(229,114,0,0.35); }}
.arrow {{ color:{SLATE}; font-weight:800; }}

.badge {{ display:inline-block; padding:3px 10px; border-radius:999px; font-size:0.72rem;
          font-weight:700; background:rgba(61,210,255,0.14); color:{CYAN};
          border:1px solid rgba(61,210,255,0.3); }}
</style>
"""


def apply_theme(title: str = "Macro Portfolio Optimizer") -> None:
    """Call once at the top of each page."""
    _register_template()
    st.markdown(_CSS, unsafe_allow_html=True)


def kpi(label: str, value: str, unit: str = "") -> str:
    unit_html = f" <span class='unit'>{unit}</span>" if unit else ""
    return (f"<div class='glass'><div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value'>{value}{unit_html}</div></div>")


# ─────────────────────────────────────────────
# Apache ECharts (via streamlit-echarts) — UVA-themed option scaffolding
# ─────────────────────────────────────────────

def echarts_base() -> dict:
    """Shared UVA dark styling for every ECharts option dict."""
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": WHITE, "fontFamily": "Inter, sans-serif"},
        "color": PALETTE,
        "tooltip": {
            "backgroundColor": "rgba(27,34,56,0.95)",
            "borderColor": "rgba(61,210,255,0.35)",
            "textStyle": {"color": WHITE},
        },
        "legend": {"textStyle": {"color": SLATE}, "top": 2, "type": "scroll",
                   "inactiveColor": "#3a4358"},
        "grid": {"left": 56, "right": 24, "top": 44, "bottom": 44, "containLabel": True},
    }


def echarts_axis(name: str = "", value: bool = True) -> dict:
    """A dark-styled axis."""
    return {
        "type": "value" if value else "category",
        "name": name,
        "nameTextStyle": {"color": SLATE},
        "axisLine": {"lineStyle": {"color": "rgba(91,100,120,0.5)"}},
        "axisLabel": {"color": SLATE},
        "splitLine": {"lineStyle": {"color": "rgba(91,100,120,0.16)"}},
    }


def echarts_area_gradient(color: str) -> dict:
    """A top→bottom fade for area fills (the futuristic look)."""
    return {
        "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
        "colorStops": [
            {"offset": 0, "color": color + "66"},
            {"offset": 1, "color": color + "05"},
        ],
    }


def flow_diagram(active: str = "") -> str:
    stages = ["Data", "Macro", "Optimizer",
              "Ensemble", "Risk", "Policy", "Findings"]
    pills = []
    for i, s in enumerate(stages):
        cls = "pill active" if s.lower() == active.lower() else "pill"
        pills.append(f"<span class='{cls}'>{s}</span>")
        if i < len(stages) - 1:
            pills.append("<span class='arrow'>→</span>")
    return "<div class='flow'>" + "".join(pills) + "</div>"
