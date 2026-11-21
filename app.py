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


def get_groq_key() -> str:
    try:
        if "GROQ_API_KEY" in st.secrets:
            return str(st.secrets["GROQ_API_KEY"]).strip()
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY", "").strip()


def fetch_available_groq_models(api_key: str) -> list[str]:
    url = "https://api.groq.com/openai/v1/models"
    req = request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "StaleGuardAI/1.0",
        },
        method="GET",
    )
    with request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    models = []
    for item in data.get("data", []):
        model_id = str(item.get("id", "")).strip()
        if not model_id:
            continue
        lower_id = model_id.lower()
        if any(skip in lower_id for skip in ("whisper", "distil-whisper", "guard", "tts", "playai")):
            continue
        models.append(model_id)
    return models


def call_groq_model(claim: str, api_key: str, model_name: str) -> dict:
    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = (
        "Evaluate the factual accuracy and temporal freshness of this claim as of November 2026. "
        "Respond strictly as JSON with keys: verdict (string), freshness_score (integer 0-100), "
        "truthfulness (string), temporal_freshness (string), evidence_confidence (string), "
        "hallucination_risk (string), and summary (string).\n\n"
        f"Claim: {claim}"
    )
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise claim freshness auditor that always responds with valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "StaleGuardAI/1.0",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=25) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    content = raw["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    parsed["_model_used"] = model_name
    return parsed


def verify_claim_with_groq(claim: str, api_key: str) -> dict:
    models = fetch_available_groq_models(api_key)
    if not models:
        raise RuntimeError("Groq account par koi chat model list nahi hua.")

    last_err = None
    for model_name in models[:6]:
        try:
            return call_groq_model(claim, api_key, model_name)
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            last_err = RuntimeError(f"Groq API HTTP Error {e.code} ({model_name}): {body}")
            if e.code in (400, 404):
                continue
            raise last_err
    raise last_err or RuntimeError("Kisi bhi available Groq model se response nahi aaya.")


groq_key = get_groq_key()
index_path = Path(__file__).parent / "index.html"

if index_path.exists():
    html_content = index_path.read_text(encoding="utf-8")
    components.html(html_content, height=900, scrolling=True)
else:
    st.error("index.html repository mein nahi mili.")

st.divider()
st.subheader("Live Verification (Streamlit Cloud + Groq)")

if not groq_key:
    st.warning("Streamlit Secrets mein GROQ_API_KEY set nahi hai. Manage app -> Settings -> Secrets mein daalein.")

claim_text = st.text_input(
    "Enter claim to verify",
    value="delhi is the capital of india",
    key="live_claim_input",
)

if st.button("Verify Claim Now", type="primary"):
    if not groq_key:
        st.error("Pehle Streamlit Secrets mein GROQ_API_KEY add karein.")
    elif not claim_text.strip():
        st.warning("Kripya claim likhein.")
    else:
        with st.spinner("Verifying claim..."):
            try:
                res = verify_claim_with_groq(claim_text.strip(), groq_key)
                c1, c2, c3 = st.columns(3)
                c1.metric("Freshness Score", f"{res.get('freshness_score', 'N/A')}%")
                c2.metric("Verdict", str(res.get("verdict", "N/A")))
                c3.metric("Temporal Freshness", str(res.get("temporal_freshness", "N/A")))
                st.write("**Summary:**", res.get("summary", ""))
                st.caption(f"Model used: {res.get('_model_used', 'N/A')}")
                with st.expander("Full JSON Output"):
                    st.json(res)
            except Exception as e:
                st.error(f"Error: {e}")
