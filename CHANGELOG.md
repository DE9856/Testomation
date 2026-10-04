# Changelog

Working log for Testomation: what was done, the state it left things in, and what comes next.
Newest session first. Decisions live in `docs/DECISIONS.md`; measurements in
`docs/SPIKE_RESULTS.md`. This file is the hand-off between sessions.

---

## Resume here (next session)

### 1. Bring the machine back up

```bash
cd ~/Desktop/Testomation
sudo systemctl start ollama                      # service is installed but NOT enabled at boot
docker compose -f deploy/compose.yaml up -d      # Postgres + pgvector (:5432)
bench/app/conduit.sh up                          # benchmark app on http://localhost:4100 (clean seed)
uv sync && uv run pytest -q                      # expect 24 passed
(cd runner && npm install && npm run typecheck)  # Chromium already installed under ~/.cache/ms-playwright
uv run testomation bench --replay                # fast sanity check (no app needed)
```

Ollama has `OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_NUM_PARALLEL=1` via
`/etc/systemd/system/ollama.service.d/testomation.conf`. Models pulled: `qwen3:4b` (the small
tier), `nomic-embed-text` (embed), plus bake-off candidates (`qwen3:8b`, `gemma3:4b`,
`gemma3n:e4b`, `phi4-mini`, `llama3.2:3b`, `qwen2.5:7b`, `qwen2.5-coder:7b`) — those can be
removed with `ollama rm` if disk matters.

### 2. First thing: commit what's uncommitted

At the end of 2026-10-04, everything after commit `28ceaf3` is uncommitted (35 paths): the v0.7
design update, `testomation bench`, the RAM check, the bake-off results and this file. The user
commits; Claude does not run `git commit` in this repo.

### 3. Then work through "Next steps" below, in order.

---

## 2026-10-04 — Review, v0.6/v0.7 design, scaffold, feasibility spike, phase 0 bench

### Summary

Started the day with documentation only (brief v0.5). Ended with a working spec runner, a
seeded-bug benchmark app with a reference suite and `testomation bench`, a completed
feasibility spike, and a design narrowed by its results (brief v0.7):

- **Works and is worth building:** the deterministic core (JSON spec + Playwright runner, seeded
  bugs, reference suite, rules-first analyzer) and **model triage** (58% vs 33% baseline; with
  rules + 0.8 gate: 16 right / 1 wrong / 7 to review of 24 real cases).
- **Doesn't work at this model size:** autonomous spec generation. Five approaches with
  `qwen3:4b`, then six other local models: best kill rate **2/8** vs **8/8** for hand-written
  specs. Phase 3 became **assisted authoring**; exploration became **gated research**.

### 1. Design review → brief v0.6

- Reviewed all 15 docs; proposed 13 changes with pros/cons; user adopted all of them.
- Brief bumped to **v0.6** (`archive/testomation-v0.5.html` kept). Key changes:
  feasibility spike before infrastructure; triage for any Playwright suite (`testomation import`);
  every approved spec runs every run (impact analysis only scopes model work); freshness from
  basis hashes instead of stale flags; confidence from logprobs + labelled neighbours (one call,
  not three samples); batched repair rounds; one model by default; LangGraph only for the
  exploration loop; typed tables + claims on edges; OpenTelemetry file traces until Langfuse in
  phase 3; replay benchmark tier; one schema source with generated types.
- Fixed doc gaps: `testomation.html` → `index.html` references, `Requirement` source in the MVP,
  temperature-0 sampling, origin guard + prompt-injection risk, helper steps, claims on edges.
- New doc: `docs/DESIGN_ROADMAP.md` (what to design before each phase, with exit gates).
- Decisions D28–D36, open questions Q17–Q25, gaps G11–G21.

### 2. Scaffold

- `pyproject.toml` (uv, Python 3.12, `requires-python <3.14`), `src/testomation/` (CLI stubs,
  `config.py` reading `TESTO_*`), `tests/`, ruff config, `.gitignore`, `.env.example`.
- `runner/` TypeScript Playwright project; `schemas/test-spec.schema.json` + examples validated
  from both Python (`tests/test_spec_schema.py`) and TypeScript (`npm run validate-examples`).
