# Tech Stack

> Source: `index.html` §13 (brief v0.6)

Everything is **free and runs locally**.

| Layer | Choice | Why |
|---|---|---|
| Browser automation | **Playwright Test** (TypeScript runner) | Workers, retries, traces, screenshot comparison, aria snapshots, built-in reports |
| Test format | **JSON test spec + spec runner**; one JSON Schema source with generated Python and TS types | Small models fill schemas reliably; no generated code is executed; no drift between languages |
| Runtime LLM | **Ollama** (native, GPU) with local models | Free and local; structured output; logprobs; OpenAI-compatible API |
| Embeddings | Local embedding model via Ollama | Labelled-neighbour vote and fuzzy matching without a paid API |
| Agents | **Plain Python** | The analyzer, test gen and planner are cascades or pipeline rounds — no framework needed |
| Exploration loop | **LangGraph** (Python) | Long, stateful loop with per-step checkpoints; the only graph |
| Job orchestration | **Python pipeline runner + Playwright Test workers** | One user, one machine; Temporal deferred |
| Memory graph | **Postgres** (generic nodes, edges, claims + typed tables for core records; JSONB) **+ pgvector** | One database, constraints where the volume is, fuzzy matching built in |
| Graph checkpoints | LangGraph Postgres checkpointer (exploration only) | Same DB as memory; resumable sessions |
| Evidence store | **Local folder** (`data/evidence/<run>/`) | Traces open directly with `npx playwright show-trace` |
| Tracing | **OpenTelemetry → local JSONL** (phases 0–2), then **Langfuse v3, self-hosted** (Docker Compose, from phase 3) | Traces from day one without the RAM cost; then tokens/latency per agent, prompt versions, scores, datasets |
| Deterministic checks | `@axe-core/playwright`, Playwright screenshot comparison, V8 coverage | Most triage and scoping without a model |
| Test data | `@faker-js/faker` in the spec runner | Synthetic data resolved at run time |
| Reporting | Local HTML/Markdown + Playwright HTML report + desktop notifications | No external services |
| Review queue | CLI (`testomation review`) over `review_item` rows | Web UI later |
| Exploration | Coverage-guided crawler + monkey/fuzz + text agent over aria snapshots | Cheap passes before any vision model |
| Benchmark | Local target app with seeded bugs + detectable Stryker mutations + replay bundles | Ground truth for every change, fast enough to actually run |
| Dev tooling | uv (Python 3.12/3.13), Node 22, Docker Compose, **Claude Code** | Claude is used to build Testomation, not inside it |

## Languages

| Language | Used for |
|---|---|
| **Python** | Pipeline runner, agents, exploration graph, memory, llm client, importer, CLI |
| **TypeScript** | Playwright config, spec runner, helper registry, fixtures |

They exchange JSON files only (specs in, results + evidence out). See
[ARCHITECTURE.md](ARCHITECTURE.md#4-two-languages-one-boundary).

## Python libraries (planned)

| Library | Used for |
|---|---|
| `opentelemetry-api`, `opentelemetry-sdk` | Stage spans from day one (file exporter until phase 3) |
| `langfuse` | Tracing from phase 3 (`observe`, `langfuse.openai`, `langfuse.langchain.CallbackHandler`) |
| `openai` | Client for Ollama's OpenAI-compatible endpoint (wrapped by `langfuse.openai`) |
| `psycopg` + `pgvector` | Postgres access and vector type |
| `pydantic` (+ `datamodel-code-generator`, dev) | Spec models generated from the JSON Schema; validation before specs are stored or run |
| `langgraph`, `langgraph-checkpoint-postgres` | The exploration loop (phase 6) |

## TypeScript libraries (planned)

| Library | Used for |
|---|---|
| `@playwright/test` | Spec runner, workers, retries, traces, reports |
| `@axe-core/playwright` | Accessibility checks |
| `@faker-js/faker` | `$faker` references |
| `ajv` | Validating specs against the JSON Schema in the runner |
| `json-schema-to-typescript` (dev) | Spec types generated from the JSON Schema |

## Model tiers

`small` (~4B on GPU) is the default for everything; `large` (~7–8B with offload) only if the
benchmark shows a gain; `vision` optional; `embed`. Candidates and RAM budget in
[LOCAL_SETUP.md](LOCAL_SETUP.md); final picks by spike and benchmark.

## Considered and not used (for now)

| Option | Why not | Revisit when |
|---|---|---|
| Temporal | One machine | Multiple machines, many concurrent runs, mid-stage durability needed |
| LangGraph for analyzer / test gen / planner | Their logic is a cascade or pipeline rounds | One of them grows a real loop (Q23) |
| Langfuse in phases 0–2 | 2–3 GB of RAM with no model calls to trace | Phase 3 |
| Arize Phoenix (single-container tracing) | Lighter, but Langfuse's prompt management, scores and datasets are already designed in | If the Langfuse stack proves too heavy |
| Playwright Test Agents (Generator, Healer) | Generator writes code; Healer self-heals (D35) | Planner plan format may be borrowed (Q21) |
| All-TypeScript (LangGraph.js) | Python's embedding and evaluation tooling is stronger | — |
| S3-compatible evidence store | One machine | Evidence shared across machines |
| Jira / Linear / GitHub Issues / Slack | No team yet | Tool used by a team |
| Hosted LLMs (incl. Claude API) | Free-and-local rule | Only if local quality is insufficient *and* paid use is accepted — the llm client makes it a config change |
| WebKit on host | Fedora isn't supported | Use the Playwright container instead |
