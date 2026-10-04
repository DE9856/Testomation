"""Spike: does Ollama enforce `contains` (+ the v3 named-role split)? Throwaway."""
import json, sys
from pathlib import Path
from jsonschema import Draft202012Validator
sys.path.insert(0, str(Path(__file__).parent))
from toolchain_check import post  # noqa: E402

schema = json.loads((Path(__file__).parent / "specgen" / "schema_v3_contains.json").read_text())
V = Draft202012Validator(schema)
# a prompt that invites ending without an expect and naming a paragraph
PROMPT = ("Write a JSON test spec that opens /#/article/dave-s-post-3 and clicks the button named "
          "'Favorite ( 0 )'. Then check the paragraph named 'Comment from alice'.")
for i in range(3):
    r = post("/api/chat", {"model": "qwen3:4b", "stream": False, "think": False, "format": schema,
                           "options": {"num_gpu": 99, "num_ctx": 8192, "temperature": 0.8, "num_predict": 2000},
                           "messages": [{"role": "user", "content": PROMPT}]})
    spec = json.loads(r["message"]["content"])
    errs = [e.message[:90] for e in V.iter_errors(spec)]
    acts = [s["action"] for s in spec["steps"]]
    targets = [s.get("target") for s in spec["steps"] if s.get("target")]
    print(f"sample {i+1}: valid={not errs} {errs[:1]} actions={acts} targets={targets}")
