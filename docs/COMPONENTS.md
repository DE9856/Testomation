# Components

> Source: `index.html` §04, with read/write detail from §06 (brief v0.6)

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
  crawler can't see ("checkout should fail without an email"). Inferred rules become
  `Requirement` nodes (source `llm`) that a human confirms at spec approval.
- **Reads:** existing flows, pages with no covering test, bug-prone components.
- **Writes:** `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint`, `Requirement` nodes, each
  with a basis (`aria:<route>` + route file).
- **Change-aware:** only re-plans pages whose basis changed.
- **Runtime:** plain code — crawl → parse → rank. If "go back for detail on high-value
  areas" turns into a real loop, revisit LangGraph (Q23).

---

## Test generation agent — *changed in v0.6*

**Job:** convert a flow into a **JSON test spec**.

| Decision | Why |
|---|---|
| **Spec, not code** | Model fills a JSON schema; Ollama constrains decoding to it, so small models can't emit invalid tests |
| **Deterministic execution** | One spec runner executes every spec — determinism of scripted tests, no generated code on the host |
| **Agents for exploration only** | Live unscripted bug hunting is a separate executor mode |

- **Before generating:** pulls targets that worked before and similar specs from memory as templates.
- **No-model path:** common patterns (login, form submit, CRUD) come from spec templates.
- **Model path (small tier; large only if the benchmark earns it):** novel flows → spec.
- **Batched repair rounds (≤ 3):** generate or repair all pending drafts → unload model →
  run all drafts → failures go back to the model with the failing step, error and aria
  snapshot. Still failing after round 3 → review queue.
- **Repair rules:** may change targets, add waits/steps; changing or removing an `expect`
  needs review (the failure might be a real bug).
- **Reads:** working targets, similar specs, test data that passed a form's validation,
  registered helper names.
- **Writes:** `TestCase` (spec + `status: draft`) linked to `Flow` (`covers`) and, when known,
  `Requirement` (`justified_by`).
- **Runtime:** plain code; the rounds are driven by the pipeline runner.

Full format → [TEST_SPEC.md](TEST_SPEC.md)

---

## Executor — *changed in v0.6*

**Job:** actually drive the browser.

| Mode | How | Use for |
|---|---|---|
| **Playwright Test + spec runner** | Runs every approved spec with workers and retries; no model loaded | Regression — fast, repeatable |
| **Exploratory agent loop** | Aria snapshot → local model picks the next spec step → execute → repeat, invariants checked on every state; vision optional | Finding bugs no spec looked for |

- **Evidence comes from Playwright itself:** trace file (screenshots, DOM snapshots,
  console, network), failure screenshots and video, axe results, Chromium JS coverage per
  test, aria snapshot on failure → `data/evidence/<run>/<test>/`.
- **Coverage per test** → `touches` edges (refines the static route → file map that scopes
  model work).
- **Origin guard:** top-level navigation off the target origin is aborted, in both modes.
- **Reads:** stored auth state (`storageState`), endpoints to mock (`page.route` / HAR).
- **Writes:** `Run`, `result` rows, `touches` edges, aria hashes for visited pages.
- **Runtime:** spec mode is plain code; exploratory mode is the one LangGraph loop and stops
  when the budget is spent or no new states appear.
- **Workers:** more when no model is loaded (spec runs); 2 while one is (exploration).

---

## Importer — *new in v0.6*

**Job:** let the analyzer work on suites Testomation didn't write.

- `testomation import <report.json>` reads any Playwright project's JSON report and its
  traces and attachments.
- Writes a `Run` (trigger `import`) and `result` rows with `external_test = "file › title"`.
- Maps a failure to a step via `test.step` titles when present; otherwise via the failing
  locator in the error and the trace's last action (Q24).
- Then the normal triage and report stages run.

---

## Analyzer agent — *changed in v0.6*

**Job:** decide what's actually a bug.

Reasons over the whole **evidence bundle**. Signal sources: failed assertions, console
exceptions, 4xx/5xx responses, visual regressions, dead-end navigation, accessibility
violations. Input is a `result` row from the spec runner **or** an imported Playwright suite.

- **Rules engine first:** known noise signatures, status codes, axe-core, screenshot diffs,
  flake history (runs under heavy machine load excluded).
- **Labelled neighbours next:** the nearest failures humans (or the benchmark) already
  labelled, by signature embedding. A close, unanimous vote decides without a model.
- **Model (small tier) only** for failures nothing else settled — **one call**; the label
  probability comes from logprobs. Confidence is a calibrated mix of that probability, the
  neighbour vote and the rules signal — never the model's self-report.
