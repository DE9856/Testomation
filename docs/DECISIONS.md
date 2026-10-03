# Decisions

Tracks what's been decided, what's still open, and gaps found in the brief.
Current brief: `testomation.html` **v0.5** (previous: `archive/testomation-v0.4.html`).

## Decided

| # | Decision | Rationale | Since | Doc |
|---|---|---|---|---|
| D1 | LLM authors/interprets tests, never runs them | Model work scales with change, not test frequency | v0.4 | [COST_STRATEGY](COST_STRATEGY.md) |
| D2 | ~~Hybrid scripted/NL tests~~ → **JSON test specs** run by one spec runner | Small models fill schemas reliably; no model-written code executed; resolves self-healing tension | v0.5 | [TEST_SPEC](TEST_SPEC.md) |
| D3 | Memory graph in Postgres (+ JSONB, pgvector), not a graph DB | 1–3 hop traversals fine with recursive CTEs | v0.4 | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D4 | Memory graph replaces the standalone test store | One source of truth | v0.4 | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D5 | ~~Temporal outside~~ → **pipeline runner + Playwright Test outside**, LangGraph inside | One machine; Temporal deferred until multi-machine | v0.5 | [AGENT_RUNTIME](AGENT_RUNTIME.md) |
| D6 | Analyzer is the first LangGraph graph | Branching + review pauses matter most there | v0.4 | [AGENT_RUNTIME](AGENT_RUNTIME.md) |
| D7 | Executor and reporter stay plain code | No branching decisions | v0.4 | [AGENT_RUNTIME](AGENT_RUNTIME.md) |
| D8 | Langfuse, **self-hosted locally** (v3 Docker Compose), wired up before first model call | Fits in 16 GB; traces from day one | v0.5 | [OBSERVABILITY](OBSERVABILITY.md) |
| D9 | LangGraph checkpoints in the same Postgres as memory | One DB; crash-safe resumption | v0.4 | [TECH_STACK](TECH_STACK.md) |
| D10 | Only **fresh** human-confirmed memory hits short-circuit analysis | Prevents "memory learns the wrong lesson" and stale short-circuits | v0.5 | [RISKS](RISKS.md) |
| D11 | **Playwright Test** (TypeScript runner) for execution, workers, retries, evidence | Don't rebuild what Playwright provides | v0.5 | [TECH_STACK](TECH_STACK.md) |
| D12 | ~~Claude API at runtime~~ → **Ollama local models at runtime; Claude (Claude Code) for building only** | Free, local, private | v0.5 | [LOCAL_SETUP](LOCAL_SETUP.md) |
| D13 | Everything free and local on one laptop | Project constraint | v0.5 | [LOCAL_SETUP](LOCAL_SETUP.md) |
| D14 | Model calls through one OpenAI-compatible llm client (`langfuse.openai` → Ollama `/v1`) | Tracing for free; provider swap is config | v0.5 | [OBSERVABILITY](OBSERVABILITY.md) |
| D15 | Model tiers: small ~4B (GPU), large ~7–8B (offload), vision optional, embed | Fits 4 GB VRAM | v0.5 | [LOCAL_SETUP](LOCAL_SETUP.md) |
| D16 | Python for the brain, TypeScript for the spec runner; JSON files between them | Best of both Playwright and LangGraph ecosystems | v0.5 | [ARCHITECTURE](ARCHITECTURE.md) |
| D17 | Evidence in a local folder; graph stores paths | Simplest on one machine | v0.5 | [TECH_STACK](TECH_STACK.md) |
| D18 | Claims table (`mem_claim`) + `mem_fact` view; edges carry full provenance | Enforces "human beats model"; audit trail | v0.5 | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D19 | Compute budget = model calls + model wall-clock per run | Money isn't the constraint locally | v0.5 | [COST_STRATEGY](COST_STRATEGY.md) |
| D20 | Confidence from sample agreement + rules signal, not model self-report | Small-model self-confidence is uncalibrated | v0.5 | [AGENT_RUNTIME](AGENT_RUNTIME.md) |
| D21 | Seeded-bug benchmark gates every prompt/model/threshold change | Ground truth from day one | v0.5 | [EVALUATION](EVALUATION.md) |
| D22 | Seeded DB restored before each run; synthetic user per test | Results and flake signals must mean something | v0.5 | [LOCAL_SETUP](LOCAL_SETUP.md) |
| D23 | Local report + desktop notification; Jira/Slack later | No external services | v0.5 | [COMPONENTS](COMPONENTS.md) |
| D24 | Review queue as CLI over interrupted graphs + `review_item` table | Simplest UI that works | v0.5 | [COMPONENTS](COMPONENTS.md) |
| D25 | MVP ingest: locally running web app URL + its repo | Narrow scope | v0.5 | [OVERVIEW](OVERVIEW.md) |
| D26 | Test impact starts from a static route → file map; runtime coverage refines it | Per-test runtime coverage is hard (Chromium-only, source maps, backend contexts) | v0.5 | [MEMORY_GRAPH](MEMORY_GRAPH.md) |
| D27 | Build order: phase 0 (infra + bench), rules-only analyzer before generation | Value early; baseline for model features | v0.5 | [ROADMAP](ROADMAP.md) |

