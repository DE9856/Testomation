# Design Risks

> Source: `testomation.html` §12 (brief v0.5)

Risks the architecture is deliberately built around. Each has a mitigation elsewhere in the
design.

| # | Risk | Why it matters | Mitigation in the design |
|---|---|---|---|
| 1 | **Self-healing can hide real bugs** | Quietly swapping a broken target buries the bug the test existed to catch. | Approved specs never self-heal: any change is a drift signal + review item. Draft repairs can't touch assertions. ([TEST_SPEC.md](TEST_SPEC.md)) |
| 2 | **Agent runs are slow and non-deterministic** | Great for exploration, bad for a repeatable regression gate. | Spec execution and agentic exploration are **separate modes**. |
| 3 | **Small local models are weaker** *(new)* | A 4–8B model misjudges things a frontier model wouldn't. | Narrow jobs, schemas instead of code, deterministic tools first, confidence from agreement, every change gated on the benchmark. |
| 4 | **Memory can learn the wrong lesson** | A 500 wrongly saved as noise is ignored forever. | LLM-inferred suppressions stay in review until a human confirms. Only fresh human claims short-circuit. |
| 5 | **Stale memory looks like fresh knowledge** | Last month's target or flow may be wrong today. | Invalidation on every commit; stale nodes and claims are hints, not answers. |
| 6 | **Shared app state makes tests lie** *(new)* | Shared accounts or leftover data make failures order-dependent; flake signals become noise. | Seeded DB restored before each run; a synthetic user per test. |
| 7 | **The laptop becomes the bottleneck** *(new)* | 16 GB RAM / 4 GB VRAM shared by Langfuse, a model, the app and browsers. Swapping makes tests time out and look flaky. | Worker cap while a model is loaded, generation and execution kept apart, machine load recorded per run and excluded from flake history. |
| 8 | **A compute budget can quietly cost coverage** | A tight budget routing everything to review moves work to humans. | Watch review-queue size next to model calls/time in Langfuse. |
| 9 | **Two orchestrators can blur into one** | LangGraph doing parallelism/retries, or the runner encoding decisions → state in both. | Runner + Playwright own jobs; LangGraph owns decisions within one item. Temporal, if it returns, replaces the runner only. |

## Resolved tension (from v0.4)

v0.4 recommended natural-language tests resolved at runtime for some cases, which is
self-healing by design and conflicted with risk #1. v0.5's **JSON spec** resolves this:
targets are fixed in the spec, runtime re-resolution only happens in exploratory mode, and any
change to an approved spec goes to review.
