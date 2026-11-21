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
    components.html(html_content, height=900, scrolling=True)
else:
    st.error("index.html repository mein nahi mili.")

st.divider()
st.subheader("Live Gemini Verification (Streamlit Cloud)")

if not gemini_key:
    st.warning("Streamlit Secrets mein GEMINI_API_KEY set nahi hai. Manage app -> Settings -> Secrets mein daalein.")

claim_text = st.text_input(
    "Enter claim to verify",
    value="red yellow makes green",
    key="live_claim_input",
)

if st.button("Verify Claim with Gemini", type="primary"):
    if not gemini_key:
        st.error("Pehle Streamlit Secrets mein GEMINI_API_KEY add karein.")
    elif not claim_text.strip():
        st.warning("Kripya claim likhein.")
    else:
        with st.spinner("Verifying claim with Gemini..."):
            try:
                res = verify_claim_with_gemini(claim_text.strip(), gemini_key)
                c1, c2, c3 = st.columns(3)
                c1.metric("Freshness Score", f"{res.get('freshness_score', 'N/A')}%")
                c2.metric("Verdict", str(res.get("verdict", "N/A")))
                c3.metric("Temporal Freshness", str(res.get("temporal_freshness", "N/A")))
                st.write("**Summary:**", res.get("summary", ""))
                with st.expander("Full JSON Output"):
                    st.json(res)
            except error.HTTPError as e:
                st.error(f"Gemini API HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')}")
            except Exception as e:
                st.error(f"Error: {e}")
