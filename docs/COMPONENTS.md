# Components

> Source: `testomation.html` §04, with read/write detail from §06 (brief v0.5)

Each component lists **what it does**, **what it reads from memory**, **what it writes**,
and **where a model is involved**.

---

## Planner agent

**Job:** turn the app into a flow graph.

Reads routes, components, API schema, or a live crawl to build a map of user flows —
e.g. `signup → verify email → onboarding`, `add to cart → checkout → payment failure`.

- **Deterministic part:** route/sitemap/OpenAPI parsing, a state-graph crawler, Playwright
  aria snapshots, import-graph analysis.
- **Model part (small tier):** naming flows, ranking what matters, inferring business rules a
  crawler can't see ("checkout should fail without an email").
- **Reads:** existing flows, pages with no covering test, bug-prone components.
- **Writes:** `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint` nodes.
- **Change-aware:** only re-plans areas a diff touched.
- **Runtime:** LangGraph — crawl → parse → rank → go back for detail on high-value areas.

---

## Test generation agent — *changed in v0.5*

**Job:** convert a flow into a **JSON test spec**.

v0.4 left the test format open (scripted code vs natural language at runtime vs hybrid).
v0.5 settles it:

| Decision | Why |
|---|---|
| **Spec, not code** | Model fills a JSON schema; Ollama constrains decoding to it, so small models can't emit invalid tests |
| **Deterministic execution** | One spec runner executes every spec — determinism of scripted tests, no generated code on the host |
| **Agents for exploration only** | Live unscripted bug hunting is a separate executor mode |

- **Before generating:** pulls targets that worked before and similar specs from memory as templates.
- **No-model path:** common patterns (login, form submit, CRUD) come from spec templates.
- **Model path (large tier):** novel flows → spec → run → read error → repair, capped at 3.
- **Repair rules:** may change targets, add waits/steps; changing or removing an `expect`
  needs review (the failure might be a real bug).
- **Reads:** working targets, similar specs, test data that passed a form's validation.
- **Writes:** `TestCase` (spec + `status: draft`) linked to `Flow` (`covers`) and
  `Requirement` (`justified_by`).
- **Runtime:** plain code in phase 3; LangGraph from phase 5.

Full format → [TEST_SPEC.md](TEST_SPEC.md)

---

## Executor — *changed in v0.5*

**Job:** actually drive the browser.

| Mode | How | Use for |
|---|---|---|
| **Playwright Test + spec runner** | Runs approved specs with workers and retries | Regression — fast, repeatable |
| **Exploratory agent loop** | Aria snapshot → local model picks next action → execute → repeat, invariants checked on every state; vision optional | Finding bugs no spec looked for |

- **Evidence comes from Playwright itself:** trace file (screenshots, DOM snapshots,
  console, network), failure screenshots and video, axe results, Chromium JS coverage per
  test, aria snapshot on failure → `data/evidence/<run>/`.
- **Coverage per test** → `touches` edges (refines the static route → file map).
- **Reads:** stored auth state (`storageState`), endpoints to mock (`page.route` / HAR).
- **Writes:** `Run`, `Evidence` paths, `touches` edges.
- **Runtime:** spec mode is plain code; exploratory mode is a LangGraph loop that stops on
  budget exhausted or no new states.
- **Workers:** 2 while a model is loaded; more for stages that don't call a model.

---

## Analyzer agent

**Job:** decide what's actually a bug.

Reasons over the whole **evidence bundle**. Signal sources: failed assertions, console
exceptions, 4xx/5xx responses, visual regressions, dead-end navigation, accessibility
violations.

- **Rules engine first:** known noise signatures, status codes, axe-core, screenshot diffs,
  flake history (runs under heavy machine load excluded).
- **Model (small tier) only** for failures nothing else could classify — sampled **3 times**;
  **agreement** sets confidence, not the model's self-report.
- **Reads:** noise signatures, past bugs on the same component, recent commits touching it.
- **Writes:** `Bug`, `NoiseSignature`, verdict claims, dedup links.
- **Runtime:** **the first LangGraph graph built.** See [AGENT_RUNTIME.md](AGENT_RUNTIME.md).

---

## Reporter

**Job:** close the loop with humans.

- Writes `data/reports/<run>/report.html` (+ Markdown): confirmed bugs, repro steps (spec
  steps), links to traces and screenshots, next to Playwright's HTML report.
- Sends a desktop notification when a run finishes or a bug is confirmed.
- GitHub Issues / Jira / Slack come later.
- **Reads:** affected requirements, owning module.
- **Writes:** report paths (ticket IDs later) onto `Bug` nodes.
- **Runtime:** plain function with templates. Model only for an optional summary.

---

## Review queue — *new in v0.5*

**Job:** hold uncertain decisions for a human.

- An interrupted LangGraph thread **is** a review item. A small `review_item` table
  (thread id, kind, node id, status, created_at) lists them, since checkpoints aren't built
  for listing.
- `testomation review` shows each item with its evidence, opens the trace with
  `npx playwright show-trace`, and resumes the graph with `Command(resume=decision)`.
- `testomation approve` promotes draft specs.
- **Writes:** human claims, `HumanDecision` nodes, Langfuse scores.
- Local web UI later.

---

## Pipeline runner — *replaces the v0.4 orchestrator*

**Job:** keep everything coordinated on one machine.

- `testomation run` executes a fixed sequence of stages (see [AGENT_RUNTIME.md](AGENT_RUNTIME.md)).
- Records each stage's state in Postgres; a crashed run resumes at the last completed stage.
  Stages are idempotent.
- Enforces the **per-run compute budget** (model calls + model wall-clock time).
- Uses the memory graph to decide which specs a diff needs.
- Groups model work by tier to avoid model swapping on the GPU.
- Fan-out and retries → Playwright Test. Reasoning inside agents → LangGraph.
- Temporal returns only if Testomation spreads across machines.

---

## Agent runtime (LangGraph)

Runs the decision loop inside each reasoning agent: plain-Python nodes for memory and rules,
one node that calls a local model, conditional edges on confidence, and a pause point for
human review. → [AGENT_RUNTIME.md](AGENT_RUNTIME.md)

## Memory graph

Not an agent — a store. Holds relationships between pages, flows, specs, bugs, commits and
human decisions, plus the claims each source made about them. → [MEMORY_GRAPH.md](MEMORY_GRAPH.md)

## Observability (Langfuse)

Self-hosted. Wraps each agent job in a trace. Model calls → generations (tokens, latency).
Deterministic steps → spans, so skipped model calls are visible too. → [OBSERVABILITY.md](OBSERVABILITY.md)

## llm client

The only code that talks to Ollama. Selects model by tier, requests structured output, and
is traced via `langfuse.openai`. → [OBSERVABILITY.md](OBSERVABILITY.md), [LOCAL_SETUP.md](LOCAL_SETUP.md)

---

## Summary: memory reads & writes per component

| Component | Reads before acting | Writes after |
|---|---|---|
| Planner | Existing flows, uncovered pages, bug-prone components | `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint` |
| Test gen | Working targets, similar specs, valid test data | `TestCase` (spec, draft) → `Flow`, `Requirement` |
| Executor | Auth state, endpoints to mock | `Run`, `Evidence`, `touches` |
| Analyzer | Noise signatures, past bugs on component, recent commits | `Bug`, `NoiseSignature`, verdict claims, dedup links |
| Reporter | Affected requirements, owning module | Report paths on `Bug` |
| Pipeline runner | Commit → `changes` → `touches` → affected specs | `Commit`, stale flags, run/stage state |
| Review queue | Low-confidence claims | Human claims, `HumanDecision` |
