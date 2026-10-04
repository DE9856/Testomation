"""Spike Q26: observe-then-assert spec generation.

Same 10 flows as specgen.py. The model never guesses the outcome page:
  1. ACTIONS: the model writes action steps only (`expect` removed from the decoder's schema).
  2. RUN: actions run on a fresh app; failures go to batched repair rounds (≤ 3), as before.
     A run that succeeds records the final page (aria snapshot) and the generated values.
  3. ASSERT: the model writes `expect` steps from the flow's stated expectation + the real final
     page + the $var names of generated values. The flow text stays the oracle.
  4. VERIFY: actions + expects run on a fresh app. Assertions get no repairs.

Run: uv run python spike/observe.py [model]   → spike/results/observe_<model>/
"""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).parent))
import specgen  # noqa: E402
from specgen import FLOWS, ROOT, SECRETS, app_context, decoder_view, post, rules, unload  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "test-spec.schema.json").read_text())
STEP_BRANCHES = SCHEMA["$defs"]["step"]["oneOf"]
EXPECT_BRANCH = next(b for b in STEP_BRANCHES if b["properties"]["action"].get("const") == "expect")

ACTIONS_SCHEMA = copy.deepcopy(SCHEMA)
ACTIONS_SCHEMA["$defs"]["step"]["oneOf"] = [b for b in STEP_BRANCHES if b is not EXPECT_BRANCH]
EXPECTS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["expects"],
    "properties": {"expects": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"$ref": "#/$defs/expect"}}},
    "$defs": {**copy.deepcopy(SCHEMA["$defs"]), "expect": copy.deepcopy(EXPECT_BRANCH)},
}
FULL_VALIDATOR = Draft202012Validator(SCHEMA)
ACTIONS_VALIDATOR = Draft202012Validator(ACTIONS_SCHEMA)

ACTIONS_NOTE = """
THIS TASK: write only the ACTION steps that perform the flow (goto, fill, click, wait_for, ...).
Do not write expect steps — assertions are added later, after the actions have been run.
Use {"$faker": ..., "as": "<name>"} for generated data so it can be checked later."""

ASSERT_RULES = """You add assertions to an end-to-end test. The test's action steps have already run
successfully; you see the page exactly as it was at the end.

Write `expect` steps that check the OUTCOME the flow describes:
- {"action": "expect", "target": ..., "assert": "visible" | "hidden" | "hasText" | "hasValue" | "count", "value": ...}
  or {"action": "expect", "assert": "url", "value": "/#/..."} (no target).
- Targets come from the snapshot. `- button "Login"` (quoted) is a NAME: {"role": "button", "name": "Login"}.
  `- paragraph: Some text` / `- listitem: Some text` (after a colon) is CONTENT, not a name:
  target it as {"text": "Some text"}. Links like `- link "bob"` are {"role": "link", "name": "bob"}.
- Generated values change every run. If the outcome involves a value that was generated, assert it
  with the same {"$var": "<name>"}, never the literal value you see.
- Check what the flow says should happen. Use what the page shows to find the right elements,
  but if the page does NOT show the expected outcome, still assert the expected outcome — the
  test should then fail, because that is a bug.
- 1 to 4 expects. Prefer specific checks (the new title, the error text, the count) over generic
  ones (a heading that is always there)."""


def chat(model: str, messages: list[dict], schema: dict) -> tuple[dict, dict]:
    try:
        r = post("/api/chat", {
            "model": model, "stream": False, "think": False, "format": decoder_view(schema),
            "messages": messages,
            "options": {"num_ctx": 8192, "num_gpu": 99, "temperature": 0, "num_predict": 2000},
        })
    except Exception as e:
        return {"_call_error": str(e)[:200]}, {"seconds": 0}
    stats = {"prompt_tokens": r.get("prompt_eval_count"), "gen_tokens": r.get("eval_count"),
             "seconds": round(r.get("total_duration", 0) / 1e9, 1)}
    try:
        return json.loads(r["message"]["content"]), stats
    except json.JSONDecodeError as e:
        return {"_invalid_json": str(e)}, stats


