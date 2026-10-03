# Observability (Langfuse)

> Source: `testomation.html` §08 (brief v0.5)

Langfuse is the record of **what each agent did, how long it took, and whether it was right.**
It is **self-hosted on the laptop** with its Docker Compose setup (v3: web, worker,
ClickHouse, Redis, S3-compatible store, Postgres). See [LOCAL_SETUP.md](LOCAL_SETUP.md) for
RAM notes.

## Mapping Langfuse concepts to Testomation

| Langfuse | Testomation |
|---|---|
| **Session** | One test run — `run-<pr>-<sha>` or `run-local-<timestamp>` |
| **Trace** | One agent job — "plan checkout flows", "triage failure #182" |
| **Span** | A non-LLM step — memory lookup, crawl, rules-engine triage, a pipeline stage |
| **Generation** | An actual model call: model name, tokens, latency, prompt version |
| **Tags** | `agent:analyzer`, `trigger:local`, `project:web-app`, `model-tier:small` |
| **Scores** | Human verdicts from the review queue |
| **Datasets** | Benchmark cases and hard triage cases, rerun on every prompt or model change |

**Deterministic steps are traced too** (as spans), so jobs that *skipped* the model are
visible — that's how you measure whether memory and rules pull their weight.

## Instrumentation sketch

```python
from langfuse import observe, get_client, propagate_attributes
from langfuse.openai import OpenAI     # drop-in client: every call → a generation

llm = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")  # local Ollama
langfuse = get_client()                # reads LANGFUSE_* env vars (self-hosted)

@observe(name="analyzer.triage", capture_input=False)  # no raw DOM / screenshots
def triage_failure(failure, run_id):
    with propagate_attributes(session_id=run_id, tags=["agent:analyzer"]):
        hit = memory.lookup_noise(failure.signature)       # (a) memory
        langfuse.update_current_span(metadata={"memory_hit": hit is not None})
        if hit and hit.source == "human" and not hit.stale:
            return hit.verdict

        verdict = rules_engine.classify(failure)           # (b) deterministic
        if verdict.confident:
            memory.claim(verdict, source="rules")
            return verdict

        verdict = llm_classify(llm, failure, tier="small", samples=3)  # (c) model
        memory.claim(verdict, source="llm",                # (d) write back
                     trace_id=langfuse.get_current_trace_id())
        return verdict
```

- Ollama exposes an OpenAI-compatible API at `/v1`; the `api_key` is required by the client
  but ignored by Ollama.
- Call `langfuse.flush()` before a short-lived worker or CLI command exits.
- Only a **fresh human-sourced** memory hit short-circuits (no silent suppression, stale until
  proven).
- To verify early (phase 3 spike): structured output (`response_format` with a JSON schema)
  through the OpenAI-compatible endpoint. Fallback: Ollama's native client with `format=`
  plus a manual `@observe(as_type="generation")`. Tracked in [DECISIONS.md](DECISIONS.md).

## How it ties to memory and compute

| Link | What it gives you |
|---|---|
| **Graph ↔ trace** | Every model-created node and claim stores its trace ID → any bug or spec traces back to the exact reasoning and prompt version. |
| **Cache rate** | `memory_hit` flag on every span → share of decisions memory answered. Should climb as the graph matures. |
| **Budget enforcement** | Pipeline runner counts model calls and time per session; stops escalating when the budget is used. |
| **Analyzer accuracy** | Review decisions as scores → real precision numbers alongside the benchmark. |
| **LangGraph tracing** | `langfuse.langchain.CallbackHandler` → each graph node is its own span. |
| **Prompts & datasets** | Prompts versioned in Langfuse; benchmark and hard cases as datasets rerun on every prompt change or model swap. |

## Metrics worth a dashboard

- Model calls, tokens and latency per run / per agent / per tier
- Memory hit rate over time
- Share of analyzer items resolved by memory vs rules vs model vs human
- Analyzer precision (from human scores and benchmark)
- Review-queue size **next to** model calls/time
- Benchmark scores per prompt/model version ([EVALUATION.md](EVALUATION.md))

## Notes for local use

- **Local models have no price.** Langfuse won't compute a cost for them; track tokens,
  latency and call counts instead.
- Keep `capture_input=False` on anything that sees page content; log evidence paths, not raw
  payloads. Still matters locally — traces get shared, screenshotted, and kept.
- Langfuse's web UI defaults to `:3000`; run the target app on another port.
