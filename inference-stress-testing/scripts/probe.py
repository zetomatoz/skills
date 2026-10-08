#!/usr/bin/env python3
"""Small API/correctness probe, deliberately separate from synthetic load."""
import json
import os
import urllib.request
from urllib.parse import urlsplit


def endpoint(env):
    base = env.get("AI_ENDPOINT", "").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("AI_ENDPOINT must be an http(s) base URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use AI_API_KEY for credentials; endpoint must not contain credentials/query/fragment")
    return base.removesuffix("/v1")


def probe(env):
    base = endpoint(env)
    model = env.get("AI_MODEL", "")
    if not model:
        raise ValueError("AI_MODEL is required")
    headers = {"Content-Type": "application/json"}
    if env.get("AI_API_KEY"):
        headers["Authorization"] = "Bearer " + env["AI_API_KEY"]
    quality = env.get("QUALITY_EVAL", "1") == "1"
    cases = [("arithmetic", "What is 2 + 3? Reply with only the integer.", "5"),
             ("extraction", "The access code is ORANGE. Reply with only the access code.", "ORANGE"),
             ("instruction", "Reply with exactly the word READY.", "READY")]
    if not quality:
        cases = [("api_smoke", "Reply with READY.", None)]
    results = []
    for name, prompt, expected in cases:
        body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 32, "temperature": 0, "stream": False}
        request = urllib.request.Request(base + "/v1/chat/completions",
                                         data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=float(env.get("REQUEST_TIMEOUT_SECONDS", "120"))) as response:
                data = json.load(response)
            text = data["choices"][0]["message"]["content"]
            passed = isinstance(text, str) and bool(text.strip()) and (expected is None or text.strip() == expected)
            results.append({"case": name, "status": "PASS" if passed else "FAIL",
                            "expected": expected, "actual": text})
        except Exception as exc:
            # Do not persist exception messages: URLs/response bodies can contain secrets.
            results.append({"case": name, "status": "FAIL", "error_type": type(exc).__name__})
    return {"status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
            "kind": "synthetic_correctness_smoke" if quality else "api_smoke",
            "scope": "Three short checks only; not a model-quality or long-context evaluation.", "cases": results}


if __name__ == "__main__":
    result = probe(os.environ)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)
