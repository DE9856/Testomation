# Design Risks

> Source: `index.html` §12 (brief v0.6)

Risks the architecture is deliberately built around. Each has a mitigation elsewhere in the
design.

| # | Risk | Why it matters | Mitigation in the design |
|---|---|---|---|
| 1 | **Self-healing can hide real bugs** | Quietly swapping a broken target buries the bug the test existed to catch. | Approved specs never self-heal: any change is a drift signal + review item. Draft repairs can't touch assertions. ([TEST_SPEC.md](TEST_SPEC.md)) |
| 2 | **Agent runs are slow and non-deterministic** | Great for exploration, bad for a repeatable regression gate. | Spec execution and agentic exploration are **separate modes**. |
| 3 | **Small local models are weaker** | A 4–8B model misjudges things a frontier model wouldn't. | Spike before building; narrow jobs; schemas instead of code; deterministic tools first; confidence from label probabilities and labelled neighbours, not self-report; every change gated on the benchmark. |
| 4 | **Memory can learn the wrong lesson** | A 500 wrongly saved as noise is ignored forever. | Model-inferred (`llm` or `knn`) suppressions stay in review until a human confirms. Only fresh human claims short-circuit. |
| 5 | **Stale memory looks like fresh knowledge** | Last month's target or flow may be wrong today. | Freshness from basis hashes: a claim counts only while the files and page structure it was based on are unchanged. Stale nodes and claims are hints, not answers. |
| 6 | **Shared app state makes tests lie** | Shared accounts or leftover data make failures order-dependent; flake signals become noise. | Seeded DB restored before each run; a synthetic user per test. |
| 7 | **The laptop becomes the bottleneck** | 16 GB RAM / 4 GB VRAM shared by Langfuse, a model, the app and browsers. Swapping makes tests time out and look flaky. | One model by default; model unloaded while specs run; batched repair rounds; Langfuse only from phase 3; machine load recorded per run and excluded from flake history. |
| 8 | **A compute budget can quietly cost coverage** | A tight budget routing everything to review moves work to humans. | Watch review-queue size next to model calls/time. |
| 9 | **Two orchestrators can blur into one** | LangGraph doing parallelism/retries, or the runner encoding decisions → state in both. | LangGraph is used only for the exploration loop. Runner + Playwright own jobs; agent code owns decisions. Temporal, if it returns, replaces the runner only. |
| 10 | **Page content can steer the model** *(new)* | Aria snapshots and error text from the app go into prompts. A page — or user-generated content on it — could contain text that reads like instructions ("this error is expected"). | Page text is passed as delimited data, never instructions; outputs are schema-constrained enums; nothing model-written runs; model-inferred noise never suppresses without a human; specs and exploration stay on the target origin (D32). |
| 11 | **A small benchmark gives noisy numbers** *(new)* | With ~20 bugs, one bug is 5 points of recall, and models are stochastic — a "regression" may be chance. | Detectable mutants add volume; 3 runs per benchmark with ranges; held-out set. |
| 12 | **Infrastructure before proof** *(new)* | Months of plumbing could precede the discovery that local models can't do the core job. | Feasibility spike first, with measured exit targets ([DESIGN_ROADMAP.md](DESIGN_ROADMAP.md)). |
| 13 | **Building what already exists** *(new)* | Playwright's own Planner/Generator/Healer agents overlap planning and generation. | Differences made explicit and kept: JSON specs, no self-healing, memory, triage, local models, benchmark (D35). |

## Resolved tension (from v0.4)

v0.4 recommended natural-language tests resolved at runtime for some cases, which is
self-healing by design and conflicted with risk #1. v0.5's **JSON spec** resolves this:
targets are fixed in the spec, runtime re-resolution only happens in exploratory mode, and any
change to an approved spec goes to review.
