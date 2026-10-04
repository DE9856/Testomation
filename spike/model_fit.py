"""Spike: does each candidate model fit this laptop, and how fast is it?

Throwaway (spike/ is never imported by the product). Stdlib only.
Usage: uv run python spike/model_fit.py [--ctx N] [--tag NAME] [model ...]
  default models: every generation model in `ollama list`; default ctx 8192
Writes spike/results/model_fit[_NAME].json and prints a table.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://localhost:11434"
DEFAULT_CTX = 8192  # spec + aria snapshot + error prompts need roughly this much
PROMPT = (
    "You write end-to-end tests for a blogging web app. In about 150 words, list the steps "
    "a user takes to sign up, publish an article with two tags, and see it on their profile."
)


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        OLLAMA + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def gpu_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout
    return int(out.strip().splitlines()[0])


def processor_split(model: str) -> str:
    """Share of the loaded model in VRAM, from /api/ps (size vs size_vram)."""
    for m in json.load(urllib.request.urlopen(OLLAMA + "/api/ps"))["models"]:
        if m["name"] == model:
            gpu = round(100 * m["size_vram"] / m["size"])
            return f"{gpu}% GPU ({m['size'] / 2**30:.1f} GiB)"
    return "?"


def unload(model: str) -> None:
    post("/api/generate", {"model": model, "keep_alive": 0})


def measure(model: str, num_ctx: int) -> dict:
    t0 = time.monotonic()
    r = post("/api/generate", {
        "model": model, "prompt": PROMPT, "stream": False, "think": False,
        "options": {"num_ctx": num_ctx, "num_predict": 256, "temperature": 0},
    })
    wall = time.monotonic() - t0
    result = {
        "model": model,
        "processor": processor_split(model),
        "gpu_mib_loaded": gpu_used_mib(),
        "load_s": round(r.get("load_duration", 0) / 1e9, 1),
        "prompt_tok_s": round(r["prompt_eval_count"] / (r["prompt_eval_duration"] / 1e9), 1),
        "gen_tok_s": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1),
        "gen_tokens": r["eval_count"],
        "wall_s": round(wall, 1),
    }
    unload(model)
    return result


def generation_models() -> list[str]:
    tags = json.load(urllib.request.urlopen(OLLAMA + "/api/tags"))["models"]
    return [m["name"] for m in tags if "embed" not in m["name"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ctx", type=int, default=DEFAULT_CTX)
    ap.add_argument("--tag", default="")
    ap.add_argument("models", nargs="*")
    args = ap.parse_args()
    models = args.models or generation_models()
    baseline = gpu_used_mib()
    results = []
    for m in models:
        print(f"measuring {m} …", file=sys.stderr)
        try:
            results.append(measure(m, args.ctx))
        except Exception as e:  # keep going; a model that fails to load is a result too
            results.append({"model": m, "error": str(e)})

    out = Path(__file__).parent / "results" / f"model_fit{'_' + args.tag if args.tag else ''}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"num_ctx": args.ctx, "gpu_baseline_mib": baseline,
                               "results": results}, indent=2))

    print(f"\nnum_ctx={args.ctx}, GPU baseline {baseline} MiB of 4096")
    print(f"{'model':<20} {'processor':<16} {'GPU MiB':>8} {'load s':>7} {'prompt t/s':>11} {'gen t/s':>8}")
    for r in results:
        if "error" in r:
            print(f"{r['model']:<20} ERROR {r['error']}")
        else:
            print(f"{r['model']:<20} {r['processor']:<16} {r['gpu_mib_loaded']:>8} {r['load_s']:>7} "
                  f"{r['prompt_tok_s']:>11} {r['gen_tok_s']:>8}")


if __name__ == "__main__":
    main()
