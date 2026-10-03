# Memory Graph

> Source: `testomation.html` §06 (brief v0.5)

The memory graph is Testomation's **long-term knowledge about the app under test**: what
exists, what's been tested, what broke, why, and what humans decided.

It keeps things connected — a bug links to the component it affects, the commit that likely
caused it, the test that found it, and the evidence that proves it — so any agent can follow
those links instead of re-deriving them.

It is **not an agent**. It's a shared store every agent reads before acting and writes after.

## Node kinds

| Group | Kinds |
|---|---|
| App structure | `Page`, `Component`, `Element`, `ApiEndpoint`, `SourceFile` |
| Test knowledge | `Flow`, `TestCase` (holds spec + status), `Run`, `Evidence` (path in the evidence folder) |
| Findings | `Bug`, `NoiseSignature` (errors known to be harmless), `Requirement` |
| History | `Commit`, `HumanDecision` (approve / reject / annotate) |

## Edges

```
Flow      —visits→           Page       —calls→     ApiEndpoint
Page      —renders→          Component  —contains→  Element
TestCase  —covers→           Flow
TestCase  —justified_by→     Requirement
TestCase  —touches→          SourceFile             (static map first, then coverage)
Commit    —changes→          SourceFile             (new in v0.5)
Bug       —found_in→         Run
Bug       —affects→          Component
Bug       —likely_caused_by→ Commit
Evidence  —matches→          NoiseSignature
HumanDecision —confirmed | rejected→ Bug / TestCase
```

### Picture

```
 Requirement ◄─justified_by── TestCase ──covers──► Flow ──visits──► Page ──calls──► ApiEndpoint
                                  │                                   │
                               touches                             renders
                                  ▼                                   ▼
                             SourceFile ◄──changes── Commit        Component ──contains──► Element
                                                       ▲              ▲
                                               likely_caused_by    affects
                                                       │              │
                          Run ◄──found_in─────────── Bug ─────────────┘
                                                       ▲
                                          confirmed | rejected
                                                       │
                                                HumanDecision

 Evidence ──matches──► NoiseSignature
```

## Nodes, edges and claims

v0.4 gave each node one `source` and one `confidence`. That can't hold an LLM verdict and a
human verdict about the same bug at the same time, which "human beats model" needs. v0.5
separates them:

| Table | Holds | Example |
|---|---|---|
| `mem_node` | Identity and description of a thing | `Bug` with key = error hash |
| `mem_edge` | How two things relate, with provenance | `Bug —affects→ Component` |
| `mem_claim` | What one source asserts about a node field | `verdict = "bug"`, source `llm`, confidence 0.67 |
| `mem_fact` (view) | The resolved value per node + field | `verdict = "not_bug"` (human claim wins) |

**Resolution rule** for each (node, field):

1. Newest **non-stale human** claim, if any.
2. Otherwise the **highest-confidence non-stale** claim (newest on ties).
3. Stale claims are never returned as the answer; they're surfaced as hints.

Losing claims are kept — they're the audit trail and benchmark material.

## How it plugs into the pipeline

| | Step | What happens |
|---|---|---|
| a | **Look up** | Query the graph first. Known noise signature? Working target for this element? Flow already planned with nothing changed since? |
| b | **Try deterministic tools** | Rules, parsers, crawlers, diffing. ([COST_STRATEGY.md](COST_STRATEGY.md)) |
| c | **Escalate to a local model** | Only what's still unanswered — with the **relevant neighbourhood** of the graph as context. |
| d | **Write back** | Answer becomes a **claim** stamped with source, confidence, Langfuse trace ID. |
| e | **Invalidate on change** | Commit → `changes` → files → `touches`/`renders` → mark dependent nodes, edges and claims `stale`. |

## What each agent reads and writes

