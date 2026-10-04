"""Spike: 10 described Conduit flows → JSON specs, run them, repair failures in batched rounds.

Design step 1, main experiment (docs/DESIGN_ROADMAP.md). Throwaway.
Per round: generate/repair every pending spec (model loaded) → unload model → reset Conduit →
run every pending spec (Playwright, model unloaded) → failures go to the next round with the
failing step, the error and the page's aria snapshot. Up to 3 repair rounds (D30).

Repairs may not change or remove `expect` steps: such a repair is flagged (it would go to
human review in the product) and the spec is not counted as passing.

Run: uv run python spike/specgen.py MODEL [--flows 1,2,...] [--rounds 3]
Writes spike/results/specgen_<model>/ (specs per round, results, summary.json).
"""

from __future__ import annotations

import argparse
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
from toolchain_check import post  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "test-spec.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
REPAIR_EXPECT_TARGETS = False  # v3: a repair may change an expect's target if assert+value stay the same
CONTEXT = ROOT / "spike" / "context"
EXAMPLES = ROOT / "spike" / "specgen" / "examples"
SECRETS = {f"{u.upper()}_PASSWORD": f"{u}-pass-1" for u in ("alice", "bob", "carol", "dave")}

FLOWS = [
    "Log in as alice; the navigation bar then shows her username 'alice'.",
    "Try to log in as alice with a wrong password; an error is shown and the user stays on the login page.",
    "Sign up a brand-new user with generated data; afterwards the navigation bar shows the new username.",
    "As alice, publish a new article with a title, description, body and two tags; the article page then shows the title.",
    "As alice, open the article \"Dave's post 3\" and post a comment; the comment appears on the page.",
    "On the home page, click the 'react' tag under Popular Tags; the feed then only lists articles tagged 'react'.",
    "As alice, favorite the article \"Dave's post 3\"; its favorite count goes from 0 to 1.",
    "As alice, open 'Your Feed'; it lists articles by bob and carol (whom she follows) and none by dave.",
    "Without logging in, open bob's profile; it lists his three articles.",
    "As alice, change her bio in settings to some generated text; her profile page then shows that bio.",
]

RULES = """You write end-to-end tests for a web app as JSON specs. A spec is a list of steps run in order by Playwright.

Step actions:
- goto {url}: open a path. Paths start with "/". This app uses hash routes: "/#/login".
- click / hover / check / uncheck {target}. ("check" ticks a checkbox. It is NOT an assertion.)
- fill {target, value}, select {target, value}, press {key, target?}
- wait_for {target, state: visible|hidden}
- expect {target?, assert, value?}: the assertion. assert is one of visible, hidden, hasText,
  hasValue, count, url. Every spec must end with at least one expect that checks the outcome.
- api, viewport, upload, helper: not needed for this app.

Targets: use what the page snapshot shows. A line `- textbox "Email"` becomes
{"role": "textbox", "name": "Email"}; `- button "Login"` becomes {"role": "button", "name": "Login"}.
Prefer role + name. Use {"text": "..."} only for plain text.
@@V2_TARGETS@@
Values:
- Passwords of the seeded users are secrets: {"$secret": "ALICE_PASSWORD"} (also BOB_, CAROL_, DAVE_).
- Generated data: {"$faker": "internet.username", "as": "name"}, then reuse it with {"$var": "name"}.
  Useful faker paths: internet.username, internet.email, internet.password, lorem.sentence,
  lorem.paragraph, lorem.word.
- Never write "$..." inside a plain string.

Seeded users: alice, bob, carol, dave; email <name>@conduit.test. alice follows bob and carol.
To log in: goto "/#/login", fill Email and Password, click button "Login", then wait for the
"Your Feed" button before continuing."""


def trim_page(path: Path, max_lines: int = 45) -> str:
    """The page's `main` region only (banner/footer repeat on every page), capped in length."""
    lines = path.read_text().splitlines()
    title = lines[0].lstrip("# ")
    main, keep = [], False
    for line in lines[1:]:
        if line.startswith("- main:"):
            keep = True
        elif line.startswith("- ") and keep:
            break
        if keep:
            main.append(line)
    if len(main) > max_lines:
        main = main[:max_lines] + ["  # … (more of the same)"]
    return f"### {title}\n" + "\n".join(main)


