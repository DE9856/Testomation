# Agent Runtime: pipeline for jobs, plain code for decisions, LangGraph for loops

> Source: `index.html` §09 (brief v0.6)

Testomation has **three different control-flow problems**:

- **Job work** — running tests in parallel, retrying failures, moving a run through its stages.
- **Decisions** — inside one agent, deciding whether memory answered a question, whether the
  rules are sure, whether to ask a human.
- **Long loops** — an exploratory session that acts, looks and acts again for minutes, and
  should survive a crash.

On one laptop: **a plain pipeline runner and Playwright Test for jobs, plain Python for
decisions, and LangGraph only for the exploration loop.**

| Concern | Pipeline runner + Playwright Test | Agent code (plain Python) | LangGraph (exploration) |
|---|---|---|---|
| Unit of work | A whole run: scope, execution, triage, generation, report | One decision on one item | One exploratory session |
| Parallelism | Playwright workers for tests; model calls one at a time | None | None |
| Durability | Stage state in Postgres; a crashed run resumes at the last completed stage | Stateless; results written as claims | Checkpointed per step to Postgres |
| Branching | Fixed sequence of stages | Early exits in a cascade | Conditional edges: new state, budget, invariants |
| Humans | — | Writes a `review_item` row and moves on | — |

## Why not LangGraph everywhere (changed in v0.6)

v0.5 made the analyzer the first LangGraph graph so `interrupt()` could pause it for review.
In practice the analyzer is a **cascade with early exits**, and the step after a human
decides is just "write the claim and apply it", which the review CLI can do itself. So there's
nothing to pause or resume. Plain Python gives:

- fewer dependencies, and no checkpoint tables living next to memory (state in one place);
- easier debugging and unit tests ("the model is never called when rules are confident");
- per-step trace spans anyway, through `@observe` / OpenTelemetry.

Test generation's repair loop moves **out** of the agent and into the pipeline as batched
rounds, because the model has to be unloaded while drafts run ([TEST_SPEC.md](TEST_SPEC.md)).

The exploratory agent is a real loop — long, stateful, worth resuming — so it's the one place
LangGraph is used.

## How a run nests

```
testomation run --pr 412              pipeline runner · stage state in Postgres
 ├─ stage: refresh basis + scope       plain code · git blob SHAs · memory-graph query
 ├─ stage: run approved specs          model unloaded · npx playwright test · retries=1
 ├─ stage: triage failures             plain code · memory → rules → neighbours → model
 ├─ stage: generate missing tests      plain code · ≤3 rounds: generate → unload → run → repair
 └─ stage: report                      plain code · local HTML / Markdown

testomation explore --budget 15m      LangGraph loop · checkpointed · its own run
testomation import report.json        triage + report for an existing Playwright suite
```

Stages are idempotent functions.

## Where LangGraph is used — and where it isn't

| Use it | Why |
|---|---|
| **Exploratory agent** | Snapshot → check invariants → choose action → act → repeat; stops on budget or no new states. Long-running, so checkpoints matter |

| Don't use it | Why |
|---|---|
| Analyzer | A cascade with early exits; review is asynchronous through `review_item` |
| Test gen | Rounds belong to the pipeline so the model can be unloaded while drafts run |
| Planner | Crawl → parse → rank is a straight line. If "go back for detail on high-value areas" becomes a real loop, revisit (Q23) |
| Spec execution | Playwright running a spec has no decisions; a graph is pure overhead |
| Reporter | Templated output — a plain function is enough |
| The pipeline | Stage order, resumption and parallel test runs stay in the runner and Playwright |
| The memory graph | LangGraph's long-term store is key-value, not linked. The explorer reaches Postgres memory through explicit lookup and write-back nodes |

## The analyzer cascade

```
         failure  (spec-runner result or imported Playwright result)
              │
     ┌────────▼────────┐
     │  memory lookup  ├── fresh human verdict ───────────────────┐
     └────────┬────────┘                                          │
              │ miss · model-only · stale                         │
     ┌────────▼────────┐                                          │
     │   rules engine  ├── confident ───────────────────────┐     │
     └────────┬────────┘                                    │     │
              │ unsure                                      │     │
     ┌────────▼────────┐                                    │     │
     │     labelled    ├── close + unanimous ─────────┐     │     │
     │    neighbours   │                              │     │     │
     └────────┬────────┘                              │     │     │
              │ unsure                                │     │     │
     ┌────────▼────────┐                              │     │     │
     │ LLM classify ×1 │                              │     │     │
     │ (if budget left)│                              │     │     │
     └────────┬────────┘                              │     │     │
              │ calibrated score                      │     │     │
     ┌────────▼────────┐                              │     │     │
     │ confidence gate ├── low ──► review_item        │     │     │
     └────────┬────────┘          (human, later)      │     │     │
              │ high                                  │     │     │
     ┌────────▼────────┐                              │     │     │
     │   write claim   │◄─────────────────────────────┴─────┴─────┘
     └────────┬────────┘
              ▼
  apply_verdict(): file bug · add noise signature · link duplicate
```

Every box except **LLM classify** runs without a generation call. The neighbour vote uses
embeddings that already exist in memory.

### Gates

