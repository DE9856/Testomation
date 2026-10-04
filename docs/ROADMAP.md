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
| 3 | Assisted authoring | Small (suggests assertions, names flows) | No | `TestCase` drafts (human-approved) → `covers` → `Flow`; `Requirement` |
| 4 | Plan the coverage | Small | No | `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint`; aria basis hashes |
| 5 | Put the model in the loop | Small + embed | No | LLM, `knn` and human claims; `HumanDecision` |
| 6 | Go exploratory — **research, gated (D43)** | Small, vision optional | **Exploration loop (the only graph)** | States from crawling |
| Later | Platformize | — | — | Dashboards from graph + Langfuse |

> Changes in v0.7 (after the spike): phase 3 becomes **assisted authoring** (D42) and phase 6 is
> **gated research** (D43). The spike itself is done ([SPIKE_RESULTS.md](SPIKE_RESULTS.md)).
>
> Changes from v0.5: a **spike** comes first; Langfuse waits for phase 3; the analyzer stays
> plain Python in phase 5; test gen uses the small model by default; the importer for
> existing Playwright suites lands with the rules-only analyzer; exploration is the only
> LangGraph graph.

---

## Spike — Prove the models — *done*

Results in [SPIKE_RESULTS.md](SPIKE_RESULTS.md): `qwen3:4b` fits fully on GPU; structured
output and logprobs work with a decoder-friendly schema; **triage meets its target; autonomous
spec generation does not** (best 1/8 seeded bugs caught vs 8/8 hand-written). The spike also
produced seeded-bug toggles, a reference suite and a working runner — the start of phase 0–1.

## Phase 0 — Set the stage — *mostly done*

> Done: Postgres + pgvector compose, Ollama with the spike's model, Conduit with seed + ~2 s reset,
> 8 seeded bugs + noise + flaky toggles, reference suite, `testomation bench` (full and replay
> tiers) with a 3-run baseline. Left: Stryker mutants with the detectable-mutant filter; more bugs
> toward ~20.


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

## Phase 3 — Assisted authoring (D42)

- Bring up the self-hosted **Langfuse** stack; existing stage spans flow into it.
- **Actions from templates and recordings, not from the model:** templates for login, sign-up,
  form submit, CRUD and "as <user>" preconditions; a recorder for the rest (Q31).
- **Assertions suggested from a menu:** the runner records the page before and after the actions;
  candidate assertions are derived deterministically from the difference (generated values become
  `$var` automatically); the small model **picks** candidates that match the flow's expectation.
- **Every draft is human-approved** with `testomation approve`, which also confirms requirements.
- Benchmark: **spec kill rate** — drafts must pass on the clean app and fail with their flow's
  seeded bug. Pass rate alone is not a target (spike, Q29).

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

## Phase 6 — Go exploratory — *research, gated (D43)*

Starts only when a local model reaches ≥ 5/8 on the generation kill-rate benchmark, because the
exploratory agent needs the action planning that failed in the spike. Until then, the cheap
parts can still be built: fuzzing and coverage-guided crawling with invariant checks (no model),
flaky-test quarantine and visual baselines. The LangGraph exploration loop waits for the gate.

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
   │                └──► Phase 6  exploration  (research, gated — D43)
   │
   └──► Phase 3  assisted authoring (templates, assertion menu, human approval) + Langfuse
           │
           └──► Phase 4  planner (feeds generation with flows)
```
