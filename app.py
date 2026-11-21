 import json
import os
from pathlib import Path
from urllib import error, request
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="StaleGuard.AI — Temporal Knowledge Defense Platform",
    layout="wide",
)


def get_gemini_key() -> str:
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "").strip()


def verify_claim_with_gemini(claim: str, api_key: str) -> dict:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    prompt = (
        "Evaluate the factual accuracy and temporal freshness of this claim as of November 2026. "
        "Respond strictly as JSON with keys: verdict (string), freshness_score (integer 0-100), "
        "truthfulness (string), temporal_freshness (string), evidence_confidence (string), "
        "hallucination_risk (string), and summary (string).\n\n"
        f"Claim: {claim}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=25) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    text = raw["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


gemini_key = get_gemini_key()
index_path = Path(__file__).parent / "index.html"

if index_path.exists():
    html_content = index_path.read_text(encoding="utf-8")
    if gemini_key:
        html_content = html_content.replace("__GEMINI_API_KEY__", gemini_key)
    components.html(html_content, height=950, scrolling=True)
else:
    st.error("index.html repository mein nahi mili.")

st.divider()
st.subheader("Direct Gemini Live Check (Streamlit Backend)")
if not gemini_key:
    st.warning("GEMINI_API_KEY Streamlit Secrets mein set nahi mili.")

claim_input = st.text_input(
    "Claim for direct Gemini check",
    value="sun rises from east",
    placeholder="Enter a claim to verify...",
)
if st.button("Verify with Gemini Now"):
    if not gemini_key:
        st.error("Pehle Streamlit Secrets mein GEMINI_API_KEY add karein.")
    elif not claim_input.strip():
        st.warning("Kripya pehle koi claim likhein.")
    else:
        try:
            result = verify_claim_with_gemini(claim_input.strip(), gemini_key)
            st.json(result)
        except error.HTTPError as e:
            st.error(f"Gemini API HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')}")
        except Exception as e:
            st.error(f"Verification error: {e}")
