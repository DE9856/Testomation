# Architecture

> Source: `index.html` §03, plus connections drawn from §04–§10 (brief v0.6)

This doc is about **how everything connects**. For what each piece does internally, see
[COMPONENTS.md](COMPONENTS.md).

## 1. System diagram

Five agents and the review queue sit behind a pipeline runner. They share one memory graph,
which points out to the two places heavy data lives: raw evidence in a local folder, and
model reasoning in traces. Everything runs on one laptop.

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
 │  plain   │ │  plain   │ │+explore* │ │  plain   │ │  plain   │ │  async   │
 └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
      │            │            │            │            │            │
      └────────────┴────────────┴────┬───────┴────────────┴────────────┘
                                     │ read first · write back
               ┌─────────────────────▼─────────────────────┐
               │                MEMORY GRAPH               │
               │   pages · flows · specs · bugs · claims   │
               │   results · noise signatures · commits    │
               │    reviews · basis hashes · run state     │
               │    LangGraph checkpoints (exploration)    │
               │            Postgres + pgvector            │
               └────────┬───────────────────────────┬──────┘
        evidence paths  │                           │ trace ids
           ┌────────────▼────────────┐  ┌───────────▼───────────┐
           │ Evidence (local folder) │  │ Langfuse (self-hosted)│
           │   Playwright traces ·   │  │   traces · tokens ·   │
           │   screenshots · video   │  │   scores · datasets   │
           └─────────────────────────┘  └───────────────────────┘

 * the exploratory mode is the one LangGraph loop
```

- Specs live **in the graph** on `TestCase` nodes (`test_case` table); the executor runs them
  with **Playwright Test**.
- The **pipeline runner** and the agents are plain Python. The **exploration loop** is the
  only LangGraph graph.
- The **review queue** lists open `review_item` rows and applies decisions directly.
- Langfuse starts in **phase 3**. Until then, stage spans go to a local OpenTelemetry file
  (`data/traces/<run>.jsonl`), and trace IDs point there.

## 2. The model path

```
 Planner  ──┐
 Test gen ──┤
 Analyzer ──┼──► llm client ─────────► Ollama · localhost:11434
 Explorer ──┘    OpenAI-compatible     small (default) · large (optional) · embed
                 via langfuse.openai
                        │
                        └──► generation span: model · tokens · latency · prompt version