| Gate | Rule | Otherwise |
|---|---|---|
| Memory | A fresh human verdict on this signature → write | Rules engine |
| Rules engine | Rule confidence `>= 0.9` → write | Neighbours |
| Neighbours | `>= k` fresh labelled neighbours above similarity `s`, all agreeing → write (source `knn`) | LLM classify |
| LLM classify | One call, small tier, verdict as an enum; the label probability comes from logprobs | — |
| Confidence gate | Calibrated score from LLM probability + neighbour vote + rules signal `>= 0.8` → write | `review_item` |
| Budget spent | LLM step skipped; the score comes from rules + neighbours only, usually low | `review_item` |

0.9, 0.8, `k = 5` and `s = 0.9` are **placeholders** until the benchmark calibrates them
([EVALUATION.md](EVALUATION.md), Q19). The verdict enum's values must start with distinct
tokens so the client can read one label probability from `top_logprobs`. If logprobs prove
unusable through the client (Q13), the fallback samples 3× at temperature > 0 and uses the
agreement share.

**Labelled neighbours** are `Bug` / `NoiseSignature` nodes with a fresh human verdict (or a
benchmark label) and an embedding. The vote looks up the nearest ones to the new failure's
signature embedding.

## Sketch

```python
from dataclasses import dataclass

@dataclass
class Verdict:
    label: str          # 'bug' | 'noise' | 'flaky' | 'test_issue'
    confidence: float
    source: str         # 'rules' | 'knn' | 'llm' | 'human'

def triage(failure, run) -> Verdict | None:
    """Returns a verdict, or None after queuing a review item."""
    if hit := memory.fresh_human_verdict(failure.signature):            # (a) memory
        return hit
    rule = rules.classify(failure)                                       # (b) rules
    if rule and rule.confidence >= RULES_GATE:
        return memory.claim(failure, rule)
    votes = memory.labelled_neighbours(failure, k=K, min_sim=MIN_SIM)    # (b) neighbours
    if votes.unanimous and len(votes) >= K:
        return memory.claim(failure, Verdict(votes.label, votes.share, "knn"))
    p = llm.classify(failure, tier="small") if run.budget.allows_call() else None  # (c)
    score = calibrate(rule, votes, p)                                    # fitted on the benchmark
    if score.confidence >= MODEL_GATE:
        return memory.claim(failure, score.verdict)                      # (d) write back
    review.enqueue(kind="triage", node=failure.signature_node,
                   suggestion=score, evidence_dir=failure.evidence_dir)
    return None

# triage stage: for each failed result → triage(); apply_verdict() for every verdict returned

# testomation review → for each open review_item
def decide(item, decision):
    memory.claim(item.node, Verdict(decision, 1.0, "human"), basis=item.basis)
    memory.human_decision(item, decision)
    traces.score(item.trace_id, name="triage", value=decision)           # Langfuse from phase 3
    apply_verdict(item.node, decision)                                   # same function as triage
    review.close(item, decision)
```

## The exploration loop (the one LangGraph graph)

```
   start (seed page, budget)
      │
 ┌────▼─────────────┐
 │ snapshot         │  aria snapshot → normalised hash → new state?
 └────┬─────────────┘
 ┌────▼─────────────┐
 │ check invariants ├── violation ──► result row + draft reproducer spec
 └────┬─────────────┘
 ┌────▼─────────────┐
 │ choose action    │  small model · spec step vocabulary · on-origin only
 └────┬─────────────┘
 ┌────▼─────────────┐
 │ act              │  runs the step through the runner's step code (Q25)
 └────┬─────────────┘
      ├── budget spent, or no new state in N steps ──► stop
      └── otherwise ──► snapshot
```

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver

class Explore(TypedDict):
    seen: list[str]            # normalised aria hashes already visited
    steps_since_new: int
    trail: list[dict]          # spec steps taken so far; a finding replays them as a draft spec

g = StateGraph(Explore)
g.add_node("snapshot", snapshot)              # plain Python
g.add_node("invariants", check_invariants)    # console errors, 5xx, axe, overflow → result rows
g.add_node("choose", choose_action)           # the only model call: picks one spec step
g.add_node("act", act)                        # sends the step to the runner (Q25)
g.add_edge(START, "snapshot")
g.add_edge("snapshot", "invariants")
g.add_conditional_edges("invariants", lambda s: END if done(s) else "choose")
g.add_edge("choose", "act")
g.add_edge("act", "snapshot")

explorer = g.compile(checkpointer=PostgresSaver(conn))   # same Postgres as memory
```

Actions are spec steps, so every finding comes with a reproducer that can be saved as a
draft spec. Navigation off the target origin is aborted (D32).

## What this buys

- **Compute rules enforced in code** — memory → rules → neighbours → model is the shape of
  one function, and a unit test can assert it.
- **Review queue without paused graphs** — a review item is a row. The decision is written as
  a human claim, applied, and sent to traces as a score.
- **One place for state** — memory and `review_item` in Postgres; checkpoints only for
  exploration sessions.
- **Visible paths** — every step is a span, so you can see how many failures took the free
  path.

## Adopt LangGraph where loops are real

If the analyzer later needs a real loop (for example "fetch more evidence and ask again"),
or the planner's detail pass does (Q23), move that agent to LangGraph then. A straight-line
agent doesn't need a framework.

## When Temporal comes back

If Testomation spreads across several machines, needs many concurrent runs, or must survive
restarts in the middle of a stage, **Temporal replaces the pipeline runner** — stage for
stage. The agents and the exploration graph stay exactly where they are. Keeping stages as
idempotent functions now makes that swap cheap.
