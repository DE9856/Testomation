# Cost & Compute Strategy

> Source: `testomation.html` §07 (brief v0.5)

## The rule

> **The LLM writes and interprets tests; it never runs them.**

A spec generated once and run a thousand times by Playwright costs **one** generation. Model
work scales with how much the app **changes**, not how often it's tested.

With local models the cost isn't money — it's **VRAM, RAM and time**. On a laptop with a
4 GB GPU, every model call avoided is seconds saved and a browser worker that doesn't wait.

## Deterministic first, model for the residue

| Stage | Deterministic first | Model only for |
|---|---|---|
| Plan | Router / sitemap / OpenAPI parsing; state-graph crawler; aria snapshots | Naming and ranking flows; inferring business rules |
| Generate | Spec templates for common patterns; boundary values from HTML attributes; schema-driven API specs; Faker references | Novel multi-step flows (as specs, never code) |
| Execute | Playwright Test running specs with role / test-id targets | **Nothing** |
| Analyze | Assertions, status codes, console allowlist, axe-core, screenshot diff, flake history | Failures matching no known signature |
| Dedupe | Hash of normalised error signature | Borderline matches (local embeddings first) |
| Report | Templated reports and notifications | Optional summary |
| Impact | Static route → file map, then coverage, via the memory graph | **Nothing** |

## Making the remaining calls cheap

| Lever | How |
|---|---|
| **Memory before model** | The graph *is* the cache. A question answered once isn't asked again. |
| **Change-triggered** | Re-plan and regenerate only what a diff touched. |
| **Model tiers** | `small` (~4B, fully on GPU) for triage, dedup, naming; `large` (~7–8B, partial CPU offload) for spec generation, planning, repair. |
| **Structured output** | JSON-schema-constrained decoding — no calls wasted on unparsable output. |
| **Text over pixels** | Aria snapshot or trimmed DOM; screenshots only for suspected visual bugs. |
| **Group work by model** | 4 GB VRAM holds one model at a time. Batch all small-tier work, then all large-tier work; keep the model loaded for the batch. |
| **Overnight batches** | Planning/generation for areas a PR didn't touch runs while the laptop is idle. |
| **Hard per-run budget** | Cap on **model calls** and **model wall-clock time** per run. Once spent, remaining items go to the review queue. |

### How the budget is enforced

- The **pipeline runner** counts model calls and model time per run (from the llm client,
  mirrored in Langfuse).
- Inside a graph, `llm_classify` sets `confidence = 0` when the budget is spent, routing the
  item to human review. ([AGENT_RUNTIME.md](AGENT_RUNTIME.md))
- Budget values are configuration; starting numbers to be set from the benchmark
  ([EVALUATION.md](EVALUATION.md)).

## Exploratory testing without a vision loop

1. **Monkey/fuzz interaction** and **coverage-guided crawling** first.
2. Check **invariants** on every state reached:
   - no console errors
   - no 5xx responses
   - no axe violations
   - nothing overflowing the viewport
3. Then a **text-based exploratory agent** over aria snapshots.
4. A small **vision model** is an optional, budgeted deep pass on high-value flows.

## Watch-outs

- A tight budget that routes everything to review just moves work to humans. Track
  review-queue size next to model calls/time. → [RISKS.md](RISKS.md)
- Resource pressure makes tests look flaky. → [LOCAL_SETUP.md](LOCAL_SETUP.md)
