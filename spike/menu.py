"""Spike: templates + assertion menu, scored by seeded-bug kill rate.

1. PLAN (model): precondition (log in as which seeded user, or nobody), start page, action steps.
   Login is a template — the model never writes it.
2. RUN on the clean app (batched repair rounds ≤ 3 for the actions). The runner records the
   settled page after the start page loads ("before") and at the end ("after").
3. MENU (deterministic): candidate assertions from the before/after difference — new headings,
   text, buttons, field values; elements that disappeared; any candidate showing a generated
   value becomes a `$var` assertion automatically.
4. PICK (model): choose the candidates that check the outcome the flow describes.
5. SCORE: a spec counts if it passes on the clean app AND fails with its flow's seeded bug on.

Run: uv run python spike/menu.py [model]   → spike/results/menu_<model>/
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import observe  # noqa: E402
from observe import ACTIONS_SCHEMA, chat, trim_snapshot  # noqa: E402
from specgen import FLOWS, ROOT, app_context, rules, unload  # noqa: E402

BUG_FOR_FLOW = {2: "login-error-hidden", 3: "signup-500", 4: "publish-500", 5: "comment-not-shown",
                6: "tag-filter-ignored", 7: "favorite-count-stuck", 9: "profile-articles-empty",
                10: "bio-not-saved"}
USERS = ["nobody", "alice", "bob", "carol", "dave"]

PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["as_user", "start", "steps"],
    "properties": {
        "as_user": {"enum": USERS},
        "start": {"type": "string", "pattern": "^/#/.*$"},
        "steps": {"type": "array", "minItems": 1, "maxItems": 15, "items": {"$ref": "#/$defs/step"}},
    },
    "$defs": ACTIONS_SCHEMA["$defs"],
}

PLAN_NOTE = """
THIS TASK: plan the test as JSON with three parts.
- "as_user": who must be logged in before the flow starts ("nobody" if no login is needed). The
  login itself is done for you — never write login steps.
- "start": the page the flow starts on, e.g. "/#/settings" or "/#/article/dave-s-post-3".
- "steps": only the ACTION steps of the flow itself (fill, click, select, wait_for, goto to a later
  page if the outcome is shown elsewhere). No expect steps — assertions are chosen afterwards.
