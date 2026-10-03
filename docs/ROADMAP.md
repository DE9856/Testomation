# Build Order

> Source: `testomation.html` §14 (brief v0.5)

Seven phases plus "later". Each leaves something usable and lays groundwork for the next.

| Phase | Name | Model? | LangGraph? | Memory milestone |
|---|---|---|---|---|
| 0 | Set the stage | No | No | — (benchmark + infra) |
| 1 | Prove the plumbing | No | No | Schema (nodes, edges, claims); `TestCase`, `Run`, `Evidence`, static `touches` |
| 2 | Tell bugs from noise — rules only | No | No | Rule claims, `Bug`, `NoiseSignature` |
| 3 | Generate specs from plain English | Large tier | No (plain repair loop) | `TestCase` drafts → `covers` → `Flow` |
| 4 | Plan the coverage | Small tier | Planner graph | `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint` |
| 5 | Put the model in the loop | Small tier | **Analyzer graph (first-class)** | LLM + human claims, `HumanDecision` |
| 6 | Go exploratory | Small/large, vision optional | Exploration loop | States from crawling |
| Later | Platformize | — | — | Dashboards from graph + Langfuse |

> Change from v0.4: the analyzer's **rules-only** half moves up to phase 2 (it's useful on
> hand-written specs and sets the benchmark baseline); a new phase 0 sets up infra and the
> benchmark first.

---

## Phase 0 — Set the stage

- `deploy/compose.yaml`: Postgres + pgvector, Langfuse stack.
- Native Ollama with candidate models pulled; `OLLAMA_MAX_LOADED_MODELS=1`.
- Target app in containers with a seeded database and fast reset.
- Seeded-bug catalogue with toggles; `testomation bench` scores a **hand-written** spec suite.

## Phase 1 — Prove the plumbing

- Spec JSON Schema + the Playwright **spec runner** (TypeScript), running hand-written specs.
- Evidence captured into `data/evidence/<run>/`.
- Memory schema created now (`mem_node`, `mem_edge`, `mem_claim`, `mem_fact`): specs, runs and
  evidence paths are the first nodes; a static route → file map gives the first `touches`.
- Langfuse tracing of pipeline stages (spans) from day one.
- **No model calls yet.**

## Phase 2 — Tell bugs from noise, rules only

- Analyzer's deterministic half: assertions, status codes, console allowlist, axe, screenshot
  diffs, flake history, dedup by error hash.
- Writes rule claims, `Bug`, `NoiseSignature`; local report + desktop notification.
- Benchmark scores here are the **baseline** every model-based feature has to beat.

## Phase 3 — Generate specs from plain English

- Test gen with the **large** local model: described flow → JSON spec under constrained decoding.
- Spike first: confirm structured output + Langfuse tracing via the OpenAI-compatible endpoint.
- Capped repair loop (plain code) that can't touch assertions.
- Drafts promoted with `testomation approve`; specs land in memory linked to their flows.
- Benchmark: spec success rate.

## Phase 4 — Plan the coverage

- Planner = crawler + parser + aria snapshots first; **small** model names and ranks flows.
- Populates `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint`.
- Re-plans only what a diff touches.

## Phase 5 — Put the model in the loop

- Analyzer becomes the first LangGraph graph: memory → rules → small model ×3 → gate →
  `interrupt()`.
- `testomation review` resumes paused graphs; decisions → human claims + Langfuse scores.
- Thresholds, sample count and budget calibrated on the benchmark.
- Move the test-gen repair loop onto LangGraph once the pattern is proven.

## Phase 6 — Go exploratory

- Fuzzing + coverage-guided crawling with invariant checks first.
- Text-based exploratory agent over aria snapshots (LangGraph loop; stops on budget or no new
  states); optional small vision model.
- Flaky-test quarantine and visual baselines.

## Later — Platformize

CI/CD plugins, dashboard and trends (from the memory graph and Langfuse), GitHub Issues /
Jira / Slack, production synthetic monitoring, RBAC, multi-project UI, plugin architecture,
WebKit via container, spec exporter, local web UI for review — and Temporal, if Testomation
ever outgrows one machine.

---

## Dependency view

```
Phase 0  infra + target app + seeded bugs + bench
   │
Phase 1  spec schema + spec runner + evidence + memory schema + tracing
   │
   ├──► Phase 2  rules-only analyzer  (baseline)
   │       │
   │       └──► Phase 5  model-in-the-loop analyzer + review queue  (first LangGraph graph)
   │                │
   │                └──► Phase 6  exploration  (reuses analyzer, invariants, budget)
   │
   └──► Phase 3  spec generation (large model)
           │
           └──► Phase 4  planner (feeds generation with flows)
```
