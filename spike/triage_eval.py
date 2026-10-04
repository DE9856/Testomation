"""Spike: triage the captured cases with one model call each (label probability from logprobs).

Compares against two baselines:
  all-bug    — "everything is a bug" (the target to beat, Q22)
  rules      — a tiny deterministic rules engine; abstains when no rule fires
Reports accuracy, per-label recall, and calibration (is the model's probability higher when it's right?).

Run: uv run python spike/triage_eval.py [model]   → spike/results/triage_eval_<model>.json
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from toolchain_check import post  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
LABELS = ["bug", "noise", "flaky", "test_issue"]
TARGET_ORIGIN = "localhost:4100"

SYSTEM = """You triage results from an automated end-to-end test run of a web app (Conduit, a blogging site).
Classify the case into exactly one verdict:
- bug: the application is broken — it does not do what the flow says it should (wrong behaviour,
  server error, missing data, missing UI feedback).
- noise: a harmless signal that does not affect the user — e.g. a blocked third-party/analytics
  request or a library deprecation warning, on a test that otherwise passed.
- flaky: timing or infrastructure trouble, not the app's logic — e.g. slow responses causing a
  timeout, especially when the same test passes on retry.
- test_issue: the test itself is wrong — it looks for an element or text that does not exist on a
  page that otherwise works (wrong target, wrong expected text, missing step in the test).
Use the evidence: the flow's intent, the failing step, the error, retry results, console/network
signals and the page at the failure. Answer as JSON."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verdict"],
          "properties": {"verdict": {"enum": LABELS}}}


def trim_aria(aria: str, limit: int = 1800) -> str:
    aria = aria.split("\n- contentinfo:")[0]
    return aria[:limit] + ("\n# … (truncated)" if len(aria) > limit else "")


def signals_text(signals: list[dict]) -> str:
    if not signals:
        return "none"
    return "\n".join(f"- {s['kind']}: {s['text'][:160]}" + (f" ({s['url'][:100]})" if s.get("url") else "")
                     for s in signals[:8])


WITH_HISTORY = False  # add the spec's run history (a fact from memory) to the evidence


def history(c: dict) -> str:
    if c["label"] == "test_issue":   # generated drafts that failed on the clean app
        return "History: new draft spec written by a model; it has never passed yet."
    return "History: approved spec; it passed on this app in previous runs."


def evidence(c: dict) -> str:
    return (history(c) + "\n" if WITH_HISTORY else "") + _evidence(c)


def _evidence(c: dict) -> str:
    if c["kind"] == "signal-on-passing-test":
        return (f"Test: {c['test']}\nFlow: {c['flow']}\nResult: PASSED (all steps and assertions succeeded).\n\n"
                f"Signal to classify:\n{signals_text([c['signal']])}\n\n"
                f"Other signals in the same test:\n{signals_text(c.get('other_signals', []))}")
    attempts = " → ".join(c["attempts"])
    return (f"Test: {c['test']}\nFlow: {c['flow']}\n"
            f"Result: {attempts} (attempts in order; retries run the same test again)\n"
            f"Failing step {c['failing_step']}: {json.dumps(c['step'])}\n\n"
            f"Error:\n{c['error'][:700]}\n\n"
            f"Console/network signals during the failing attempt:\n{signals_text(c['signals'])}\n\n"
            f"Page at the moment of failure (aria snapshot):\n{trim_aria(c['aria'])}")


def classify(model: str, c: dict) -> dict:
    r = post("/api/chat", {
        "model": model, "stream": False, "think": False, "format": SCHEMA,
        "logprobs": True, "top_logprobs": 5,
        "options": {"num_ctx": 8192, "num_gpu": 99, "temperature": 0, "num_predict": 30},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": evidence(c)}],
    })
    verdict = json.loads(r["message"]["content"])["verdict"]
    probs: dict[str, float] = {}
    text = ""
    for t in r.get("logprobs") or []:
        before, text = text, text + t["token"]
        frag = t["token"].strip('" ')
        if '"verdict"' in before and frag and any(lab.startswith(frag) for lab in LABELS):
            for alt in t.get("top_logprobs", []):
                f = alt["token"].strip('" ')
                for lab in LABELS:
                    if f and lab.startswith(f):
                        probs[lab] = probs.get(lab, 0.0) + math.exp(alt["logprob"])
            break
    return {"verdict": verdict, "p": round(probs.get(verdict, float("nan")), 3),
            "probs": {k: round(v, 3) for k, v in probs.items()},
            "seconds": round(r.get("total_duration", 0) / 1e9, 2)}