## Open questions

| # | Question | Status / notes |
|---|---|---|
| Q1 | ~~Temporal from day one, or Redis first?~~ | **Closed (D5):** neither — pipeline runner + Playwright Test. |
| Q2 | Which models per tier? | **Partly closed (D15):** tiers and candidates set; final picks by benchmark. |
| Q3 | ~~Embedding model~~ | **Closed:** local via Ollama; candidate `nomic-embed-text` (768-d). Benchmark may change it. |
| Q4 | Natural keys for `Flow`, `Component`, `Element` | Open. Others proposed in [MEMORY_GRAPH](MEMORY_GRAPH.md#natural-keys-proposed). |
| Q5 | Confidence thresholds | **Process closed (D21):** calibrated on the benchmark. Values TBD. |
| Q6 | Per-run budget values | Units decided (D19); numbers TBD from the benchmark. |
| Q7 | ~~Core service language~~ | **Closed (D16).** |
| Q8 | ~~Ingest inputs for MVP~~ | **Closed (D25).** |
| Q9 | ~~Review queue UI~~ | **Closed (D24)** for now; web UI later. |
| Q10 | ~~Test draft lifecycle~~ | **Closed:** `status` on `TestCase`: draft → approved → quarantined → retired. |
| Q11 | Multi-tenancy | `project` column added now; full isolation later. |
| Q12 | Which target app for the benchmark? | Candidate: a RealWorld ("Conduit") implementation. *(new)* |
| Q13 | Does structured output via Ollama's OpenAI-compatible endpoint work with `langfuse.openai` for our schemas? | Verify in phase 3 spike; fallback is native Ollama client + manual generation tracing. *(new)* |
| Q14 | Backend coverage for `touches` | Static map first; how/if to add per-test backend coverage later. *(new)* |
| Q15 | Crawler: build our own state-graph crawler or adapt an existing tool? | Open. *(new)* |
| Q16 | Sample count for agreement (3?) and whether to vary temperature or prompts | Calibrate on benchmark. *(new)* |

## Gaps found in the v0.4 brief

| # | Observation | Resolution |
|---|---|---|
| G1 | Edges had no provenance beyond `source` | **Resolved (D18):** `confidence`, `trace_id`, `stale`, `updated_at` on `mem_edge`. |
| G2 | No `Commit → SourceFile` edge | **Resolved:** `Commit —changes→ SourceFile`. |
| G3 | Root-cause suggestion and regression clustering are "later" but cheap as graph queries | **Open:** reconsider promoting once phase 5 is done. |
| G4 | A stale human-sourced hit could short-circuit | **Resolved (D10):** memory node requires fresh human claims. |
| G5 | Self-healing risk vs NL-at-runtime tests | **Resolved (D2):** JSON specs; approved specs never self-heal. |
| G6 | No agent wrote `Component`/`Element` | **Resolved:** Planner writes them (parsing + aria snapshots). |
| G7 | Review queue not in the system diagram | **Resolved:** in the v0.5 diagram. |
| G8 | One Executor box despite two modes | **Resolved:** documented as two modes in [COMPONENTS](COMPONENTS.md); diagram labels the spec mode. |
| G9 | No app state reset strategy | **Resolved (D22).** |
| G10 | No ground truth for accuracy before human reviews exist | **Resolved (D21).** |
