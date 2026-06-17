"""Findings, renders docs/FINDINGS.md so the write-up and dashboard stay in sync."""

import sys as _sys
from pathlib import Path as _Path
for _p in (_Path(__file__).resolve().parent, _Path(__file__).resolve().parent.parent):
    if (_p / "data_access.py").exists() and str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import streamlit as st

import data_access as da
import theme

st.set_page_config(page_title="Findings", layout="wide")
theme.apply_theme()

st.markdown(theme.flow_diagram(active="Findings"), unsafe_allow_html=True)

md_path = da.REPO_ROOT / "docs" / "FINDINGS.md"
if md_path.exists():
    text = md_path.read_text()
    st.markdown(text, unsafe_allow_html=False)
else:
    st.warning("docs/FINDINGS.md not found.")
