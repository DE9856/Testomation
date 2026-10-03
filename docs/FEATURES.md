# Feature Catalog

> Source: `testomation.html` §02 (brief v0.5)

Every item is a **candidate** feature, grouped by where it sits in the system.

- **core** — what an MVP needs to be useful at all
- **later** — what turns a working tool into a platform

Items marked *(later)* inside a core group are individually later.

---

## Planning & test generation — core

| Feature | Description |
|---|---|
| Autonomous flow discovery | Crawls or reads the app and proposes the user flows worth testing. |
| Natural-language test authoring | "Test that guest checkout fails without an email" → runnable **spec**. |
| Structured test specs | Tests are JSON specs run by one Playwright runner; the model never writes executable code. |
| Edge-case & negative-path enumeration | Boundary values, invalid inputs, error states alongside the happy path. |
| Coverage gap analysis | Flows/routes with no test touching them. *(graph query)* |
| Requirement-to-test traceability | Each test linked to the story/spec line that justified it. *(graph query)* |
| Synthetic test data generation | `$faker` references produce realistic data at run time, no real PII. |
| Test impact analysis | Given a diff, rerun only affected tests. Static route → file map first; runtime coverage refines it. *(graph query)* |

## Memory & knowledge — core

| Feature | Description |
|---|---|
| Persistent app knowledge graph | Pages, flows, tests, bugs, commits, human decisions as linked nodes across runs. |
| Memory-first lookups | Check what's known before reasoning from scratch. |
| Claims with provenance | Every verdict records who asserted it, how sure, and the Langfuse trace. Conflicting claims coexist. |
| Change-aware invalidation | A commit touching a file marks dependent memory stale until re-verified. |

## Execution — core

| Feature | Description |
|---|---|
| Parallel runs | Playwright Test workers — 2 while a model is loaded, more otherwise. |
| App state reset | Seeded DB restored before each run; a synthetic user per test. |
| Browser matrix | Chromium + Firefox on the laptop; WebKit via the Playwright container. |
| Responsive viewport testing | Phone, tablet, desktop breakpoints. |
| Visual regression diffing | Playwright's built-in screenshot comparison against a baseline. |
| Combined API + UI verification | Set up state via backend (`api` step), verify the frontend reflects it. |
| Accessibility auditing | axe-core on every page visited. |
| Auth & session handling | Saved Playwright storage state. |
| Third-party mocking | Route interception and HAR replay. |
| Per-branch environments *(later)* | Throwaway local compose environment per branch. |
| Exploratory session recording | Agent free-roams; every action and state change logged — finds bugs nobody wrote a test for. |

## Bug detection & analysis — core

| Feature | Description |
|---|---|
| Console & network error classification | Real app errors vs expected noise. |
| Severity & priority scoring | Blocked checkout outranks misaligned footer. |
| Deduplication | Error-signature hash first, local embeddings for borderline cases. |
| Confidence scoring | Agreement across repeated model samples + rules signal, calibrated on the benchmark. |
| Flaky test detection & quarantine | Pass/fail history per test; runs under heavy machine load excluded. |
| Multimodal visual bug detection *(later)* | Small local vision model on suspected layout bugs. |
| Root-cause suggestion *(later)* | Correlate failure timing with recent commits. *(graph query)* |
| Regression clustering *(later)* | Group failures from the same bug. *(graph query)* |

## Human-in-the-loop & collaboration — core

| Feature | Description |
|---|---|
| Review queue | `testomation review` CLI to approve / reject / edit uncertain items. Web UI later. |
| One-click test approval | Specs start as drafts; `testomation approve` promotes them. |
| Local run report | HTML/Markdown per run with repro steps and trace links, next to Playwright's HTML report. |
| Desktop notifications | When a run finishes or a bug is confirmed. |
| Inline annotation *(later)* | Comment on a screenshot or trace step. |
| GitHub Issues / Jira / Slack *(later)* | Tickets and channel posts once the tool leaves the laptop. |
| Audit trail | Every agent decision reviewable through claims and Langfuse traces. |

## Evaluating Testomation itself — core *(new in v0.5)*

| Feature | Description |
|---|---|
| Seeded-bug benchmark | Local target app with toggleable known bugs. |
| Regression runs on every change | Prompt, model or threshold changes rerun the benchmark first. |
| Threshold calibration | Confidence gates set from benchmark precision/recall, refined with review scores. |

## Reporting & analytics — later

| Feature | Description |
|---|---|
| Live dashboard | Coverage, pass rate, flake rate, open bugs. |
| Trend graphs per release | Quality improving or degrading? |
| Per-module health scoring | Most bug-prone / worst-covered areas. *(graph query)* |
| Exportable reports | PDF/CSV for stakeholders. |
| LLM usage tracking | Tokens, latency and calls per run and per agent via Langfuse. |
| Custom alerting rules | "Notify me only if a payment flow breaks." |

## Platform & integration — later

| Feature | Description |
|---|---|
| CI/CD plugins | GitHub Actions, GitLab CI, CircleCI. |
| Event-driven triggers | On push, on deploy, nightly, on demand. |
| Public API / SDK | Script Testomation into other tooling. |
| Multi-project support | Several apps with isolated memory; `project` column exists from day one. |
| Production synthetic monitoring | Light suite continuously against prod. |
| Plugin architecture | Custom checks without forking. |

## Security & governance — later

| Feature | Description |
|---|---|
| Secrets management | `$secret` references resolved from the environment at run time; never stored. |
| PII redaction | Mask sensitive data in screenshots/logs. |
| Role-based access control | Who can approve tests, view evidence, change monitoring. |
| Sandboxed execution | Isolated browser sessions; specs not code, so nothing model-written runs on the host. |
