"""Spike: capture real, labelled triage cases from the reference suite under seeded bugs/noise/flakes.

For each variant: BUGS=<variant> reset → run bench/reference (retries per variant) → keep
evidence (failing step, error, attempts, console/network signals, aria at failure).
Labels come from what was switched on, not from judgement:
  bug        a reference spec failing with a seeded bug on
  noise      a console/network signal on a test that passed (harmless by construction)
  flaky      a failure with only the intermittent-delay variant on
  test_issue a model-generated spec failing on the clean app (from earlier spike runs)
Also records the reference suite's kill matrix (which spec catches which bug).

Run: uv run python spike/triage_capture.py   → spike/results/triage_cases.json, kill_matrix.json
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spike" / "results"
SECRETS = {f"{u.upper()}_PASSWORD": f"{u}-pass-1" for u in ("alice", "bob", "carol", "dave")}
REFERENCE = ROOT / "bench" / "reference"

BUGS = {  # seeded bug → the reference spec written to catch it
    "login-error-hidden": "ref02-wrong-password", "signup-500": "ref03-signup",
    "publish-500": "ref04-publish", "comment-not-shown": "ref05-comment",
    "tag-filter-ignored": "ref06-tag-filter", "favorite-count-stuck": "ref07-favorite",
    "profile-articles-empty": "ref09-profile", "bio-not-saved": "ref10-bio",
}
NOISE = ["noise-analytics", "noise-console-warning"]
FLAKY = "flaky-slow-articles"


def run_suite(bugs: str, tag: str, retries: int) -> list[dict]:
    work = OUT / "triage_runs" / tag
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    subprocess.run([str(ROOT / "bench" / "app" / "conduit.sh"), "reset"], check=True,
                   capture_output=True, env={**os.environ, "BUGS": bugs})
    results = work / "results.json"
    env = {**os.environ, **SECRETS, "TESTO_SPECS_DIR": str(REFERENCE), "TESTO_RETRIES": str(retries),
           "TESTO_RESULTS_FILE": str(results), "TESTO_WORKERS": "2"}
    subprocess.run(["npx", "playwright", "test", "--output", str(work / "test-results")],
                   cwd=ROOT / "runner", env=env, capture_output=True)
    specs = {json.loads(p.read_text())["id"]: json.loads(p.read_text()) for p in REFERENCE.glob("*.json")}
    tests = []

    def att(res: dict, name: str) -> str:
        a = next((a for a in res.get("attachments", []) if a["name"] == name), None)
        if not a:
            return ""
        return Path(a["path"]).read_text() if a.get("path") else base64.b64decode(a.get("body", "")).decode()

    def walk(suite: dict) -> None:
        for s in suite.get("specs", []):
            for t in s["tests"]:
                attempts = []
                for res in t["results"]:
                    step = next((a["description"] for a in res.get("annotations", []) + t.get("annotations", [])
                                 if a["type"] == "failing-step"), None)
                    attempts.append({
                        "status": res["status"], "failing_step": step,
                        "error": re.sub(r"\x1b\[[0-9;]*m", "", res.get("error", {}).get("message", ""))[:1200],
                        "aria": att(res, "aria-snapshot")[:3000],
                        "signals": json.loads(att(res, "signals") or "[]"),
                    })
                spec = specs.get(s["title"], {})
                tests.append({"test": s["title"], "flow": spec.get("flow", ""), "steps": spec.get("steps", []),
                              "attempts": attempts, "final": attempts[-1]["status"] if attempts else "missing"})
        for c in suite.get("suites", []):
            walk(c)

    for s in json.loads(results.read_text())["suites"]:
        walk(s)
    return tests


def case_from_failure(t: dict, label: str, variant: str) -> dict:
    first_fail = next(a for a in t["attempts"] if a["status"] != "passed")
    step_no = int(first_fail["failing_step"]) if first_fail["failing_step"] else None
    return {"label": label, "variant": variant, "kind": "failed-test", "test": t["test"], "flow": t["flow"],
            "failing_step": step_no,
            "step": t["steps"][step_no - 1] if step_no and step_no <= len(t["steps"]) else None,
            "attempts": [a["status"] for a in t["attempts"]], "error": first_fail["error"],
            "signals": first_fail["signals"], "aria": first_fail["aria"]}


def test_issue_cases(limit: int = 6) -> list[dict]:
    """Model-generated specs that failed on the clean app in earlier spike runs (wrong targets etc.)."""
    cases, seen = [], set()
    for summary in sorted(OUT.glob("specgen_qwen3_4b_v*/summary.json")):
        run = summary.parent
        for rdir in sorted(run.glob("round*")):
            res = rdir / "results.json"
            if not res.exists():
                continue
            for suite in json.loads(res.read_text())["suites"]:
                for s in suite.get("specs", []):
                    for t in s["tests"]:
                        r = t["results"][-1]
                        if r["status"] == "passed" or s["title"] in seen:
                            continue
                        step = next((a["description"] for a in t.get("annotations", []) if a["type"] == "failing-step"), None)
                        spec = json.loads((rdir / "specs" / f"{s['title']}.json").read_text())
                        aria = next((a for a in r.get("attachments", []) if a["name"] == "aria-snapshot"), None)
                        aria_text = (Path(aria["path"]).read_text() if aria and aria.get("path") else
                                     base64.b64decode(aria["body"]).decode() if aria else "")
                        n = int(step) if step else None
                        seen.add(s["title"])
                        cases.append({"label": "test_issue", "variant": f"generated:{run.name}", "kind": "failed-test",
                                      "test": s["title"], "flow": spec.get("flow", ""), "failing_step": n,
                                      "step": spec["steps"][n - 1] if n and n <= len(spec["steps"]) else None,
                                      "attempts": ["failed"],
                                      "error": re.sub(r"\x1b\[[0-9;]*m", "", r.get("error", {}).get("message", ""))[:1200],
                                      "signals": [], "aria": aria_text[:3000]})
    return cases[:limit]


def main() -> None:
    cases, kill = [], {}
    clean = run_suite("", "clean", 0)
    kill["clean_passed"] = [t["test"] for t in clean if t["final"] == "passed"]
    print(f"clean: {len(kill['clean_passed'])}/{len(clean)} passed", flush=True)

    for bug, target in BUGS.items():
        tests = run_suite(bug, bug, 0)
        failed = [t for t in tests if t["final"] != "passed"]
        kill[bug] = {"target": target, "caught_by_target": any(t["test"] == target for t in failed),
                     "failed": [t["test"] for t in failed]}
        cases += [case_from_failure(t, "bug", bug) for t in failed]
        print(f"{bug}: {len(failed)} failing {[t['test'] for t in failed]}", flush=True)

    for noise in NOISE:
        tests = run_suite(noise, noise, 0)
        seen = set()
        for t in tests:
            if t["final"] != "passed":
                continue
            for sig in t["attempts"][-1]["signals"]:
                key = (sig["kind"], sig["text"][:80])
                if key in seen:
                    continue
                seen.add(key)
                cases.append({"label": "noise", "variant": noise, "kind": "signal-on-passing-test",
                              "test": t["test"], "flow": t["flow"], "signal": sig, "attempts": ["passed"],
                              "other_signals": [s for s in t["attempts"][-1]["signals"] if s is not sig][:5]})
        print(f"{noise}: {sum(c['variant'] == noise for c in cases)} signal cases", flush=True)

    flaky_cases = []
    for i in range(3):
        for t in run_suite(FLAKY, f"{FLAKY}-{i}", 1):
            if any(a["status"] != "passed" for a in t["attempts"]):
                flaky_cases.append(case_from_failure(t, "flaky", FLAKY))
        if len(flaky_cases) >= 5:
            break
    cases += flaky_cases[:6]
    print(f"flaky: {len(flaky_cases)} cases", flush=True)

    ti = test_issue_cases()
    cases += ti
    print(f"test_issue: {len(ti)} cases", flush=True)

    subprocess.run([str(ROOT / "bench" / "app" / "conduit.sh"), "reset"], check=True, capture_output=True,
                   env={**os.environ, "BUGS": ""})
    for i, c in enumerate(cases):
        c["id"] = f"case{i + 1:02d}"
    (OUT / "triage_cases.json").write_text(json.dumps(cases, indent=1))
    (OUT / "kill_matrix.json").write_text(json.dumps(kill, indent=1))
    from collections import Counter
    print("cases:", len(cases), dict(Counter(c["label"] for c in cases)))


if __name__ == "__main__":
    main()
