# Spike Results

> Design step 1 ([DESIGN_ROADMAP.md](DESIGN_ROADMAP.md#step-1--feasibility-spike)). **In progress.**
> Raw numbers in `spike/results/`. Started 2026-10-04.

## Setup

| Piece | State |
|---|---|
| Target app | Conduit in `bench/app/` on `:4100`; 4 users, 12 articles; reset ~2.3 s (D37) |
| Ollama | 0.35.0, system service, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1` (drop-in `/etc/systemd/system/ollama.service.d/testomation.conf`) |
| Models | `qwen3:4b`, `gemma3:4b` (small candidates), `qwen3:8b`, `qwen2.5:7b` (large candidates), `nomic-embed-text` (embed, 768-d confirmed) — all Q4_K_M |

## Model fit and speed (RTX 3050 4 GB, `spike/model_fit.py`)

Warm runs, `temperature 0`, `think: false`, 256-token answer. Ollama's default layer placement:

| Model | Context | On GPU | Prompt tok/s | Gen tok/s |
|---|---|---|---|---|
| qwen3:4b | 4k | 87% | 433 | 43.6 |
| qwen3:4b | 8k | 72% | 254 | 32.7 |
| gemma3:4b | 4k | 54% | 222 | 30.3 |
| gemma3:4b | 8k | 52% | 204 | 29.6 |
| qwen2.5:7b | 8k | 50% | 153 | 15.7 |
| qwen3:8b | 8k | 43% | 94 | 12.7 |

**Forcing all layers onto the GPU (`num_gpu: 99`):**

| Model | Context | On GPU | VRAM used | Prompt tok/s | Gen tok/s |
|---|---|---|---|---|---|
| qwen3:4b | 4k | 100% | 3138 MiB | 346 | 55.3 |
| qwen3:4b | 8k | 100% | 3718 MiB | 344 | 55.2 |

### Findings so far

1. **Ollama's default placement leaves ~1.2 GB of VRAM unused** (it stops near 2.8 GB of 4 GB).
   Forcing full offload puts `qwen3:4b` entirely on the GPU even at 8k context, and
   generation goes from 33 → 55 tok/s. The llm client should pass `num_gpu` per tier
   (configuration, not code). Headroom at 8k is ~380 MiB, so this needs the GPU free of other
   work — the desktop currently uses ~12 MiB.
2. **`gemma3:4b` doesn't fit as well** as `qwen3:4b` (52–54% on GPU at default placement;
   its vision weights add size) and is ~half the speed. Full offload crashes (see Toolchain).
3. **The large tier is ~3–4× slower** (12–16 tok/s, under half on GPU). A ~500-token spec
   takes ~35–40 s per generation before repairs. It has to earn its place on quality (D15).
4. **First loads are slow** (up to ~24 s cold from disk vs 3–6 s warm) — keep the model
   loaded for a whole batch, as the design already says.
5. `think: false` works for `qwen3` through the native API. Thinking must stay off for
   structured output (see Toolchain).

## Toolchain (Q13) — `spike/toolchain_check.py`, `schema_variants.py`, `grammar_probe.py`

Three described Conduit flows → spec; three triage cases → verdict. Native `/api/chat`, `/v1`
via the OpenAI SDK, and `/v1` via `langfuse.openai` (wrapper only; no Langfuse server).

| Question | Answer |
|---|---|
| Does `format` / `response_format` enforce our spec schema? | **Not as first written — 0/3 schema-valid.** The `target` def was `type: object` + `properties` + a `oneOf` of bare `{"required": [...]}` branches. Ollama's converter follows the `oneOf` and drops the siblings, so every branch is untyped and `target` became "any value" (`"target": "Email"`). It logs only pattern warnings, so the drop is **silent** |
| After making each `target` branch a complete object and anchoring patterns (`^/.*$`)? | **3/3 schema-valid** on `qwen3:4b` (native, `/v1`, `langfuse.openai`) and on `gemma3:4b` native. Minimal probes confirm nested objects, `anyOf` of objects and enums are all enforced |
| Unanchored `pattern` (`^/`)? | Skipped with a warning ("accepting any string") — anchor every pattern with `^…$` |
| Runaway output? | `gemma3:4b` via `/v1` looped the same step for 678 lines until truncated (invalid JSON, ~150 s). Fixed in the schema with `steps.maxItems: 40`, which the decoder enforces |
| qwen3 thinking + structured output? | Works on a tiny prompt, but spends 7–28k chars of reasoning per spec, takes 90–140 s instead of 4–9 s, gave no better specs, and on real prompts overflowed the 8k context (HTTP 500). **Thinking off** |
| Logprobs? | **Yes — native, `/v1`, and through `langfuse.openai`**, identical values. The verdict token's `top_logprobs` give a label distribution |
| Triage on 3 easy cases | Both models 3/3 correct. `qwen3:4b` gives graded probabilities (0.969 / 0.973 / 0.999); `gemma3:4b` gives 1.0 for everything — useless for calibration |
| `gemma3:4b` full GPU offload | llama-server **crashes** (core dump) with the vision projector on GPU; Ollama falls back to projector on CPU |

### Schema-valid is not the same as sensible

With a bare prompt (no step vocabulary, no examples, no page snapshot), the valid specs are
still poor:

- `qwen3:4b` invents ARIA roles (`"role": "input"`, `"role": "Article Title"`), uses `check`
  (tick a checkbox) as if it were an assertion, writes `$secret`/`$faker` as plain strings
  (`"$secret:ALICE_PASSWORD"`, `"faker_email"`), and often has no `expect` step.
- `gemma3:4b` turns UI flows into `api` calls against UI routes (`POST /login`).

Most of this is expected from the prompt, which explained nothing. Two fixes belong in the
**schema**, where the decoder enforces them: `role` as an enum of real ARIA roles, and
literal string values that start with `$` disallowed. The rest is prompt work: the step
vocabulary, 2–3 example specs, and the page's aria snapshot. That's the spec-generation step.

### Toolchain verdict

- **Q13: yes, with a decoder-friendly schema.** Structured output and logprobs both work
  through `/v1` and `langfuse.openai`, so the planned llm client design stands.
- **Small-tier lead: `qwen3:4b`** — fits fully on GPU, 55 tok/s, graded logprobs.
  `gemma3:4b` is slower, can't fully offload, loops, and its probabilities are all 1.0.

## Spec generation — `spike/specgen.py`

10 flows described in plain English (login, wrong password, sign-up, publish, comment, tag
filter, favorite, followed feed, profile, bio). Prompt: step vocabulary, routes, each page's
trimmed aria snapshot, 2 verified example specs (different flows). Per round: generate/repair
all → unload model → reset Conduit → run all (2 workers) → failures go back with the failing
step, the error and the aria snapshot at failure. ≤ 3 repair rounds. A spec counts only if it
passes on the clean app, contains an `expect`, and no repair changed an assertion.

| Run | Pass (target ≥ 7) | Passing after round 0/1/2/3 | Avg s per generation |
|---|---|---|---|
| `qwen3:4b`, prompt v1 | 3/10 | 2 / 4 / 4 / 4 (one needed a changed assertion) | 8.4 |
| `qwen3:4b`, prompt v2 (targeting rules spelled out) | 3/10 | 3 / 3 / 3 / 3 | 8.2 |
| `qwen3:4b`, v2 + schema v3 + expect-target repair | **4/10** | 3 / 4 / 4 / 4 | 7.9 |
| `qwen3:8b`, prompt v1 | 2/10 | 2 / 2 / 2 / 2 | 40.7 |
| `qwen3:8b`, prompt v2 | 2/10 | 2 / 2 / 2 / 2 | 42.0 |

Prompts are ~3.4–3.8k tokens; specs ~340 tokens. A full 10-flow run with repairs takes ~6 min
on 4b and ~25 min on 8b. Raw: `spike/results/specgen_*`.

### What failed, and why

| Cause | Flows | Fixable by |
|---|---|---|
| **Snapshot text content treated as an accessible name** (`- listitem: Wrong email…` → `{role: listitem, name: …}`, which never matches) | 02, 05, 10 | **Schema**: `name` only on roles that can have one (adopted, D40) — fixed flow 05. A prompt rule (v2) changed nothing |
| **Guessing what the page shows after an action** (bio location, error element, author names as headings, what a tag click shows) — the model never sees the page *after* its steps | 02, 06, 08, 10 | Not by repairs: assertions are frozen, and allowing expect-*target* repairs (v3a) recovered none. Needs the model to observe the real outcome (Q26) |
| **Generated value asserted as a literal** (fills `$faker`, then expects `"Generated bio text"`) | 10 | Prompt/lint: an `expect` value that echoes a filled field should use the same `$var` |
| **No `expect` at all**, even after the lint repair message, every round | 07 | Lint keeps it out of the suite. JSON Schema `contains` would force it, but **Ollama ignores `contains`** silently |
| **Duplicate elements** (two "Favorite ( 0 )" buttons; strict mode refuses to guess) | 07 | Schema gap: no way to say "the first one" (Q27) |
| **Login not finished before navigating** | 04 | Example/prompt; the examples already show waiting for "Your Feed" |
| Runaway / crash on one flow (`qwen3:8b`, flow 10: HTTP 500 after 85 s, every time) | 10 (8b) | `num_predict` cap + treat a failed call as a failed generation (done in the harness) |

### Schema and decoder lessons (all verified)

- **Constrain, don't instruct.** Everything moved by the decoder worked first time (role enum,
  no `$` literals, no names on paragraphs); the same rules as prompt text were ignored.
- **Ollama silently ignores** `contains`/`minContains`, unanchored patterns, and patterns using
  `\s` in a class — the whole constraint is dropped, not partly enforced.
- **Some regexes break the grammar outright.** `(.|\n)*` in a string pattern made strings stop
  closing: JSON broke on 8 of 10 flows and output tripled. Validators need that form for
  multi-line text, Ollama needs `.*`. So the schema file keeps the validator form and the **llm
  client rewrites it for the decoder** (D39).

### Verdict on spec generation

**Target missed: 4/10 at best vs ≥ 7/10.** Per the exit gate, the plan should change before
building phase 3 as designed:

1. **The large tier is out** (D15): `qwen3:8b` is 5× slower and scored lower. Drop `large` from
   the default setup; revisit only with a different model family.
2. **Free-text-to-spec without seeing the outcome doesn't work at 4B.** Half the failures are
   the model guessing what the page shows after its actions. The strongest candidate fix is
   **observe-then-assert generation** (Q26): run the action steps first, show the model the
   real resulting snapshot, then let it write the `expect`s, judged against the flow's stated
   expectation. That's one more spike experiment before deciding.
3. **Template-first generation stays important** (login, form submit, CRUD from templates, model
   only for the rest), and the schema should keep absorbing every mistake that can be made
   impossible.

## Observe-then-assert (Q26) — `spike/observe.py`

Same 10 flows. The model writes **action steps only** (`expect` removed from the decoder's
schema); actions run on a fresh app with ≤ 3 batched repair rounds; once they run cleanly, the
runner records the settled final page and the generated values; then the model writes the
`expect`s from the flow's stated expectation + that real page; then the whole spec is verified
on a fresh app (no assertion repairs). ~5 min per run.

| Run | Actions run cleanly | Spec passes | **Checks the stated outcome** |
|---|---|---|---|
| First try (final snapshot taken before the page settled — harness bug) | 7/10 | 5/10 | 1/10 — asserted a "Loading…" message, the sign-up form it had just left, an invented error text |
| Page settled first (`networkidle` + 500 ms), faker paths as an enum | 7/10 | 3/10 | **2/10** (login shows alice; wrong password shows the real error) |

For comparison, the best direct-generation run (v3a, "4/10 pass") also checks the stated outcome
in only **~1.5/10**: one real check (bob's three articles), one partial ("Your Feed" visible —
proves a login, not that alice is shown), two hollow ("Home" link visible; "a paragraph" visible).

### What observing fixed, and what it didn't

- **Fixed: outcomes the model couldn't see.** With the real page in front of it, the model found
  the actual error text (`Wrong email/password combination`) on the first try.
- **New failure: missing preconditions.** In the actions-only prompt the model dropped "as
  alice" twice (no login steps → editor and comment box never appear), and repairs from a
  logged-out page couldn't infer it. A **login template** solves this without a model.
- **Still ignored: `$var` for generated values.** It asserted the literal generated username
  (`"Aurelia84"`), which changes every run. Fixable **deterministically**: the runner knows every
  generated value, so literals equal to one can be rewritten to `{"$var": …}` automatically.
- **Wrong target form for links:** it used a link's full accessible name
  (`"Carol's post 1 Post 1 by carol Read more…"`) as `text`. Fixable by a deterministic rewrite
  (text equal to a link's name in the snapshot → `{role: link, name}`), or by pointing at the
  heading inside.
- **Hollow assertions** (tag buttons exist instead of "the feed is filtered"; profile heading
  instead of the new bio) — the model picks easy, always-true checks. Nothing in the pipeline
  catches that today.

### The bigger lesson: pass rate is the wrong metric

Every run so far looked better by pass rate than by "does it check the outcome". A spec that
asserts something always true passes forever and catches nothing. The benchmark must score
generated specs by **whether they catch the seeded bug for their flow** — run each spec against
the bugged variant and count it only if it fails there and passes on the clean app (Q29).

## Overall verdict on spec generation (Q22)

**Target missed by a wide margin: ~2/10 specs that pass *and* check the outcome, vs ≥ 7/10.**
Neither prompting, schema constraints, a bigger model, nor observing the outcome closes the gap
for free-text → spec at 4B. What did work, reliably, was everything **deterministic**: schema
constraints, the runner, observation of the real page.

Recommendation — narrow phase 3 before building it (the exit gate's "stop and narrow scope"):

1. **Templates own the structure, the model fills slots.** Login, sign-up, form submit, CRUD and
   "as <user>" preconditions come from templates; the model chooses which template and fills
   targets/values from the snapshot — small, checkable choices it handled well here.
2. **Observe, then let the model choose assertions from a menu.** After the actions run, derive
   candidate assertions deterministically from the *difference* between the page before and
   after (new text, new elements, URL change, changed values); the model only picks the ones
   that match the flow's stated expectation. Generated values become `$var` automatically.
3. **Score specs by seeded-bug kill rate**, not pass rate, from the first experiment on.
4. **Keep the model where it did well:** triage with label probabilities (both small models were
   right on the easy cases with graded confidence for `qwen3:4b`), naming/ranking flows.

Next spike steps: triage on ~20 captured failures (the other half of the model's job), then a
quick test of (1)+(2) on these 10 flows.

## Seeded bugs and the reference suite

Conduit now has **toggleable seeded bugs** (`BUGS=<ids> bench/app/conduit.sh reset`, tagged
`[testomation bug]` in the code; the backend injects the list into the page for frontend bugs):

| Bug | Kind | Caught by |
|---|---|---|
| `login-error-hidden` | frontend: wrong password shows no error | ref02 |
| `signup-500` | backend: sign-up returns 500 | ref03 |
| `publish-500` | backend: publishing returns 500 | ref04 |
| `comment-not-shown` | frontend: posted comment never appears | ref05 |
| `tag-filter-ignored` | backend: tag filter ignored | ref06 |
| `favorite-count-stuck` | backend: favorite not saved | ref07 |
| `profile-articles-empty` | backend: profile lists no articles | ref09 |
| `bio-not-saved` | backend: bio change dropped | ref10 |
| `noise-analytics`, `noise-console-warning` | harmless console/network errors | — (must not be reported) |
| `flaky-slow-articles` | ~40% of article-list requests take 6 s | — |

`bench/reference/` holds 10 hand-written specs, one per flow. **Clean app: 10/10 pass (3 runs).
Kill matrix: 8/8** — each bug fails exactly its own spec and nothing else.

Writing them found three more things:
- **Upstream Conduit bug**: saving settings re-hashed the password every time (`||` instead of
  `&&`), so any bio change silently broke later logins — including other specs running in
  parallel. Fixed in the clean baseline (`UPSTREAM.md`).
- **Runner race**: after a click, the next step could start before the request it triggered
  finished (the profile loaded before the bio save). `waitForLoadState('networkidle')` doesn't
  help on an already-loaded SPA, so the runner now counts in-flight same-origin requests and
  waits for 300 ms of quiet after each click/press (≤ 3 s).
- **Schema gap closed**: identical elements (two "Favorite ( 0 )" buttons) needed an optional
  `nth` on targets (Q27 → D41).

## Triage — `spike/triage_capture.py`, `triage_eval.py`

24 real cases captured from the reference suite under each variant, labelled by what was switched
on: 8 bug, 7 noise (signals on passing tests — including the *expected* 422 from the
wrong-password test), 3 flaky, 6 test_issue (model-written specs that failed on the clean app).
One `qwen3:4b` call per case, verdict + label probability from logprobs. ~0.8 s per case.

| | Accuracy | bug | noise | flaky | test_issue |
|---|---|---|---|---|---|
| "Everything is a bug" baseline | 33% | 8/8 | 0/7 | 0/3 | 0/6 |
| `qwen3:4b` | **58%** | 8/8 | 3/7 | 3/3 | **0/6** |

- Calibration is usable: mean p **0.97 when right, 0.78 when wrong**.
- The 4 noise misses are all the expected 422 from the wrong-password test (an error signal that
  is the point of that test), at p 0.51–0.71 — below the 0.8 gate, so they'd go to review.
- **All 6 broken generated specs were called "bug", mostly at p ≥ 0.96.** From the evidence alone,
  "the test looks for something that isn't there" and "the app lost something" look the same.
- **Giving the model the spec's history as evidence didn't help** (still 0/6). As a **rule** —
  "a draft that has never passed → suspect the test first" — it fixes all six.

As the designed cascade (rules → model with 0.8 gate → human review):

| | Auto-filed right | Auto-filed **wrong** | To review |
|---|---|---|---|
| Model + basic rules | 13 | **4** | 7 |
| + history rule | **16** | **1** (the expected 422, p 0.93) | 7 |

**Triage target met** (beats "everything is a bug"; probabilities separate right from wrong).
The history rule is consistent with the design: drafts don't file bugs, they go to repair/review.

## Templates + assertion menu, scored by kill rate — `spike/menu.py`

The model plans (precondition user, start page, action steps); login is a template; the runner
records the page before and after the actions; candidate assertions are derived
**deterministically** from that difference (plus key elements shown at the end), with generated
values auto-named and offered as `$var` checks; the model only **picks** candidates. A spec counts
if it passes on the clean app **and fails with its flow's seeded bug on** (8 flows have one).

| Run | Actions ran | Pass on clean | **Kill rate** |
|---|---|---|---|
| Reference suite (hand-written) | 10/10 | 10/10 | **8/8** |
| Menu, try 1 (parallel observation runs polluted each other's diffs) | 5/10 | 1/10 | 1/8 |
| Menu, try 2 (serial, every generated value named, end-state items offered) | 5/10 | 3/10 | **1/8** |

- **Picking from a menu works sometimes**: publish picked the generated title/body (kills the
  publish-500 bug); the followed-feed flow picked carol's posts. But it also picked always-true
  items (the tag list instead of the filtered articles — misses the tag-filter bug) and unrelated
  content (another flow's article title on alice's profile instead of her new bio).
- **Planning the actions is now the bottleneck**: 5/10 plans never ran, and repairs fixed none —
  an invented secret (`ALICE_EMAIL`), navigating by clicking through a feed where the target isn't
  shown, clicking an ambiguous "dave" link (9 matches) for a flow about bob.
- Two more things the schema can absorb: `$secret` names as an enum of known secrets, and nameless
  `role` targets only together with `nth` or not at all.

## Final verdict (Q22)

| Target | Result | Verdict |
|---|---|---|
| Specs from plain English (≥ 7/10 useful) | Best **1/8 bugs caught** vs 8/8 for hand-written specs; ~2/10 meaningful specs by any method | **Missed, by far** |
| Triage beats "everything is a bug"; probabilities separate right from wrong | 58% vs 33%; p 0.97 right vs 0.78 wrong; with the cascade 16 right / 1 wrong / 7 review of 24 | **Met** |
| Toolchain (structured output, logprobs, `langfuse.openai`) | Works with a decoder-friendly schema (D38–D41) | **Met** |
| Fits the laptop | `qwen3:4b` fully on GPU at 8k context, 55 tok/s; worst case 5.0 GB RAM, no swap | **Met** |

**What this means for the plan:**

1. **The deterministic core is sound and worth building as designed**: the spec format and runner,
   seeded-bug benchmark, reference suite, rules-first analyzer. Every fix that worked in this spike
   was deterministic.
2. **The model earns its place in triage** (phase 2 rules + phase 5 cascade): keep as designed,
   with the history rule and the 0.8 gate.
3. **Autonomous spec generation at 4B does not work** on even a small app, with any of the five
   approaches tried. Phase 3 should become **assisted authoring**: templates and recorded flows
   produce the actions, the model *suggests* assertions (menu picks) and names flows, and every
   draft goes to human approval — which the design already requires — measured by kill rate.
4. Exploration (phase 6) relies on the same planning ability that failed here; treat it as
   research until a stronger local model passes the same kill-rate benchmark.

## Model bake-off on the kill-rate benchmark (Q32) — `spike/bakeoff.sh`

The templates + assertion-menu harness (`spike/menu.py`), unchanged, run once per model. Gate to
re-open autonomous generation / exploration (D43): **≥ 5/8**. Reference suite: 8/8.

| Model | Size | Actions ran | Pass on clean | **Kill rate** |
|---|---|---|---|---|
| `qwen3:4b` | 4.0B | 5/10 | 3/10 | 1/8 |
| `phi4-mini` | 3.8B | 4/10 | 3/10 | **2/8** |
| `llama3.2:3b` | 3.2B | 4/10 | 4/10 | **2/8** |
| `gemma3:4b` | 4.3B | 1/10 | 1/10 | 1/8 |
| `gemma3n:e4b` | ~4B effective | 3/10 | 3/10 | 0/8 |
| `qwen2.5-coder:7b` | 7.6B (partial offload) | 1/10 | 1/10 | 0/8 |
| `qwen2.5:7b` | 7.6B (partial offload) | 3/10 | 3/10 | **2/8** |

**No model is near the gate.** Differences of one bug are within noise (one run each; the prompt
and examples were developed against `qwen3:4b`), so the honest reading is that every local model
that fits this laptop scores 0–2/8, and size (3B → 7B) doesn't change it. This confirms D42/D43.
The bake-off is re-runnable in one command whenever a new local model appears — that is the gate.

## Peak RAM — `spike/ram_check.py`

Phase 0–2 stack (Postgres + Conduit, no Langfuse), sampled every 0.5 s; 15.3 GB total.

| Scenario | Peak used | Lowest available | Swap growth | GPU |
|---|---|---|---|---|
| Idle | 4.2 GB | 11.1 GB | none | — |
| `qwen3:4b` generating (all layers on GPU) | 4.5 GB | 10.8 GB | none | 3.7 GB |
| Reference suite, 2 workers, model unloaded | 4.5 GB | 10.8 GB | none | — |
| **Suite on 2 workers while the model generates** | **5.0 GB** | **10.3 GB** | **none** | 3.7 GB |

Well inside the design's 5–7 GB estimate for phases 0–2, leaving ~10 GB — room for Langfuse
(2–3 GB) in phase 3 and for more Playwright workers when no model is loaded.

## Still to do

- [x] Toolchain: structured output, logprobs, `langfuse.openai` (Q13) — works with a
      decoder-friendly schema (above)
- [x] `gemma3:4b` with full offload — crashes; projector must stay on CPU
- [x] Schema: `role` enum of ARIA roles; forbid literal strings starting with `$`; no names on
      nameless roles
- [x] 10 described Conduit flows → specs, ≤ 3 batched repair rounds, small vs large tier —
      **4/10, target missed** (above)
- [x] Observe-then-assert generation on the same 10 flows (Q26) — 2/10 meaningful; fixes the
      unseen-outcome failures, not the rest
- [x] Templates + assertion menu from the before/after diff, scored by seeded-bug kill rate — 1/8
- [x] ~20 captured failures → one-call triage with label probabilities — 24 cases, target met
- [x] Seeded bugs with toggles + reference suite (kill matrix 8/8)
- [x] Peak RAM / swap with model + 2 Playwright workers + Conduit — 5.0 GB worst case, no swap
- [x] Verdict against the targets (Q22) — see Final verdict