- **Reads:** noise signatures, labelled neighbours, past bugs on the same component, recent
  commits touching it.
- **Writes:** `Bug`, `NoiseSignature`, verdict claims, `duplicate_of` edges; `review_item`
  rows for low confidence.
- **Runtime:** plain Python cascade. See [AGENT_RUNTIME.md](AGENT_RUNTIME.md).

---

## Reporter

**Job:** close the loop with humans.

- Writes `data/reports/<run>/report.html` (+ Markdown): confirmed bugs, repro steps (spec
  steps), links to traces and screenshots, next to Playwright's HTML report.
- Sends a desktop notification when a run finishes or a bug is confirmed.
- GitHub Issues / Jira / Slack come later.
- **Reads:** affected requirements, owning module.
- **Writes:** report paths (ticket IDs later) onto `bug` rows.
- **Runtime:** plain function with templates. Model only for an optional summary.

---

## Review queue — *changed in v0.6*

**Job:** hold uncertain decisions for a human.

- A review item is a **row** in `review_item` (kind, node, suggestion with its score,
  evidence dir, trace id, status). Kinds: `triage`, `draft_spec`, `repair_assertion`,
  `drift`, `noise_confirm`.
- `testomation review` shows each open item with its evidence, opens the trace with
  `npx playwright show-trace`, and records the decision.
- A decision becomes a human claim and a `HumanDecision` node, is sent to traces as a score,
  and is applied with the same `apply_verdict()` the analyzer uses (file bug, add noise
  signature, link duplicate). No graph is paused or resumed.
- `testomation approve` promotes draft specs, and confirms or edits their requirement.
- Local web UI later.

---

## Pipeline runner — *changed in v0.6*

**Job:** keep everything coordinated on one machine.

- `testomation run` executes a fixed sequence of stages (see [AGENT_RUNTIME.md](AGENT_RUNTIME.md)).
- Records each stage's state in Postgres; a crashed run resumes at the last completed stage.
  Stages are idempotent.
- Runs **every approved spec** every run; uses the memory graph only to decide which flows to
  re-plan and which specs to regenerate.
- Refreshes file hashes in `basis_state` at the start of each run.
- Enforces the **per-run compute budget** (model calls + model wall-clock time).
- Groups model work by tier and **unloads the model** (`keep_alive: 0`) before any stage that
  runs browsers; drives test-gen repair rounds.
- Fan-out and retries → Playwright Test.
- Temporal returns only if Testomation spreads across machines.

---

## Exploration runtime (LangGraph)

Runs the exploratory loop: snapshot → invariants → choose action → act, checkpointed to
Postgres so a long session resumes where it stopped. The only LangGraph graph.
→ [AGENT_RUNTIME.md](AGENT_RUNTIME.md)

## Memory graph

Not an agent — a store. Holds relationships between pages, flows, specs, bugs, commits and
human decisions, typed tables for core records, result rows, and the claims each source made
about them. → [MEMORY_GRAPH.md](MEMORY_GRAPH.md)

## Observability

OpenTelemetry spans to a local file in phases 0–2; self-hosted Langfuse from phase 3. Each
agent job is a trace; model calls are generations (tokens, latency); deterministic steps are
spans, so skipped model calls are visible too. → [OBSERVABILITY.md](OBSERVABILITY.md)

## llm client

The only code that talks to Ollama. Selects the model by tier, requests structured output,
returns the label probability from logprobs, and is traced via `langfuse.openai`.
→ [OBSERVABILITY.md](OBSERVABILITY.md), [LOCAL_SETUP.md](LOCAL_SETUP.md)

---

## Summary: memory reads & writes per component

| Component | Reads before acting | Writes after |
|---|---|---|
| Planner | Existing flows, uncovered pages, bug-prone components | `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint`, `Requirement` |
| Test gen | Working targets, similar specs, valid test data, helper names | `TestCase` (spec, draft) → `Flow`, `Requirement` |
| Executor | Auth state, endpoints to mock | `Run`, `result` rows, `touches`, aria hashes |
| Importer | — | `Run` (import), `result` rows |
| Analyzer | Noise signatures, labelled neighbours, past bugs on component, recent commits | `Bug`, `NoiseSignature`, verdict claims, `duplicate_of`, `review_item` |
| Reporter | Affected requirements, owning module | Report paths on `bug` |
| Pipeline runner | Changed files → `touches` / `renders` → model-work scope | `Commit`, file hashes, run/stage state |
| Review queue | Open `review_item` rows | Human claims, `HumanDecision` |