- `deploy/compose.yaml` (Postgres + pgvector), `deploy/sql/001_memory.sql` (draft DDL, applies
  cleanly; `mem_fact` / `mem_edge_fact` views not written yet).

### 3. Benchmark app (Conduit)

- Vendored `TonyMckes/conduit-realworld-example-app` (MIT, commit `5e127d8`) into
  `bench/app/conduit/`; one container serves API + built frontend on **:4100**; own Postgres;
  seeded through the API (`seed.mjs`: alice/bob/carol/dave, password `<name>-pass-1`, emails
  `<name>@conduit.test`, 12 articles, comments, favorites, alice follows bob and carol);
  `conduit.sh up|reset|down` — reset copies a template DB (~2.3 s).
- **The frontend uses hash routes**: `/#/login`, `/#/register`, `/#/editor`, `/#/settings`,
  `/#/profile/<name>`, `/#/article/<slug>`.
- Upstream fixes in the clean baseline (all tagged `[testomation patch]`, listed in
  `bench/app/conduit/UPSTREAM.md`): SPA fallback (harmless), `distinct: true` on article counts
  (12 articles were counted as 24), **settings save re-hashed the password every time** (`||` →
  `&&`; it silently broke later logins, including parallel specs).
- **Seeded bugs** behind `BUGS=<id,...> bench/app/conduit.sh reset` (tagged `[testomation bug]`;
  backend reads `BUGS`, injects `window.__BUGS` for frontend bugs):
  `login-error-hidden`, `signup-500`, `publish-500`, `comment-not-shown`, `tag-filter-ignored`,
  `favorite-count-stuck`, `profile-articles-empty`, `bio-not-saved` (bugs);
  `noise-analytics`, `noise-console-warning` (noise); `flaky-slow-articles` (flaky).
  Catalogue: `bench/catalogue.toml`.
- **Reference suite** `bench/reference/ref01…ref10` (one hand-written spec per flow). Clean:
  10/10 (3 runs). Kill matrix: 8/8, no collateral failures.

### 4. Spec runner (`runner/`)

- `steps.ts` executes every action except `upload`/`helper`; `$faker`/`$var`/`$secret` values;
  `nth` on targets; 5 s action timeout.
- `spec-runner.spec.ts`: one test per spec, one `test.step` per step; **origin guard** (aborts
  off-origin navigation with a clear error); on failure a `failing-step` annotation + `aria-snapshot`
  attachment; `signals` attachment (console errors, failed requests, 4xx/5xx) on every test;
  optional `final-aria`/`vars` (`TESTO_ATTACH_FINAL=1`) and `before-aria` (`_observe_after`) for
  experiments.
- **Settle after click/press**: counts in-flight same-origin requests and waits for 300 ms of quiet
  (≤ 3 s). `waitForLoadState('networkidle')` does NOT work for this on an already-loaded SPA.
- `scripts/capture-aria.ts` captures page snapshots; `scripts/validate-examples.ts`.

### 5. Feasibility spike (`spike/`, results in `docs/SPIKE_RESULTS.md`)

