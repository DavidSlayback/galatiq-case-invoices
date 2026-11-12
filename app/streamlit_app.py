"""Acme invoice agents dashboard. Run: ``python main.py ui`` (or ``streamlit run app/streamlit_app.py``)."""

import sys
from pathlib import Path

import streamlit as st

PAGES = Path(__file__).parent / "views"  # not "pages/": Streamlit would auto-list those files by name
# `streamlit run` puts app/ on the path, not the repo root the pages import from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

st.set_page_config(page_title="Acme Invoice Agents", page_icon=":material/receipt_long:", layout="wide")
nav = st.navigation(
    [
        st.Page(PAGES / "process.py", title="Process an invoice", icon=":material/upload_file:", default=True),
        st.Page(PAGES / "inbox.py", title="Review inbox", icon=":material/inbox:"),
        st.Page(PAGES / "history.py", title="History", icon=":material/history:"),
        st.Page(PAGES / "batch.py", title="Run all samples", icon=":material/fact_check:"),
        st.Page(PAGES / "roi.py", title="Business impact", icon=":material/trending_down:"),
    ]
)
nav.run()
