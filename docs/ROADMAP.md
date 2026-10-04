# Build Order

> Source: `index.html` §14 (brief v0.6)

A feasibility spike, then seven phases plus "later". Each leaves something usable and lays
groundwork for the next. What has to be **designed** before each phase is in
[DESIGN_ROADMAP.md](DESIGN_ROADMAP.md).

| Phase | Name | Model? | LangGraph? | Memory milestone |
|---|---|---|---|---|
| Spike | Prove the models | Small (+ large to compare) | No | — (throwaway) |
| 0 | Set the stage | No | No | — (benchmark + infra) |
| 1 | Prove the plumbing | No | No | Schema (nodes, typed tables, `result`, edges, claims, basis); `TestCase`, `Run`, static `touches` |
| 2 | Tell bugs from noise — rules only | No | No | Rule claims, `Bug`, `NoiseSignature` |
| 3 | Generate specs from plain English | Small (large only if it earns it) | No (batched rounds) | `TestCase` drafts → `covers` → `Flow`; inferred `Requirement` |
| 4 | Plan the coverage | Small | No | `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint`; aria basis hashes |
| 5 | Put the model in the loop | Small + embed | No | LLM, `knn` and human claims; `HumanDecision` |
| 6 | Go exploratory | Small, vision optional | **Exploration loop (the only graph)** | States from crawling |
| Later | Platformize | — | — | Dashboards from graph + Langfuse |

> Changes from v0.5: a **spike** comes first; Langfuse waits for phase 3; the analyzer stays
> plain Python in phase 5; test gen uses the small model by default; the importer for
> existing Playwright suites lands with the rules-only analyzer; exploration is the only
> LangGraph graph.

---

## Spike — Prove the models (1–2 weeks, throwaway)

- Conduit in a container, a minimal spec runner, Ollama and a script. **No** Postgres,
  Langfuse, LangGraph or memory.
- Measure: share of generated specs that pass on the clean app (small vs large tier),
  triage accuracy on ~20 captured failures with label probabilities, peak RAM / swap with a
  model and 2 workers, tokens/s per tier.
- Confirm the toolchain: structured output with the spec schema's discriminated union;
  logprobs through `/v1` and `langfuse.openai` (Q13).
- Output: `docs/SPIKE_RESULTS.md`. Spike code lives in `spike/` and is never imported.

## Phase 0 — Set the stage

- `deploy/compose.yaml`: Postgres + pgvector. (The Langfuse stack is added in phase 3.)
- Native Ollama with the model(s) the spike picked; `OLLAMA_MAX_LOADED_MODELS=1`.
- Target app in containers with a seeded database and fast reset.
- Seeded-bug catalogue with toggles; detectable-mutant filter; replay bundles recorded.
- `testomation bench` scores a **hand-written** spec suite, 3 runs, with ranges.

## Phase 1 — Prove the plumbing

- Spec JSON Schema (single source) with generated Pydantic + TS types and shared examples.
- The Playwright **spec runner** (TypeScript) with fixtures, the helper registry and the
  origin guard, running hand-written specs.
- Evidence captured into `data/evidence/<run>/`; results ingested as `result` rows. The same
  ingest reads external Playwright JSON reports (`testomation import`).
- Memory schema created now: `mem_node`, typed tables, `result`, `mem_edge`, `mem_claim`,
  `basis_state`, `review_item`, `mem_fact`. Specs and runs are the first nodes; a static
  route → file map gives the first `touches`; file hashes fill `basis_state`.
- OpenTelemetry spans for pipeline stages to `data/traces/<run>.jsonl` from day one.
- **No model calls yet.**

## Phase 2 — Tell bugs from noise, rules only

- Analyzer's deterministic half: assertions, status codes, console allowlist, axe, screenshot
  diffs, flake history, dedup by error hash.
- Works on spec-runner results **and** imported Playwright suites.
- Writes rule claims, `Bug`, `NoiseSignature`; local report + desktop notification.
- Benchmark scores here (both tiers) are the **baseline** every model-based feature has to beat.

## Phase 3 — Generate specs from plain English

- Bring up the self-hosted **Langfuse** stack; existing stage spans flow into it.
- Test gen with the **small** model: described flow → JSON spec under constrained decoding.
  Try the large tier on the full benchmark; keep it only if it earns its place.
- **Batched repair rounds** (≤ 3) with the model unloaded while drafts run; repairs can't
  touch assertions.
- Drafts promoted with `testomation approve`, which also confirms inferred requirements.
- Benchmark: spec success rate.

## Phase 4 — Plan the coverage

- Planner = crawler + parser + aria snapshots first; **small** model names and ranks flows
  and infers business rules.
- Populates `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint`, each with an aria basis.
- Re-plans only pages whose basis changed.

## Phase 5 — Put the model in the loop

- Analyzer cascade (plain Python): memory → rules → labelled neighbours → small model ×1 with
  logprobs → calibrated gate → `review_item`.
- `testomation review` decides items; decisions → human claims, `HumanDecision`, trace scores,
  new labelled neighbours.
- Gates, neighbour `k`/similarity, score combination and budget calibrated on the benchmark.

## Phase 6 — Go exploratory

- Fuzzing + coverage-guided crawling with invariant checks first.
- Text-based exploratory agent over aria snapshots — the **one LangGraph loop** (stops on
  budget or no new states; checkpointed); actions are spec steps; on-origin only; optional
  small vision model.
- Flaky-test quarantine and visual baselines.

## Later — Platformize

CI/CD plugins, dashboard and trends (from the memory graph and Langfuse), GitHub Issues /
Jira / Slack, production synthetic monitoring, RBAC, multi-project UI, plugin architecture,
WebKit via container, spec exporter, local web UI for review, test selection once the full
suite gets slow (Q20) — and Temporal, if Testomation ever outgrows one machine.

---

## Dependency view

```
Spike    models + toolchain + RAM, measured  (throwaway)
   │
Phase 0  infra + target app + seeded bugs + replay bundles + bench
   │
Phase 1  spec schema + spec runner + evidence + importer + memory schema + file traces
   │
   ├──► Phase 2  rules-only analyzer, also for imported suites  (baseline)
   │       │
   │       └──► Phase 5  model-in-the-loop analyzer + review queue
   │                │
   │                └──► Phase 6  exploration  (the one LangGraph loop)
   │
   └──► Phase 3  spec generation (small model) + Langfuse
           │
           └──► Phase 4  planner (feeds generation with flows)
```
