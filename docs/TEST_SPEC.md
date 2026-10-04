# Test Spec

> Source: `index.html` §05 (brief v0.6)

A test is **data, not code**. A model fills a JSON schema; one Playwright runner interprets it.

Why:

- Small local models fill a fixed schema far more reliably than they write free-form code.
- Ollama's structured output constrains decoding to the schema — invalid specs can't be produced.
- Nothing a model writes is executed on the laptop.
- Specs are easy to diff, dedupe, store in the memory graph, template and repair.
- Targets are limited to role/label/test-id by construction — no brittle CSS.

## Example

```json
{
  "spec_version": 1,
  "id": "checkout.guest.no-email",
  "flow": "guest-checkout",
  "requirement": "checkout.email-required",
  "steps": [
    { "action": "goto",   "url": "/cart" },
    { "action": "click",  "target": { "role": "button", "name": "Checkout" } },
    { "action": "fill",   "target": { "label": "Name" },  "value": { "$faker": "person.fullName" } },
    { "action": "fill",   "target": { "label": "Email" }, "value": "" },
    { "action": "click",  "target": { "role": "button", "name": "Place order" } },
    { "action": "expect", "target": { "role": "alert" },  "assert": "hasText", "value": "Email is required" }
  ]
}
```

`requirement` is optional. In the MVP it names a business rule the planner inferred or a
human added at approval (see [MEMORY_GRAPH.md](MEMORY_GRAPH.md#where-requirements-come-from-mvp)).

Each step is discriminated by `action`, which keeps the JSON Schema simple for constrained
decoding.

## One schema, two languages

- `schemas/test-spec.schema.json` is the **only** definition of a spec.
- Pydantic models (Python) and TypeScript types are **generated** from it — never edited by
  hand.
- `schemas/examples/` holds valid and invalid example specs. Both sides validate them in
  tests, so the brain and the hands can't drift.
- At generation time, the registered helper names are injected into the schema as an enum,
  so constrained decoding can only name helpers that exist.
- **The schema must be decoder-friendly (D38)**, because Ollama silently drops what it can't
  convert: each `anyOf` branch a complete typed object; every `pattern` anchored `^…$`;
  arrays capped (`steps.maxItems: 40`). `targets` are therefore an `anyOf` of five complete
  objects (`{testid}`, `{role, name?}`, `{label}`, `{placeholder}`, `{text}`).
- **Constraints the decoder enforces, so the model can't get them wrong:** `role` is an enum of
  the ARIA roles Playwright accepts (a model asked for `role: "input"` gets `textbox`), and a
  literal string value may not start with `$` (pattern `^([^$].*)?$`), so secrets and generated
  data must use the `$secret` / `$faker` / `$var` objects.
- `name` is only allowed on roles that can have an accessible name (D40). Paragraphs, list
  items and plain text are targeted with `{"text": ...}` — in an aria snapshot,
  `- listitem: Some text` is content, not a name.
- The schema file holds the validator-correct patterns; the llm client rewrites them into
  the form Ollama's grammar accepts when it builds a request (D39). Ollama also ignores
  `contains`, so "a spec must have an `expect`" is a lint rule, not a schema rule.

## Step vocabulary

| Action | Fields | Notes |
|---|---|---|
| `goto` | `url` | A path relative to the target's base URL — must start with `/` (`^/.*$`) |
| `click`, `hover` | `target` | |
| `fill`, `select` | `target`, `value` | Value may be a literal or a reference |
| `check`, `uncheck` | `target` | |
| `press` | `key`, optional `target` | |
| `upload` | `target`, `file` | `file` is a `$fixture` reference |
| `wait_for` | `target`, `state` | `visible` · `hidden` |
| `expect` | `target` or page, `assert`, `value` | `visible` · `hidden` · `hasText` · `hasValue` · `count` · `url` · `ariaSnapshot` |
| `api` | `method`, `path`, `body`, optional `expect` | Backend setup/verification via Playwright's request context; `path` must start with `/` |
| `viewport` | `preset` | `phone` · `tablet` · `desktop` |
| `helper` | `name`, `args` | Runs a registered, hand-written helper (see below) — *new in v0.6* |

## Targets

Exactly one of, in order of preference (each may add `"nth": n`, 0-based, when several
elements match — D41):

1. `testid`
2. `role` + `name`
3. `label`
4. `placeholder`
5. `text`

CSS and XPath are **not in the schema**.

## Value references

| Reference | Meaning |
|---|---|
| `{"$faker": "internet.email", "as": "email"}` | Synthetic data generated at run time (`@faker-js/faker`); `as` names it for reuse |
| `{"$var": "email"}` | Reuse a value generated earlier in the same spec |
| `{"$secret": "TEST_ADMIN_PASSWORD"}` | Credential resolved from the environment at run time; never stored |
| `{"$fixture": "invoice.pdf"}` | File from the project's fixtures folder |

## Growing the vocabulary: helper steps

Specs will need things the core vocabulary can't express — dialogs, downloads, iframes,
drag-and-drop, network assertions. Rather than growing the format into a programming
language:

- A human writes a **helper** in `runner/helpers/<name>.ts` exporting `name`, an `args` JSON
  Schema, and `run(page, args)`.
- A spec calls it with `{ "action": "helper", "name": "acceptDownload", "args": { … } }`.
- Models can only **name** registered helpers (the enum above); they never write one.
- A helper that many specs use can be promoted into the core vocabulary with a
  `spec_version` bump.

## Origin guard

- `goto.url` and `api.path` must be relative (schema pattern `^/`), so a spec can't point
  anywhere else.
- The runner resolves every path against `TESTO_TARGET_URL` and aborts top-level navigation
  to any other origin. Third-party subresources follow the mocking rules (`page.route` / HAR).
- Exploratory mode uses the same guard.

## Spec runner

- One Playwright Test file (`runner/spec-runner.spec.ts`) reads the run's spec files and
  registers one `test()` per spec.
- Each step runs inside `test.step()`, so steps appear by name in traces and the HTML report,
  and the failing step index is easy for the analyzer to read.
- Fixtures add: axe check after each navigation, Chromium JS coverage, aria snapshot on
  failure, saved auth state, route/HAR mocks, the origin guard, the helper registry.
- Output: Playwright JSON reporter results + evidence folder, ingested by Python as `result`
  rows.

**Exporter (later):** turns a spec into a readable `.spec.ts` for anyone who wants to own a
test outside Testomation.

## Lifecycle

```
draft    ──approve──►  approved
draft    ──reject───►  retired
approved ──flaky────►  quarantined ──fixed──► approved
approved ──obsolete─►  retired
```

Stored as `status` on the `test_case` row (not inside the spec). Only `approved` specs run in
regression — and all of them run, every run.

## Repair rounds (drafts only) — *changed in v0.6*

Repairs are **batched**, so the model and the browsers never compete for RAM:

```
round 1..3
  ├─ generate / repair every pending draft      model loaded (small tier)
  ├─ unload the model                           keep_alive: 0
  ├─ run every pending draft                    Playwright, full worker count
  └─ passing → ready for `testomation approve`
     failing → next round gets: spec + failing step + error + aria snapshot

after round 3, still failing → review queue ("couldn't make it pass — real bug?")
```

| Repair may | Repair may not (needs review) |
|---|---|
| Change a `target` | Change or remove an `expect` |
| Add `wait_for` or intermediate steps | Delete steps that lead to an `expect` |
| Fix `goto` URLs | Change `value`s that an `expect` depends on |

## Approved specs never self-heal

Any change to an approved spec — including a target that no longer resolves — is a **drift
signal** for the analyzer and a **review item**. This is what keeps "self-healing hides real
bugs" from happening. See [RISKS.md](RISKS.md).

## Storage

- Source of truth: `test_case.spec` (+ `status`) in the memory graph.
- Per run: materialised to `data/runs/<run>/specs/*.json` for the runner.
- Embeddings of specs (optional) help find similar specs to template from.
