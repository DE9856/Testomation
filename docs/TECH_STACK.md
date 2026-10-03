# Tech Stack

> Source: `testomation.html` §13 (brief v0.5)

Everything is **free and runs locally**.

| Layer | Choice | Why |
|---|---|---|
| Browser automation | **Playwright Test** (TypeScript runner) | Workers, retries, traces, screenshot comparison, aria snapshots, built-in reports |
| Test format | **JSON test spec + spec runner** | Small models fill schemas reliably; no generated code is executed |
| Runtime LLM | **Ollama** (native, GPU) with local models | Free and local; structured output; OpenAI-compatible API |
| Embeddings | Local embedding model via Ollama | Fuzzy matching without a paid API |
| Agent runtime | **LangGraph** (Python) | Branching decision loops, human-review interrupts, per-step checkpoints |
| Job orchestration | **Python pipeline runner + Playwright Test workers** | One user, one machine; Temporal deferred |
| Memory graph | **Postgres** (nodes, edges, claims; JSONB) **+ pgvector** | One database, fuzzy matching built in |
| Graph checkpoints | LangGraph Postgres checkpointer | Same DB as memory; resumable agent state |
| Evidence store | **Local folder** (`data/evidence/<run>/`) | Traces open directly with `npx playwright show-trace` |
| LLM observability | **Langfuse v3, self-hosted** (Docker Compose) | Traces, tokens/latency per agent, prompt versions, scores, datasets |
| Deterministic checks | `@axe-core/playwright`, Playwright screenshot comparison, V8 coverage | Most triage and impact analysis without a model |
| Test data | `@faker-js/faker` in the spec runner | Synthetic data resolved at run time |
| Reporting | Local HTML/Markdown + Playwright HTML report + desktop notifications | No external services |
| Review queue | CLI (`testomation review`) | Web UI later |
| Exploration | Coverage-guided crawler + monkey/fuzz + text agent over aria snapshots | Cheap passes before any vision model |
| Benchmark | Local target app with seeded bugs + Stryker mutations | Ground truth for every change |
| Dev tooling | uv (Python 3.12/3.13), Node 22, Docker Compose, **Claude Code** | Claude is used to build Testomation, not inside it |

## Languages

| Language | Used for |
|---|---|
| **Python** | Pipeline runner, agents, LangGraph graphs, memory, llm client, CLI |
| **TypeScript** | Playwright config, spec runner, fixtures |

They exchange JSON files only (specs in, results + evidence out). See
[ARCHITECTURE.md](ARCHITECTURE.md#4-two-languages-one-boundary).

## Python libraries (planned)

| Library | Used for |
|---|---|
| `langgraph`, `langgraph-checkpoint-postgres` | Agent graphs and checkpoints |
| `langfuse` | Tracing (`observe`, `langfuse.openai`, `langfuse.langchain.CallbackHandler`) |
| `openai` | Client for Ollama's OpenAI-compatible endpoint (wrapped by `langfuse.openai`) |
| `psycopg` + `pgvector` | Postgres access and vector type |
| `jsonschema` | Validating specs before they're stored or run |

## Model tiers

`small` (~4B on GPU), `large` (~7–8B with offload), `vision` (optional), `embed`. Candidates
and RAM budget in [LOCAL_SETUP.md](LOCAL_SETUP.md); final picks by benchmark.

## Deferred (not on the laptop yet)

| Was / could be | Comes back when |
|---|---|
| Temporal | Multiple machines, many concurrent runs, mid-stage durability needed |
| S3-compatible evidence store | Evidence shared across machines |
| Jira / Linear / GitHub Issues / Slack | Tool used by a team |
| Hosted LLMs (incl. Claude API) | Only if local quality is insufficient *and* paid use is accepted — the llm client makes it a config change |
| WebKit on host | Use the Playwright container instead |