def rules(c: dict) -> str | None:
    """A deliberately small deterministic baseline. None = abstain (would escalate)."""
    if WITH_HISTORY and c["label"] == "test_issue":
        return "test_issue"           # a draft that has never passed: suspect the test first
    if c["kind"] == "signal-on-passing-test":
        url = c["signal"].get("url") or ""
        host = urlparse(url).netloc
        if host and host != TARGET_ORIGIN:
            return "noise"            # third-party resource on a passing test
        return None
    if c["attempts"][-1] == "passed":
        return "flaky"                # failed, then passed on retry
    if any(s["kind"] == "http" and (s.get("status") or 0) >= 500 for s in c["signals"]):
        return "bug"                  # server error during the failing attempt
    return None


def cascade(rows: list[dict], gate: float = 0.8) -> dict:
    """Rules decide when they fire; otherwise the model decides if p >= gate; else human review."""
    right = wrong = review = 0
    for r in rows:
        verdict = r["rules"] or (r["verdict"] if r["p"] == r["p"] and r["p"] >= gate else None)
        if verdict is None:
            review += 1
        elif verdict == r["label"]:
            right += 1
        else:
            wrong += 1
    return {"auto_right": right, "auto_wrong": wrong, "to_review": review}


def main() -> None:
    global WITH_HISTORY
    WITH_HISTORY = "--history" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    model = args[0] if args else "qwen3:4b"
    cases = json.loads((OUT / "triage_cases.json").read_text())
    rows = []
    for c in cases:
        m = classify(model, c)
        rows.append({"id": c["id"], "label": c["label"], "variant": c["variant"], **m, "rules": rules(c)})
        mark = "✓" if m["verdict"] == c["label"] else "✗"
        print(f"{c['id']} {c['label']:<10} → {m['verdict']:<10} p={m['p']:<5} {mark}  rules={rows[-1]['rules']}  ({c['variant']})", flush=True)
    post("/api/generate", {"model": model, "keep_alive": 0})

    n = len(rows)
    acc = sum(r["verdict"] == r["label"] for r in rows) / n
    all_bug = sum(r["label"] == "bug" for r in rows) / n
    fired = [r for r in rows if r["rules"]]
    rules_acc = sum(r["rules"] == r["label"] for r in fired) / max(len(fired), 1)
    combined = sum((r["rules"] or r["verdict"]) == r["label"] for r in rows) / n
    right = [r["p"] for r in rows if r["verdict"] == r["label"] and r["p"] == r["p"]]
    wrong = [r["p"] for r in rows if r["verdict"] != r["label"] and r["p"] == r["p"]]
    per_label = {lab: f"{sum(r['verdict'] == lab for r in rows if r['label'] == lab)}/{sum(r['label'] == lab for r in rows)}"
                 for lab in LABELS}
    confident = [r for r in rows if r["p"] == r["p"] and r["p"] >= 0.9]
    summary = {
        "model": model, "cases": n, "labels": dict(Counter(r["label"] for r in rows)),
        "model_accuracy": round(acc, 3), "all_bug_baseline": round(all_bug, 3),
        "rules_coverage": f"{len(fired)}/{n}", "rules_accuracy_when_fired": round(rules_acc, 3),
        "rules_then_model_accuracy": round(combined, 3), "per_label_recall": per_label,
        "mean_p_when_right": round(sum(right) / max(len(right), 1), 3),
        "mean_p_when_wrong": round(sum(wrong) / max(len(wrong), 1), 3),
        "accuracy_when_p>=0.9": f"{sum(r['verdict'] == r['label'] for r in confident)}/{len(confident)}",
        "confusion": dict(Counter(f"{r['label']}→{r['verdict']}" for r in rows if r["verdict"] != r["label"])),
        "mean_seconds": round(sum(r["seconds"] for r in rows) / n, 2),
        "cascade_rules_then_model_gate_0.8": cascade(rows),
    }
    (OUT / f"triage_eval_{model.replace(':', '_')}{'_history' if WITH_HISTORY else ''}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print("\n" + json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
