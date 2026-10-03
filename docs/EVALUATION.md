# Evaluation

> Source: `testomation.html` §11 (brief v0.5)

Without ground truth there's no way to tell whether a new prompt, threshold or model made
Testomation better or worse. Review-queue scores help, but they only exist once humans have
reviewed things. A **seeded-bug benchmark** works from day one — and matters more with small
local models, which are easier to make worse by accident.

## The benchmark

| Part | What |
|---|---|
| **Target app** | One small but realistic web app (auth, forms, CRUD, lists), run locally with a seeded database. A RealWorld ("Conduit") implementation is a good candidate. |
| **Hand-planted bugs** | ~20 across categories (below), each with an id, category and expected report. |
| **Mutation bugs** | A mutation-testing tool such as Stryker adds many small automatic bugs to the app's code. |
| **Toggles** | Every bug can be switched on/off (env flag or patch), so the same app runs clean or bugged. |

### Bug categories to cover

| Category | Example |
|---|---|
| Broken flow | Checkout button does nothing |
| Missing validation | Form accepts an empty email |
| Server error | Profile save returns 500 |
| Console error | Uncaught exception on the settings page |
| Layout break | Button overlaps text at phone width |
| Accessibility | Input without a label |
| Intentional flake | Element appears after a random delay |
| **Harmless noise** | Analytics request blocked — must **not** be reported |

## What gets measured

| Metric | Question it answers |
|---|---|
| Bug recall | Of the seeded bugs, how many were reported? |
| False-positive rate | How many reports on the clean app, or for planted noise? |
| Noise precision | When something was called noise, was it really noise? |
| Review-queue rate | How much work was pushed to a human? |
| Spec success rate | Share of generated specs that are valid and pass on the clean app within the repair cap |
| Model calls & time per run | What did it cost in compute? |
| Memory hit rate | How much did memory answer on a second run? |

## How it's used

- **`testomation bench`** runs the clean and bugged variants and scores them. Results go to
  `bench/results/<timestamp>.json` and to Langfuse as dataset runs.
- **Gate every change** — any prompt, model or threshold change reruns the benchmark before
  it's kept. A change that drops recall or raises false positives is rejected.
- **Calibrate thresholds** — the analyzer's gates (0.9 rules, 0.8 model) and sample count are
  set from benchmark precision/recall, then refined with review-queue scores.
- **Pick models** — the tier candidates in [LOCAL_SETUP.md](LOCAL_SETUP.md) compete here.
- **Set the budget** — starting values for `TESTO_BUDGET_CALLS` / `_SECONDS` come from what
  the benchmark needs to reach target recall.

## Phasing

| Phase | Benchmark role |
|---|---|
| 0 | Built; scores a hand-written spec suite |
| 2 | Baseline for the rules-only analyzer |
| 3 | Spec success rate for generation |
| 5 | Calibrates model thresholds; scores model-in-the-loop triage |
| 6 | Measures what exploration finds that specs didn't |

## Guard against overfitting

Keep a **held-out** set of seeded bugs that prompts are never tuned against, and rotate in
new mutation bugs periodically. If held-out recall lags tuned recall by a lot, prompts are
being fitted to the benchmark rather than improving.
