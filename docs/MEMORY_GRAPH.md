# Memory Graph

> Source: `index.html` §06 (brief v0.6)

The memory graph is Testomation's **long-term knowledge about the app under test**: what
exists, what's been tested, what broke, why, and what humans decided.

It keeps things connected. A bug links to the component it affects, the commit that likely
caused it, the run that found it and the result that proves it, so any agent can follow
those links instead of re-deriving them.

It is **not an agent**. It's a shared store every agent reads before acting and writes after.

## Node kinds

| Group | Kinds |
|---|---|
| App structure | `Page`, `Component`, `Element`, `ApiEndpoint`, `SourceFile` |
| Test knowledge | `Flow`, `TestCase` (typed: spec + status), `Run` (typed) |
| Findings | `Bug` (typed), `NoiseSignature` (typed; errors known to be harmless), `Requirement` |
| History | `Commit` (typed), `HumanDecision` (approve / reject / annotate) |

**Not nodes:** `result` rows — one per test per run, holding the outcome, the failing step,
the error signature and the evidence paths. They replace v0.5's `Evidence` nodes, because
results are high-volume and nobody disputes them.

## Edges

```
Flow      —visits→           Page       —calls→     ApiEndpoint
Page      —renders→          Component  —contains→  Element
TestCase  —covers→           Flow
TestCase  —justified_by→     Requirement
TestCase  —touches→          SourceFile             (static map first, then coverage)
Commit    —changes→          SourceFile
Bug       —found_in→         Run
Bug       —affects→          Component
Bug       —likely_caused_by→ Commit
Bug       —duplicate_of→     Bug                    (fuzzy dedup; new in v0.6)
HumanDecision —confirmed | rejected→ Bug / TestCase
```