| Agent | Reads before acting | Writes after |
|---|---|---|
| Planner | Existing flows, pages with no covering test, bug-prone components | `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint` |
| Test gen | Targets that worked, similar specs, test data that passed validation | `TestCase` (spec + status) linked to flows and requirements |
| Executor | Stored auth state, endpoints to mock | `Run`, `Evidence` paths, `touches` edges |
| Analyzer | Noise signatures, past bugs on same component, recent commits touching it | `Bug`, `NoiseSignature`, verdict claims, dedup links |
| Reporter | Affected requirements, owning module | Report paths (ticket IDs later) on `Bug` |
| Pipeline runner | Commit → `changes` → `touches` → affected specs | `Commit` nodes, stale flags |
| Review queue | Low-confidence claims awaiting a human | Human claims, `HumanDecision` (also → Langfuse scores) |

## Features that become graph queries

| Feature | Query |
|---|---|
| Coverage gap analysis | `Page`s with no incoming `covers` path |
| Test impact analysis | commit → `changes` → files → `touches` → tests to rerun |
| Traceability | test → `justified_by` → requirement |
| Dedup & regression clustering | failures sharing a component **and** an error signature |
| Root-cause suggestion | bug → component → recent commits touching it |
| Per-module health | bug and coverage counts rolled up per component |

## Trust rules

1. **Provenance on everything** — nodes, edges and claims all record source, confidence and trace ID.
2. **Human beats model** — via the claim resolution rule above.
3. **No silent suppression** — an LLM-inferred `NoiseSignature` never auto-hides a failure
   until a human confirms it.
4. **Stale until proven** — stale nodes and claims can *inform* an agent but can't
   *short-circuit* a decision, **including human claims**.

## Storage

Postgres + **pgvector** ("is this error similar to a known one?"). Traversals are mostly 1–3
hops — recursive CTEs handle that. A dedicated graph DB only if traversals get deep or slow.
Embedding size follows the local embedding model: **768** for the current candidate
(`nomic-embed-text`). Change the column if the model changes.

```sql
-- nodes: the things the system knows about
CREATE TABLE mem_node (
  id          uuid PRIMARY KEY,
  project     text NOT NULL DEFAULT 'default',
  kind        text NOT NULL,        -- 'Page', 'Bug', 'TestCase', ...
  key         text NOT NULL,        -- natural key, e.g. route or error hash
  props       jsonb NOT NULL DEFAULT '{}',
  embedding   vector(768),          -- optional; size of the local embed model
  source      text NOT NULL,        -- who created it: 'rules' | 'llm' | 'human'
  trace_id    text,                 -- Langfuse trace that created it
  stale       boolean NOT NULL DEFAULT false,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project, kind, key)
);

-- edges: how those things relate, with the same provenance
CREATE TABLE mem_edge (
  src         uuid REFERENCES mem_node(id),
  rel         text NOT NULL,        -- 'covers', 'touches', 'changes', ...
  dst         uuid REFERENCES mem_node(id),
  props       jsonb NOT NULL DEFAULT '{}',
  source      text NOT NULL,
  confidence  real NOT NULL DEFAULT 1.0,
  trace_id    text,
  stale       boolean NOT NULL DEFAULT false,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (src, rel, dst)
);

-- claims: what each source asserts about a node; several can coexist
CREATE TABLE mem_claim (
  id          uuid PRIMARY KEY,
  node_id     uuid NOT NULL REFERENCES mem_node(id),
  field       text NOT NULL,        -- 'verdict', 'is_noise', 'severity', ...
  value       jsonb NOT NULL,
  source      text NOT NULL,        -- 'rules' | 'llm' | 'human'
  confidence  real NOT NULL,
  trace_id    text,
  stale       boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);
```

`mem_fact` is a view over `mem_claim` implementing the resolution rule, so agents read one
value per node and field.

### Natural keys (proposed)

| Kind | Key |
|---|---|
| `Page` | normalised route |
| `NoiseSignature` / `Bug` | hash of normalised error signature |
| `SourceFile` | repo-relative path |
| `Commit` | SHA |
| `ApiEndpoint` | `METHOD /path` |
| `TestCase` | spec `id` |
| `Run` | run id |

Still to confirm for `Flow`, `Component`, `Element` — see [DECISIONS.md](DECISIONS.md).

## Related

- Memory risks ("learns the wrong lesson", "stale looks fresh") → [RISKS.md](RISKS.md)
- Trace ID ↔ Langfuse → [OBSERVABILITY.md](OBSERVABILITY.md)
