"""`testomation bench`: score the seeded-bug benchmark (docs/EVALUATION.md).

Full tier: the reference suite runs on the clean app and under every catalogue variant, N times.
  - bug variants   → kill rate: does the spec named in `catches` fail? (and no other spec)
  - noise variants → false alarms: any spec failing under harmless noise
  - flaky variant  → how often specs fail with no bug present (no retries)
  - clean          → every reference spec must pass
Replay tier (`--replay`): scores triage on recorded cases without running the app. The analyzer
arrives in phase 2; until then it reports the baselines the analyzer has to beat.

Results: bench/results/<timestamp>.json
"""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from testomation.runner import ROOT, run_specs

BENCH = ROOT / "bench"
CONDUIT = BENCH / "app" / "conduit.sh"
REFERENCE = BENCH / "reference"
# Seeded benchmark users (public test data, not real credentials; see bench/app/README.md).
SECRETS = {f"{u.upper()}_PASSWORD": f"{u}-pass-1" for u in ("alice", "bob", "carol", "dave")}


@dataclass(frozen=True)
class Variant:
    id: str
    kind: str  # 'bug' | 'noise' | 'flaky'
    category: str
    description: str
    catches: str | None = None
    held_out: bool = False


def load_catalogue(path: Path = BENCH / "catalogue.toml") -> list[Variant]:
    data = tomllib.loads(path.read_text())
    variants = [Variant(**v) for v in data["variant"]]
    for v in variants:
        if v.kind not in ("bug", "noise", "flaky"):
            raise ValueError(f"{v.id}: unknown kind {v.kind!r}")
        if v.kind == "bug" and not v.catches:
            raise ValueError(f"{v.id}: a bug needs `catches` (the reference spec that must fail)")
    return variants


def reset_app(bugs: str = "") -> None:
    subprocess.run([str(CONDUIT), "reset"], check=True, capture_output=True,
                   env={**os.environ, "BUGS": bugs})


def span(values: list[float]) -> dict:
    """Mean and min–max — benchmark numbers are reported as ranges (EVALUATION.md)."""
    return {"mean": round(sum(values) / len(values), 3), "min": min(values), "max": max(values)}


def run_full(runs: int, work: Path) -> dict:
    variants = load_catalogue()
    n_specs = len(list(REFERENCE.glob("*.json")))
    per_run: list[dict] = []
    for r in range(runs):
        row: dict = {}
        for v in [Variant("clean", "clean", "", "")] + variants:
            reset_app("" if v.id == "clean" else v.id)
            results = run_specs(REFERENCE, work / f"run{r}" / v.id, secrets=SECRETS)
            failed = sorted(t.spec_id for t in results if not t.passed)
            row[v.id] = {"failed": failed, "total": len(results)}
            passed = len(results) - len(failed)
            note = f"  failing: {', '.join(failed)}" if failed else ""
            label = f"run {r + 1}/{runs} {v.id:<24}"
            print(f"  {label} {passed}/{len(results)} passed{note}", flush=True)
        per_run.append(row)
    reset_app("")

    return {"tier": "full", "runs": runs, "summary": score(variants, per_run, n_specs),
            "kill_matrix": kill_matrix(variants, per_run), "per_run": per_run}


def _caught(v: Variant, run: dict) -> bool:
    return v.catches in run[v.id]["failed"]


def _failures(variants: list[Variant], kind: str, run: dict) -> int:
    return sum(len(run[v.id]["failed"]) for v in variants if v.kind == kind)


def score(variants: list[Variant], per_run: list[dict], n_specs: int) -> dict:
    bugs = [v for v in variants if v.kind == "bug"]
    held = [v for v in bugs if v.held_out]
    return {
        "clean_pass_rate": span([(n_specs - len(r["clean"]["failed"])) / n_specs for r in per_run]),
        "kill_rate": span([sum(_caught(v, r) for v in bugs) / len(bugs) for r in per_run]),
        "kill_rate_held_out": span([sum(_caught(v, r) for v in held) / max(1, len(held))
                                    for r in per_run]),
        "collateral_failures": span([sum(len(set(r[v.id]["failed"]) - {v.catches}) for v in bugs)
                                     for r in per_run]),
        "noise_false_alarms": span([_failures(variants, "noise", r) for r in per_run]),
        "flaky_failure_rate": span([_failures(variants, "flaky", r) / n_specs for r in per_run]),
    }


def kill_matrix(variants: list[Variant], per_run: list[dict]) -> dict:
    return {v.id: {"catches": v.catches, "caught_in_runs": sum(_caught(v, r) for r in per_run)}
            for v in variants if v.kind == "bug"}


def run_replay(path: Path = BENCH / "replay" / "cases.json") -> dict:
    cases = json.loads(path.read_text())
    labels = Counter(c["label"] for c in cases)
    return {
        "tier": "replay", "cases": len(cases), "labels": dict(labels),
        "analyzer": "not implemented yet (phase 2)",
        "baselines": {"everything_is_a_bug": round(labels.get("bug", 0) / len(cases), 3)},
    }


def main(*, runs: int = 3, replay: bool = False) -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = BENCH / "results"
    out_dir.mkdir(exist_ok=True)
    if replay:
        result = run_replay()
    else:
        n = len(load_catalogue()) + 1
        print(f"bench: reference suite × {n} app variants × {runs} runs", flush=True)
        result = run_full(runs, ROOT / "data" / "bench" / stamp)
    result["timestamp"] = stamp
    out = out_dir / f"{stamp}-{result['tier']}.json"
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result.get("summary", result), indent=1))
    print(f"→ {out.relative_to(ROOT)}")
    return 0