def action_examples() -> list[dict]:
    msgs = []
    for f in sorted(specgen.EXAMPLES.glob("*.json")):
        spec = json.loads(f.read_text())
        spec["steps"] = [s for s in spec["steps"] if s["action"] != "expect"]
        msgs += [{"role": "user", "content": f"Flow: {spec['flow']}"},
                 {"role": "assistant", "content": json.dumps(spec)}]
    return msgs


def system() -> str:
    return rules("v2") + ACTIONS_NOTE + "\n\n" + app_context()


def gen_actions(model: str, flow: str, idx: int) -> tuple[dict, dict]:
    spec, stats = chat(model, [{"role": "system", "content": system()}, *action_examples(),
                               {"role": "user", "content": f"Flow: {flow}"}], ACTIONS_SCHEMA)
    spec.update(id=f"flow{idx:02d}", flow=flow)
    return spec, stats


def repair_actions(model: str, spec: dict, failure: dict) -> tuple[dict, dict]:
    fixed, stats = chat(model, [{"role": "system", "content": system()}, {"role": "user", "content": (
        f"These action steps failed when run.\n\nFlow: {spec['flow']}\n\nSpec:\n{json.dumps(spec, indent=1)}\n\n"
        f"Failed at step {failure['step'] or '(before running)'}: {failure['error']}\n\n"
        f"Page at the moment of failure (aria snapshot):\n{failure['aria']}\n\n"
        "Return the corrected action steps (you may change targets, add wait_for or missing steps, fix urls).")}],
        ACTIONS_SCHEMA)
    fixed.update(id=spec["id"], flow=spec["flow"])
    return fixed, stats


def trim_snapshot(aria: str, limit: int = 3500) -> str:
    """Drop the footer (same on every page) and cap the length."""
    out = re.split(r"\n- contentinfo:", aria)[0]
    return out[:limit] + ("\n# … (truncated)" if len(out) > limit else "")


def gen_expects(model: str, spec: dict, observed: dict) -> tuple[list[dict], dict]:
    var_lines = "\n".join(f"- {k} = {json.dumps(v)}  → assert it as {{\"$var\": \"{k}\"}}"
                          for k, v in observed["vars"].items()) or "- (none)"
    out, stats = chat(model, [{"role": "system", "content": ASSERT_RULES}, {"role": "user", "content": (
        f"Flow: {spec['flow']}\n\nAction steps that ran:\n{json.dumps(spec['steps'], indent=1)}\n\n"
        f"Generated values in this run:\n{var_lines}\n\n"
        f"Page at the end of the actions (aria snapshot):\n{trim_snapshot(observed['aria'])}\n\n"
        "Return {\"expects\": [...]}.")}], EXPECTS_SCHEMA)
    return out.get("expects", []), stats


WORKERS = "2"


