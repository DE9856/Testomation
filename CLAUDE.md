# CLAUDE.md

Guidance for Claude (and humans) working in this repository.

## Status

**Design stage, with scaffolding only.** The repo holds the idea documentation for
Testomation plus a bare skeleton (packaging, CLI stubs, draft spec schema, runner stub,
compose, draft memory DDL) and a working step executor in `runner/` (`steps.ts`: all actions
except `upload`/`helper`, origin guard, failing-step annotation + aria snapshot on failure).
No agent logic yet — the feasibility spike is done (`docs/SPIKE_RESULTS.md`); phase 0 is next. The source of truth is the project brief `index.html` (**v0.7**, served on
GitHub Pages); the Markdown files in `docs/` are a split-out, editable version of it. Keep the
two in sync. If they disagree, flag it rather than silently picking one. Previous briefs are
kept in `archive/` (v0.4–v0.6).

## What Testomation is

An autonomous software testing platform. It reads a codebase or app, decides what needs
testing, writes the tests itself, drives a real browser to run them, tells real bugs apart
from noise, and reports back — asking a human only when it isn't sure.

**After the spike (v0.7):** the model *assists* test authoring (templates/recordings give the
actions, the model picks assertions, a human approves every draft — D42) and *decides* triage.
Autonomous generation and exploration wait until a local model passes the kill-rate benchmark
(D43).

It sits **alongside** scripted regression testing, not instead of it: it fills the gap
between "what we remembered to test" and "what the app can actually do."

## Ground rules (v0.7)

- **Free and local.** Everything runs on one laptop (Ryzen 7 5800H, 16 GB RAM, RTX 3050 4 GB
  VRAM, Fedora). No paid APIs or hosted services in the product.
- **Claude builds it; Ollama runs it.** Claude (Claude Code) is the assistant used to *build*
  Testomation. The product itself calls **only local models via Ollama**. Never add the
  `anthropic` SDK or any paid API as a runtime dependency.
- **Playwright does the running.** Playwright Test provides execution, workers, retries,
  traces, screenshots and reports. Don't rebuild what it already does.
- **Tracing: OpenTelemetry first, Langfuse from phase 3.** Phases 0–2 write spans to a local
  file; self-hosted Langfuse (Docker Compose) arrives with the first model call.

## Doc map

**Picking up work? Read [CHANGELOG.md](CHANGELOG.md) first** — the last session's state, how to
bring the services up, and the ordered next steps.

| File | Read it when you need… |
|---|---|
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | The pitch, ground rules, pipeline, what changed in v0.6, how it differs from Playwright's agents |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How every part connects: agents, runner, stores, model path, data flow |
| [docs/COMPONENTS.md](docs/COMPONENTS.md) | What each agent/service does, its inputs and outputs |
| [docs/TEST_SPEC.md](docs/TEST_SPEC.md) | The JSON test format, helper steps, origin guard, spec runner, lifecycle, repair rounds |
| [docs/MEMORY_GRAPH.md](docs/MEMORY_GRAPH.md) | Nodes, typed tables, edges, claims, basis-hash freshness, SQL schema, trust rules |
| [docs/COST_STRATEGY.md](docs/COST_STRATEGY.md) | Where models are and aren't allowed; compute budget |
| [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) | OpenTelemetry file traces, Langfuse mapping, instrumentation, metrics |
| [docs/AGENT_RUNTIME.md](docs/AGENT_RUNTIME.md) | Pipeline runner for jobs, plain-Python agents, the analyzer cascade, the LangGraph exploration loop |
| [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) | Laptop limits, services, model tiers, RAM budget, app state, repo layout |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Seeded-bug benchmark, replay and full tiers, metrics, how thresholds and models are chosen |
| [docs/FEATURES.md](docs/FEATURES.md) | Full feature catalog, core vs later |
| [docs/RISKS.md](docs/RISKS.md) | Design risks the architecture is built around |
| [docs/TECH_STACK.md](docs/TECH_STACK.md) | Chosen tools per layer and why; what was considered and not used |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Build order: spike, phases 0–6 + later |
| [docs/DESIGN_ROADMAP.md](docs/DESIGN_ROADMAP.md) | What to design and decide before each phase, with exit gates |
| [docs/SPIKE_RESULTS.md](docs/SPIKE_RESULTS.md) | Measured feasibility: model fit/speed on this laptop, spike findings |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decisions made, decisions still open, gaps found and resolved |

## Core principles (do not violate without discussion)

1. **The LLM writes and interprets tests; it never runs them.** Execution is Playwright Test.
   Model work should scale with how much the app *changes*, not how often it's tested.
