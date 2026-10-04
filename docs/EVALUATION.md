# Evaluation

> Source: `index.html` §11 (brief v0.6)

Without ground truth there's no way to tell whether a new prompt, threshold or model made
Testomation better or worse. Review-queue scores help, but they only exist once humans have
reviewed things. A **seeded-bug benchmark** works from day one. It matters even more with
small local models, which are easy to make worse by accident.

## The benchmark

| Part | What |
|---|---|
| **Target app** | One small but realistic web app (auth, forms, CRUD, lists), run locally with a seeded database: **Conduit** (RealWorld; React + Express + Postgres), vendored in `bench/app/` (D37). `bench/app/conduit.sh up` / `reset` start it on `:4100` and restore the seed in ~2 s. |
| **Hand-planted bugs** | ~20 across categories (below), each with an id, category, expected report and a `held_out` flag. |
| **Mutation bugs** | A mutation-testing tool such as Stryker adds many small automatic bugs. **Only detectable mutants count**: ones the hand-written reference spec suite kills. The rest change nothing a user could see and would only drag recall down. |
| **Toggles** | Every bug can be switched on/off (env flag or patch), so the same app runs clean or bugged. |
| **Replay bundles** | For each bug, the recorded evidence of its failure (`result` row + evidence folder + expected label), in `bench/replay/<bug-id>/`. Re-recorded when the app or the catalogue changes. |

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

## Two tiers

| Tier | Command | What runs | Takes | Gates |
|---|---|---|---|---|
| **Replay** | `testomation bench --replay` | Recorded failure evidence → analyzer only. No app, no browsers, no generation | Minutes | Every analyzer prompt, threshold, rule or model change |
| **Full** | `testomation bench` | Clean + bugged app → whole pipeline: generate, execute, triage | Hours | Generation, planning or model changes; nightly |

The full tier is too slow to run on every analyzer tweak, and a gate that's slow gets
skipped. The replay tier keeps the gate honest for the part that changes most often.

## What gets measured

| Metric | Question it answers |
|---|---|
| Bug recall | Of the seeded bugs, how many were reported? |
| False-positive rate | How many reports on the clean app, or for planted noise? |
| Noise precision | When something was called noise, was it really noise? |
| Review-queue rate | How much work was pushed to a human? |
| Spec success rate | Share of generated specs that are valid and pass on the clean app within 3 repair rounds |
| **Spec kill rate** | Share of generated specs that pass on the clean app **and fail** with their flow's seeded bug on. The spike showed pass rate alone rewards always-true assertions (Q29) |
| Model calls & time per run | What did it cost in compute? |
| Memory hit rate | How much did memory answer on a second run? |

**Report ranges, not single numbers.** With ~20 hand-planted bugs, one bug is 5 points of
recall, and the models are stochastic. Each benchmark run repeats **3 times** and reports
mean and min–max. A change is rejected if it moves recall down, or false positives up,
by more than the run-to-run range.

## How it's used

- **`testomation bench`** results go to `bench/results/<timestamp>.json` and, from phase 3,
  to Langfuse as dataset runs.
- **Gate every change** — analyzer changes on the replay tier; generation, planning and model
  changes on the full tier. A change that drops recall or raises false positives beyond the
  range is rejected.
- **Calibrate thresholds** — the rules gate, neighbour `k` and similarity, the model gate, and
  how label probability, neighbour vote and rules signal are combined (Q19) are fitted on
  benchmark precision/recall, then refined with review-queue scores.
- **Pick models** — the tier candidates in [LOCAL_SETUP.md](LOCAL_SETUP.md) compete here,
  including whether the `large` tier earns a place at all (D15).
- **Set the budget** — starting values for `TESTO_BUDGET_CALLS` / `_SECONDS` come from what
  the benchmark needs to reach target recall.

## Phasing

| Phase | Benchmark role |
|---|---|
| Spike | A handful of planted bugs and ~20 captured failures — enough to judge feasibility |
| 0 | Built; mutants filtered; replay bundles recorded; scores a hand-written spec suite |
| 2 | Baseline for the rules-only analyzer (both tiers) |
| 3 | Spec success rate; decides the `large` tier |
| 5 | Calibrates neighbours, logprob gate and budget; scores model-in-the-loop triage |
| 6 | Measures what exploration finds that specs didn't |

## Guard against overfitting

Keep a **held-out** set of seeded bugs that prompts are never tuned against — their replay
bundles are excluded from tuning too — and rotate in new detectable mutants periodically. If
held-out recall lags tuned recall by more than the run-to-run range, prompts are being fitted
to the benchmark rather than improving.
