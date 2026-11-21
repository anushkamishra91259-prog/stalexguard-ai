import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_json(200, {"status": "ok", "endpoint": "/api/verify"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(raw_body)
        except Exception:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        claim = (data.get("claim") or "").strip()
        api_key = (data.get("apiKey") or os.environ.get("GEMINI_API_KEY") or "").strip()

        if not claim:
            self._send_json(400, {"error": "Missing 'claim' field"})
            return

        if not api_key:
            self._send_json(400, {"error": "Missing Gemini API key"})
            return

        prompt = (
            "Evaluate the following claim for factual accuracy and temporal freshness in 2026. "
            "Return ONLY valid JSON with keys: "
            "truthfulness (string), freshness (string), confidence (string), "
            "hallucination_risk (string), freshnessScore (number 0-100), "
            "status (string), statusText (string), verdictTitle (string), "
            "verdictSummary (string), factualError (string), freshCorrection (string), "
            "staleClaim (string), groundTruth (string).\n\n"
            f"Claim: {claim}"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        req_payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(req_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                gemini_raw = json.loads(resp.read().decode("utf-8"))

            text_out = (
                gemini_raw.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "{}")
            )
            parsed = json.loads(text_out)
            self._send_json(200, parsed)
        except urllib.error.HTTPError as e:
            err_text = e.read().decode("utf-8", errors="ignore")
            self._send_json(e.code, {"error": f"Gemini API error: {err_text[:300]}"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})