2. **Tests are JSON specs, not code.** Models fill a schema; one spec runner executes it.
   Nothing a model writes is ever executed on the host, and specs never leave the target
   app's origin.
3. **Memory → deterministic tools → model → write back.** Every agent step follows this order.
4. **Provenance on everything.** Nodes, edges and claims record source (`rules` / `knn` /
   `llm` / `human`), confidence, trace ID and basis.
5. **Human beats model.** Resolved per node field and per edge from claims; losing claims are
   kept.
6. **No silent suppression or self-healing.** A model-inferred (`llm` or `knn`)
   `NoiseSignature` never hides a failure until a human confirms it. Approved specs never
   change without review. Repairs to drafts may not touch assertions.
7. **Stale until proven.** Freshness comes from basis hashes. Stale memory can inform a
   decision but cannot short-circuit one — including human claims.
8. **Pipeline runner + Playwright own jobs; agent code owns decisions; LangGraph only for the
   exploration loop.** Never blur them.
9. **Confidence comes from label probabilities, labelled neighbours and rules, not model
   self-report**, and thresholds are calibrated on the benchmark.
10. **Every prompt, model or threshold change is gated on the seeded-bug benchmark** — the
    replay tier for analyzer changes, the full tier for generation and model changes.
11. **Respect the laptop.** One model loaded at a time, and unloaded while specs run; two
    Playwright workers while a model is loaded; generation and execution kept apart
    (batched repair rounds).
12. **Only use a framework where logic loops.** Agents, executor and reporter stay plain
    code.

## Vocabulary

- **Spec** — a JSON test: steps with role/label targets and assertions. Stored on a
  `TestCase` node (`test_case` table). Lifecycle `draft → approved → quarantined → retired`.
- **Spec runner** — the one Playwright Test file that interprets specs.
- **Helper step** — a hand-written TypeScript helper a spec can call by name; models can only
  name registered helpers.
- **Run** — one execution of the pipeline (`run-<pr>-<sha>`, `run-local-<timestamp>` or
  `run-import-<timestamp>`).
- **Result** — one row per test per run: outcome, failing step, error signature, evidence path.
- **Evidence** — Playwright trace, screenshots, video, axe results, coverage for a run. Lives
  in `data/evidence/<run>/`; memory stores only paths (on `result` rows).
- **Claim** — one source's assertion about a node field or an edge (e.g. verdict = bug,
  source = llm, confidence = 0.71). Several claims can coexist; `mem_fact` resolves them.
- **Basis** — the file hashes and normalised aria-snapshot hashes a node, edge or claim was
  based on. It's fresh while they still match `basis_state`.
- **Labelled neighbours** — past failures with a fresh human (or benchmark) verdict, nearest
  by embedding; their vote is a claim with source `knn`.
- **Noise signature** — a known-harmless error pattern.
- **Review queue** — open `review_item` rows, decided via `testomation review`.
- **Model tiers** — `small` (~4B, on GPU; the default for everything), `large` (~7–8B, CPU
  offload; only if the benchmark earns it), `vision` (optional), `embed`.
- **Compute budget** — per-run cap on model calls and model wall-clock time.
- **Spike** — the throwaway feasibility test that comes before any infrastructure.
- **Benchmark** — local target app with toggleable seeded bugs; `testomation bench` (full
  tier) and `testomation bench --replay` (replay tier).

## Commands

- `uv sync` · `uv run pytest` · `uv run ruff check .` · `uv run testomation --help`
- `cd runner && npm install && npm run typecheck && npm run validate-examples`
- `docker compose -f deploy/compose.yaml up -d` (Postgres + pgvector; applies `deploy/sql/`)
- `bench/app/conduit.sh up | reset | down` (benchmark target app on :4100; `BUGS=<id,...>` before
  `reset` switches seeded bugs on)
- `uv run testomation bench [--runs N]` (full tier, ~12 min) · `uv run testomation bench --replay`

## Working conventions for this repo

- Change a decision → update `docs/DECISIONS.md`, every doc that references it, **and** the
  matching section of `index.html` (bump its version in the sidebar and footer).
- Before bumping the brief's version, copy the current `index.html` to
  `archive/testomation-v<old version>.html`.
- Prefer concrete examples (node names, edge names, table columns, spec fields) over prose.
- When proposing something not covered, add it under "Open questions" in `docs/DECISIONS.md`
  rather than stating it as settled.
- Model names are configuration, not code — refer to tiers (`small`, `large`) in designs.
- `schemas/test-spec.schema.json` and `deploy/sql/001_memory.sql` mirror `docs/TEST_SPEC.md` and
  `docs/MEMORY_GRAPH.md`; change them together. Spec examples must pass in both Python and TS.