def banner(path: Path) -> str:
    lines = path.read_text().splitlines()[1:]
    out = []
    for line in lines:
        if line.startswith("- ") and out and not line.startswith("- banner"):
            break
        out.append(line)
    return "\n".join(out)


V2_TARGETS = """
Two snapshot forms mean different things:
- `- button "Login"` (quoted): "Login" is the element's accessible NAME → {"role": "button", "name": "Login"}.
- `- listitem: Wrong email/password combination` or `- paragraph: Some text` (after a colon): that is
  text CONTENT, not a name. Paragraphs, list items and plain text never have a name, so
  {"role": "paragraph", "name": ...} never matches. Target the text instead:
  {"text": "Wrong email/password combination"}.
- Author names in feeds are links (`- link "bob"`), not headings.
- To check something you typed earlier, assert with the same {"$var": ...} you filled it with.
"""


def rules(version: str) -> str:
    return RULES.replace("@@V2_TARGETS@@", V2_TARGETS if version == "v2" else "")


def app_context() -> str:
    pages = ["home", "login", "register", "home-logged-in", "editor", "settings",
             "profile-alice", "article-logged-in"]
    return "\n\n".join([
        "## Navigation bar, logged out\n" + banner(CONTEXT / "home.yaml"),
        "## Navigation bar, logged in as alice\n" + banner(CONTEXT / "editor.yaml"),
        "## Pages (main region of each, from Playwright aria snapshots)",
        *[trim_page(CONTEXT / f"{p}.yaml") for p in pages],
    ])


def examples() -> list[dict]:
    msgs = []
    for f in sorted(EXAMPLES.glob("*.json")):
        spec = json.loads(f.read_text())
        msgs += [{"role": "user", "content": f"Flow: {spec['flow']}"},
                 {"role": "assistant", "content": json.dumps(spec)}]
    return msgs


def decoder_view(schema: dict) -> dict:
    """The schema as Ollama should see it. Validators need `(.|\\n)*` for multi-line strings, but in
    Ollama's grammar that breaks JSON (strings stop closing). Ollama's `.` already allows newlines,
    so `.*` is the equivalent there. The llm client owns this rewrite; the schema file stays the
    single source (D31)."""
    return json.loads(json.dumps(schema).replace("(.|\\\\n)*", ".*"))


def chat(model: str, messages: list[dict]) -> tuple[dict, dict]:
    try:
        r = post("/api/chat", {
            "model": model, "stream": False, "think": False, "format": decoder_view(SCHEMA),
            "messages": messages,
            # num_predict caps a runaway generation (a 40-step spec is ~1500 tokens)
            "options": {"num_ctx": 8192, "num_gpu": NUM_GPU.get(model, 99), "temperature": 0,
                        "num_predict": 2000},
        })
    except Exception as e:  # a failed call is a failed generation, not a crashed experiment
        return {"_call_error": str(e)[:200], "steps": []}, {"prompt_tokens": 0, "gen_tokens": 0, "seconds": 0}
    stats = {"prompt_tokens": r.get("prompt_eval_count"), "gen_tokens": r.get("eval_count"),
             "seconds": round(r.get("total_duration", 0) / 1e9, 1)}
    try:
        return json.loads(r["message"]["content"]), stats
    except json.JSONDecodeError as e:
        return {"_invalid_json": str(e)}, stats


PROMPT = "v1"
NUM_GPU = {"qwen3:8b": -1, "qwen2.5:7b": -1, "qwen2.5-coder:7b": -1, "gemma3n:e4b": -1, "gemma3:4b": -1}  # >4 GB models: Ollama places layers (-1)


def generate(model: str, flow: str, idx: int) -> tuple[dict, dict]:
    messages = [{"role": "system", "content": rules(PROMPT) + "\n\n" + app_context()}, *examples(),
                {"role": "user", "content": f"Flow: {flow}"}]
    spec, stats = chat(model, messages)
    spec["id"] = f"flow{idx:02d}"  # stable file/test names; the model's id is not under test
    spec["flow"] = flow
    return spec, stats


