"""Spike: which JSON Schema constructs does Ollama's constrained decoding actually enforce?

toolchain_check.py showed specs that parse but break the schema (e.g. "target": "Email"
instead of an object). Hypothesis: unsupported constructs are dropped and left unconstrained.
Variants, each run on the same flows (native /api/chat, think off):
  A  original schema ($ref/$defs, oneOf, const, pattern)
  B  $refs inlined
  C  B + oneOf→anyOf, const→single-value enum
  D  C + no `pattern` keywords
Run: uv run python spike/schema_variants.py [model]
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).parent))
from toolchain_check import FLOWS, OPTS, SCHEMA, SYSTEM, post  # noqa: E402

VALIDATOR = Draft202012Validator(SCHEMA)  # always validate against the real schema


def inline_refs(node, defs):
    if isinstance(node, dict):
        if "$ref" in node:
            return inline_refs(copy.deepcopy(defs[node["$ref"].split("/")[-1]]), defs)
        return {k: inline_refs(v, defs) for k, v in node.items() if k not in ("$defs", "$schema", "$id")}
    if isinstance(node, list):
        return [inline_refs(v, defs) for v in node]
    return node


def rewrite(node, drop_pattern=False):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "oneOf":
                out["anyOf"] = rewrite(v, drop_pattern)
            elif k == "const":
                out["enum"] = [v]
            elif k == "pattern" and drop_pattern:
                continue
            else:
                out[k] = rewrite(v, drop_pattern)
        return out
    if isinstance(node, list):
        return [rewrite(v, drop_pattern) for v in node]
    return node


def variants() -> dict[str, dict]:
    inlined = inline_refs(SCHEMA, SCHEMA["$defs"])
    return {
        "A_original": SCHEMA,
        "B_inlined": inlined,
        "C_inlined_anyOf_enum": rewrite(inlined),
        "D_C_no_pattern": rewrite(inlined, drop_pattern=True),
    }


def run(model: str, schema: dict, flow: str) -> dict:
    r = post("/api/chat", {
        "model": model, "stream": False, "format": schema, "think": False, "options": OPTS,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": flow}],
    })
    text = r["message"]["content"]
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        return {"parsed": False, "raw": text[:200]}
    errs = [e.message[:140] for e in VALIDATOR.iter_errors(spec)]
    return {"parsed": True, "valid": not errs, "errors": errs[:2], "spec": spec}


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen3:4b"
    results = {}
    for name, schema in variants().items():
        rows = [run(model, schema, f) for f in FLOWS]
        results[name] = rows
        ok = sum(r.get("valid", False) for r in rows)
        print(f"{name:<24} {ok}/{len(rows)} valid", flush=True)
        for r in rows:
            if not r.get("valid"):
                print("    ", r.get("errors") or r.get("raw"))
    post("/api/generate", {"model": model, "keep_alive": 0})
    out = Path(__file__).parent / "results" / f"schema_variants_{model.replace(':', '_')}.json"
    out.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
