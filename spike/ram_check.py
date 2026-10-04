"""Spike: peak RAM / swap / VRAM on this laptop for the phase 0–2 stack (no Langfuse yet).

Scenarios (sampled every 0.5 s from /proc/meminfo and nvidia-smi):
  idle     — Postgres (deploy/compose.yaml) + Conduit up, nothing running
  model    — qwen3:4b loaded fully on GPU, generating
  suite    — reference suite on 2 Playwright workers, model unloaded (the designed default)
  both     — reference suite on 2 workers while the model generates (exploration-like worst case)

Run: uv run python spike/ram_check.py   → spike/results/ram_check.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from testomation.bench import REFERENCE, SECRETS, reset_app  # noqa: E402
from testomation.runner import ROOT, run_specs  # noqa: E402

MODEL = "qwen3:4b"


def meminfo() -> dict[str, int]:
    vals = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":")
        vals[k] = int(v.split()[0]) // 1024  # MiB
    return vals


def gpu_mib() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout
    return int(out.strip().splitlines()[0])


class Sampler:
    def __init__(self) -> None:
        self.samples: list[dict] = []
        self._stop = threading.Event()

    def __enter__(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            m = meminfo()
            self.samples.append({"used": m["MemTotal"] - m["MemAvailable"], "available": m["MemAvailable"],
                                 "swap_used": m["SwapTotal"] - m["SwapFree"], "gpu": gpu_mib()})
            time.sleep(0.5)

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._t.join()

    def summary(self) -> dict:
        s = self.samples
        return {"samples": len(s), "peak_used_mib": max(x["used"] for x in s),
                "min_available_mib": min(x["available"] for x in s),
                "swap_used_mib": {"start": s[0]["swap_used"], "peak": max(x["swap_used"] for x in s)},
                "peak_gpu_mib": max(x["gpu"] for x in s)}


def ollama(body: dict) -> None:
    import urllib.request
    req = urllib.request.Request("http://localhost:11434/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=600).read()


def generate_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        ollama({"model": MODEL, "prompt": "Write a 300-word test plan for a blogging app.", "stream": False,
                "think": False, "options": {"num_gpu": 99, "num_ctx": 8192, "num_predict": 400}})


def main() -> None:
    subprocess.run(["docker", "compose", "-f", str(ROOT / "deploy" / "compose.yaml"), "up", "-d"],
                   check=True, capture_output=True)
    reset_app("")
    ollama({"model": MODEL, "keep_alive": 0})
    total = meminfo()["MemTotal"]
    result: dict = {"mem_total_mib": total, "scenarios": {}}
    work = ROOT / "data" / "ram_check"

    with Sampler() as s:
        time.sleep(5)
    result["scenarios"]["idle"] = s.summary()

    with Sampler() as s:
        stop = threading.Event()
        t = threading.Thread(target=generate_loop, args=(stop,))
        t.start()
        time.sleep(25)
        stop.set()
        t.join()
    result["scenarios"]["model"] = s.summary()
    ollama({"model": MODEL, "keep_alive": 0})

    with Sampler() as s:
        run_specs(REFERENCE, work / "suite", secrets=SECRETS, workers=2)
    result["scenarios"]["suite"] = s.summary()

    reset_app("")
    with Sampler() as s:
        stop = threading.Event()
        t = threading.Thread(target=generate_loop, args=(stop,))
        t.start()
        time.sleep(5)  # model loaded and busy before browsers start
        run_specs(REFERENCE, work / "both", secrets=SECRETS, workers=2)
        stop.set()
        t.join()
    result["scenarios"]["both"] = s.summary()
    ollama({"model": MODEL, "keep_alive": 0})
    reset_app("")

    out = ROOT / "spike" / "results" / "ram_check.json"
    out.write_text(json.dumps(result, indent=1))
    print(f"MemTotal {total} MiB")
    for name, r in result["scenarios"].items():
        print(f"{name:<6} peak used {r['peak_used_mib']:>6} MiB  min available {r['min_available_mib']:>6} MiB  "
              f"swap {r['swap_used_mib']['start']}→{r['swap_used_mib']['peak']} MiB  GPU {r['peak_gpu_mib']} MiB")


if __name__ == "__main__":
    main()