def repair(model: str, spec: dict, failure: dict) -> tuple[dict, dict]:
    messages = [
        {"role": "system", "content": rules(PROMPT) + "\n\n" + app_context()},
        {"role": "user", "content": (
            f"This spec failed when run.\n\nFlow: {spec['flow']}\n\nSpec:\n{json.dumps(spec, indent=1)}\n\n"
            f"Failed at step {failure['step'] or '(lint, before running)'}: {failure['error']}\n\n"
            f"Page at the moment of failure (aria snapshot):\n{failure['aria']}\n\n"
            "Return the corrected spec. You may change targets, add wait_for or missing steps, and fix "
            "goto urls. " + ("Do not change an expect's assert or value, and do not remove expect "
            "steps; you MAY change an expect's target if it pointed at the wrong element."
            if REPAIR_EXPECT_TARGETS else "Do not change or remove expect steps — if an expect itself "
            "is wrong, return the spec unchanged."))},
    ]
    fixed, stats = chat(model, messages)
    fixed["id"], fixed["flow"] = spec["id"], spec["flow"]
    return fixed, stats


def expects(spec: dict) -> list[str]:
    """What an assertion claims. With REPAIR_EXPECT_TARGETS, the target is not part of the claim."""
    out = []
    for s in spec.get("steps", []):
        if s.get("action") == "expect":
            claim = {k: v for k, v in s.items() if not (REPAIR_EXPECT_TARGETS and k == "target")}
            out.append(json.dumps(claim, sort_keys=True))
    return out


def unload(model: str) -> None:
    post("/api/generate", {"model": model, "keep_alive": 0})