A `result` row points at its `Bug` or `NoiseSignature` through its `signature` column (the
node's key), not through an edge.

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
                                                       ▲  └─duplicate_of─► Bug
                                          confirmed | rejected
                                                       │
                                                HumanDecision

 result rows ──signature──► Bug / NoiseSignature        (a column, not an edge)
```

## Nodes, typed tables, edges and claims

| Table | Holds | Example |
|---|---|---|
| `mem_node` | Identity of every thing: kind, natural key, provenance, basis | `Bug` with key = error hash |
| Typed tables (`test_case`, `run`, `bug`, `noise_signature`, `git_commit`) | Undisputed facts for the busiest kinds, 1:1 with `mem_node` | `test_case.status = 'approved'` |
| `result` | One row per test per run, with evidence paths | `failed` at step 6, `data/evidence/run-…/checkout.guest.no-email/` |
| `mem_edge` | How two things relate; the row is the first claim about the link | `Bug —affects→ Component` |
| `mem_claim` | What one source asserts about a node field **or an edge** | `verdict = "bug"`, source `llm`, confidence 0.71 |
| `basis_state` | The current hash of every basis key | `file:src/pages/Checkout.tsx` → blob SHA |
| `mem_fact`, `mem_edge_fact` (views) | The resolved value per node + field, and the edges that currently hold | `verdict = "not_bug"` (human claim wins) |

**Where a value goes:** typed columns hold facts no source disputes (the spec, its status,
timestamps, paths). Anything a source can get wrong — a verdict, a severity, whether a
link holds — is a **claim**.

**Resolution rule** for each (node, field) and each edge:

1. Newest **fresh human** claim, if any.
2. Otherwise the **highest-confidence fresh** claim (newest on ties). For edges, the edge row
   itself counts as the first claim.
3. Stale claims are never returned as the answer; they're surfaced as hints.

Losing claims are kept — they're the audit trail and benchmark material.

Claim sources: `rules` · `knn` (vote of labelled neighbours) · `llm` · `human`.

## Freshness (basis hashes)

v0.5 marked memory `stale` by walking `changes → touches → renders` on every commit. Shared
files (layout, utils, API client) would have marked nearly everything stale on nearly every
commit. v0.6 makes freshness **computed**:

- Every node, edge and claim records a **basis**: the hashes of what it was based on.
  `{"file:src/pages/Checkout.tsx": "<blob sha>", "aria:/checkout": "<hash>"}`
- `basis_state` holds the **current** hash of each key. File hashes come from
  `git ls-tree -r HEAD` (blob SHAs, free) at the start of a run. Aria hashes come from the
  pages each run visits.
- A claim is **fresh** while every entry in its basis matches `basis_state`. A missing key
  counts as changed.
- A revert makes the old hashes match again, so the memory is fresh again. No invalidation
  job, nothing rewritten.
- Changes that don't come from git (seed data, config) still show up through aria hashes.

**Basis policy (draft — Q18):**

| Written by | Example | Basis |
|---|---|---|
| Planner | `Page`, `Element`, `Flow` nodes | `aria:<route>` + the route's source file |
| Test gen | A working target for an element | `aria:<route>` |
| Static map | `TestCase —touches→ SourceFile` | `spec:<id>` (hash of the spec) + the route file |
| Analyzer | Verdict on a `Bug` signature | Files the failing test touches + `aria:<route>` at the failing step |
| Human | Verdict, noise confirmation | Same basis as the claim being decided |
| Git ingest | `Commit —changes→ SourceFile` | None — commits are immutable |

An **empty basis** means "never stale". It's allowed only for kinds in the code-independent
list (proposed: `Commit`, `HumanDecision`, origin-kind `NoiseSignature`).

Aria snapshots are **normalised** before hashing: keep roles and accessible names, and mask
numbers, dates, faker-generated values and user-generated text (Q17). Otherwise every run
would produce a new hash.

## How it plugs into the pipeline

| | Step | What happens |
|---|---|---|
| a | **Look up** | Query the graph first. Known noise signature? Working target for this element? Flow already planned, and still fresh? |
| b | **Try deterministic tools** | Rules, parsers, crawlers, diffing, the labelled-neighbour vote. ([COST_STRATEGY.md](COST_STRATEGY.md)) |
| c | **Escalate to a local model** | Only what's still unanswered — with the **relevant neighbourhood** of the graph as context. |
| d | **Write back** | The answer becomes a **claim** stamped with source, confidence, trace ID and basis. |
| e | **Check freshness** | A claim counts only while its basis hashes match the current ones. Nothing is rewritten when code changes. |

## What each agent reads and writes

| Agent | Reads before acting | Writes after |
|---|---|---|
| Planner | Existing flows, pages with no covering test, bug-prone components | `Page`, `Component`, `Element`, `Flow`, `ApiEndpoint`, inferred `Requirement`s |
| Test gen | Targets that worked, similar specs, test data that passed validation | `TestCase` (spec + status) linked to flows and requirements |
| Executor | Stored auth state, endpoints to mock | `Run`, `result` rows, `touches` edges, aria hashes in `basis_state` |
| Analyzer | Noise signatures, labelled neighbours, past bugs on the same component, recent commits touching it | `Bug`, `NoiseSignature`, verdict claims, `duplicate_of` edges |
| Reporter | Affected requirements, owning module | Report paths (ticket IDs later) on `bug` |
| Pipeline runner | Changed files → `touches` / `renders` → flows and specs needing model work | `Commit` nodes, file hashes in `basis_state`, run/stage state |
| Review queue | Open `review_item` rows | Human claims, `HumanDecision` (also → trace scores) |

## Features that become graph queries

| Feature | Query |
|---|---|
| Coverage gap analysis | `Page`s with no incoming `covers` path |
| Model-work scope | changed files → `touches` / `renders` → flows to re-plan, specs to regenerate (every approved spec still runs — D26) |
| Traceability | test → `justified_by` → requirement |
| Dedup & regression clustering | results sharing a `signature`; `duplicate_of` edges for fuzzy matches |
| Root-cause suggestion | bug → component → recent commits touching it |
| Per-module health | bug and coverage counts rolled up per component |

## Trust rules

1. **Provenance on everything** — nodes, edges and claims all record source, confidence,
   trace ID and basis.
2. **Human beats model** — via the resolution rule above, for node fields **and edges**.
3. **No silent suppression** — a `NoiseSignature` inferred by a model (`llm` or `knn`) never
   hides a failure until a human confirms it.
4. **Stale until proven** — stale nodes and claims can *inform* an agent but can't
   *short-circuit* a decision, **including human claims**. "Stale" means the basis no longer
   matches.

## Storage

Postgres + **pgvector** ("is this error similar to a known one?"). Traversals are mostly 1–3
hops, which recursive CTEs handle. A dedicated graph DB is only worth it if traversals get
deep or slow. Embedding size follows the local embedding model: **768** for the current
candidate (`nomic-embed-text`). Change the column if the model changes.

```sql
-- nodes: the identity of everything the system knows about
CREATE TABLE mem_node (
  id          uuid PRIMARY KEY,
  project     text NOT NULL DEFAULT 'default',
  kind        text NOT NULL,        -- 'Page', 'Bug', 'TestCase', ...
  key         text NOT NULL,        -- natural key, e.g. route or error hash
  props       jsonb NOT NULL DEFAULT '{}',   -- only for kinds without a typed table
  embedding   vector(768),          -- optional; size of the local embed model
  source      text NOT NULL,        -- 'rules' | 'knn' | 'llm' | 'human'
  trace_id    text,                 -- trace that created it
  basis       jsonb NOT NULL DEFAULT '{}',   -- {"aria:/checkout": "…", "file:src/…": "…"}
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project, kind, key)
);

