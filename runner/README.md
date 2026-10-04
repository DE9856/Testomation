# Spec runner

Playwright Test project that executes Testomation JSON specs (`docs/TEST_SPEC.md`).

```bash
npm install && npx playwright install chromium
TESTO_SPECS_DIR=path/to/specs ALICE_PASSWORD=... npx playwright test
```

| Env | Default | Meaning |
|---|---|---|
| `TESTO_SPECS_DIR` | — | Folder of spec JSON files; one test per file |
| `TESTO_TARGET_URL` | `http://localhost:4100` | Base URL and the only allowed origin |
| `TESTO_RESULTS_FILE` | `test-results/results.json` | Playwright JSON report |
| `TESTO_WORKERS` / `TESTO_RETRIES` | `2` / `1` | Parallelism and retries |
| `TESTO_BROWSERS` | `chromium` | Comma list: `chromium,firefox` |
| any `$secret` name | — | Resolved from the environment at run time |

On failure each test gets a `failing-step` annotation (1-based) and an `aria-snapshot`
attachment, for triage and repair rounds. `scripts/validate-examples.ts` checks the schema
examples; `scripts/capture-aria.ts` captures page snapshots (spike context).
