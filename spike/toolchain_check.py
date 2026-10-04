"""Spike: does the toolchain do what the design assumes? (Q13)

1. Structured output with schemas/test-spec.schema.json (a discriminated union) — native
   /api/chat `format` and OpenAI-compatible /v1 `response_format`. Output validated with jsonschema.
2. qwen3 thinking on vs off under structured output.
3. Logprobs: returned at all? Can a label probability be read at the verdict token?
4. The same /v1 calls through `langfuse.openai` (no Langfuse server running; just the wrapper).

Throwaway. Run:
  uv run --with openai --with langfuse python spike/toolchain_check.py [model ...]
Writes spike/results/toolchain_<model>.json.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
OLLAMA = "http://localhost:11434"
SCHEMA = json.loads((ROOT / "schemas" / "test-spec.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
OPTS = {"num_ctx": 8192, "num_gpu": 99, "temperature": 0}

SYSTEM = """You write end-to-end test specs as JSON for the Conduit blogging app.
Pages: / (home, global feed), /login (fields labelled "Email", "Password"; button "Sign in"),
/register (fields "Username", "Email", "Password"; button "Sign up"), /editor (fields "Article Title",
"What's this article about?", "Write your article (in markdown)", "Enter tags"; button "Publish Article"),
/settings, /profile/<username>. Seeded user: alice@conduit.test / password in $secret ALICE_PASSWORD.
Use role/label targets. Paths start with "/". Only output the JSON spec."""

FLOWS = [
    "Log in as alice and check her username 'alice' appears in the navigation bar.",
    "Sign up a brand-new user with faker data and check the user ends up on the home page.",
    "As alice, publish an article with a title, description, body and two tags, then check the "
    "article page shows the title.",
]

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"enum": ["bug", "noise", "flaky"]}},
    "required": ["verdict"],
    "additionalProperties": False,
}
TRIAGE_CASES = [  # (description, expected)
    ("Test 'publish article' failed at step 6: expected heading 'My post' visible; page shows "
     "'Internal Server Error'. Network: POST /api/articles → 500.", "bug"),
    ("Console error on /: 'Failed to load resource: net::ERR_BLOCKED_BY_CLIENT "
     "https://www.google-analytics.com/analytics.js'. All assertions passed.", "noise"),
    ("Test 'login' timed out waiting for button 'Sign in' on attempt 1, passed on retry with no "
     "code changes. Machine load was high during the run.", "flaky"),
]
TRIAGE_SYSTEM = ("Classify a test failure from a web app test run. 'bug' = the app is broken; "
                 "'noise' = harmless, expected error; 'flaky' = timing/infrastructure, not the app. "
                 "Answer as JSON.")


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def check_spec(text: str) -> dict:
    try:
        spec = json.loads(text)
    except json.JSONDecodeError as e:
        return {"parsed": False, "error": str(e)[:120], "raw": text[:300]}
    errors = [e.message[:160] for e in VALIDATOR.iter_errors(spec)]
    return {"parsed": True, "valid": not errors, "errors": errors[:3],
            "steps": len(spec.get("steps", [])), "spec": spec}


# ---------- 1 + 2: structured output, native API ----------

def native_spec(model: str, flow: str, think: bool | None) -> dict:
    body = {"model": model, "stream": False, "format": SCHEMA, "options": OPTS,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": flow}]}
    if think is not None:
        body["think"] = think
    t0 = time.monotonic()
    try:
        r = post("/api/chat", body)
    except Exception as e:
        return {"call_error": str(e)[:300]}
    out = check_spec(r["message"]["content"])
    out["seconds"] = round(time.monotonic() - t0, 1)
    out["thinking_chars"] = len(r["message"].get("thinking") or "")
    return out


# ---------- 1: structured output, /v1 (plain OpenAI SDK and langfuse.openai) ----------

def v1_client(wrapped: bool):
    if wrapped:
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-spike")
        os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-spike")
        os.environ.setdefault("LANGFUSE_HOST", "http://localhost:1")  # nothing listening: wrapper only
        from langfuse.openai import OpenAI
    else:
        from openai import OpenAI
    return OpenAI(base_url=OLLAMA + "/v1", api_key="ollama")


def v1_spec(client, model: str, flow: str) -> dict:
    t0 = time.monotonic()
    try:
        r = client.chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": flow}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "test_spec", "schema": SCHEMA, "strict": True}},
            extra_body={"options": {"num_ctx": 8192, "num_gpu": 99}, "reasoning_effort": "none"},
        )
    except Exception as e:
        return {"call_error": str(e)[:300]}
    out = check_spec(r.choices[0].message.content or "")
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out


# ---------- 3: logprobs ----------

def label_probability(tokens: list[dict], labels: list[str]) -> dict:
    """Find the token where the verdict value starts; return P(label) from its top_logprobs."""
    text = ""
    for t in tokens:
        before = text
        text += t["token"]
        if '"verdict"' in before and before.rstrip().endswith(('":', '": "', ':"', ': "', '"')) \
                and any(lab.startswith(t["token"].strip('" ')) for lab in labels if t["token"].strip('" ')):
            probs: dict[str, float] = {}
            for alt in t.get("top_logprobs", []):
                frag = alt["token"].strip('" ')
                for lab in labels:
                    if frag and lab.startswith(frag):
                        probs[lab] = probs.get(lab, 0.0) + math.exp(alt["logprob"])
            return {"at_token": t["token"], "probs": {k: round(v, 3) for k, v in probs.items()},
                    "alts": [a["token"] for a in t.get("top_logprobs", [])]}
    return {"not_found": True, "tokens": [t["token"] for t in tokens][:20]}


def v1_triage(client, model: str, case: str) -> dict:
    try:
        r = client.chat.completions.create(
            model=model, temperature=0, logprobs=True, top_logprobs=5,
            messages=[{"role": "system", "content": TRIAGE_SYSTEM}, {"role": "user", "content": case}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "triage", "schema": TRIAGE_SCHEMA, "strict": True}},
            extra_body={"options": {"num_gpu": 99}, "reasoning_effort": "none"},
        )
    except Exception as e:
        return {"call_error": str(e)[:300]}
    choice = r.choices[0]
    lp = choice.logprobs.content if choice.logprobs else None
    if not lp:
        return {"answer": choice.message.content, "logprobs": None}
    tokens = [{"token": t.token, "logprob": t.logprob,
               "top_logprobs": [{"token": a.token, "logprob": a.logprob} for a in t.top_logprobs]}
              for t in lp]
    return {"answer": choice.message.content, **label_probability(tokens, ["bug", "noise", "flaky"])}


def native_triage(model: str, case: str) -> dict:
    try:
        r = post("/api/chat", {
            "model": model, "stream": False, "format": TRIAGE_SCHEMA, "think": False,
            "logprobs": True, "top_logprobs": 5, "options": {"num_gpu": 99, "temperature": 0},
            "messages": [{"role": "system", "content": TRIAGE_SYSTEM}, {"role": "user", "content": case}],
        })
    except Exception as e:
        return {"call_error": str(e)[:300]}
    tokens = r.get("logprobs")
    if not tokens:
        return {"answer": r["message"]["content"], "logprobs": None}
    return {"answer": r["message"]["content"], **label_probability(tokens, ["bug", "noise", "flaky"])}


def main() -> None:
    models = sys.argv[1:] or ["qwen3:4b"]
    plain, wrapped = v1_client(False), v1_client(True)
    for model in models:
        print(f"\n=== {model}", flush=True)
        res: dict = {"model": model}

        thinks = [False, True] if model.startswith("qwen3") else [None]
        for think in thinks:
            key = f"native_think_{think}"
            res[key] = [native_spec(model, f, think) for f in FLOWS]
            print(key, summarize(res[key]), flush=True)
        res["v1_plain"] = [v1_spec(plain, model, f) for f in FLOWS]
        print("v1_plain", summarize(res["v1_plain"]), flush=True)
        res["v1_langfuse"] = [v1_spec(wrapped, model, f) for f in FLOWS]
        print("v1_langfuse", summarize(res["v1_langfuse"]), flush=True)

        for name, fn in [("triage_native", lambda c: native_triage(model, c)),
                         ("triage_v1_plain", lambda c: v1_triage(plain, model, c)),
                         ("triage_v1_langfuse", lambda c: v1_triage(wrapped, model, c))]:
            res[name] = [{"expected": exp, **fn(case)} for case, exp in TRIAGE_CASES]
            for t in res[name]:
                print(name, t.get("expected"), "→", t.get("answer"), t.get("probs", t.get("call_error") or t.get("logprobs", "?")), flush=True)

        post("/api/generate", {"model": model, "keep_alive": 0})
        out = ROOT / "spike" / "results" / f"toolchain_{model.replace(':', '_')}.json"
        out.write_text(json.dumps(res, indent=2))


def summarize(rows: list[dict]) -> str:
    if any("call_error" in r for r in rows):
        return "CALL ERROR: " + next(r["call_error"] for r in rows if "call_error" in r)
    valid = sum(r.get("valid", False) for r in rows)
    secs = [r["seconds"] for r in rows]
    extra = [r["errors"] for r in rows if r.get("parsed") and not r.get("valid")]
    return f"{valid}/{len(rows)} schema-valid, {secs} s" + (f", errors: {extra}" if extra else "")


if __name__ == "__main__":
    main()
