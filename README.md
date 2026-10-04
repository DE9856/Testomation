# Testomation

An autonomous software testing platform. It reads a codebase or app, decides what needs
testing, writes the tests itself, drives a real browser to run them, tells real bugs apart
from noise, and reports back — asking a human only when it isn't sure.

It sits **alongside** scripted regression testing, not instead of it: it fills the gap
between "what we remembered to test" and "what the app can actually do."

**📄 Project brief (v0.6): https://de9856.github.io/Testomation/**

> **Status: design stage.** There is no code yet. This repo holds the idea documentation.

## The pipeline

```
 Ingest ──► Plan ──► Generate ──► Execute ──► Analyze & Report
```

| # | Step | What happens |
|---|---|---|
| 01 | **Ingest** | A locally running web app (URL) + its repo |
| 02 | **Plan** | Reason about flows, edge cases, boundaries, negative paths → coverage plan |
| 03 | **Generate** | Each planned flow → a JSON test spec validated against a schema |
| 04 | **Execute** | Playwright Test runs every approved spec via one spec runner; traces, screenshots, DOM, console, network captured |
| 05 | **Analyze & report** | Classify failures, dedupe, write a local report with repro steps |

Inside every step: **check memory → try deterministic tools → call a local model only for
what's still unanswered → write the result back with provenance**, all traced (OpenTelemetry
file first, self-hosted Langfuse from phase 3).

The analyzer also works on its own: `testomation import` triages any existing Playwright
suite's report.

## Ground rules

- **Free and local.** Everything runs on one laptop. No paid APIs or hosted services.
- **Ollama at runtime.** The product calls only local models served by Ollama.
- **Playwright does the running.** Execution, workers, retries, traces and reports come from
  Playwright Test.
- **Tests are JSON specs, not code.** Models fill a schema; nothing a model writes is
  executed on the host.
- **Traced locally.** OpenTelemetry spans to a file first; self-hosted Langfuse (Docker
  Compose) from the first model call.

## Repository layout

| Path | What it is |
|---|---|
| [`index.html`](index.html) | The project brief (v0.6) — source of truth, served on GitHub Pages |
| [`docs/`](docs/) | The brief split into editable Markdown files |
| [`archive/`](archive/) | Previous briefs (v0.4, v0.5) |
| [`CLAUDE.md`](CLAUDE.md) | Guidance for working in this repo |

## Docs

| File | Covers |
|---|---|
| [OVERVIEW](docs/OVERVIEW.md) | The pitch, ground rules, pipeline, what changed in v0.6 |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | How agents, runner, stores and model path connect |
| [COMPONENTS](docs/COMPONENTS.md) | What each agent/service does, its inputs and outputs |
| [TEST_SPEC](docs/TEST_SPEC.md) | JSON test format, spec runner, lifecycle, repair rules |
| [MEMORY_GRAPH](docs/MEMORY_GRAPH.md) | Nodes, typed tables, edges, claims, freshness, SQL schema, trust rules |
| [COST_STRATEGY](docs/COST_STRATEGY.md) | Where models are and aren't allowed; compute budget |
| [OBSERVABILITY](docs/OBSERVABILITY.md) | Langfuse mapping, instrumentation, metrics |
| [AGENT_RUNTIME](docs/AGENT_RUNTIME.md) | Pipeline runner, plain-Python agents, the analyzer cascade, the exploration loop |
| [LOCAL_SETUP](docs/LOCAL_SETUP.md) | Laptop limits, services, model tiers, RAM budget |
| [EVALUATION](docs/EVALUATION.md) | Seeded-bug benchmark, replay and full tiers, metrics, threshold selection |
| [FEATURES](docs/FEATURES.md) | Feature catalog, core vs later |
| [RISKS](docs/RISKS.md) | Design risks the architecture is built around |
| [TECH_STACK](docs/TECH_STACK.md) | Chosen tools per layer and why |
| [ROADMAP](docs/ROADMAP.md) | Build order: spike, phases 0–6 + later |
| [DESIGN_ROADMAP](docs/DESIGN_ROADMAP.md) | What to design and decide before each phase, with exit gates |
| [DECISIONS](docs/DECISIONS.md) | Decisions made, open questions, gaps resolved |
