import os
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="StaleGuard.AI — Temporal Knowledge Defense Platform",
    layout="wide",
)

# Streamlit Secrets ya environment se key read karein (optional)
gemini_key = ""
try:
    gemini_key = st.secrets.get("GEMINI_API_KEY", "")
except Exception:
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

index_path = Path(__file__).parent / "index.html"
if index_path.exists():
    html_content = index_path.read_text(encoding="utf-8")
    if gemini_key:
        html_content = html_content.replace("__GEMINI_API_KEY__", gemini_key)
    components.html(html_content, height=950, scrolling=True)
else:
    st.error("index.html repository mein nahi mili.")