```

One small client (`src/testomation/llm/`) wraps every model call. It picks the model by
**tier**, requests JSON-schema structured output, returns the parsed value **plus the label
probability** (from logprobs) when the schema has a label, and is traced automatically.
Swapping Ollama for another OpenAI-compatible server later is a config change.

## 3. The layers

| Layer | Owner | Responsibility |
|---|---|---|
| **Jobs** (outer) | Pipeline runner + Playwright Test | Stage order, resumption, parallel test runs, retries, compute budget, loading and unloading the model |
| **Decisions** (inner) | Agent code (plain Python); LangGraph for the exploration loop | One decision on one item: memory → rules → neighbours → model → gate → review item |
| **Knowledge** (shared) | Postgres memory graph | Everything known about the app; read before every decision, written after |

Sidecars:

| Store / service | Holds | Linked from graph by |
|---|---|---|
| Evidence folder (`data/evidence/<run>/`) | Playwright traces, screenshots, video, axe results, coverage | `result.evidence_dir` |
| Traces: OpenTelemetry file (phases 0–2), Langfuse (from phase 3) | Traces, spans, generations, tokens/latency, prompt versions, scores, datasets | `trace_id` on nodes, edges, claims |
| Ollama (native) | Local models by tier | Called through the llm client only |

## 4. Two languages, one boundary

| Side | Language | Contains |
|---|---|---|
| Brain | Python | Pipeline runner, agents, exploration graph, memory, llm client, CLI |
| Hands | TypeScript | Playwright config, spec runner, helper registry, fixtures (axe, coverage, aria snapshot on failure, origin guard) |

They meet only through files:

```
Python ── writes ──► data/runs/<run>/specs/*.json ──► npx playwright test (spec runner)
Python ◄── reads ─── data/runs/<run>/results.json + data/evidence/<run>/…  ◄── Playwright
Python ◄── reads ─── any Playwright project's JSON report + traces          ◄── testomation import
```

**One schema, two languages:** `schemas/test-spec.schema.json` is the only definition of a
spec. Pydantic models and TypeScript types are generated from it, and the example specs in
`schemas/examples/` are validated by both sides in tests (D31).

## 5. Connection map (who talks to whom)

| From | To | What flows | Direction |
|---|---|---|---|
| Pipeline runner | Memory graph | File hashes into `basis_state`; changed files → `touches` / `renders` → flows and specs needing model work; stage state | read + write |
| Pipeline runner | Ollama | Unload the model (`keep_alive: 0`) before any stage that runs browsers | control |
| Pipeline runner | Playwright Test | All approved specs (or a round of drafts), worker count, retries (CLI invocation) | dispatch |
| Pipeline runner | Agents | Stage work (function calls) | dispatch |
| Pipeline runner | Traces | One span per stage; model calls/time counted against budget | write + read |
| Every agent | Memory graph | Lookups before acting; nodes/edges/claims with provenance and basis after | read + write |
| Planner, Test gen, Analyzer, Explorer | Ollama | Model calls via the llm client, by tier | call |
| llm client | Traces | One generation per model call | write |
| Planner | Target app / repo | Crawl, aria snapshots, route + import parsing | read |
| Spec runner | Browsers | Spec steps as Playwright actions, on the target origin only | dispatch |
| Spec runner | Evidence folder | Trace, screenshots, video, axe, coverage, aria snapshot on failure | write |
| Executor (Python side) | Memory graph | `Run`, `result` rows, `touches` edges, aria hashes | write |
| Importer (`testomation import`) | Memory graph | An external Playwright report → `Run` (trigger `import`) + `result` rows | write |
| Analyzer | Evidence folder | Evidence for a failure | read |
| Analyzer | Review queue | Low-confidence verdicts as `review_item` rows | write |
| Review queue (CLI) | Memory graph | Human claims, `HumanDecision` nodes, `apply_verdict()` | write |
| Review queue | Traces | Human verdict as a **score** | write |
| Reporter | `data/reports/<run>/` | HTML/Markdown report linking evidence | write |
| Reporter | Desktop | Notification | write |
| Explorer (LangGraph) | Postgres | Checkpoints (same DB as memory) | write |
| `testomation bench` | Target app, traces | Toggles seeded bugs, runs pipeline or replays evidence, records dataset runs | control |

## 6. How a run flows end-to-end

```
testomation run --pr 412              pipeline runner · stage state in Postgres
 ├─ stage: refresh basis + scope       plain code · git blob SHAs · memory-graph query
 ├─ stage: run approved specs          model unloaded · npx playwright test · retries=1
 ├─ stage: triage failures             plain code · memory → rules → neighbours → model
 ├─ stage: generate missing tests      plain code · ≤3 rounds: generate → unload → run → repair
 └─ stage: report                      plain code · local HTML / Markdown
```

1. **Trigger.** `testomation run` (for a PR, a local diff, or a full run). The runner opens a
   trace session and records the run in Postgres.
2. **Reset.** The target app's seeded database is restored.
3. **Refresh basis.** Current file hashes (git blob SHAs) go into `basis_state`. Claims whose
   basis no longer matches now read as stale. Nothing is rewritten.
4. **Scope model work.** Changed files → `touches` / `renders` → flows to re-plan and specs to
   regenerate. No model.
5. **Execute.** **Every approved spec** runs with the model unloaded. Results and evidence
   are ingested as `Run`, `result` rows and `touches`; visited pages update their aria hashes.
6. **Triage.** Each failure goes through the analyzer cascade: memory → rules → neighbours →
   small model (if budget left) → confidence gate → claim, or a `review_item` row.
7. **Fill gaps.** Planner and Test gen handle in-scope and uncovered flows. Drafts go through
   up to 3 batched rounds (generate → unload → run → repair) and land as **drafts** for
   `testomation approve`.
8. **Report.** Confirmed bugs go into the local report with repro steps and trace links;
   desktop notification.
9. **Learn.** Review decisions become human claims and trace scores, and new labelled
   neighbours. Next run, memory answers those questions for free.

Model work is grouped by tier within a run (embeddings, then small-model work, then any
large-model work), and the model is unloaded whenever browsers run, except during
exploration.

## 7. Where models sit (and don't)

```
                       uses LangGraph?   calls a model?
Planner                no                small: naming/ranking flows, inferring business rules
Test gen               no                small (large if the benchmark earns it): novel flows → spec; repair
Executor (specs)       no                never
Executor (exploratory) yes (only one)    small: next action over aria snapshots; vision optional
Analyzer               no                embed: neighbour vote · small ×1 with logprobs: unsettled failures
Reporter               no                optional summary
Pipeline runner        no                never
```

## 8. Storage topology

One Postgres server (pgvector image), two databases:

| Database | Contents |
|---|---|
| `testomation` | Memory graph (`mem_node`, typed tables, `result`, `mem_edge`, `mem_claim`, `basis_state`, `mem_fact` / `mem_edge_fact` views), run + stage state, `review_item`, exploration checkpoints |
| `langfuse` | From phase 3: Langfuse's own tables (its event data lives in its ClickHouse) |

Heavy blobs never go into Postgres — only paths.

## 9. Boundaries that must stay sharp

- **Jobs ↔ decisions ↔ loops.** Jobs, order, parallelism and retries in the runner and
  Playwright. Decisions in plain agent code. LangGraph only inside the exploration loop. If
  Temporal returns, it replaces the runner and nothing else.
- **LangGraph store ↔ memory graph.** The explorer reaches the Postgres memory graph through
  explicit lookup and write-back nodes, not LangGraph's key-value store.
- **Spec ↔ code.** Models produce specs; only the hand-written spec runner and helpers are
  code.
- **Spec execution ↔ exploration.** Two executor modes, never one agent.
- **Target origin ↔ the rest of the web.** Specs and exploration never leave the target
  app's origin (D32).
- **Graph ↔ files ↔ traces.** The graph stores IDs and paths; evidence and reasoning live in
  their own systems.
- **Build-time Claude ↔ runtime Ollama.** Claude never appears in the product's dependencies.
