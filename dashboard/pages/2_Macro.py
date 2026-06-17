"""Macro — regime + signals, as sub-tabs."""

import sys
from pathlib import Path

_DASH = str(Path(__file__).resolve().parent.parent)
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)

import streamlit as st

import theme
import sec_regime
import sec_signals

st.set_page_config(page_title="Macro", layout="wide")
theme.apply_theme()

st.markdown("# Macro")
st.markdown(theme.flow_diagram(active="Macro"), unsafe_allow_html=True)
st.caption("The macro inputs to the model — what regime we're in, and which macro "
           "signals actually move each asset.")

tab_regime, tab_signals = st.tabs(["Regime", "Signals"])
with tab_regime:
    sec_regime.render()
with tab_signals:
    sec_signals.render()
