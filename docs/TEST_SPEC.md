# Test Spec

> Source: `testomation.html` §05 (brief v0.5)

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
  "requirement": "REQ-142",
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

Each step is discriminated by `action`, which keeps the JSON Schema simple for constrained
decoding. The schema lives at `schemas/test-spec.schema.json` (planned).

## Step vocabulary

| Action | Fields | Notes |
|---|---|---|
| `goto` | `url` | Relative to the target's base URL |
| `click`, `hover` | `target` | |
| `fill`, `select` | `target`, `value` | Value may be a literal or a reference |
| `check`, `uncheck` | `target` | |
| `press` | `key`, optional `target` | |
| `upload` | `target`, `file` | `file` is a `$fixture` reference |
| `wait_for` | `target`, `state` | `visible` · `hidden` |
| `expect` | `target` or page, `assert`, `value` | `visible` · `hidden` · `hasText` · `hasValue` · `count` · `url` · `ariaSnapshot` |
| `api` | `method`, `path`, `body`, optional `expect` | Backend setup/verification via Playwright's request context |
| `viewport` | `preset` | `phone` · `tablet` · `desktop` |

## Targets

Exactly one of, in order of preference:

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

## Spec runner

- One Playwright Test file (`runner/spec-runner.spec.ts`) reads the run's spec files and
  registers one `test()` per spec.
- Each step runs inside `test.step()`, so steps appear by name in traces and the HTML report,
  and the failing step index is easy for the analyzer to read.
- Fixtures add: axe check after each navigation, Chromium JS coverage, aria snapshot on
  failure, saved auth state, route/HAR mocks.
- Output: Playwright JSON reporter results + evidence folder, ingested by Python.

**Exporter (later):** turns a spec into a readable `.spec.ts` for anyone who wants to own a
test outside Testomation.

## Lifecycle

```
draft    ──approve──►  approved
draft    ──reject───►  retired
approved ──flaky────►  quarantined ──fixed──► approved
approved ──obsolete─►  retired
```

Stored as `status` on the `TestCase` node (not inside the spec). Only `approved` specs run in
regression.

## Repair loop (drafts only)

```
run draft ─► fails ─► large model gets: spec + failing step + error + aria snapshot
                         │
                         ▼
                 corrected spec (schema-constrained) ─► validate ─► run again
                         │
                 after 3 attempts ─► review queue ("couldn't make it pass — real bug?")
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

- Source of truth: `TestCase.props.spec` (+ `status`) in the memory graph.
- Per run: materialised to `data/runs/<run>/specs/*.json` for the runner.
- Embeddings of specs (optional) help find similar specs to template from.
