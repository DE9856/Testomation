# Architecture

> Source: `testomation.html` §03, plus connections drawn from §04–§10 (brief v0.5)

This doc is about **how everything connects**. For what each piece does internally, see
[COMPONENTS.md](COMPONENTS.md).

## 1. System diagram

Five agents and the review queue sit behind a pipeline runner. They share one memory graph,
which points out to the two places heavy data lives: raw evidence in a local folder, and
model reasoning in Langfuse. Everything runs on one laptop.

```
                 ┌───────────────────────────────────────┐
                 │            PIPELINE RUNNER            │
                 │     testomation run · stage state     │
                 │         per-run compute budget        │
                 └───────────────────┬───────────────────┘
                                     │
      ┌────────────┬────────────┬────┴───────┬────────────┬────────────┐
 ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐
 │ Planner  │ │ Test gen │ │ Executor │ │ Analyzer │ │ Reporter │ │  Review  │
 │  agent   │ │  → spec  │ │Playwright│ │  agent   │ │local html│ │queue CLI │
 │LangGraph │ │LangGraph │ │   Test   │ │LangGraph │ │  plain   │ │ resumes  │
 └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
      │            │            │            │            │            │
      └────────────┴────────────┴────┬───────┴────────────┴────────────┘
                                     │ read first · write back
               ┌─────────────────────▼─────────────────────┐
               │                MEMORY GRAPH               │
               │   pages · flows · specs · bugs · claims   │
               │    noise signatures · commits · reviews   │
               │     run state · LangGraph checkpoints     │
               │            Postgres + pgvector            │
               └────────┬───────────────────────────┬──────┘
        evidence paths  │                           │ trace ids
           ┌────────────▼────────────┐  ┌───────────▼───────────┐
           │ Evidence (local folder) │  │ Langfuse (self-hosted)│
           │   Playwright traces ·   │  │   traces · tokens ·   │
           │   screenshots · video   │  │   scores · datasets   │
           └─────────────────────────┘  └───────────────────────┘
```

- Specs live **in the graph** on `TestCase` nodes; the executor runs them with **Playwright Test**.
- The **pipeline runner** is plain Python; agents that branch run as **LangGraph graphs**
  inside its stages.
- The **review queue** lists and resumes paused graphs.

## 2. The model path

```
 Planner  ──┐
 Test gen ──┼──► llm client ─────────► Ollama · localhost:11434
 Analyzer ──┘    OpenAI-compatible     small · large · embed models
                 via langfuse.openai
                        │
                        └──► Langfuse generation: model · tokens · latency · prompt version
```

One small client (`src/testomation/llm/`) wraps every model call. It picks the model by
**tier**, requests JSON-schema structured output, and is traced automatically. Swapping
Ollama for another OpenAI-compatible server later is a config change.

## 3. The layers

| Layer | Owner | Responsibility |
|---|---|---|
| **Jobs** (outer) | Pipeline runner + Playwright Test | Stage order, resumption, parallel test runs, retries, compute budget |
| **Decisions** (inner) | LangGraph | One agent's decision on one item: memory → rules → model → gate → human review |
| **Knowledge** (shared) | Postgres memory graph | Everything known about the app; read before every decision, written after |

Sidecars:

| Store / service | Holds | Linked from graph by |
|---|---|---|
| Evidence folder (`data/evidence/<run>/`) | Playwright traces, screenshots, video, axe results, coverage | `Evidence` nodes holding paths |
| Langfuse (self-hosted) | Traces, spans, generations, tokens/latency, prompt versions, scores, datasets | `trace_id` on nodes, edges, claims |
| Ollama (native) | Local models by tier | Called through the llm client only |

## 4. Two languages, one boundary

| Side | Language | Contains |
|---|---|---|
| Brain | Python | Pipeline runner, agents, LangGraph, memory, llm client, CLI |
| Hands | TypeScript | Playwright config, spec runner, fixtures (axe, coverage, aria snapshot on failure) |

They meet only through files:

```
Python ── writes ──► data/runs/<run>/specs/*.json ──► npx playwright test (spec runner)
Python ◄── reads ─── data/runs/<run>/results.json + data/evidence/<run>/…  ◄── Playwright
```

## 5. Connection map (who talks to whom)