def run(specs: dict[str, dict], out: Path) -> dict[str, dict]:
    spec_dir = out / "specs"
    shutil.rmtree(spec_dir, ignore_errors=True)
    spec_dir.mkdir(parents=True)
    for sid, spec in specs.items():
        (spec_dir / f"{sid}.json").write_text(json.dumps(spec, indent=1))
    subprocess.run([str(ROOT / "bench" / "app" / "conduit.sh"), "reset"], check=True, capture_output=True)
    results = out / "results.json"
    env = {**os.environ, **SECRETS, "TESTO_SPECS_DIR": str(spec_dir), "TESTO_RETRIES": "0",
           "TESTO_RESULTS_FILE": str(results), "TESTO_WORKERS": WORKERS, "TESTO_ATTACH_FINAL": "1"}
    subprocess.run(["npx", "playwright", "test", "--output", str(out / "test-results")],
                   cwd=ROOT / "runner", env=env, capture_output=True)
    outcome: dict[str, dict] = {}

    def attachment(res: dict, name: str) -> str:
        a = next((a for a in res.get("attachments", []) if a["name"] == name), None)
        if not a:
            return ""
        return Path(a["path"]).read_text() if a.get("path") else base64.b64decode(a.get("body", "")).decode()

    def walk(suite: dict) -> None:
        for s in suite.get("specs", []):
            for t in s["tests"]:
                res = t["results"][-1]
                step = next((a["description"] for a in t.get("annotations", []) if a["type"] == "failing-step"), None)
                err = re.sub(r"\x1b\[[0-9;]*m", "", res.get("error", {}).get("message", ""))
                outcome[s["title"]] = {
                    "status": res["status"], "step": step, "error": err[:600],
                    "aria": (attachment(res, "aria-snapshot") or attachment(res, "final-aria"))[:4000],
                    "vars": json.loads(attachment(res, "vars") or "{}"),
                }
        for c in suite.get("suites", []):
            walk(c)

    for s in json.loads(results.read_text())["suites"]:
        walk(s)
    return outcome


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen3:4b"
    out = ROOT / "spike" / "results" / f"observe_{model.replace(':', '_')}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    log: dict = {"model": model, "flows": {}}
    t_start = time.monotonic()

    # 1. actions
    pending, calls = {}, []
    for i, flow in enumerate(FLOWS, 1):
        spec, st = gen_actions(model, flow, i)
        pending[spec["id"]] = spec
        calls.append(st)
        log["flows"][spec["id"]] = {"flow": flow, "history": []}
    print(f"actions generated for {len(pending)} flows", flush=True)

    # 2. run actions, batched repair rounds
    observed: dict[str, dict] = {}
    actions_ok: dict[str, dict] = {}
    for rnd in range(4):
        unload(model)
        valid = {sid: s for sid, s in pending.items() if not list(ACTIONS_VALIDATOR.iter_errors(s))}
        failures = {sid: {"step": None, "aria": "", "error": "Does not match the schema: " + "; ".join(
            e.message[:150] for e in list(ACTIONS_VALIDATOR.iter_errors(s))[:3])}
            for sid, s in pending.items() if sid not in valid}
        outcome = run(valid, out / f"actions_round{rnd}") if valid else {}
        for sid in valid:
            o = outcome.get(sid, {"status": "missing", "step": None, "error": "no result", "aria": "", "vars": {}})
            log["flows"][sid]["history"].append({"phase": "actions", "round": rnd, "status": o["status"],
                                                 "step": o["step"], "error": o["error"][:300]})
            if o["status"] == "passed":
                actions_ok[sid], observed[sid] = valid[sid], o
            else:
                failures[sid] = o
        print(f"actions round {rnd}: {len(actions_ok)}/{len(FLOWS)} run cleanly", flush=True)
        pending = {sid: pending[sid] for sid in failures}
        if not pending or rnd == 3:
            break
        for sid, f in failures.items():
            pending[sid], st = repair_actions(model, pending[sid], f)
            calls.append(st)

    # 3. assertions from the observed outcome
    full: dict[str, dict] = {}
    for sid, spec in actions_ok.items():
        exp, st = gen_expects(model, spec, observed[sid])
        calls.append(st)
        full[sid] = {**spec, "steps": spec["steps"] + exp}
        log["flows"][sid]["expects"] = exp
    unload(model)

    # 4. verify on a fresh app
    final = run({sid: s for sid, s in full.items() if not list(FULL_VALIDATOR.iter_errors(s))}, out / "verify")
    for sid, e in log["flows"].items():
        o = final.get(sid)
        e["final"] = ("no-actions" if sid not in actions_ok else "invalid" if o is None
                      else "passed" if o["status"] == "passed" and e.get("expects") else "failed")
        if o and o["status"] != "passed":
            e["verify_error"] = f"step {o['step']}: {o['error'][:300]}"
        if sid in full:
            (out / f"{sid}.json").write_text(json.dumps(full[sid], indent=1))
    ok = sum(e["final"] == "passed" for e in log["flows"].values())
    gen = [c for c in calls if c.get("seconds")]
    log["summary"] = {"passed": ok, "actions_ok": len(actions_ok), "model_calls": len(calls),
                      "mean_seconds": round(sum(c["seconds"] for c in gen) / max(len(gen), 1), 1),
                      "wall_minutes": round((time.monotonic() - t_start) / 60, 1)}
    (out / "summary.json").write_text(json.dumps(log, indent=1))
    print(f"\n{model}: {ok}/{len(FLOWS)} pass (actions ran cleanly for {len(actions_ok)}); {log['summary']}")


if __name__ == "__main__":
    main()
