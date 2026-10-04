# Local Setup

> Source: `index.html` §10 (brief v0.6)

The whole system runs on one laptop. Its limits shape several design choices.

## The machine

| Part | Spec | What it means |
|---|---|---|
| CPU | AMD Ryzen 7 5800H, 8 cores / 16 threads | Plenty for Playwright workers and partial model offload |
| RAM | 16 GB (~14 GB usable) | The tightest constraint once Langfuse, models and browsers run together |
| GPU | NVIDIA RTX 3050 Laptop, 4 GB VRAM | One ~4B model fully on GPU; ~7–8B only with CPU offload |
| OS | Fedora Linux | Chromium/Firefox fine; WebKit via the official Playwright container (Fedora isn't officially supported by Playwright) |
| Disk | ~450 GB free | Room for models, traces, video |
| Installed | Docker, podman, Node 22, uv, Ollama, Python 3.14 | Pin Python 3.12/3.13 with uv — 3.14 may lack wheels for some deps |

## Who uses which model

| When | Model | Notes |
|---|---|---|
| **Building** Testomation | Claude (Claude Code) | Writes code and docs. Never a runtime dependency. |
| **Running** Testomation | Local models via Ollama | No paid APIs, no keys, no data leaving the laptop |

## Services

| Service | How it runs | Notes |
|---|---|---|
| Ollama | Native install, GPU, `:11434` | Native avoids container GPU passthrough. `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`. The runner unloads the model (`keep_alive: 0`) before browser stages |
| Postgres + pgvector | Container, `:5432` | One server: `testomation` database; `langfuse` database added in phase 3 |
| Langfuse v3 | Docker Compose: web, worker, ClickHouse, Redis, S3-compatible store — **from phase 3** | Web UI `:3000` by default — run the target app on another port |
| Target app | Container with seeded database | Restored before each run |
| Playwright | Host, Node 22 | Chromium + Firefox; WebKit via container when needed |

## Model tiers

| Tier | Size | Candidates | Used for |
|---|---|---|---|
| `small` | ~4B, fully on GPU | Qwen3 4B, Gemma 3 4B | **Default for all text work**: triage, dedup, flow naming, planning, spec generation, repair, exploration |
| `large` | ~7–8B, partial CPU offload | Qwen3 8B, Qwen2.5-Coder 7B | **Optional** — enabled only if the benchmark shows a real gain on generation or planning |
| `vision` | ~4B multimodal | Gemma 3 4B | Optional visual triage / exploration |
| `embed` | small | nomic-embed-text (768-d) | Labelled-neighbour vote, fuzzy matching of errors and specs |

**Candidates only** — the spike and the benchmark ([EVALUATION.md](EVALUATION.md)) pick the
actual models. Model names live in config (e.g. `TESTO_MODEL_SMALL`), never in code. Until the
large tier earns its place, `TESTO_MODEL_LARGE` points at the small model. If Gemma 3 4B wins
the small tier, it can double as the vision tier and save a model swap. If a Qwen3 model is a
candidate, check in the spike how its thinking mode interacts with structured output.

## RAM budget (estimates)

| Consumer | Phases 0–2 | From phase 3 |
|---|---|---|
| OS + desktop | 3–4 GB | 3–4 GB |
| Langfuse stack | — | 2–3 GB (ClickHouse is the largest part) |
| Postgres | ~0.3 GB | ~0.3 GB |
| Ollama | — | ~1 GB with the small model on GPU; 2–3 GB only if the large tier is enabled |
| Target app | 0.5–1 GB | 0.5–1 GB |
| Playwright, 2 workers | 1–1.5 GB | 1–1.5 GB |
| **Total** | **~5–7 GB of ~14 GB** | **~8–13 GB of ~14 GB** |

Rules of thumb:

- **Unload the model while specs run.** Spec runs and repair-round runs happen with no model
  loaded, so they can use more workers.
- **Two workers while a model is loaded** — in practice, during exploration.
- **Separate generation from execution** — batched repair rounds keep them apart.
- **Lean evidence** — trace/video `retain-on-failure` or `on-first-retry`, not for every pass.
- **Record machine load per run** (free RAM, swap, load average on the `run` row). A test
  that times out because the laptop is swapping looks flaky; such runs don't count toward
  flake history.
- If memory gets tight, cap ClickHouse's memory in the Langfuse compose config before cutting
  anything else.

## App state

Results only mean something if every run starts from the same place.

- Target app runs in containers with a **seeded database restored before each run** (a
  Postgres template database makes this fast: `CREATE DATABASE app TEMPLATE app_seed`).
- Each test creates its **own synthetic user** via `$faker`, so parallel workers never fight
  over an account.
- Exploratory sessions only ever touch this disposable copy, and never leave its origin.

## Proposed repo layout

```
testomation/
├── pyproject.toml              # uv, Python 3.12 / 3.13
├── src/testomation/
│   ├── cli.py                  # testomation run | import | explore | review | approve | bench
│   ├── pipeline/               # stages: basis + scope, execute, triage, generate, report
│   ├── agents/                 # planner, testgen, analyzer (plain Python), explorer (LangGraph)
│   ├── ingest/                 # spec-runner results + imported Playwright reports → result rows
│   ├── memory/                 # schema, queries, claims, freshness
│   ├── llm/                    # Ollama client via langfuse.openai, model tiers, logprobs
│   └── evidence/               # local evidence store
├── runner/                     # TypeScript: Playwright config + spec runner + fixtures
│   └── helpers/                # hand-written helper steps (registry)
├── schemas/
│   ├── test-spec.schema.json   # the one source; Pydantic + TS types generated from it
│   └── examples/               # valid + invalid specs, validated by both sides
├── bench/                      # target app, seeded bugs, replay bundles, scoring
├── deploy/
│   ├── compose.yaml            # Postgres + pgvector; Langfuse stack from phase 3
│   └── sql/                    # memory DDL
├── spike/                      # throwaway feasibility spike; never imported
└── data/                       # gitignored: evidence, reports, run specs, traces
```

## Environment variables (proposed)

| Variable | Purpose |
|---|---|
| `TESTO_DATABASE_URL` | Postgres `testomation` database |
| `TESTO_OLLAMA_URL` | Default `http://localhost:11434/v1` |
| `TESTO_MODEL_SMALL` / `_LARGE` / `_VISION` / `_EMBED` | Model per tier (`_LARGE` defaults to the small model) |
| `TESTO_BUDGET_CALLS` / `TESTO_BUDGET_SECONDS` | Per-run compute budget |
| `TESTO_TARGET_URL` | Base URL of the app under test; the origin guard's allowed origin |
| `TESTO_TRACE_DIR` | Where OpenTelemetry file traces go (default `data/traces`) |
| `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Self-hosted Langfuse (from phase 3) |
