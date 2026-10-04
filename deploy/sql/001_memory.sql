-- Memory schema v0 (draft). Source: docs/MEMORY_GRAPH.md → Storage.
-- Frozen as v1 in design step 2; mem_fact / mem_edge_fact views still to write.

CREATE EXTENSION IF NOT EXISTS vector;

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