| From | To | What flows | Direction |
|---|---|---|---|
| Pipeline runner | Memory graph | Commit → `changes` → files → `touches` → specs to run; stage state | read + write |
| Pipeline runner | Playwright Test | Spec list, worker count, retries (CLI invocation) | dispatch |
| Pipeline runner | Agents | Stage work (function calls / graph invocations) | dispatch |
| Pipeline runner | Langfuse | One span per stage; counts model calls/time against budget | write + read |
| Every agent | Memory graph | Lookups before acting; nodes/edges/claims with provenance after | read + write |
| Planner, Test gen, Analyzer | Ollama | Model calls via the llm client, by tier | call |
| llm client | Langfuse | One generation per model call | write |
| Planner | Target app / repo | Crawl, aria snapshots, route + import parsing | read |
| Test gen | Spec runner | Draft spec to run inside generate → run → repair | call |
| Spec runner | Browsers | Spec steps as Playwright actions | dispatch |
| Spec runner | Evidence folder | Trace, screenshots, video, axe, coverage, aria snapshot on failure | write |
| Executor (Python side) | Memory graph | `Run`, `Evidence` paths, `touches` edges | write |
| Analyzer | Evidence folder | Evidence bundle for a failure | read |
| Analyzer | Review queue | Low-confidence verdicts (`interrupt()` + `review_item` row) | pause |
| Review queue (CLI) | Analyzer graph | Human decision (`Command(resume=...)`) | resume |
| Review queue | Memory graph | Human claims, `HumanDecision` nodes | write |
| Review queue | Langfuse | Human verdict as a **score** | write |
| Reporter | `data/reports/<run>/` | HTML/Markdown report linking evidence | write |
| Reporter | Desktop | Notification | write |
| LangGraph | Postgres | Checkpoints (same DB as memory) | write |
| `testomation bench` | Target app, Langfuse | Toggles seeded bugs, runs pipeline, records dataset runs | control |

## 6. How a run flows end-to-end

```
testomation run --pr 412              pipeline runner · stage state in Postgres
 ├─ stage: invalidate + impact         plain code · memory-graph query
 ├─ stage: run affected specs          npx playwright test · workers=2 · retries=1
 ├─ stage: triage failures          →  Analyzer graph, one thread per failure
 ├─ stage: generate missing tests   →  Test-gen graph (spec → run → repair, capped)
 └─ stage: report                      plain code · local HTML / Markdown
```

1. **Trigger.** `testomation run` (for a PR, a local diff, or a full run). The runner opens a
   Langfuse session and records the run in Postgres.
2. **Reset.** The target app's seeded database is restored.
3. **Invalidate.** The commit's `changes` edges lead to files; dependents via `touches` and
   `renders` are marked `stale`.
4. **Impact analysis.** Changed files → `touches` → approved specs to rerun. No model.
5. **Execute.** Specs are written to the run folder; Playwright Test runs them with 2 workers.
   Results + evidence are ingested as `Run`, `Evidence`, `touches`.
6. **Triage.** Each failure gets an Analyzer graph thread: memory → rules → small model ×3
   (if budget left) → confidence gate → write a claim, or pause for review.
7. **Fill gaps.** Uncovered or diff-touched flows go to Planner and Test gen. New specs land as
   **drafts** for `testomation approve`.
8. **Report.** Confirmed bugs go into the local report with repro steps and trace links;
   desktop notification.
9. **Learn.** Review decisions become human claims and Langfuse scores; next run, memory
   answers those questions for free.

Model work is grouped by tier within a run (all small-model work, then all large-model work)
so the 4 GB GPU doesn't keep swapping models.

## 7. Where models sit (and don't)

```
                       uses LangGraph?   calls a model?
Planner                yes               small: naming/ranking flows, inferring business rules
Test gen               yes               large: novel flows → spec; repair (templates otherwise)
Executor (specs)       no                never
Executor (exploratory) yes               small/large text over aria snapshots; vision optional
Analyzer               yes (first)       small ×3: failures matching no known signature
Reporter               no                optional summary
Pipeline runner        no                never
```

## 8. Storage topology

One Postgres server (pgvector image), two databases:

| Database | Contents |
|---|---|
| `testomation` | Memory graph (`mem_node`, `mem_edge`, `mem_claim`, `mem_fact` view), run + stage state, `review_item`, LangGraph checkpoints |
| `langfuse` | Langfuse's own tables (its event data lives in its ClickHouse) |

Heavy blobs never go into Postgres — only paths.

## 9. Boundaries that must stay sharp

- **Runner/Playwright ↔ LangGraph.** Jobs, order, parallelism and retries outside; decisions
  for one item inside. If Temporal returns, it replaces the runner, not LangGraph.
- **LangGraph store ↔ memory graph.** Agents reach the Postgres memory graph through explicit
  lookup and write-back nodes, not LangGraph's key-value store.
- **Spec ↔ code.** Models produce specs; only the hand-written spec runner is code.
- **Spec execution ↔ exploration.** Two executor modes, never one agent.
- **Graph ↔ files ↔ traces.** The graph stores IDs and paths; evidence and reasoning live in
  their own systems.
- **Build-time Claude ↔ runtime Ollama.** Claude never appears in the product's dependencies.
