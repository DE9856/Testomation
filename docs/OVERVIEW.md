# Overview

> Source: `index.html` §00–§01 (brief v0.6)

## The problem

Traditional test automation still needs a human to do two jobs:

1. Decide **what** to test.
2. **Write** the script.

Testomation moves both to an AI agent that reasons about the app like a QA engineer,
generates its own coverage, and only asks a human when it isn't sure whether something is
actually broken.

It is meant to sit **alongside** scripted regression testing — filling the gap between
"what we remembered to test" and "what the app can actually do."

## Ground rules (v0.6)

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
| 01 | **Ingest** | MVP: a locally running web app (URL) + its repo. For triage alone: any Playwright project's JSON report and traces. OpenAPI, design files, user stories later. | Planner (input side), Importer |
| 02 | **Plan** | Reason about what to test — flows, edge cases, boundaries, negative paths → coverage plan | Planner agent |
| 03 | **Generate** | Each planned flow → a **JSON test spec** validated against a schema | Test-gen agent |
| 04 | **Execute** | Playwright Test runs every approved spec via one spec runner; traces, screenshots, DOM, console, network captured | Executor |
| 05 | **Analyze & report** | Compare evidence to expected behaviour, classify, dedupe, write a local report with repro steps | Analyzer + Reporter |

## The loop inside every step

```
check memory graph (fresh claims only)
   └─► try deterministic tools (rules, parsers, labelled-neighbour vote)
          └─► call a local model only for what's still unanswered
                 └─► write result back as a claim (with provenance and basis)
                        └─► whole job is traced
```

In code, that loop is a plain-Python cascade in each agent. LangGraph is used only for the
exploration loop.

## What changed since v0.5

| Change | Why | Detail |
|---|---|---|
| **Spike before infrastructure** | Find out whether local models are good enough before months of plumbing | [DESIGN_ROADMAP.md](DESIGN_ROADMAP.md) |
| **Triage for any Playwright suite** | Useful from phase 2; real-world failures to calibrate on | [COMPONENTS.md](COMPONENTS.md#importer--new-in-v06) |
| **All approved specs run every run** | A wrong impact map can't hide a regression; impact analysis now scopes model work only | [ARCHITECTURE.md](ARCHITECTURE.md#6-how-a-run-flows-end-to-end) |
| **Freshness from basis hashes** | Precise invalidation; a revert makes memory fresh again | [MEMORY_GRAPH.md](MEMORY_GRAPH.md#freshness-basis-hashes) |
| **Confidence from logprobs + labelled neighbours** | One model call instead of three, and a score that can be calibrated | [AGENT_RUNTIME.md](AGENT_RUNTIME.md#the-analyzer-cascade) |
| **Batched repair rounds** | The model and the browsers never compete for RAM | [TEST_SPEC.md](TEST_SPEC.md#repair-rounds-drafts-only--changed-in-v06) |
| **One model by default** | No model swaps; the large tier must earn its place on the benchmark | [LOCAL_SETUP.md](LOCAL_SETUP.md#model-tiers) |
| **LangGraph only for exploration** | The analyzer is a cascade and review is asynchronous; nothing to pause or resume | [AGENT_RUNTIME.md](AGENT_RUNTIME.md) |
| **Typed tables + claims on edges** | Constraints where the volume is; humans can overrule inferred links | [MEMORY_GRAPH.md](MEMORY_GRAPH.md) |
| **Langfuse from phase 3** | 2–3 GB of RAM back while there's nothing but stages to trace | [OBSERVABILITY.md](OBSERVABILITY.md) |
| **Replay benchmark tier** | Analyzer changes are gated in minutes, not hours | [EVALUATION.md](EVALUATION.md#two-tiers) |
| **One schema source, origin guard, helper steps** | No drift between Python and TypeScript; specs stay on the target; the vocabulary can grow safely | [TEST_SPEC.md](TEST_SPEC.md) |

## How it differs from Playwright Test Agents

Playwright ships official **Planner, Generator and Healer** agents. They explore an app,
write a Markdown test plan, generate tests, and repair failing ones. They run inside a
coding-agent tool, using that tool's model. That overlaps Testomation's planning and
generation, so the differences are deliberate (D35):

| | Playwright Test Agents | Testomation |
|---|---|---|
| Test output | `.spec.ts` code | JSON specs; nothing a model writes is executed |
| Failing tests | Healer repairs them | Approved specs never self-heal; drift is a review item |
| Models | Whatever the coding tool uses | Local Ollama models only |
| Memory across runs | — | Memory graph with claims, provenance and freshness |
| Bug vs noise | — | Analyzer cascade with a review queue |
| Measuring itself | — | Seeded-bug benchmark gates every change |

Their Generator and Healer aren't reused, because they'd break principles 2 and 6. Whether
the planner should emit a human-editable Markdown plan the way theirs does is open (Q21).

## Cross-cutting layers

None of these adds a pipeline step. They change how **every** step behaves.

| Layer | One-liner | Detail |
|---|---|---|
| **Memory graph** | Shared, persistent map of the app and everything learned about it. | [MEMORY_GRAPH.md](MEMORY_GRAPH.md) |
| **Cost & compute** | The LLM authors and interprets tests but never runs them. Deterministic tools first. | [COST_STRATEGY.md](COST_STRATEGY.md) |
| **Observability** | Every agent job is traced — OpenTelemetry file first, self-hosted Langfuse from phase 3 — including jobs that never called a model. | [OBSERVABILITY.md](OBSERVABILITY.md) |
| **Agent runtime** | Pipeline runner + Playwright Test for jobs; plain-Python agents for decisions; LangGraph only for the exploration loop. | [AGENT_RUNTIME.md](AGENT_RUNTIME.md) |

Memory makes most model calls unnecessary, the analyzer's cascade enforces "memory and rules
before the model" in code, traces prove it's working, and the benchmark shows it's right.
