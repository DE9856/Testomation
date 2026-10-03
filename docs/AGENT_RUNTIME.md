# Agent Runtime: pipeline outside, LangGraph inside

> Source: `testomation.html` §09 (brief v0.5)

Testomation has **two different orchestration problems**:

- **Job work** — running tests in parallel, retrying failures, moving a run through its stages.
- **Reasoning control flow** — inside one agent, deciding whether memory answered a question,
  whether the rules engine is sure, whether to ask a human.

On one laptop, the job side doesn't need Temporal. **A plain pipeline runner and Playwright
Test on the outside, LangGraph on the inside.**

| Concern | Pipeline runner + Playwright Test | LangGraph |
|---|---|---|
| Unit of work | A whole run: impact analysis, execution, triage, reporting | One agent's decision on one item |
| Parallelism | Playwright workers for tests; model calls one at a time | Within a single graph, if at all |
| Durability | Stage state in Postgres; crashed run resumes at last completed stage | Graph state checkpointed per step to Postgres |
| Branching | Fixed sequence of stages | Conditional edges: memory hit, confidence, budget |
| Humans | — | `interrupt()` pauses a graph until the review queue answers |

## How a run nests

```
testomation run --pr 412              pipeline runner · stage state in Postgres
 ├─ stage: invalidate + impact         plain code · memory-graph query
 ├─ stage: run affected specs          npx playwright test · workers=2 · retries=1
 ├─ stage: triage failures          →  Analyzer graph, one thread per failure
 ├─ stage: generate missing tests   →  Test-gen graph (spec → run → repair, capped)
 └─ stage: report                      plain code · local HTML / Markdown
```

Stages are idempotent functions. Each stage that needs reasoning invokes a small, focused
graph. Everything else stays plain code.

## Where LangGraph is used — and where it isn't

| Use it | Why |
|---|---|
| **Analyzer** (first, best fit) | Memory → rules → model → confidence gate → file or pause for review |
| **Test gen** | Generate spec → run → read error → repair, hard retry cap |
| **Planner** | Crawl → parse → rank → go back for detail on high-value areas |
| **Exploratory agent** | Natural loop; stops on budget exhausted or no new states |

| Don't use it | Why |
|---|---|
| Spec execution | Playwright running a spec has no decisions; a graph is pure overhead |
| Reporter | Templated output — a plain function is enough |
| The pipeline | Stage order, resumption and parallel test runs stay in the runner and Playwright |
| The memory graph | LangGraph's long-term store is key-value, not linked. Agents reach Postgres memory via lookup/write-back **nodes** |

## The analyzer as a graph

```
         failure
            │
   ┌────────▼────────┐
   │  memory lookup  ├─ human-confirmed, fresh ┐
   └────────┬────────┘                         │
            │ miss / unconfirmed / stale       │
   ┌────────▼────────┐                         │
   │   rules engine  ├─ confident ──────┐      │
   └────────┬────────┘                  │      │
            │ unsure                    │      │
   ┌────────▼────────┐                  │      │
   │ LLM classify ×3 │                  │      │
   │ (if budget left)│                  │      │
   └────────┬────────┘                  │      │
            │ agreement                 │      │
   ┌────────▼────────┐                  │      │
   │ confidence gate ├─ low ───┐        │      │
   └────────┬────────┘         │        │      │
            │ high      ┌──────▼──────┐ │      │
            │           │ interrupt() │ │      │
            │           │ review queue│ │      │
            │           └──────┬──────┘ │      │
            │                  │        │      │
   ┌────────▼────────┐                  │      │
   │    write back   │◄────────┴────────┴──────┘
   │ claim in memory │
   └────────┬────────┘
            │
            ▼
   file bug · add noise signature · link dupe
```

Every box except **LLM classify** is plain Python. A cheap path never touches a model.

### Gates

| Gate | Rule | Otherwise |
|---|---|---|
| Memory | Fresh human claim → write | Rules engine |
| Rules engine | `confidence >= 0.9` → write | LLM classify |
| LLM classify | 3 samples from the small tier; confidence = share that agree | — |
| Confidence gate | `confidence >= 0.8` → write | Human review (`interrupt()`) |
| Budget spent | LLM node sets `confidence = 0` | Human review |

0.9 and 0.8 are **placeholders** until the benchmark calibrates them ([EVALUATION.md](EVALUATION.md)).
With 3 samples, agreement is 0.33 / 0.67 / 1.0 — so "≥ 0.8" means unanimous. Calibration may
change the sample count, too.

## Sketch

```python
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.postgres import PostgresSaver
from langfuse.langchain import CallbackHandler

class Triage(TypedDict):
    failure: dict
    verdict: Optional[dict]
    confidence: float
    source: str                     # 'memory' | 'rules' | 'llm' | 'human'

def memory_lookup(s): ...           # plain Python; only fresh human claims count as a hit
def rules_engine(s):  ...           # plain Python, no model
def llm_classify(s):  ...           # the ONLY node that calls a model (local, small tier);
                                    # 3 samples, confidence = agreement;
                                    # confidence=0 if the run's compute budget is spent
def review(s):
    decision = interrupt({"failure_id": s["failure"]["id"]})   # graph pauses here
    return {"verdict": decision, "source": "human", "confidence": 1.0}
def write_back(s):    ...           # memory.claim(verdict, source=s["source"], ...)

g = StateGraph(Triage)
for name, fn in [("memory", memory_lookup), ("rules", rules_engine),
                 ("llm", llm_classify), ("review", review), ("write", write_back)]:
    g.add_node(name, fn)

g.add_edge(START, "memory")
g.add_conditional_edges("memory", lambda s: "write" if s["source"] == "human" else "rules")
g.add_conditional_edges("rules",  lambda s: "write" if s["confidence"] >= 0.9 else "llm")
g.add_conditional_edges("llm",    lambda s: "write" if s["confidence"] >= 0.8 else "review")
g.add_edge("review", "write")
g.add_edge("write", END)

analyzer = g.compile(checkpointer=PostgresSaver(conn))   # same Postgres as memory

# inside the pipeline's triage stage
cfg = {"configurable": {"thread_id": f"triage-{failure['id']}"},
       "callbacks": [CallbackHandler()]}                  # every node -> Langfuse span
analyzer.invoke({"failure": failure}, config=cfg)

# later, when a reviewer decides in `testomation review`
analyzer.invoke(Command(resume=reviewer_decision), config=cfg)
```

## What this buys

- **Compute rules enforced in code** — memory → rules → model is the graph's *shape*.
- **Review queue for free** — an interrupted graph *is* a review item. The decision resumes
  it, is written as a human claim, and sent to Langfuse as a score.
- **Crash-safe exploration** — checkpoints in the same Postgres as memory.
- **Visible paths** — every node is a span; see how many failures took the free path.

## Adopt it incrementally

Build the **analyzer** as a graph first (phase 5). Move other agents over only when their
logic actually branches or loops — a straight-line agent doesn't need a framework.

## When Temporal comes back

If Testomation spreads across several machines, needs many concurrent runs, or must survive
restarts in the middle of a stage, **Temporal replaces the pipeline runner** — stage for
stage — and LangGraph stays exactly where it is. Keeping stages as idempotent functions now
makes that swap cheap.
