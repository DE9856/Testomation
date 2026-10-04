# Decisions

Tracks what's been decided, what's still open, and gaps found in the brief.
Current brief: `index.html` **v0.6** (previous: `archive/testomation-v0.5.html`,
`archive/testomation-v0.4.html`).

## Decided

| # | Decision | Rationale | Since | Doc |
|---|---|---|---|---|
| D1 | LLM authors/interprets tests, never runs them | Model work scales with change, not test frequency | v0.4 | [COST_STRATEGY](COST_STRATEGY.md) |
| D2 | ~~Hybrid scripted/NL tests~~ → **JSON test specs** run by one spec runner | Small models fill schemas reliably; no model-written code executed; resolves self-healing tension | v0.5 | [TEST_SPEC](TEST_SPEC.md) |
| D3 | Memory graph in Postgres (+ JSONB, pgvector), not a graph DB | 1–3 hop traversals fine with recursive CTEs | v0.4 | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D4 | Memory graph replaces the standalone test store | One source of truth | v0.4 | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D5 | ~~Temporal outside~~ → **pipeline runner + Playwright Test own jobs** (agents own decisions, see D6) | One machine; Temporal deferred until multi-machine | v0.5 (reworded v0.6) | [AGENT_RUNTIME](AGENT_RUNTIME.md) |
| D6 | ~~Analyzer is the first LangGraph graph~~ → **Agents are plain Python; LangGraph only for the exploration loop** | The analyzer is a cascade with early exits and review is asynchronous, so nothing needs pausing or resuming. Test-gen rounds belong to the pipeline because the model is unloaded while drafts run. Exploration is a long, checkpointed loop, which is where LangGraph earns its place | v0.6 | [AGENT_RUNTIME](AGENT_RUNTIME.md) |
| D7 | Executor and reporter stay plain code | No branching decisions | v0.4 | [AGENT_RUNTIME](AGENT_RUNTIME.md) |
| D8 | Langfuse, **self-hosted locally** (v3 Docker Compose), ~~wired up before first model call~~ → **started in phase 3 with the first model call; phases 0–2 write OpenTelemetry spans to a local file** | Saves 2–3 GB of RAM while only pipeline stages exist to trace; Langfuse's SDK is built on OpenTelemetry, so the instrumentation carries over | v0.6 | [OBSERVABILITY](OBSERVABILITY.md) |
| D9 | LangGraph checkpoints in the same Postgres as memory — **exploration loop only** | One DB; a long exploratory session resumes where it stopped | v0.4 (scoped v0.6) | [TECH_STACK](TECH_STACK.md) |
| D10 | Only **fresh** human-confirmed memory hits short-circuit analysis; **fresh = its basis hashes still match (D28)** | Prevents "memory learns the wrong lesson" and stale short-circuits | v0.5 (v0.6) | [RISKS](RISKS.md) |
| D11 | **Playwright Test** (TypeScript runner) for execution, workers, retries, evidence | Don't rebuild what Playwright provides | v0.5 | [TECH_STACK](TECH_STACK.md) |
| D12 | ~~Claude API at runtime~~ → **Ollama local models at runtime; Claude (Claude Code) for building only** | Free, local, private | v0.5 | [LOCAL_SETUP](LOCAL_SETUP.md) |
| D13 | Everything free and local on one laptop | Project constraint | v0.5 | [LOCAL_SETUP](LOCAL_SETUP.md) |
| D14 | Model calls through one OpenAI-compatible llm client (`langfuse.openai` → Ollama `/v1`) | Tracing for free; provider swap is config | v0.5 | [OBSERVABILITY](OBSERVABILITY.md) |
| D15 | Model tiers: ~~small ~4B (GPU), large ~7–8B (offload)~~ → **one model by default — `small` (~4B, on GPU) for all text work; `large` (~7–8B, CPU offload) only if the benchmark shows a gain**; `vision` optional; `embed` | No model swaps and faster everything; the schema constrains output, so a 4B model may be enough | v0.6 | [LOCAL_SETUP](LOCAL_SETUP.md) |
| D16 | Python for the brain, TypeScript for the spec runner; JSON files between them | Best of both Playwright and LangGraph ecosystems | v0.5 | [ARCHITECTURE](ARCHITECTURE.md) |
| D17 | Evidence in a local folder; graph stores paths | Simplest on one machine | v0.5 | [TECH_STACK](TECH_STACK.md) |
| D18 | Claims table (`mem_claim`) + `mem_fact` view; edges carry full provenance **and can be disputed by claims too** | Enforces "human beats model" for links (`likely_caused_by`, `duplicate_of`) as well as fields; audit trail | v0.5 (v0.6) | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D19 | Compute budget = model calls + model wall-clock per run | Money isn't the constraint locally | v0.5 | [COST_STRATEGY](COST_STRATEGY.md) |
| D20 | ~~Confidence from sample agreement + rules signal~~ → **Confidence from one call's label probability (logprobs) + a vote of labelled neighbours + the rules signal**, calibrated on the benchmark, never model self-report. Neighbour-vote claims carry source `knn` | Repeated samples from one small model are correlated, cost 3× and give only 0.33 / 0.67 / 1.0; self-report is uncalibrated | v0.6 | [AGENT_RUNTIME](AGENT_RUNTIME.md) |
| D21 | Seeded-bug benchmark gates every prompt/model/threshold change — **replay tier for analyzer changes, full tier for generation/model changes; only detectable mutants count; scores reported as ranges** | Ground truth from day one; a gate that takes hours gets skipped; ~20 bugs give noisy numbers | v0.5 (v0.6) | [EVALUATION](EVALUATION.md) |
| D22 | Seeded DB restored before each run; synthetic user per test | Results and flake signals must mean something | v0.5 | [LOCAL_SETUP](LOCAL_SETUP.md) |
| D23 | Local report + desktop notification; Jira/Slack later | No external services | v0.5 | [COMPONENTS](COMPONENTS.md) |
| D24 | Review queue as CLI over ~~interrupted graphs +~~ the **`review_item` table**; a decision is applied directly | Simplest UI that works; nothing to resume | v0.6 | [COMPONENTS](COMPONENTS.md) |
| D25 | MVP ingest: locally running web app URL + its repo, **plus any Playwright JSON report + traces for triage** | Narrow scope; the analyzer is useful to existing Playwright suites from phase 2 and gets real-world failures to calibrate on | v0.6 | [OVERVIEW](OVERVIEW.md) |
| D26 | ~~Test impact starts from a static route → file map~~ → **Every approved spec runs every run; impact analysis (static map, refined by coverage) only scopes model work** | A wrong map can't hide a regression; execution is cheap, model work isn't | v0.6 | [ARCHITECTURE](ARCHITECTURE.md) |
| D27 | Build order: **feasibility spike first**, then phase 0 (infra + bench), rules-only analyzer before generation | Tests the riskiest assumption before months of plumbing; value early; baseline for model features | v0.6 | [ROADMAP](ROADMAP.md), [DESIGN_ROADMAP](DESIGN_ROADMAP.md) |
| D28 | **Freshness from basis hashes**: each node, edge and claim records the file hashes (git blob SHAs) and normalised aria-snapshot hashes it was based on; `stale` is computed, not stored | Shared files would mark nearly everything stale on every commit; a revert makes memory fresh again; no invalidation job | v0.6 | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D29 | **Typed tables** for `TestCase`, `Run`, `Bug`, `NoiseSignature`, `Commit` (1:1 with `mem_node`), plus **`result` rows** that replace `Evidence` nodes. Typed columns hold undisputed facts; anything a source can get wrong is a claim | Constraints and simpler queries where the volume is; the generic graph stays flexible for app structure | v0.6 | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D30 | Test-gen repairs run in **batched rounds**: generate all → unload model → run all → repair all, ≤ 3 rounds | No RAM contention between model and browsers; fewer model loads; keeps "generation and execution apart" true | v0.6 | [TEST_SPEC](TEST_SPEC.md) |
| D31 | The spec schema has **one source** (`schemas/test-spec.schema.json`); Pydantic and TypeScript types are generated from it; shared example specs are validated by both sides | No drift between brain and hands | v0.6 | [TEST_SPEC](TEST_SPEC.md) |
| D32 | **Specs and exploration stay on the target origin**: `goto` / `api` paths are relative only and off-origin navigation is aborted. Page text in prompts is data, never instructions | Model-written specs can't reach other sites; limits prompt injection from page content | v0.6 | [TEST_SPEC](TEST_SPEC.md), [RISKS](RISKS.md) |
| D33 | **`helper` steps** call hand-written TypeScript helpers from a registry; models can only name registered helpers | Lets the spec vocabulary grow without becoming a programming language or letting models write code | v0.6 | [TEST_SPEC](TEST_SPEC.md) |
| D34 | MVP `Requirement` nodes come from business rules the planner infers (source `llm`) and from humans at approval; the spec's `requirement` field is optional | MVP ingest has no user stories, but traceability still works | v0.6 | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D35 | Positioned against **Playwright Test Agents**: their Generator (writes code) and Healer (self-heals) aren't reused | Keeps principles 2 and 6; makes Testomation's differences explicit | v0.6 | [OVERVIEW](OVERVIEW.md) |
| D36 | The brief lives at **`index.html`** (served by GitHub Pages); each superseded version is copied to `archive/testomation-v<version>.html` | One linkable source of truth | v0.6 | `CLAUDE.md` |

