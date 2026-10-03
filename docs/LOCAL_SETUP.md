# Local Setup

> Source: `testomation.html` §10 (brief v0.5)

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
| Ollama | Native install, GPU, `:11434` | Native avoids container GPU passthrough. `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1` |
| Postgres + pgvector | Container, `:5432` | One server, two databases: `testomation`, `langfuse` |
| Langfuse v3 | Docker Compose: web, worker, ClickHouse, Redis, S3-compatible store | Web UI `:3000` by default — run the target app on another port |
| Target app | Container with seeded database | Restored before each run |
| Playwright | Host, Node 22 | Chromium + Firefox; WebKit via container when needed |

## Model tiers

| Tier | Size | Candidates | Used for |
|---|---|---|---|
| `small` | ~4B, fully on GPU | Qwen3 4B, Gemma 3 4B | Triage, dedup, flow naming |
| `large` | ~7–8B, partial CPU offload | Qwen3 8B, Qwen2.5-Coder 7B | Spec generation, planning, repair |
| `vision` | ~4B multimodal | Gemma 3 4B | Optional visual triage / exploration |
| `embed` | small | nomic-embed-text (768-d) | Fuzzy matching of errors and specs |

**Candidates only** — the benchmark ([EVALUATION.md](EVALUATION.md)) picks the actual models.
Model names live in config (e.g. `TESTO_MODEL_SMALL`), never in code. If Gemma 3 4B wins the
small tier, it can double as the vision tier and save a model swap.

## RAM budget (estimates)

| Consumer | Approx. RAM |
|---|---|
| OS + desktop | 3–4 GB |
| Langfuse stack | 2–3 GB (ClickHouse is the largest part) |
| Postgres | ~0.3 GB |
| Ollama | ~1 GB with small model on GPU; 2–3 GB with large model offloading |
| Target app | 0.5–1 GB |
| Playwright, 2 workers | 1–1.5 GB |
| **Total** | **~9–13 GB of ~14 GB** |

Rules of thumb:

- **Two workers with a model loaded**; raise the count only for stages that don't call a model.
- **Separate generation from execution** — no large-model generation during a big test batch.
- **Lean evidence** — trace/video `retain-on-failure` or `on-first-retry`, not for every pass.
- **Record machine load per run** (free RAM, swap, load average on the `Run` node). A test
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
- Exploratory sessions only ever touch this disposable copy.

## Proposed repo layout

```
testomation/
├── pyproject.toml              # uv, Python 3.12 / 3.13
├── src/testomation/
│   ├── cli.py                  # testomation run | review | bench | approve
│   ├── pipeline/               # stages: impact, execute, triage, generate, report
│   ├── agents/                 # planner, testgen, analyzer (LangGraph graphs)
│   ├── memory/                 # schema, queries, claims, invalidation
│   ├── llm/                    # Ollama client via langfuse.openai, model tiers
│   └── evidence/               # local evidence store
├── runner/                     # TypeScript: Playwright config + spec runner + fixtures
├── schemas/test-spec.schema.json
├── bench/                      # target app, seeded bugs, scoring
├── deploy/compose.yaml         # Postgres + pgvector, Langfuse stack
└── data/                       # gitignored: evidence, reports, run specs
```

## Environment variables (proposed)

| Variable | Purpose |
|---|---|
| `TESTO_DATABASE_URL` | Postgres `testomation` database |
| `TESTO_OLLAMA_URL` | Default `http://localhost:11434/v1` |
| `TESTO_MODEL_SMALL` / `_LARGE` / `_VISION` / `_EMBED` | Model per tier |
| `TESTO_BUDGET_CALLS` / `TESTO_BUDGET_SECONDS` | Per-run compute budget |
| `TESTO_TARGET_URL` | Base URL of the app under test |
| `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Self-hosted Langfuse |
