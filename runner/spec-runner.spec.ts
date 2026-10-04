import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from '@playwright/test';
import { runStep, trackTraffic, type Step, type Vars } from './steps.ts';

// One test() per spec file; one test.step() per spec step (docs/TEST_SPEC.md → Spec runner).
// On failure: the failing step index is recorded as an annotation and the page's aria
// snapshot is attached, for the analyzer and the repair round.
// Still to come (phase 1): axe, coverage, helper registry.

type Spec = { id: string; steps: Step[] };

const specsDir = process.env.TESTO_SPECS_DIR;
const specs: Spec[] = specsDir
  ? readdirSync(specsDir).filter((f) => f.endsWith('.json')).sort()
      .map((f) => JSON.parse(readFileSync(join(specsDir, f), 'utf8')) as Spec)
  : [];

const base = new URL(process.env.TESTO_TARGET_URL ?? 'http://localhost:4100');
const blocked: string[] = [];
// Signals for the analyzer: console errors, failed requests and 4xx/5xx responses (any test).
type Signal = { kind: 'console' | 'requestfailed' | 'http'; text: string; url?: string; status?: number };
let signals: Signal[] = [];

test.beforeEach(async ({ page }) => {
  signals = [];
  trackTraffic(page, base.origin);
  page.on('console', (m) => {
    if (m.type() === 'error') signals.push({ kind: 'console', text: m.text().slice(0, 300), url: m.location().url });
  });
  page.on('pageerror', (e) => signals.push({ kind: 'console', text: `Uncaught ${e.name}: ${e.message}`.slice(0, 300) }));
  page.on('requestfailed', (r) => signals.push({ kind: 'requestfailed', text: r.failure()?.errorText ?? 'failed', url: r.url() }));
  page.on('response', (r) => {
    if (r.status() >= 400) signals.push({ kind: 'http', text: `${r.request().method()} ${r.status()}`, url: r.url(), status: r.status() });
  });

  // Origin guard (D32): top-level navigation off the target origin is aborted, and the step
  // that caused it fails with a clear message instead of an opaque chrome-error page.
  blocked.length = 0;
  await page.route('**/*', (route) => {
    const req = route.request();
    if (req.isNavigationRequest() && req.frame() === page.mainFrame()
        && new URL(req.url()).origin !== base.origin) {
      blocked.push(req.url());
      return route.abort('blockedbyclient');
    }
    return route.fallback();
  });
});

test.afterEach(async ({}, info) => {
  if (signals.length) await info.attach('signals', { body: JSON.stringify(signals), contentType: 'application/json' });
});

for (const spec of specs) {
  test(spec.id, async ({ page }, info) => {
    const vars: Vars = new Map();
    for (const [i, step] of spec.steps.entries()) {
      await test.step(`${i + 1}. ${step.action}`, async () => {
        try {
          await runStep(page, step, vars);
          if (blocked.length) throw new Error(`origin guard blocked navigation to ${blocked[0]}`);
          // Spike Q26: `_observe_after: n` records the settled page after step n (the "before" state).
          if ((spec as any)._observe_after === i + 1) {
            await page.waitForTimeout(400);
            await info.attach('before-aria', { body: await page.locator('body').ariaSnapshot(), contentType: 'text/yaml' });
          }
        } catch (e) {
          info.annotations.push({ type: 'failing-step', description: String(i + 1) });
          const aria = await page.locator('body').ariaSnapshot({ timeout: 2000 }).catch(() => '');
          await info.attach('aria-snapshot', { body: aria, contentType: 'text/yaml' });
          await info.attach('vars', { body: JSON.stringify(Object.fromEntries(vars)), contentType: 'application/json' });
          throw e;
        }
      });
    }
    // TESTO_ATTACH_FINAL=1: also record the page and generated values after the last step
    // (used to let a model write assertions against the real outcome — spike Q26).
    if (process.env.TESTO_ATTACH_FINAL === '1') {
      // Let the page settle first: navigation, fetches and "Loading…" states finish.
      await page.waitForLoadState('networkidle').catch(() => {});
      await page.waitForTimeout(500);
      await info.attach('final-aria', { body: await page.locator('body').ariaSnapshot(), contentType: 'text/yaml' });
      await info.attach('vars', { body: JSON.stringify(Object.fromEntries(vars)), contentType: 'application/json' });
    }
  });
}