## Open questions

| # | Question | Status / notes |
|---|---|---|
| Q1 | ~~Temporal from day one, or Redis first?~~ | **Closed (D5):** neither — pipeline runner + Playwright Test. |
| Q2 | Which models per tier? | **Partly closed (D15):** one `small` model by default; spike and benchmark pick it and decide whether `large` earns a place. |
| Q3 | ~~Embedding model~~ | **Closed:** local via Ollama; candidate `nomic-embed-text` (768-d). Benchmark may change it. |
| Q4 | Natural keys for `Flow`, `Component`, `Element` | Open. Proposed in design step 2, confirmed in step 7 ([DESIGN_ROADMAP](DESIGN_ROADMAP.md)). |
| Q5 | Confidence thresholds | **Process closed (D21):** calibrated on the benchmark. Values TBD. |
| Q6 | Per-run budget values | Units decided (D19); numbers TBD from the benchmark. |
| Q7 | ~~Core service language~~ | **Closed (D16).** |
| Q8 | ~~Ingest inputs for MVP~~ | **Closed (D25).** |
| Q9 | ~~Review queue UI~~ | **Closed (D24)** for now; web UI later. |
| Q10 | ~~Test draft lifecycle~~ | **Closed:** `status` on `TestCase`: draft → approved → quarantined → retired. |
| Q11 | Multi-tenancy | `project` column added now; full isolation later. |
| Q12 | Which target app for the benchmark? | Candidate: a RealWorld ("Conduit") implementation. Closed in design step 3. |
| Q13 | Does Ollama's OpenAI-compatible endpoint, through `langfuse.openai`, handle our spec schema (a discriminated union) under structured output, and pass **logprobs** through? | Verify in the **spike**. Fallback: Ollama's native client (`format=`, `logprobs`) plus a manual generation span. *(extended v0.6)* |
| Q14 | Backend coverage for `touches` | Static map first; how/if to add per-test backend coverage later. |
| Q15 | Crawler: build our own state-graph crawler or adapt an existing tool? | Open. Closed in design step 7. |
| Q16 | ~~Sample count for agreement (3?) and whether to vary temperature or prompts~~ | **Closed (D20):** one call with logprobs replaces sampling; see Q19. If logprobs aren't usable, the fallback samples 3× at temperature > 0 (at temperature 0 every sample agrees). |
| Q17 | How is an aria snapshot normalised before hashing for a basis? | Open. Starting point: keep roles and accessible names; mask numbers, dates, faker-generated values and user-generated text. *(new)* |
| Q18 | Basis policy per claim kind, and which kinds may have an empty basis | Open. Draft in [MEMORY_GRAPH](MEMORY_GRAPH.md#freshness-basis-hashes); empty basis proposed only for `Commit`, `HumanDecision` and origin-kind `NoiseSignature`. *(new)* |
| Q19 | How to combine label probability, neighbour vote and rules signal into one score; neighbour `k` and minimum similarity | Open. Candidates: logistic regression or isotonic calibration fitted on the benchmark. Placeholders: k = 5, similarity ≥ 0.9. *(new)* |
| Q20 | When does test selection come back? | Open. When a full run of approved specs exceeds a time limit (e.g. 10 min); impact analysis then picks specs again. *(new)* |
| Q21 | Should the planner emit a human-editable Markdown plan, like Playwright's planner agent, before specs are generated? | Open. *(new)* |
| Q22 | Spike exit targets | Proposed in [DESIGN_ROADMAP](DESIGN_ROADMAP.md#step-1--feasibility-spike); confirm before the spike starts. *(new)* |
| Q23 | Does the planner's "go back for detail on high-value areas" need a loop framework? | Open. Default: plain code; LangGraph only if the loop proves real. *(new)* |
| Q24 | For imported Playwright suites (no spec), how is a failure mapped to a step and an element? | Open. Use `test.step` titles when present; otherwise the failing locator from the error and the trace's last action. *(new)* |
| Q25 | The exploration loop is Python (LangGraph) but browser actions live in the TypeScript runner. How does it drive the browser? | Open. Proposed: a TypeScript **step server** (the spec runner's step code over stdio JSON), so each step is implemented once. Alternative: Playwright for Python in the explorer, duplicating step code. *(new)* |

## Gaps found in the v0.5 brief

| # | Observation | Resolution |
|---|---|---|
| G11 | Docs and `CLAUDE.md` pointed at `testomation.html` after it was renamed to `index.html` | **Resolved (D36).** |
| G12 | `Requirement` nodes had no source in the MVP (ingest is URL + repo), yet the example spec used `REQ-142` | **Resolved (D34).** |
| G13 | Three samples at temperature 0 always agree, so "agreement" measured nothing | **Resolved (D20):** no sampling; the fallback requires temperature > 0. |
| G14 | `goto` could leave the target origin; page text reaches model prompts unguarded | **Resolved (D32)** + risk #10. |
| G15 | The step vocabulary had no way to grow except into a language | **Resolved (D33).** |
| G16 | Edges couldn't hold competing claims, so a human couldn't overrule an LLM-inferred link | **Resolved (D18).** |
| G17 | The per-spec generate → run → repair loop interleaved the model and browsers, contradicting "keep generation and execution apart" | **Resolved (D30).** |
| G18 | The overview said every reasoning agent is a LangGraph graph, while the roadmap adopted LangGraph incrementally | **Resolved (D6).** |
| G19 | Shared files (layout, utils, API client) would mark nearly all memory stale on every commit | **Resolved (D28).** |
| G20 | Phase 1 required the whole Langfuse stack before any model call existed | **Resolved (D8).** |
| G21 | No bridge was defined between the Python exploration loop and the TypeScript browser runner | **Open (Q25).** |

## Gaps found in the v0.4 brief

| # | Observation | Resolution |
|---|---|---|
| G1 | Edges had no provenance beyond `source` | **Resolved (D18):** `confidence`, `trace_id`, freshness and `updated_at` on `mem_edge`. |
| G2 | No `Commit → SourceFile` edge | **Resolved:** `Commit —changes→ SourceFile`. |
| G3 | Root-cause suggestion and regression clustering are "later" but cheap as graph queries | **Open:** reconsider promoting once phase 5 is done. |
| G4 | A stale human-sourced hit could short-circuit | **Resolved (D10):** memory node requires fresh human claims. |
| G5 | Self-healing risk vs NL-at-runtime tests | **Resolved (D2):** JSON specs; approved specs never self-heal. |
| G6 | No agent wrote `Component`/`Element` | **Resolved:** Planner writes them (parsing + aria snapshots). |
| G7 | Review queue not in the system diagram | **Resolved:** in the v0.5 diagram. |
| G8 | One Executor box despite two modes | **Resolved:** documented as two modes in [COMPONENTS](COMPONENTS.md); diagram labels the spec mode. |
| G9 | No app state reset strategy | **Resolved (D22).** |
| G10 | No ground truth for accuracy before human reviews exist | **Resolved (D21).** |
