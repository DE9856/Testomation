# Design Roadmap

> Source: `index.html` §15 (brief v0.6)

[ROADMAP.md](ROADMAP.md) says **what gets built** in which phase. This doc says **what has to
be designed and decided** before each phase starts, what each design step produces, and how
you know it's done.

The rule: **design one step ahead of the build, not the whole thing up front.** Steps 1–3
are done before any product code is written. After that, each step is finished just before
its phase starts, and later steps stay rough until then.

## How to make design decisions here

| Rule | In practice |
|---|---|
| **Measure before deciding** | Anything that depends on model quality (tiers, thresholds, budget, prompts) is decided by the spike or the benchmark, not by argument |
| **Freeze contracts, not internals** | The spec schema, file formats, table DDL and the llm client interface are versioned and changed deliberately. Code behind them changes freely |
| **Write it down in order** | `DECISIONS.md` first, then every doc that references it, then `index.html` (bump the version) |
| **Unsure → open question** | A proposal that isn't settled goes under "Open questions" in `DECISIONS.md`, with the step that will close it |
| **Every step has an exit gate** | A step is done when its gate passes, not when the doc looks complete |

## The steps at a glance

| Step | Design focus | Before | Closes | Exit gate |
|---|---|---|---|---|
| 1 | Feasibility spike | everything | Q13, Q22; informs Q2 | Spike report with numbers for every question |
| 2 | Contracts | Phase 0–1 | Q4 (proposed) | Example specs validate in Python and TypeScript; DDL applies to a fresh Postgres |
| 3 | Benchmark | Phase 0 | Q12 | Stable scores across 3 runs on clean and bugged variants |
| 4 | Execution & ingest | Phase 1 | Q24 | Spec-runner and imported results land as `result` rows; crashed run resumes |
| 5 | Rules-only analyzer | Phase 2 | — | Baseline recall / false positives on both benchmark tiers |
| 6 | Generation | Phase 3 | Q2, Q13 (Langfuse wiring) | Spec success rate measured; `large` tier kept or dropped |
| 7 | Planner & freshness | Phase 4 | Q4, Q15, Q17, Q18, Q21, Q23 | Second-run memory hit rate measured; a one-file change re-plans only affected pages |
| 8 | Model in the loop | Phase 5 | Q5, Q6, Q19 | Thresholds fitted on the benchmark; held-out recall within the run-to-run range |
| 9 | Exploration | Phase 6 | Q25 | Finds a seeded bug the approved specs missed, within budget, with no off-origin navigation |

```
 Step 1 spike ──► Step 2 contracts ──► Step 3 benchmark ──►  (design stage ends: build starts)
                                                              │
     Step 4 ──► Step 5 ──► Step 6 ──► Step 7 ──► Step 8 ──► Step 9
     phase 1    phase 2    phase 3    phase 4    phase 5    phase 6
```

---

## Step 1 — Feasibility spike

**Goal:** find out whether local models on this laptop are good enough before building any
infrastructure. It's the riskiest assumption in the project.

**Setup (throwaway):** Conduit in a container, a minimal spec runner (one TypeScript file),
Ollama, a Python script. No Postgres, no Langfuse, no LangGraph, no memory graph. A handful
of planted bugs.

**Questions and proposed targets (Q22):**

| Question | How | Proposed target |
|---|---|---|
| Can the small model write usable specs? | 10 described Conduit flows → spec under the draft schema; ≤ 3 batched repair rounds | ≥ 7 of 10 pass on the clean app |
| Does the large tier earn its place? | Same 10 flows on the large tier | Keep it only if ≥ 2 more pass, or repairs halve |
| Can the small model triage? | ~20 captured failures (planted bugs + noise), one call each, label probability from logprobs | Beats the "everything is a bug" baseline, and right answers get higher probabilities than wrong ones |
| Does the toolchain behave? | Structured output with the spec schema's discriminated union; logprobs through `/v1` and `langfuse.openai` (Q13) | Works, or the fallback is chosen |
| Does it fit? | Peak RAM and swap with model + 2 workers + Conduit; tokens/s per tier | No swapping; numbers recorded |

**Produce:** `docs/SPIKE_RESULTS.md` with the numbers, the model picks, and any fallbacks
chosen. Spike code stays in `spike/` and is never imported by the product.

**Exit gate:** every question has a number. If the small model misses its targets, stop and
narrow scope before building (e.g. generation from templates only, with the model limited to
planning and triage). Moving to hosted models would change the ground rules, so it needs an
explicit decision.

**Don't:** build the pipeline runner, the memory schema or the CLI.

---

## Step 2 — Contracts

**Goal:** lock the interfaces between parts so each part can be built and tested on its own.

| Contract | Design work | Produces |
|---|---|---|
| Spec schema v1 | Step vocabulary, targets, references, `helper` steps, origin rule (D31–D33) | `schemas/test-spec.schema.json`, `schemas/examples/` (valid + invalid), generated Pydantic + TS types |
| Result format | What Python reads from the Playwright JSON reporter; evidence layout `data/evidence/<run>/<test>/`; error-signature normalisation rules (versioned) | A short format note in `schemas/`, plus fixtures |
| Memory DDL v1 | Tables from [MEMORY_GRAPH.md](MEMORY_GRAPH.md); proposed natural keys for `Flow` / `Component` / `Element` (Q4) | `deploy/sql/001_memory.sql` |
| llm client interface | `complete(tier, prompt_id, input, schema) → value, label_probs, usage`; prompts as versioned files | `src/testomation/llm/` interface + a fake for tests |
| Trace attributes | Run/session id, agent, tier, `memory_hit` — the same names in the OTel file and in Langfuse later | A table in [OBSERVABILITY.md](OBSERVABILITY.md) |
| Helper registry | Helper file shape (`name`, `args` schema, `run`) and how names reach the schema enum | `runner/helpers/README.md` |

