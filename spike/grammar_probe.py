"""Spike: minimal schemas to find what Ollama's `format` actually enforces. Throwaway."""
import json, sys
from pathlib import Path
from jsonschema import Draft202012Validator
sys.path.insert(0, str(Path(__file__).parent))
from toolchain_check import post  # noqa: E402

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3:4b"
PROMPT = ("Write test steps as JSON for: open /login, type alice@conduit.test into the Email field, "
          "click the Sign in button. Each step has an action and a target.")
target_obj = {"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"],
              "additionalProperties": False}
PROBES = {
    "1 nested object, no union": {"type": "object", "required": ["steps"], "properties": {"steps": {
        "type": "array", "items": {"type": "object", "required": ["action", "target"], "additionalProperties": False,
        "properties": {"action": {"type": "string"}, "target": target_obj}}}}},
    "2 anyOf of two objects": {"type": "object", "required": ["steps"], "properties": {"steps": {
        "type": "array", "items": {"anyOf": [
            {"type": "object", "required": ["action", "url"], "additionalProperties": False,
             "properties": {"action": {"enum": ["goto"]}, "url": {"type": "string"}}},
            {"type": "object", "required": ["action", "target"], "additionalProperties": False,
             "properties": {"action": {"enum": ["click", "fill"]}, "target": target_obj, "value": {"type": "string"}}}]}}}},
    "3 enum only at top": {"type": "object", "required": ["verdict"], "properties": {"verdict": {"enum": ["x", "y"]}}},
}
for name, schema in PROBES.items():
    v = Draft202012Validator(schema)
    oks = []
    for _ in range(2):
        r = post("/api/chat", {"model": MODEL, "stream": False, "format": schema, "think": False,
                               "options": {"num_gpu": 99, "temperature": 0.7},
                               "messages": [{"role": "user", "content": PROMPT}]})
        out = json.loads(r["message"]["content"])
        errs = [e.message[:100] for e in v.iter_errors(out)]
        oks.append("valid" if not errs else f"INVALID {errs[:1]} :: {json.dumps(out)[:160]}")
    print(f"{name}: {oks}")
