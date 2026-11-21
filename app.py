import json
import os
import re
from pathlib import Path
from urllib import error, request
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="StaleGuard.AI — Temporal Knowledge Defense Platform",
    layout="wide",
)

PREFERRED_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
    "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct",
]


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

    available = []
    for item in data.get("data", []):
        model_id = str(item.get("id", "")).strip()
        if not model_id:
            continue
        lower_id = model_id.lower()
        if any(skip in lower_id for skip in ("whisper", "guard", "tts", "playai", "embed", "prompt-guard")):
            continue
        available.append(model_id)

    ordered = [m for m in PREFERRED_MODELS if m in available]
    for m in available:
        if m not in ordered:
            ordered.append(m)
    return ordered


def call_groq_model(claim: str, api_key: str, model_name: str) -> dict:
    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = (
        "You are an accurate, objective fact-checker as of November 2026.\n"
        "Carefully analyze the exact statement in Claim.\n"
        "- Mark is_true = true ONLY if the statement is factually accurate and not false/misleading.\n"
        "- Mark is_true = false if the statement is factually false, incorrect, or falsely negated.\n"
        "- Never guess randomly; explain the exact real-world fact clearly and concisely in summary.\n"
        "- Set freshness_score to an integer from 0 to 100 reflecting factual accuracy & freshness.\n\n"
        "Respond strictly as JSON with keys:\n"
        "is_true (boolean), verdict ('TRUE' or 'FALSE'), freshness_score (integer 0-100), "
        "truthfulness ('VERIFIED TRUE' or 'FALSE CLAIM'), summary (string).\n\n"
        f"Claim: {claim}"
    )
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": "You are a strict, accurate fact-checker. Always return valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
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

    raw_is_true = parsed.get("is_true")
    raw_verdict = str(parsed.get("verdict", "")).strip().upper()
    if isinstance(raw_is_true, bool):
        strict_true = raw_is_true
    elif raw_verdict in ("TRUE", "VERIFIED TRUE", "FACTUAL"):
        strict_true = True
    else:
        strict_true = False

    parsed["is_true"] = strict_true
    parsed["verdict"] = "TRUE" if strict_true else "FALSE"
    parsed["truthfulness"] = "VERIFIED TRUE" if strict_true else "FALSE CLAIM"

    score = parsed.get("freshness_score")
    try:
        score_int = int(score)
    except Exception:
        score_int = 95 if strict_true else 10
    parsed["freshness_score"] = max(0, min(100, score_int))
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
            if e.code in (400, 404, 429):
                continue
            raise last_err
    raise last_err or RuntimeError("Kisi bhi available Groq model se response nahi aaya.")


def inject_result_into_html(html_str: str, claim: str, res: dict) -> str:
    is_true = bool(res.get("is_true", False))
    verdict_text = "TRUE" if is_true else "FALSE"
    truth_text = "VERIFIED TRUE" if is_true else "FALSE CLAIM"
    score = res.get("freshness_score", 95 if is_true else 10)
    summary = str(res.get("summary", "")).replace('"', "&quot;").replace("'", "&#39;")
    safe_claim = claim.replace('"', "&quot;").replace("'", "&#39;")

    updated = re.sub(r"35\s*%", f"{score}%", html_str)
    updated = updated.replace("UNVERIFIED / AWAITING EVIDENCE", verdict_text)
    updated = updated.replace("Verification Pending", truth_text)
    updated = updated.replace(
        "Claim is being cross-referenced against authoritative multi-source registries.",
        summary,
    )
    if not is_true:
        updated = updated.replace("VERIFIED TRUE", "FALSE CLAIM")

    sync_script = f"""
    <script>
    (function() {{
      const claimVal = "{safe_claim}";
      const isTrue = {str(is_true).lower()};
      const verdictText = "{verdict_text}";
      const truthText = "{truth_text}";
      const scoreText = "{score}%";
      const summaryText = "{summary}";

      function applyVerdictToDom() {{
        document.querySelectorAll("textarea, input[type='text']").forEach(el => {{
          if (el.value !== undefined) {{
            el.value = claimVal;
            el.dispatchEvent(new Event("input", {{ bubbles: true }}));
          }}
        }});

        document.querySelectorAll("*").forEach(node => {{
          if (node.children.length === 0 && node.textContent) {{
            const t = node.textContent.trim();
            if (t === "UNVERIFIED / AWAITING EVIDENCE" || t === "UNVERIFIED") {{
              node.textContent = verdictText;
            }} else if (t === "Verification Pending" || t === "VERIFIED TRUE" || t === "FALSE CLAIM") {{
              node.textContent = truthText;
            }} else if (t === "TRUE" || t === "FALSE") {{
              if (!isTrue && t === "TRUE") {{
                node.textContent = "FALSE";
              }} else if (isTrue && t === "FALSE") {{
                node.textContent = "TRUE";
              }}
            }} else if (/^35\\s*%$/.test(t)) {{
              node.textContent = scoreText;
            }} else if (t === "Claim is being cross-referenced against authoritative multi-source registries.") {{
              node.textContent = summaryText || truthText;
            }}
          }}
        }});
      }}

      if (document.readyState === "loading") {{
        document.addEventListener("DOMContentLoaded", applyVerdictToDom);
      }} else {{
        applyVerdictToDom();
      }}
      setTimeout(applyVerdictToDom, 400);
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
    value="delhi is the capital of india",
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
