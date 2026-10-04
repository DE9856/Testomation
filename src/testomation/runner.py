"""Python side of the spec runner: run a folder of JSON specs with Playwright, read the results.

The TypeScript runner (`runner/`) executes specs; this module invokes it and turns its JSON
report into typed results. Python and TypeScript meet only through files (ARCHITECTURE.md §4).
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = ROOT / "runner"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class Attempt:
    status: str  # 'passed' | 'failed' | 'timedOut' | 'interrupted' | 'skipped'
    failing_step: int | None = None
    error: str = ""
    signals: list[dict] = field(default_factory=list)
    aria: str = ""


@dataclass
class TestResult:
    spec_id: str
    attempts: list[Attempt]

    @property
    def status(self) -> str:
        return self.attempts[-1].status if self.attempts else "missing"

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def flaky(self) -> bool:
        """Failed at least once, then passed on a retry."""
        return self.passed and any(a.status != "passed" for a in self.attempts)


def _attachment(result: dict, name: str) -> str:
    a = next((a for a in result.get("attachments", []) if a["name"] == name), None)
    if not a:
        return ""
    if a.get("path"):
        p = Path(a["path"])
        return p.read_text() if p.exists() else ""
    return base64.b64decode(a.get("body", "")).decode()


def parse_report(report: dict) -> list[TestResult]:
    """Playwright JSON reporter output → one TestResult per spec (test title = spec id)."""
    out: list[TestResult] = []

    def walk(suite: dict) -> None:
        for s in suite.get("specs", []):
            for t in s.get("tests", []):
                attempts = []
                for r in t.get("results", []):
                    notes = r.get("annotations", []) + t.get("annotations", [])
                    step = next((n.get("description") for n in notes
                                 if n.get("type") == "failing-step"), None)
                    attempts.append(Attempt(
                        status=r["status"],
                        failing_step=int(step) if step and r["status"] != "passed" else None,
                        error=_ANSI.sub("", r.get("error", {}).get("message", "")),
                        signals=json.loads(_attachment(r, "signals") or "[]"),
                        aria=_attachment(r, "aria-snapshot"),
                    ))
                out.append(TestResult(spec_id=s["title"], attempts=attempts))
        for child in suite.get("suites", []):
            walk(child)

    for suite in report.get("suites", []):
        walk(suite)
    return out


def run_specs(spec_dir: Path, work_dir: Path, *, secrets: dict[str, str] | None = None,
              workers: int = 2, retries: int = 0,
              target_url: str | None = None) -> list[TestResult]:
    """Run every spec in `spec_dir`; evidence goes under `work_dir`."""
    work_dir.mkdir(parents=True, exist_ok=True)
    results = work_dir / "results.json"
    results.unlink(missing_ok=True)
    env = {**os.environ, **(secrets or {}), "TESTO_SPECS_DIR": str(spec_dir.resolve()),
           "TESTO_RESULTS_FILE": str(results), "TESTO_WORKERS": str(workers),
           "TESTO_RETRIES": str(retries)}
    if target_url:
        env["TESTO_TARGET_URL"] = target_url
    subprocess.run(["npx", "playwright", "test", "--output", str(work_dir / "test-results")],
                   cwd=RUNNER_DIR, env=env, capture_output=True, check=False)
    if not results.exists():
        raise RuntimeError("the spec runner produced no report — is `npm install` done in runner/?")
    return parse_report(json.loads(results.read_text()))