-- typed tables: 1:1 with mem_node for the busiest kinds
CREATE TABLE test_case (
  node_id      uuid PRIMARY KEY REFERENCES mem_node(id),
  spec         jsonb NOT NULL,      -- validated against schemas/test-spec.schema.json
  spec_version int  NOT NULL,
  status       text NOT NULL CHECK (status IN ('draft','approved','quarantined','retired'))
);

CREATE TABLE run (
  node_id      uuid PRIMARY KEY REFERENCES mem_node(id),
  trigger      text NOT NULL,       -- 'pr' | 'local' | 'bench' | 'import'
  commit_sha   text,
  started_at   timestamptz NOT NULL,
  finished_at  timestamptz,
  machine_load jsonb                -- free RAM, swap, load average
);

CREATE TABLE bug (
  node_id      uuid PRIMARY KEY REFERENCES mem_node(id),
  first_seen   uuid REFERENCES run(node_id),
  report_path  text,
  ticket_id    text                 -- later
);

CREATE TABLE noise_signature (
  node_id      uuid PRIMARY KEY REFERENCES mem_node(id),
  match_kind   text NOT NULL CHECK (match_kind IN ('signature','origin','pattern')),
  pattern      text NOT NULL        -- the hash, the third-party origin, or a regex
);

CREATE TABLE git_commit (
  node_id      uuid PRIMARY KEY REFERENCES mem_node(id),
  sha          text NOT NULL,
  parent_sha   text,
  committed_at timestamptz NOT NULL
);

-- results: one row per test per run (replaces v0.5 Evidence nodes)
CREATE TABLE result (
  id            uuid PRIMARY KEY,
  run_id        uuid NOT NULL REFERENCES run(node_id),
  test_case_id  uuid REFERENCES test_case(node_id),  -- null for imported Playwright tests
  external_test text,               -- 'file › title' for imported tests
  outcome       text NOT NULL,      -- 'passed' | 'failed' | 'timedOut' | 'skipped' | 'flaky'
  failing_step  int,
  signature     text,               -- normalised error-signature hash = Bug / NoiseSignature key
  evidence_dir  text NOT NULL,      -- data/evidence/<run>/<test>/
  duration_ms   int,
  CHECK (test_case_id IS NOT NULL OR external_test IS NOT NULL)
);

