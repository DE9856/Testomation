import { defineConfig, devices } from '@playwright/test';

// The Python pipeline invokes this with TESTO_SPECS_DIR pointing at data/runs/<run>/specs.
export default defineConfig({
  testDir: '.',
  testMatch: 'spec-runner.spec.ts',
  workers: Number(process.env.TESTO_WORKERS ?? 2),
  retries: Number(process.env.TESTO_RETRIES ?? 1),
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: [['json', { outputFile: process.env.TESTO_RESULTS_FILE ?? 'test-results/results.json' }], ['html', { open: 'never' }]],
  use: {
    actionTimeout: 5_000,
    navigationTimeout: 10_000,
    baseURL: process.env.TESTO_TARGET_URL ?? 'http://localhost:4100',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: (process.env.TESTO_BROWSERS ?? 'chromium').split(',').map((name) => ({
    name,
    use: { ...devices[name === 'firefox' ? 'Desktop Firefox' : 'Desktop Chrome'] },
  })),
});
