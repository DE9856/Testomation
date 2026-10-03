# Overview

> Source: `testomation.html` §00–§01 (brief v0.5)

## The problem

Traditional test automation still needs a human to do two jobs:

1. Decide **what** to test.
2. **Write** the script.

Testomation moves both to an AI agent that reasons about the app like a QA engineer,
generates its own coverage, and only asks a human when it isn't sure whether something is
actually broken.

It is meant to sit **alongside** scripted regression testing — filling the gap between
"what we remembered to test" and "what the app can actually do."

## Ground rules (v0.5)

| Rule | Meaning |
|---|---|
| **Free and local** | Everything runs on one laptop. No paid APIs or hosted services in the product. |
| **Ollama at runtime** | Every model call the product makes goes to local models served by Ollama. |
| **Claude for building** | Claude (Claude Code) helps *build* Testomation. It is not part of the product's runtime. |
| **Playwright does the running** | Playwright Test handles execution, workers, retries, traces, screenshots. Testomation doesn't rebuild that. |

## The pipeline

```
 Ingest ──► Plan ──► Generate ──► Execute ──► Analyze & Report
```

| # | Step | What happens | Owning component |
|---|---|---|---|
| 01 | **Ingest** | MVP: a locally running web app (URL) + its repo. OpenAPI, design files, user stories later. | Planner (input side) |
| 02 | **Plan** | Reason about what to test — flows, edge cases, boundaries, negative paths → coverage plan | Planner agent |
| 03 | **Generate** | Each planned flow → a **JSON test spec** validated against a schema | Test-gen agent |
| 04 | **Execute** | Playwright Test runs specs via one spec runner; traces, screenshots, DOM, console, network captured | Executor |
| 05 | **Analyze & report** | Compare evidence to expected behaviour, classify, dedupe, write a local report with repro steps | Analyzer + Reporter |

## The loop inside every step

```
check memory graph
   └─► try deterministic tools
          └─► call a local model only for what's still unanswered
                 └─► write result back as a claim (with provenance)
                        └─► whole job is traced in Langfuse
```

In code, that loop is a small LangGraph graph per reasoning agent.

## What changed since v0.4

| Change | Why | Detail |
|---|---|---|
| **Tests are JSON specs, not code** | Small models fill schemas reliably; nothing model-written is executed | [TEST_SPEC.md](TEST_SPEC.md) |
| **Local models via Ollama** | Free, private; replaces the Claude API at runtime | [LOCAL_SETUP.md](LOCAL_SETUP.md) |
| **No Temporal for now** | One machine: a plain pipeline runner + Playwright Test workers is enough | [AGENT_RUNTIME.md](AGENT_RUNTIME.md) |
| **Budget is compute, not money** | VRAM, RAM and time are the scarce things now | [COST_STRATEGY.md](COST_STRATEGY.md) |
| **Claims in memory** | Human, rules and model verdicts coexist so "human beats model" is enforceable | [MEMORY_GRAPH.md](MEMORY_GRAPH.md) |
| **Seeded-bug benchmark** | Ground truth from day one | [EVALUATION.md](EVALUATION.md) |
| **App state reset** | Results and flake signals only mean something from a known start | [LOCAL_SETUP.md](LOCAL_SETUP.md) |
| **Local reporting** | HTML/Markdown report + desktop notification; Jira/Slack later | [COMPONENTS.md](COMPONENTS.md) |

## Cross-cutting layers

None of these adds a pipeline step. They change how **every** step behaves.

| Layer | One-liner | Detail |
|---|---|---|
| **Memory graph** | Shared, persistent map of the app and everything learned about it. | [MEMORY_GRAPH.md](MEMORY_GRAPH.md) |
| **Cost & compute** | The LLM authors and interprets tests but never runs them. Deterministic tools first. | [COST_STRATEGY.md](COST_STRATEGY.md) |
| **Observability** | Self-hosted Langfuse traces every agent job — including ones that never called a model. | [OBSERVABILITY.md](OBSERVABILITY.md) |
| **Agent runtime** | LangGraph inside each agent; pipeline runner + Playwright Test around them. | [AGENT_RUNTIME.md](AGENT_RUNTIME.md) |

Memory makes most model calls unnecessary, LangGraph enforces "memory and rules before the
model" in code, Langfuse proves it's working, and the benchmark shows it's right.