-- edges: how things relate; the row is the first claim about the link
CREATE TABLE mem_edge (
  id          uuid PRIMARY KEY,
  src         uuid NOT NULL REFERENCES mem_node(id),
  rel         text NOT NULL,        -- 'covers', 'touches', 'changes', ...
  dst         uuid NOT NULL REFERENCES mem_node(id),
  props       jsonb NOT NULL DEFAULT '{}',
  source      text NOT NULL,
  confidence  real NOT NULL DEFAULT 1.0,
  trace_id    text,
  basis       jsonb NOT NULL DEFAULT '{}',
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (src, rel, dst)
);

-- claims: what each source asserts about a node field or an edge; several can coexist
CREATE TABLE mem_claim (
  id          uuid PRIMARY KEY,
  node_id     uuid REFERENCES mem_node(id),
  edge_id     uuid REFERENCES mem_edge(id),
  field       text NOT NULL,        -- 'verdict', 'is_noise', 'severity', ...; 'holds' for edges
  value       jsonb NOT NULL,
  source      text NOT NULL,        -- 'rules' | 'knn' | 'llm' | 'human'
  confidence  real NOT NULL,
  trace_id    text,
  basis       jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  CHECK ((node_id IS NULL) <> (edge_id IS NULL))
);

-- current hash per basis key
CREATE TABLE basis_state (
  project     text NOT NULL,
  key         text NOT NULL,        -- 'file:src/pages/Checkout.tsx', 'aria:/checkout', 'spec:<id>'
  hash        text NOT NULL,        -- git blob SHA, normalised aria hash, spec hash
  observed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project, key)
);

-- fresh while every basis entry still matches basis_state
CREATE FUNCTION is_fresh(p text, b jsonb) RETURNS boolean AS $$
  SELECT NOT EXISTS (
    SELECT 1 FROM jsonb_each_text(b) e
    LEFT JOIN basis_state s ON s.project = p AND s.key = e.key
    WHERE s.hash IS DISTINCT FROM e.value)
$$ LANGUAGE sql STABLE;

-- items waiting for a human (see COMPONENTS.md → Review queue)
CREATE TABLE review_item (
  id           uuid PRIMARY KEY,
  kind         text NOT NULL,       -- 'triage' | 'draft_spec' | 'repair_assertion' | 'drift' | 'noise_confirm'
  node_id      uuid REFERENCES mem_node(id),
  suggestion   jsonb,               -- what the agent would have decided, with its score
  evidence_dir text,
  trace_id     text,
  status       text NOT NULL DEFAULT 'open',   -- 'open' | 'decided'
  decision     jsonb,
  created_at   timestamptz NOT NULL DEFAULT now(),
  decided_at   timestamptz
);
```

`mem_fact` is a view over `mem_claim` implementing the resolution rule with `is_fresh()`, so
agents read one value per node and field. `mem_edge_fact` does the same for edges.

### Natural keys (proposed)

| Kind | Key |
|---|---|
| `Page` | normalised route |
| `NoiseSignature` / `Bug` | hash of normalised error signature (origin-kind noise: the origin) |
| `SourceFile` | repo-relative path |
| `Commit` | SHA |
| `ApiEndpoint` | `METHOD /path` |
| `TestCase` | spec `id` |
| `Run` | run id |
| `Requirement` | slug, e.g. `checkout.email-required` |

Still to confirm for `Flow`, `Component`, `Element` — see [DECISIONS.md](DECISIONS.md) (Q4).

### Where requirements come from (MVP)

MVP ingest is a URL and a repo, with no user stories. So `Requirement` nodes come from:

- **Business rules the planner infers** ("checkout should fail without an email"), source
  `llm`.
- **Humans**, who confirm or edit the requirement when they approve a spec that's justified by
  it.

The spec's `requirement` field is optional. Importing user stories and issues comes later.

## Related

- Memory risks ("learns the wrong lesson", "stale looks fresh") → [RISKS.md](RISKS.md)
- Trace ID ↔ Langfuse → [OBSERVABILITY.md](OBSERVABILITY.md)
