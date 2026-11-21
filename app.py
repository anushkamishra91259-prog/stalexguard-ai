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
        "You are a factual claim checker as of November 2026. Decide decisively whether the claim is TRUE or FALSE "
        "(do not say Unverified or Awaiting Evidence for clear factual claims). "
        "Respond strictly as JSON with keys: is_true (boolean), verdict (string: 'TRUE' or 'FALSE'), "
        "freshness_score (integer 0-100), truthfulness (string: 'VERIFIED TRUE' or 'FALSE CLAIM'), "
        "temporal_freshness (string), evidence_confidence (string: 'HIGH'), "
        "hallucination_risk (string: 'LOW' or 'HIGH'), and summary (string).\n\n"
        f"Claim: {claim}"
    )
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": "You are a decisive fact-checking engine. Always return valid JSON with clear TRUE or FALSE verdicts.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
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


def inject_result_into_html(html_str: str, claim: str, res: dict) -> str:
    is_true = bool(res.get("is_true", str(res.get("verdict", "")).strip().upper() == "TRUE"))
    status_label = "TRUE" if is_true else "FALSE"
    truth_label = "VERIFIED TRUE" if is_true else "FALSE CLAIM"
    score = res.get("freshness_score", 95 if is_true else 10)
    summary = str(res.get("summary", "")).replace('"', "&quot;")
    safe_claim = claim.replace('"', "&quot;")

    updated = html_str.replace("35%", f"{score}%")
    updated = updated.replace("UNVERIFIED / AWAITING EVIDENCE", status_label)
    updated = updated.replace("Verification Pending", truth_label)
    updated = updated.replace("UNVERIFIED", truth_label)
    updated = updated.replace(
        "Claim is being cross-referenced against authoritative multi-source registries.",
        summary,
    )
    updated = updated.replace("UNKNOWN", "CURRENT" if is_true else "INCORRECT")
    updated = updated.replace("LOW", "HIGH" if is_true else "VERIFIED")

    sync_script = f"""
    <script>
    (function() {{
      const claimVal = "{safe_claim}";
      const statusText = "{status_label}";
      const scoreText = "{score}%";
      const summaryText = "{summary}";
      window.addEventListener("DOMContentLoaded", () => {{
        document.querySelectorAll("textarea, input[type='text']").forEach(el => {{
          if (!el.value || el.value.trim().length > 0) {{
            el.value = claimVal;
            el.dispatchEvent(new Event("input", {{ bubbles: true }}));
          }}
        }});
        document.querySelectorAll("*").forEach(node => {{
          if (node.children.length === 0 && node.textContent) {{
            const t = node.textContent.trim();
            if (t === "UNVERIFIED / AWAITING EVIDENCE" || t === "UNVERIFIED") {{
              node.textContent = statusText;
            }} else if (t === "Verification Pending") {{
              node.textContent = summaryText || statusText;
            }} else if (t === "35%") {{
              node.textContent = scoreText;
            }}
          }}
        }});
      }});
    }})();
    </script>
    """
    return updated + sync_script


groq_key = get_groq_key()
index_path = Path(__file__).parent / "index.html"

if "latest_verification" not in st.session_state:
    st.session_state["latest_verification"] = None

st.subheader("Live Claim Check (TRUE / FALSE via Groq)")
claim_text = st.text_input(
    "Enter claim to verify",
    value="dogs baby is puppy",
    key="live_claim_input",
)

if st.button("Verify Claim Now", type="primary"):
    if not groq_key:
        st.error("Streamlit Secrets mein GROQ_API_KEY add karein.")
    elif not claim_text.strip():
        st.warning("Kripya claim likhein.")
    else:
        with st.spinner("Verifying claim..."):
            try:
                res = verify_claim_with_groq(claim_text.strip(), groq_key)
                st.session_state["latest_verification"] = {
                    "claim": claim_text.strip(),
                    "result": res,
                }
            except Exception as e:
                st.error(f"Error: {e}")

latest = st.session_state.get("latest_verification")
if latest:
    res = latest["result"]
    verdict_display = "TRUE" if res.get("is_true") else "FALSE"
    c1, c2, c3 = st.columns(3)
    c1.metric("Result", verdict_display)
    c2.metric("Freshness / Accuracy Score", f"{res.get('freshness_score', 'N/A')}%")
    c3.metric("Model", str(res.get("_model_used", "Groq")))
    st.write("**Explanation:**", res.get("summary", ""))

if index_path.exists():
    html_content = index_path.read_text(encoding="utf-8")
    if latest:
        html_content = inject_result_into_html(
            html_content, latest["claim"], latest["result"]
        )
    components.html(html_content, height=900, scrolling=True)
else:
    st.error("index.html repository mein nahi mili.")