- **Fit and speed:** `qwen3:4b` fits fully on the 4 GB GPU at 8k context only when forced
  (`num_gpu: 99`) → 55 tok/s (33 tok/s with Ollama's default placement). 7–8B models: 12–16 tok/s,
  partial offload. `gemma3:4b` crashes with full offload. Thinking mode must be off.
- **Toolchain (Q13):** structured output and logprobs work natively, via `/v1`, and through
  `langfuse.openai` — **only with a decoder-friendly schema**. Ollama silently drops: `oneOf`
  siblings beside `type`/`properties`, unanchored patterns, `\s` in classes, `contains`. The
  pattern `(.|\n)*` breaks the grammar outright. → D38 (decoder-friendly schema), D39 (the llm
  client rewrites patterns for the decoder), D40 (`name` only on nameable roles), D41 (`nth`).
- **"Constrain, don't instruct":** every rule moved into the schema worked first time (role enum,
  no `$`-literals, no names on paragraphs, faker paths enum); every rule left in the prompt was
  ignored.
- **Spec generation (10 flows):** direct generation 3–4/10 pass but ~1.5 meaningful;
  observe-then-assert 2/10 meaningful; templates + deterministic assertion menu: kill rate 1/8.
  `qwen3:8b`: 2/10 at 5× the time. **Pass rate is the wrong metric** → kill rate (Q29).
- **Triage (24 real labelled cases):** 58% vs 33%; bugs 8/8 at p ≥ 0.95; all 6 broken generated
  specs called "bug" (history as evidence didn't help; as a rule it fixes all six).
- **Bake-off (Q32):** phi4-mini 2/8, llama3.2:3b 2/8, qwen2.5:7b 2/8, qwen3:4b 1/8, gemma3:4b 1/8,
  gemma3n:e4b 0/8, qwen2.5-coder:7b 0/8. None near the ≥ 5/8 gate.
- **RAM:** worst case (suite on 2 workers while the model generates) 5.0 GB of 15.3 GB, no swap.

### 6. Design v0.7 (after the spike)

- **D42:** phase 3 = **assisted authoring** — templates and recorded flows give actions; the model
  picks assertions from a deterministic before/after menu; a human approves every draft; scored
  by kill rate.
- **D43:** exploration (phase 6) is **research, gated** on a model reaching ≥ 5/8.
- Brief **v0.7** (`archive/testomation-v0.6.html` kept); all docs, `CLAUDE.md`, README updated.

### 7. Phase 0: `testomation bench`

- `src/testomation/runner.py` — runs a spec folder via the TS runner, parses the Playwright JSON
  report into `TestResult`/`Attempt` (status, failing step, error, signals, aria).
- `src/testomation/bench.py` + `bench/catalogue.toml` — `testomation bench [--runs N]` (full tier,
  ~12 min for 3 runs) and `--replay` (24 cases in `bench/replay/cases.json`; reports the 33%
  baseline until the analyzer exists).
- **Baseline (`bench/results/20261004-185607-full.json`):** clean 100%, kill rate 8/8 (held-out
  2/2), collateral 0, noise false alarms 0, flaky variant fails 0–20% of specs.
- `tests/test_bench.py` (catalogue, ranges, report parsing, reference specs schema-valid).

---

## Current state (end of 2026-10-04)

| Area | State |
|---|---|
| Design | Brief **v0.7**; decisions D1–D43; open questions listed below |
| Phase 0 (stage) | Mostly done — left: Stryker mutants, more seeded bugs |
| Phase 1 (plumbing) | Partly: runner executes specs, `runner.py` parses results. **No** pipeline runner, memory writes, tracing, `run`/`import` commands yet |
| Phase 2 (rules analyzer) | Not started; the spike's rules + history rule are the starting point |
| Phase 3 (assisted authoring) | Designed (D42); prototype parts in `spike/menu.py` (templates, before/after menu, picks) |
| Phases 4–6 | Not started; 6 is gated (D43) |
| Tests | 24 Python tests, TS typecheck, schema examples in both languages — all green |

**Still open (relevant soon):** Q4 natural keys for Flow/Component/Element · Q5/Q6 thresholds and
budget values · Q11 multi-tenancy · Q14 backend coverage · Q15 crawler · Q17 aria normalisation ·
Q18 basis policy · Q19 how to combine label probability, neighbours, rules · Q20 when test
selection returns · Q21 Markdown plans · Q23 planner loop · Q24 imported-suite failure mapping ·
Q25 Python↔TS bridge for exploration · Q28 expect-target repair · Q29 kill rate (proposed) ·
Q31 how flows are recorded.

---

## Next steps (do in this order)

### A. Commit (user)

Everything after `28ceaf3`. `spike/results/**/test-results/` is git-ignored (videos/traces).

### B. Finish phase 0

1. **More seeded bugs, toward ~20** (currently 8 bugs + 2 noise + 1 flaky). Each needs: a toggle in
   Conduit (`bug("<id>")`, tag `[testomation bug]`), a catalogue entry in `bench/catalogue.toml`
   (`kind`, `category`, `catches`, `held_out`), and — if no existing reference spec catches it — a
   new reference spec in `bench/reference/`. Then `uv run testomation bench --runs 3` must show
   kill rate 100% and no collateral failures. Candidates covering missing categories:
   - layout break at phone width (needs a `viewport` step + visibility check)
   - accessibility: an input without a label (needs axe in the runner — see C.6)
   - uncaught console exception on the settings page (a `bug`, unlike the noise variants)
   - re-plant the article-count bug (pagination shows an empty extra page)
   - follow button doesn't follow (flow 08 has no bug yet); login redirects to the wrong page
     (flow 01 has no bug yet)
   - editing an article doesn't save; deleting a comment fails; markdown not rendered
   - a second flaky variant (random 500 on retryable endpoint)
2. **Stryker mutants + detectable-mutant filter.** Plan: mutate the backend only (frontend mutants
   need a rebuild per mutant — too slow); mount `backend/` into the app container so a mutant only
   needs a restart; StrykerJS `command` runner calling a script that restarts the app and runs the
   reference suite; sample ~50 mutants; keep only those the reference suite kills
   ("detectable"); store them as extra catalogue entries. Estimate runtime first (~20 s × N).
3. Mark phase 0 done in `docs/ROADMAP.md` and the brief.

### C. Phase 1 — prove the plumbing (design step 2 + 4 first)

Freeze the contracts (DESIGN_ROADMAP step 2), then build:

1. **Memory DDL v1**: write the `mem_fact` / `mem_edge_fact` views and `is_fresh()` use in
   `deploy/sql/`; add a migration approach (numbered SQL files + a `schema_version` table).
2. **`src/testomation/memory/`**: connection (`psycopg`), insert/read for `mem_node`, typed
   tables (`test_case`, `run`, `result`), `basis_state` refresh from `git ls-tree -r HEAD`.
3. **Ingest** (`src/testomation/ingest/`): `runner.TestResult` → `run` + `result` rows with
   evidence paths under `data/evidence/<run>/<test>/` (move Playwright's output there).
4. **`testomation run`** (pipeline runner): stages refresh-basis → run approved specs → (triage
   stub) → report; stage state in Postgres; resume after a crash; specs read from `test_case`
   (status `approved`), materialised to `data/runs/<run>/specs/`.
5. **`testomation import <report.json>`**: any Playwright project's JSON report → `run` (trigger
   `import`) + `result` rows (Q24: map failures via `test.step` titles / failing locator).
6. **Runner fixtures still missing**: axe after each navigation (`@axe-core/playwright`), Chromium
   JS coverage per test (→ `touches`), helper registry (`helper` step), `upload` with `$fixture`.
7. **OpenTelemetry file traces** (`data/traces/<run>.jsonl`) for each stage — see
   `docs/OBSERVABILITY.md` for the exporter snippet and attribute names.
8. **Generated types** from the schema (Pydantic via `datamodel-code-generator`, TS via
   `json-schema-to-typescript`) replacing the hand-written `Step`/`Target` types in `steps.ts`.

### D. Phase 2 — rules-only analyzer

- Port the spike's rules (`spike/triage_eval.py::rules`) and the history rule into
  `src/testomation/agents/analyzer.py`; signature normalisation + dedup by hash; noise signatures
  (`signature` / `origin` / `pattern`).
- Make `testomation bench --replay` score the real analyzer. Target to beat (spike, with the model):
  cascade **16 right / 1 wrong / 7 review** of 24. Rules-only will cover fewer — record its
  baseline.

### E. Later (already designed)

Phase 3 assisted authoring (decide Q31: recorder), phase 4 planner, phase 5 model in the loop
(port `spike/triage_eval.py` classification + calibration), Langfuse in phase 3. Re-run
`spike/bakeoff.sh <model>` whenever a new local model appears (gate ≥ 5/8 re-opens autonomous
generation and exploration).

---

## Things to remember (lessons from 2026-10-04)

- **Constrain, don't instruct.** If the model must not do X, make the decoder schema forbid X.
- **Check what Ollama actually enforces** after any schema change: `journalctl -u ollama | grep
  "conversion was incomplete"`, and validate real outputs with `jsonschema` — drops are silent.
- **Score specs by kill rate, never by pass rate alone.** Always-true assertions pass forever.
- **Specs that share a user can interfere** when run in parallel; the reference suite is designed
  for it (different articles/fields per flow). Observation runs must be serial (`workers=1`).
- **Reset the app before every run** (`BUGS=... bench/app/conduit.sh reset`); leave it on `BUGS=`
  (clean) when done.
- Spike code (`spike/`) is throwaway and excluded from ruff; product code is `src/` + `runner/`.
- The user commits; Claude doesn't. Chain planned steps without asking; stop for decisions that
  change the plan.