def run_specs(specs: dict[str, dict], out: Path) -> dict[str, dict]:
    """Run specs with Playwright (model unloaded). Returns id → {status, step, error, aria}."""
    spec_dir = out / "specs"
    shutil.rmtree(spec_dir, ignore_errors=True)
    spec_dir.mkdir(parents=True)
    for sid, spec in specs.items():
        (spec_dir / f"{sid}.json").write_text(json.dumps(spec, indent=1))
    subprocess.run([str(ROOT / "bench" / "app" / "conduit.sh"), "reset"], check=True,
                   capture_output=True)
    results_file = out / "results.json"
    env = {**os.environ, **SECRETS, "TESTO_SPECS_DIR": str(spec_dir), "TESTO_RETRIES": "0",
           "TESTO_RESULTS_FILE": str(results_file), "TESTO_WORKERS": "2"}
    t0 = time.monotonic()
    subprocess.run(["npx", "playwright", "test", "--output", str(out / "test-results")],
                   cwd=ROOT / "runner", env=env, capture_output=True)
    run_s = round(time.monotonic() - t0, 1)
    report = json.loads(results_file.read_text())
    outcome: dict[str, dict] = {}

    def walk(suite: dict) -> None:
        for s in suite.get("specs", []):
            for t in s["tests"]:
                res = t["results"][-1]
                step = next((a["description"] for a in t.get("annotations", [])
                             if a["type"] == "failing-step"), None)
                aria = next((a for a in res.get("attachments", []) if a["name"] == "aria-snapshot"), None)
                aria_text = ""
                if aria and aria.get("path"):
                    aria_text = Path(aria["path"]).read_text()
                elif aria and aria.get("body"):
                    import base64
                    aria_text = base64.b64decode(aria["body"]).decode()
                err = re.sub(r"\x1b\[[0-9;]*m", "", res.get("error", {}).get("message", ""))
                outcome[s["title"]] = {"status": res["status"], "step": step,
                                       "error": err[:600], "aria": aria_text[:3000]}
        for c in suite.get("suites", []):
            walk(c)

    for s in report["suites"]:
        walk(s)
    print(f"  ran {len(specs)} specs in {run_s}s", flush=True)
    return outcome


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--flows", default="")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--prompt", default="v1", choices=["v1", "v2"])
    ap.add_argument("--schema", default="", help="experimental schema file (default: the real one)")
    ap.add_argument("--repair-expect-targets", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    global PROMPT, SCHEMA, VALIDATOR, REPAIR_EXPECT_TARGETS
    PROMPT = args.prompt
    REPAIR_EXPECT_TARGETS = args.repair_expect_targets
    if args.schema:
        SCHEMA = json.loads(Path(args.schema).read_text())
        VALIDATOR = Draft202012Validator(SCHEMA)
    picks = [int(x) for x in args.flows.split(",")] if args.flows else list(range(1, len(FLOWS) + 1))
    out = ROOT / "spike" / "results" / f"specgen_{args.model.replace(':', '_')}_{args.tag or args.prompt}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)

    log: dict = {"model": args.model, "prompt": args.prompt, "schema": args.schema or "real",
                 "repair_expect_targets": REPAIR_EXPECT_TARGETS, "rounds": [], "flows": {}}
    pending: dict[str, dict] = {}
    original_expects: dict[str, list[str]] = {}
    gen_stats = []
    print(f"== {args.model}: generating {len(picks)} specs", flush=True)
    for i in picks:
        spec, stats = generate(args.model, FLOWS[i - 1], i)
        gen_stats.append(stats)
        sid = f"flow{i:02d}"
        pending[sid] = spec
        original_expects[sid] = expects(spec)
        log["flows"][sid] = {"flow": FLOWS[i - 1], "history": []}
        print(f"  {sid}: {len(spec.get('steps', []))} steps, {stats}", flush=True)

    passed: dict[str, dict] = {}
    for rnd in range(0, args.rounds + 1):
        unload(args.model)
        rdir = out / f"round{rnd}"
        valid = {sid: s for sid, s in pending.items() if not list(VALIDATOR.iter_errors(s))}
        failures = {}
        for sid in set(pending) - set(valid):
            errs = [e.message[:200] for e in VALIDATOR.iter_errors(pending[sid])][:3]
            log["flows"][sid]["history"].append({"round": rnd, "status": "schema-invalid", "error": "; ".join(errs)})
            failures[sid] = {"status": "schema-invalid", "step": None, "aria": "",
                             "error": "The spec does not match the schema: " + "; ".join(errs)}
        # Lint before running (the product would too): a spec without an expect checks nothing.
        for sid in [sid for sid, sp in valid.items() if not expects(sp)]:
            valid.pop(sid)
            failures[sid] = {"status": "no-expect", "step": None, "aria": "",
                             "error": "The spec has no expect step, so it checks nothing. Add expect "
                                      "step(s) at the end that verify the outcome described in the flow."}
            log["flows"][sid]["history"].append({"round": rnd, "status": "no-expect"})
        outcome = run_specs(valid, rdir) if valid else {}
        for sid, spec in valid.items():
            o = outcome.get(sid, {"status": "missing", "step": None, "error": "no result", "aria": ""})
            entry = {"round": rnd, "status": o["status"], "step": o["step"], "error": o["error"][:300]}
            log["flows"][sid]["history"].append(entry)
            if o["status"] == "passed":
                passed[sid] = spec
            else:
                failures[sid] = o
        log["rounds"].append({"round": rnd, "ran": len(valid), "passed_total": len(passed)})
        print(f"round {rnd}: {len(passed)}/{len(picks)} passing so far", flush=True)
        pending = {sid: pending[sid] for sid in failures}
        if not pending or rnd == args.rounds:
            break
        for sid, failure in failures.items():  # repair round (model loaded again)
            fixed, stats = repair(args.model, pending[sid], failure)
            if not original_expects[sid]:  # adding the first assertions is allowed
                original_expects[sid] = expects(fixed)
            if expects(fixed) != original_expects[sid]:
                log["flows"][sid]["history"].append({"round": rnd + 1, "status": "repair-changed-expect"})
                log["flows"][sid]["flagged"] = True
            pending[sid] = fixed
            gen_stats.append(stats)

    unload(args.model)
    for sid, entry in log["flows"].items():
        spec = passed.get(sid)
        entry["final"] = ("passed" if spec and not entry.get("flagged") else
                          "passed-but-expect-changed" if spec else "failed")
        entry["has_expect"] = bool(spec and expects(spec))
        if spec:
            (out / f"{sid}.final.json").write_text(json.dumps(spec, indent=1))
    log["generation"] = {
        "calls": len(gen_stats),
        "mean_seconds": round(sum(s["seconds"] for s in gen_stats) / len(gen_stats), 1),
        "mean_prompt_tokens": round(sum(s["prompt_tokens"] or 0 for s in gen_stats) / len(gen_stats)),
        "mean_gen_tokens": round(sum(s["gen_tokens"] or 0 for s in gen_stats) / len(gen_stats)),
    }
    (out / "summary.json").write_text(json.dumps(log, indent=1))
    ok = sum(e["final"] == "passed" and e["has_expect"] for e in log["flows"].values())
    print(f"\n{args.model}: {ok}/{len(picks)} pass with an expect and unchanged assertions; "
          f"by round: {[r['passed_total'] for r in log['rounds']]}; generation {log['generation']}")


if __name__ == "__main__":
    main()
