"""Spike: does Ollama enforce the role enum and the no-leading-$ string pattern? Throwaway."""
import json, sys
from pathlib import Path
from jsonschema import Draft202012Validator
sys.path.insert(0, str(Path(__file__).parent))
from toolchain_check import post, SCHEMA  # noqa: E402

V = Draft202012Validator(SCHEMA)
PROMPT = ("Write a JSON test spec: open /login, fill the Email field with alice@conduit.test, fill the "
          "Password field with the secret ALICE_PASSWORD, click Sign in. Use role targets like input.")
for i in range(3):
    r = post("/api/chat", {"model": "qwen3:4b", "stream": False, "think": False, "format": SCHEMA,
                           "options": {"num_gpu": 99, "num_ctx": 8192, "temperature": 0.8},
                           "messages": [{"role": "user", "content": PROMPT}]})
    spec = json.loads(r["message"]["content"])
    errs = [e.message[:100] for e in V.iter_errors(spec)]
    fills = [(s.get("target"), s.get("value")) for s in spec["steps"] if s["action"] == "fill"]
    print(f"sample {i + 1}: valid={not errs} {errs[:1]} fills={fills}")
