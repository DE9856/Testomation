"""Spike: raw output of one flow under each 'no leading $' pattern, to see what breaks JSON. Throwaway."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import specgen  # noqa: E402

base = json.loads((Path(__file__).parent / "specgen" / "schema_v3.json").read_text())
for pat in ["^([^$](.|\\n)*)?$", "^([^$].*)?$", None]:
    s = json.loads(json.dumps(base))
    for b in s["$defs"]["value"]["anyOf"]:
        if b.get("type") == "string":
            if pat is None: b.pop("pattern", None)
            else: b["pattern"] = pat
    specgen.SCHEMA = s
    specgen.PROMPT = "v2"
    spec, stats = specgen.generate("qwen3:4b", specgen.FLOWS[1], 2)
    bad = "_invalid_json" in spec
    print(f"pattern={pat!r}: invalid_json={bad} gen_tokens={stats['gen_tokens']} {stats['seconds']}s")
    if bad: print("   ", spec["_invalid_json"][:200])