Use {"$faker": ..., "as": "<name>"} for generated data."""


def login(user: str) -> list[dict]:
    if user == "nobody":
        return []
    return [
        {"action": "goto", "url": "/#/login"},
        {"action": "fill", "target": {"role": "textbox", "name": "Email"}, "value": f"{user}@conduit.test"},
        {"action": "fill", "target": {"role": "textbox", "name": "Password"}, "value": {"$secret": f"{user.upper()}_PASSWORD"}},
        {"action": "click", "target": {"role": "button", "name": "Login"}},
        {"action": "wait_for", "target": {"role": "button", "name": "Your Feed"}, "state": "visible"},
    ]


def name_generated(steps: list[dict]) -> list[dict]:
    """Give every $faker value a name, so it can always be asserted as a $var later."""
    n = 0
    for st in steps:
        v = st.get("value")
        if isinstance(v, dict) and "$faker" in v and "as" not in v:
            n += 1
            v["as"] = f"gen{n}"
    return steps


def build(plan: dict, sid: str, flow: str) -> dict:
    name_generated(plan["steps"])
    pre = login(plan["as_user"]) + [{"action": "goto", "url": plan["start"]}]
    return {"spec_version": 1, "id": sid, "flow": flow, "_observe_after": len(pre),
            "steps": pre + plan["steps"]}


def gen_plan(model: str, flow: str) -> dict:
    system = rules("v2") + PLAN_NOTE + "\n\n" + app_context()
    plan, _ = chat(model, [{"role": "system", "content": system}, {"role": "user", "content": f"Flow: {flow}"}], PLAN_SCHEMA)
    return plan


def repair_plan(model: str, plan: dict, flow: str, failure: dict) -> dict:
    system = rules("v2") + PLAN_NOTE + "\n\n" + app_context()
    fixed, _ = chat(model, [{"role": "system", "content": system}, {"role": "user", "content": (
        f"Flow: {flow}\n\nThis plan failed when run:\n{json.dumps(plan, indent=1)}\n\n"
        f"(The login and the goto to the start page run first, then the steps.)\n"
        f"Failure: {failure['error'][:500]}\n\nPage at the failure (aria snapshot):\n{trim_snapshot(failure['aria'], 2500)}\n\n"
        "Return the corrected plan.")}], PLAN_SCHEMA)
    return fixed


# ---------- the deterministic assertion menu ----------

LINE = re.compile(r'^\s*- (?P<role>[a-z]+)(?: "(?P<name>[^"]*)")?(?: \[[^\]]*\])?(?::\s*(?P<text>.*))?$')
KEEP = {"heading", "button", "link", "textbox", "paragraph", "listitem", "text", "alert", "status", "strong", "emphasis"}


def items(aria: str) -> list[tuple[str, str, str]]:
    """(role, name, text) for each meaningful line of an aria snapshot, footer dropped."""
    out = []
    for line in aria.split("\n- contentinfo:")[0].splitlines():
        m = LINE.match(line)
        if not m or m["role"] not in KEEP:
            continue
        name, text = (m["name"] or "").strip(), (m["text"] or "").strip().strip('"')
        if not name and not text:
            continue
        out.append((m["role"], name, text))
    return out


def menu(before: str, after: str, variables: dict) -> list[dict]:
    b, a = items(before), items(after)
    b_set, a_set = set(b), set(a)
    cands: list[tuple[int, str, dict]] = []  # (priority, description, expect)
    seen = set()

    def add(prio: int, desc: str, exp: dict) -> None:
        key = json.dumps(exp, sort_keys=True)
        if key not in seen:
            seen.add(key)
            cands.append((prio, desc, exp))

    for k, v in variables.items():  # generated values now visible → assert via $var
        sv = str(v)
        if any(sv and (sv in n or sv in t) for _, n, t in a):
            add(0, f'the generated value "{k}" ({sv[:40]}) is shown on the page',
                {"action": "expect", "target": {"role": "main"}, "assert": "hasText", "value": {"$var": k}})
    for role, name, text in a:
        if (role, name, text) in b_set:
            continue
        if any(str(v) and (str(v) in name or str(v) in text) for v in variables.values()):
            continue  # covered by the $var candidate
        if role == "textbox" and name:
            add(2, f'field "{name}" now contains "{text[:50]}"',
                {"action": "expect", "target": {"role": "textbox", "name": name}, "assert": "hasValue", "value": text})
        elif name:
            prio = 1 if role in ("heading", "alert", "status") else 3
            add(prio, f'{role} "{name}" appeared', {"action": "expect", "target": {"role": role, "name": name}, "assert": "visible"})
        elif text:
            add(1, f'text "{text[:70]}" appeared', {"action": "expect", "target": {"text": text}, "assert": "visible"})
    for role, name, text in b:
        if (role, name, text) in a_set or not name or role == "textbox":
            continue
        if any(r == role and n == name for r, n, _ in a):
            continue  # still present somewhere
        add(4, f'{role} "{name}" disappeared', {"action": "expect", "target": {"role": role, "name": name}, "assert": "hidden"})
    for role, name, text in a:  # present at the end (unchanged): for outcomes that are a state
        if (role, name, text) not in b_set:
            continue
        if role in ("heading", "alert", "status") and name:
            add(5, f'{role} "{name}" is shown', {"action": "expect", "target": {"role": role, "name": name}, "assert": "visible"})
        elif role in ("paragraph", "listitem", "text") and text and len(text) > 3:
            add(6, f'text "{text[:70]}" is shown', {"action": "expect", "target": {"text": text}, "assert": "visible"})
    cands.sort(key=lambda c: c[0])
    return [{"desc": d, "expect": e} for _, d, e in cands[:30]]


def pick(model: str, flow: str, cands: list[dict]) -> list[int]:
    listing = "\n".join(f"{i}. {c['desc']}" for i, c in enumerate(cands))
    schema = {"type": "object", "additionalProperties": False, "required": ["picks"],
              "properties": {"picks": {"type": "array", "minItems": 1, "maxItems": 4,
                                       "items": {"enum": list(range(len(cands)))}}}}
    out, _ = chat(model, [{"role": "system", "content": (
        "You choose assertions for an end-to-end test. The flow's actions have run; below is what "
        "changed on the page, then what is shown at the end. Pick the 1–4 items that prove the OUTCOME "
        "the flow describes. Ignore incidental items (navigation chrome, unrelated content). Answer as JSON.")},
        {"role": "user", "content": f"Flow: {flow}\n\nWhat changed:\n{listing}"}], schema)
    return [p for p in out.get("picks", []) if isinstance(p, int) and 0 <= p < len(cands)]


def run_variant(specs: dict[str, dict], out: Path, bugs: str) -> dict[str, dict]:
    env_backup = os.environ.get("BUGS")
    os.environ["BUGS"] = bugs
    try:
        return observe.run(specs, out)
    finally:
        if env_backup is None:
            os.environ.pop("BUGS", None)
        else:
            os.environ["BUGS"] = env_backup


def before_after(out: Path, sid: str) -> tuple[str, str]:
    """Read the before/after snapshots from a run's JSON report."""
    import base64
    report = json.loads((out / "results.json").read_text())

    def find(suite):
        for s in suite.get("specs", []):
            if s["title"] == sid:
                return s["tests"][0]["results"][-1]
        for c in suite.get("suites", []):
            r = find(c)
            if r:
                return r

    res = next(r for r in (find(s) for s in report["suites"]) if r)

    def att(name):
        a = next((a for a in res.get("attachments", []) if a["name"] == name), None)
        if not a:
            return ""
        return Path(a["path"]).read_text() if a.get("path") else base64.b64decode(a["body"]).decode()
    return att("before-aria"), att("final-aria")