**Exit gate:** both languages validate every example spec (and reject the invalid ones); the
DDL applies to a fresh Postgres; one hand-written spec runs end-to-end through the minimal
runner.

**Don't:** design agent internals yet.

---

## Step 3 — Benchmark

**Goal:** ground truth before the first real feature, so every later step can be measured.

**Design work:**

- Pick the target app (Q12): a Conduit implementation with a stable seed and fast
  template-database reset.
- Bug catalogue format — `bench/bugs/<id>.yaml`: id, category, toggle (env flag or patch),
  expected report (page, signal type, signature hint), `held_out`.
- A hand-written **reference spec suite** — used to filter mutants (only the ones it kills
  count) and to score phases 0–2.
- Replay bundle format — `bench/replay/<bug-id>/`: evidence folder + `result` JSON +
  expected label.
- Scoring: recall, false positives, noise precision, review rate, spec success, compute —
  each as mean and min–max over 3 runs.

**Exit gate:** `testomation bench` scores the reference suite on the clean and bugged
variants with ranges no wider than ±1 bug across 3 runs, and `--replay` runs in minutes.

**The design stage ends here.** From now on, design runs one step ahead of the build.

---

## Step 4 — Execution and ingest (before phase 1)

**Design work:** spec-runner fixtures (axe after navigation, aria snapshot on failure,
Chromium coverage, origin guard); evidence retention (`retain-on-failure`); the importer for
external Playwright reports, including how a failure maps to a step without a spec (Q24);
pipeline stage state and resumption; machine load recorded per run; OpenTelemetry file
traces.

**Exit gate:** a hand-written spec suite and one external Playwright project both produce
`result` rows with evidence; killing a run mid-stage and rerunning resumes at the last
completed stage.

---

## Step 5 — Rules-only analyzer (before phase 2)

**Design work:** the rule catalogue (status codes, console allowlist, axe impact levels,
screenshot-diff thresholds, flake-history window), each rule with an id and a fixed
confidence; noise signature kinds (`signature`, `origin`, `pattern`); dedup by signature
hash; the report template.

**Exit gate:** baseline recall and false-positive numbers on both benchmark tiers, recorded
as the bar every model feature must beat.

---

## Step 6 — Generation (before phase 3)

**Design work:** prompts (versioned files); spec templates for login / form / CRUD; the
batched repair-round state (which drafts are in which round); `testomation approve`
(writes `HumanDecision`, sets status, confirms the requirement); inferring requirements
(D34). Bring up Langfuse and check that the existing spans arrive (Q13).

**Exit gate:** spec success rate measured on the full benchmark; the `large` tier kept or
dropped on the numbers (D15).

---

## Step 7 — Planner and memory freshness (before phase 4)

**Design work:**

- Crawler: build or adapt (Q15).
- Natural keys for `Flow`, `Component`, `Element` (Q4, confirming step 2's proposal).
- Aria-snapshot normalisation (Q17).
- Basis policy per claim kind, and the list of kinds allowed an empty basis (Q18).
- Whether the planner's detail pass needs a loop (Q23).
- Whether the plan is shown to humans as Markdown before generation (Q21).

**Exit gate:** on an unchanged app, the second run's planning lookups are mostly answered by
memory (hit rate measured); changing one page's source re-plans only the pages whose basis
changed.

---

## Step 8 — Model in the loop (before phase 5)

**Design work:** the neighbour vote (`k`, minimum similarity, which labels count); reading the
label probability from logprobs (verdict enum with distinct first tokens); how the three
signals combine and are calibrated (Q19); gate values (Q5); budget values (Q6); the
`testomation review` flow for each `review_item` kind.

**Exit gate:** thresholds fitted on the benchmark; held-out recall within the run-to-run
range of tuned recall; review-queue rate tracked next to model calls.

---

## Step 9 — Exploration (before phase 6)

**Design work:** the LangGraph loop (state, stop conditions, checkpoints); the invariant list;
the novelty measure (new normalised aria hashes); actions limited to the spec step
vocabulary so findings replay as draft specs; the Python ↔ TypeScript bridge (Q25).

**Exit gate:** within its budget, exploration finds at least one seeded bug the approved
specs missed, and makes no off-origin navigation.

---

## Decision calendar

| Open question | Closed in |
|---|---|
| Q13 Structured output, logprobs through the client | Step 1 (Langfuse wiring: step 6) |
| Q22 Spike exit targets | Before step 1 starts |
| Q2 Models per tier | Step 1 (proposal), step 6 (final) |
| Q4 Natural keys | Step 2 (proposal), step 7 (final) |
| Q12 Benchmark target app | Step 3 |
| Q24 Imported-suite failure mapping | Step 4 |
| Q15, Q17, Q18, Q21, Q23 Planner and freshness | Step 7 |
| Q5, Q6, Q19 Thresholds, budget, score combination | Step 8 |
| Q25 Exploration bridge | Step 9 |
| Q11, Q14, Q20 Multi-tenancy, backend coverage, test selection | Later |
