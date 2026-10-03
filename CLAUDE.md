# CLAUDE.md

Guidance for Claude (and humans) working in this repository.

## Status

**Design stage — there is no code yet.** This repo holds the idea documentation for
Testomation. The source of truth is the project brief `testomation.html` (**v0.5**); the
Markdown files in `docs/` are a split-out, editable version of it. Keep the two in sync. If
they disagree, flag it rather than silently picking one. The previous brief is kept at
`archive/testomation-v0.4.html`.

## What Testomation is

An autonomous software testing platform. It reads a codebase or app, decides what needs
testing, writes the tests itself, drives a real browser to run them, tells real bugs apart
from noise, and reports back — asking a human only when it isn't sure.

It sits **alongside** scripted regression testing, not instead of it: it fills the gap
between "what we remembered to test" and "what the app can actually do."

## Ground rules (v0.5)

- **Free and local.** Everything runs on one laptop (Ryzen 7 5800H, 16 GB RAM, RTX 3050 4 GB
  VRAM, Fedora). No paid APIs or hosted services in the product.
- **Claude builds it; Ollama runs it.** Claude (Claude Code) is the assistant used to *build*
  Testomation. The product itself calls **only local models via Ollama**. Never add the
  `anthropic` SDK or any paid API as a runtime dependency.
- **Playwright does the running.** Playwright Test provides execution, workers, retries,
  traces, screenshots and reports. Don't rebuild what it already does.
- **Langfuse, self-hosted.** Runs locally with Docker Compose.

## Doc map

| File | Read it when you need… |
|---|---|
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | The pitch, ground rules, pipeline, what changed in v0.5 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How every part connects: agents, runner, stores, model path, data flow |
| [docs/COMPONENTS.md](docs/COMPONENTS.md) | What each agent/service does, its inputs and outputs |
| [docs/TEST_SPEC.md](docs/TEST_SPEC.md) | The JSON test format, spec runner, lifecycle, repair rules |
| [docs/MEMORY_GRAPH.md](docs/MEMORY_GRAPH.md) | Node/edge/claim model, SQL schema, read-first/write-back loop, trust rules |
| [docs/COST_STRATEGY.md](docs/COST_STRATEGY.md) | Where models are and aren't allowed; compute budget |
| [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) | Langfuse mapping, instrumentation with Ollama, metrics |
| [docs/AGENT_RUNTIME.md](docs/AGENT_RUNTIME.md) | Pipeline runner (outside) vs LangGraph (inside), the analyzer graph |
| [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) | Laptop limits, services, model tiers, RAM budget, app state, repo layout |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Seeded-bug benchmark, metrics, how thresholds and models are chosen |
| [docs/FEATURES.md](docs/FEATURES.md) | Full feature catalog, core vs later |
| [docs/RISKS.md](docs/RISKS.md) | Design risks the architecture is built around |
| [docs/TECH_STACK.md](docs/TECH_STACK.md) | Chosen tools per layer and why |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Build order, phases 0–6 + later |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decisions made, decisions still open, gaps found and resolved |

## Core principles (do not violate without discussion)

1. **The LLM writes and interprets tests; it never runs them.** Execution is Playwright Test.
   Model work should scale with how much the app *changes*, not how often it's tested.
2. **Tests are JSON specs, not code.** Models fill a schema; one spec runner executes it.
   Nothing a model writes is ever executed on the host.
3. **Memory → deterministic tools → model → write back.** Every agent step follows this order.
4. **Provenance on everything.** Nodes, edges and claims record source (`rules` / `llm` /
   `human`), confidence, and the Langfuse trace ID.
5. **Human beats model.** Resolved per node and field from claims; losing claims are kept.
6. **No silent suppression or self-healing.** An LLM-inferred `NoiseSignature` never hides a
   failure until a human confirms it. Approved specs never change without review. Repairs to
   drafts may not touch assertions.
7. **Stale until proven.** Invalidated memory can inform a decision but cannot short-circuit
   one — including human claims.
8. **Pipeline runner + Playwright own jobs; LangGraph owns decisions.** Never blur the two.
9. **Confidence comes from agreement and rules, not model self-report**, and thresholds are
   calibrated on the benchmark.
10. **Every prompt, model or threshold change is gated on the seeded-bug benchmark.**
11. **Respect the laptop.** One model loaded at a time, two Playwright workers while a model
    is loaded, generation and execution kept apart.
12. **Only use a framework where logic branches.** Executor and reporter stay plain code.

## Vocabulary

- **Spec** — a JSON test: steps with role/label targets and assertions. Stored on a
  `TestCase` node. Lifecycle `draft → approved → quarantined → retired`.
- **Spec runner** — the one Playwright Test file that interprets specs.
- **Run** — one execution of the pipeline (`run-<pr>-<sha>` or `run-local-<timestamp>`).
- **Evidence** — Playwright trace, screenshots, video, axe results, coverage for a run. Lives
  in `data/evidence/<run>/`; memory stores only paths.
- **Claim** — one source's assertion about a node field (e.g. verdict = bug, source = llm,
  confidence = 0.67). Several claims can coexist; `mem_fact` resolves them.
- **Noise signature** — a known-harmless error pattern.
- **Review queue** — interrupted LangGraph threads waiting for a human, listed via
  `testomation review`.
- **Model tiers** — `small` (~4B, on GPU), `large` (~7–8B, CPU offload), `vision`
  (optional), `embed`.
- **Compute budget** — per-run cap on model calls and model wall-clock time.
- **Benchmark** — local target app with toggleable seeded bugs; `testomation bench`.

## Working conventions for this repo

- Change a decision → update `docs/DECISIONS.md`, every doc that references it, **and** the
  matching section of `testomation.html` (bump its version in the sidebar and footer).
- Prefer concrete examples (node names, edge names, table columns, spec fields) over prose.
- When proposing something not covered, add it under "Open questions" in `docs/DECISIONS.md`
  rather than stating it as settled.
- Model names are configuration, not code — refer to tiers (`small`, `large`) in designs.
