# Feature Catalog

> Source: `index.html` §02 (brief v0.6)

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
| Structured test specs | Tests are JSON specs run by one Playwright runner; the model never writes executable code. Named helper steps cover what the core vocabulary can't. |
| Edge-case & negative-path enumeration | Boundary values, invalid inputs, error states alongside the happy path. |
| Coverage gap analysis | Flows/routes with no test touching them. *(graph query)* |
| Requirement-to-test traceability | Each test linked to the business rule that justified it — inferred by the planner and confirmed at approval in the MVP; user stories and issues later. *(graph query)* |
| Synthetic test data generation | `$faker` references produce realistic data at run time, no real PII. |
| Change-scoped model work | Given a diff, work out which flows to re-plan and which specs to regenerate. Every approved spec still runs. Static route → file map first; runtime coverage refines it. *(graph query)* |

## Memory & knowledge — core

| Feature | Description |
|---|---|
| Persistent app knowledge graph | Pages, flows, tests, bugs, commits, human decisions as linked nodes across runs. |
| Memory-first lookups | Check what's known before reasoning from scratch. |
| Claims with provenance | Every verdict — and every disputed link — records who asserted it, how sure, and the trace. Conflicting claims coexist. |
| Change-aware freshness | Each claim records the file and page-structure hashes it was based on. It's stale once they change, and fresh again after a revert. |

## Execution — core

| Feature | Description |
|---|---|
| Parallel runs | Playwright Test workers. The model is unloaded while specs run, so more workers fit; 2 while a model is loaded (exploration). |
| App state reset | Seeded DB restored before each run; a synthetic user per test. |
| Browser matrix | Chromium + Firefox on the laptop; WebKit via the Playwright container. |
| Responsive viewport testing | Phone, tablet, desktop breakpoints. |
| Visual regression diffing | Playwright's built-in screenshot comparison against a baseline. |
| Combined API + UI verification | Set up state via backend (`api` step), verify the frontend reflects it. |
| Accessibility auditing | axe-core on every page visited. |
| Auth & session handling | Saved Playwright storage state. |
| Third-party mocking | Route interception and HAR replay. |
| Per-branch environments *(later)* | Throwaway local compose environment per branch. |
| Exploratory session recording | Agent free-roams the target origin; every action and state change logged, and findings replay as draft specs — finds bugs nobody wrote a test for. |

## Bug detection & analysis — core

| Feature | Description |
|---|---|
| Triage for existing Playwright suites *(new)* | `testomation import` points the analyzer at any Playwright project's JSON report and traces — no Testomation specs needed. |
| Console & network error classification | Real app errors vs expected noise. |
| Severity & priority scoring | Blocked checkout outranks misaligned footer. |
| Deduplication | Error-signature hash first, local embeddings for borderline cases (`duplicate_of` links a human can reject). |
| Confidence scoring | Label probability from one model call (logprobs) + a vote of similar failures humans already labelled + the rules signal, calibrated on the benchmark — not the model's self-report. |
| Flaky test detection & quarantine | Pass/fail history per test; runs under heavy machine load excluded. |
| Multimodal visual bug detection *(later)* | Small local vision model on suspected layout bugs. |
| Root-cause suggestion *(later)* | Correlate failure timing with recent commits. *(graph query)* |
| Regression clustering *(later)* | Group failures from the same bug. *(graph query)* |

## Human-in-the-loop & collaboration — core

| Feature | Description |
|---|---|
| Review queue | `testomation review` CLI to approve / reject / edit uncertain items. Web UI later. |
| One-click test approval | Specs start as drafts; `testomation approve` promotes them and confirms their requirement. |
| Local run report | HTML/Markdown per run with repro steps and trace links, next to Playwright's HTML report. |
| Desktop notifications | When a run finishes or a bug is confirmed. |
| Inline annotation *(later)* | Comment on a screenshot or trace step. |
| GitHub Issues / Jira / Slack *(later)* | Tickets and channel posts once the tool leaves the laptop. |
| Audit trail | Every agent decision reviewable through claims and traces. |

## Evaluating Testomation itself — core

| Feature | Description |
|---|---|
| Seeded-bug benchmark | Local target app with toggleable known bugs; only detectable mutants count. |
| Regression runs on every change | Replay tier (recorded evidence through the analyzer, minutes) for analyzer changes; full tier for generation and model changes, and nightly. |
| Threshold calibration | Confidence gates set from benchmark precision/recall (reported as ranges over 3 runs), refined with review scores. |

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
| Test selection | Run only affected specs once the full suite gets slow (Q20). |

## Security & governance — later

| Feature | Description |
|---|---|
| Secrets management | `$secret` references resolved from the environment at run time; never stored. |
| PII redaction | Mask sensitive data in screenshots/logs. |
| Role-based access control | Who can approve tests, view evidence, change monitoring. |
| Sandboxed execution | Isolated browser sessions; specs not code, so nothing model-written runs on the host; specs and exploration never leave the target origin. |
