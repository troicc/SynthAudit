from __future__ import annotations

import streamlit as st

from synthaudit import SCIENTIFIC_NOTICE, __version__

st.set_page_config(page_title="SynthAudit", page_icon="🧪", layout="wide")
st.title(f"SynthAudit {__version__}")
st.caption("A representation-agnostic audit layer for reaction-edit retrosynthesis")
st.warning(SCIENTIFIC_NOTICE)
st.info(
    "The five-page audit workspace is installed by the product phase; core logic lives in the package."
)
