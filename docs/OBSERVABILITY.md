# Observability

> Source: `index.html` §08 (brief v0.6)

Traces are the record of **what each agent did, how long it took, and whether it was
right.** Two stages:

| Phases | Where traces go | Why |
|---|---|---|
| 0–2 | **OpenTelemetry spans → a local JSONL file** (`data/traces/<run>.jsonl`) | No model calls yet; only pipeline stages to trace. Saves 2–3 GB of RAM |
| 3 on | **Langfuse, self-hosted** with its Docker Compose setup (v3: web, worker, ClickHouse, Redis, S3-compatible store, Postgres) | Generations, tokens, latency, prompt versions, scores, datasets |

See [LOCAL_SETUP.md](LOCAL_SETUP.md) for RAM notes.

## Before Langfuse (phases 0–2)

Pipeline code uses the **OpenTelemetry API**, with a file exporter:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter(
    out=open(f"data/traces/{run_id}.jsonl", "a"),
    formatter=lambda span: span.to_json(indent=None) + "\n")))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("testomation")

with tracer.start_as_current_span("stage.execute", attributes={"run.id": run_id}):
    ...
```

Langfuse's Python SDK is built on OpenTelemetry, so these spans can be exported to it in
phase 3 without changing pipeline code. Confirm the exact wiring then (Q13). Until then,
`trace_id` on nodes and claims points into the JSONL file.

**Trace attributes** use the same names in both stages: `run.id` (= session), `agent`,
`model.tier`, `memory_hit`, `stage`.

## Mapping Langfuse concepts to Testomation

| Langfuse | Testomation |
|---|---|
| **Session** | One test run — `run-<pr>-<sha>`, `run-local-<timestamp>` or `run-import-<timestamp>` |
| **Trace** | One agent job — "plan checkout flows", "triage failure #182" |
| **Span** | A non-LLM step — memory lookup, crawl, rules-engine triage, neighbour vote, a pipeline stage |
| **Generation** | An actual model call: model name, tokens, latency, prompt version |
| **Tags** | `agent:analyzer`, `trigger:local`, `project:web-app`, `model-tier:small` |
| **Scores** | Human verdicts from the review queue |
| **Datasets** | Benchmark cases, replay bundles and hard triage cases, rerun on every prompt or model change |

**Deterministic steps are traced too** (as spans), so jobs that *skipped* the model are
visible — that's how you measure whether memory and rules pull their weight.

## Instrumentation sketch (phase 3 on)

```python
from langfuse import observe, get_client, propagate_attributes
from langfuse.openai import OpenAI     # drop-in client: every call → a generation

llm = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")  # local Ollama
langfuse = get_client()                # reads LANGFUSE_* env vars (self-hosted)

@observe(name="analyzer.triage", capture_input=False)  # no raw DOM / screenshots
def triage_failure(failure, run_id):
    with propagate_attributes(session_id=run_id, tags=["agent:analyzer"]):
        hit = memory.fresh_human_verdict(failure.signature)    # (a) memory
        langfuse.update_current_span(metadata={"memory_hit": hit is not None})
        if hit:
            return hit

        rule = rules_engine.classify(failure)                  # (b) deterministic
        if rule.confident:
            return memory.claim(failure, rule, source="rules")

        votes = memory.labelled_neighbours(failure)            # (b) embeddings, no generation
        if votes.decisive:
            return memory.claim(failure, votes.verdict, source="knn")

        p = llm_classify(llm, failure, tier="small")           # (c) one call, logprobs → p(label)
        verdict = calibrate(rule, votes, p)                    # gate + review_item: AGENT_RUNTIME.md
        return memory.claim(failure, verdict, source="llm",    # (d) write back
                            trace_id=langfuse.get_current_trace_id())
```

- Ollama exposes an OpenAI-compatible API at `/v1`; the `api_key` is required by the client
  but ignored by Ollama.
- Call `langfuse.flush()` before a short-lived worker or CLI command exits.
- Only a **fresh human-sourced** memory hit short-circuits (no silent suppression, stale until
  proven).
- To verify in the **spike**: structured output (`response_format` with the spec schema's
  discriminated union) and `logprobs` / `top_logprobs` through the OpenAI-compatible endpoint
  and `langfuse.openai`. Fallback: Ollama's native client (`format=`, `logprobs`) plus a manual
  `@observe(as_type="generation")`. Tracked in [DECISIONS.md](DECISIONS.md) (Q13).

## How it ties to memory and compute

| Link | What it gives you |
|---|---|
| **Graph ↔ trace** | Every model-created node and claim stores its trace ID → any bug or spec traces back to the exact reasoning and prompt version. |
| **Cache rate** | `memory_hit` flag on every span → share of decisions memory answered. Should climb as the graph matures. |
| **Budget enforcement** | Pipeline runner counts model calls and time per session; stops escalating when the budget is used. |
| **Analyzer accuracy** | Review decisions as scores → real precision numbers alongside the benchmark. |
| **Exploration tracing** | `langfuse.langchain.CallbackHandler` on the exploration graph → each node is its own span. |
| **Prompts & datasets** | Prompts versioned in Langfuse; benchmark, replay and hard cases as datasets rerun on every prompt change or model swap. |

## Metrics worth a dashboard

- Model calls, tokens and latency per run / per agent / per tier
- Memory hit rate over time
- Share of analyzer items resolved by memory vs rules vs neighbours vs model vs human
- Analyzer precision (from human scores and benchmark)
- Review-queue size **next to** model calls/time
- Benchmark scores per prompt/model version, with ranges ([EVALUATION.md](EVALUATION.md))

## Notes for local use

- **Local models have no price.** Langfuse won't compute a cost for them; track tokens,
  latency and call counts instead.
- Keep `capture_input=False` on anything that sees page content; log evidence paths, not raw
  payloads. Still matters locally — traces get shared, screenshotted, and kept.
- Langfuse's web UI defaults to `:3000`; run the target app on another port.