def main() -> None:
    observe.WORKERS = "1"  # serial: a before/after diff must not see other tests' changes
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen3:4b"
    out = ROOT / "spike" / "results" / f"menu_{model.replace(':', '_')}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    log = {"model": model, "flows": {}}

    plans = {f"flow{i:02d}": gen_plan(model, f) for i, f in enumerate(FLOWS, 1)}
    flows = {f"flow{i:02d}": f for i, f in enumerate(FLOWS, 1)}
    ok_specs, observed = {}, {}
    pending = dict(plans)
    for rnd in range(4):
        unload(model)
        specs = {}
        for sid, p in pending.items():
            if not isinstance(p.get("steps"), list) or p.get("as_user") not in USERS:
                continue
            specs[sid] = build(p, sid, flows[sid])
        res = observe.run(specs, out / f"actions_round{rnd}") if specs else {}
        failures = {}
        for sid in pending:
            o = res.get(sid)
            if o and o["status"] == "passed":
                ok_specs[sid], observed[sid] = specs[sid], (out / f"actions_round{rnd}", o["vars"])
            else:
                failures[sid] = o or {"error": "plan did not match the schema", "aria": ""}
        print(f"actions round {rnd}: {len(ok_specs)}/10 run cleanly", flush=True)
        if not failures or rnd == 3:
            break
        pending = {sid: repair_plan(model, pending[sid], flows[sid], failures[sid]) for sid in failures}

    full = {}
    for sid, spec in ok_specs.items():
        run_dir, variables = observed[sid]
        before, after = before_after(run_dir, sid)
        cands = menu(before, after, variables)
        picks = pick(model, flows[sid], cands) if cands else []
        expects = [cands[i]["expect"] for i in picks]
        log["flows"][sid] = {"flow": flows[sid], "as_user": plans[sid].get("as_user"),
                             "menu": [c["desc"] for c in cands], "picked": [cands[i]["desc"] for i in picks]}
        if expects:
            final = {k: v for k, v in spec.items() if k != "_observe_after"}
            final["steps"] = spec["steps"] + expects
            full[sid] = final
            (out / f"{sid}.json").write_text(json.dumps(final, indent=1))
    unload(model)

    clean = run_variant(full, out / "verify_clean", "") if full else {}
    kills = {}
    for i, bug in BUG_FOR_FLOW.items():
        sid = f"flow{i:02d}"
        if sid in full and clean.get(sid, {}).get("status") == "passed":
            r = run_variant({sid: full[sid]}, out / f"verify_{bug}", bug)
            kills[sid] = r.get(sid, {}).get("status") != "passed"
    for sid in flows:
        e = log["flows"].setdefault(sid, {"flow": flows[sid]})
        e["clean"] = clean.get(sid, {}).get("status", "no-spec")
        e["kills_bug"] = kills.get(sid)
    subprocess.run([str(ROOT / "bench" / "app" / "conduit.sh"), "reset"], capture_output=True,
                   env={**os.environ, "BUGS": ""})  # leave the app clean
    killed = sum(bool(v) for v in kills.values())
    passed = sum(e["clean"] == "passed" for e in log["flows"].values())
    log["summary"] = {"actions_ran": len(ok_specs), "clean_pass": passed,
                      "kill_rate": f"{killed}/{len(BUG_FOR_FLOW)}"}
    (out / "summary.json").write_text(json.dumps(log, indent=1))
    print(f"\n{model}: actions ran {len(ok_specs)}/10, pass on clean {passed}/10, "
          f"kill rate {killed}/{len(BUG_FOR_FLOW)} (reference suite: 8/8)")
    for sid, e in log["flows"].items():
        print(f"  {sid} clean={e['clean']:<8} kills={e.get('kills_bug')}  picked={e.get('picked')}")


if __name__ == "__main__":
    main()
