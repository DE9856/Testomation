// Interprets one spec step with Playwright. The only code that turns specs into browser actions.
// Vocabulary: docs/TEST_SPEC.md. Values: $faker / $var / $secret / $fixture references.
import { expect, type Locator, type Page } from '@playwright/test';
import { faker } from '@faker-js/faker';

export type Target =
  | { testid: string } | { role: string; name?: string } | { label: string }
  | { placeholder: string } | { text: string };
export type Step = { action: string; [field: string]: any };
export type Vars = Map<string, unknown>;

const VIEWPORTS = { phone: { width: 390, height: 844 }, tablet: { width: 820, height: 1180 },
  desktop: { width: 1280, height: 800 } } as const;

export function locate(page: Page, t: Target & { nth?: number }): Locator {
  const loc = 'testid' in t ? page.getByTestId(t.testid)
    : 'role' in t ? page.getByRole(t.role as any, t.name ? { name: t.name } : {})
    : 'label' in t ? page.getByLabel(t.label)
    : 'placeholder' in t ? page.getByPlaceholder(t.placeholder)
    : page.getByText(t.text);
  return t.nth === undefined ? loc : loc.nth(t.nth);
}

export function resolve(value: unknown, vars: Vars): unknown {
  if (value === null || typeof value !== 'object') return value;
  const v = value as Record<string, any>;
  if ('$faker' in v) {
    const fn = (v.$faker as string).split('.').reduce((o: any, k) => o?.[k], faker);
    if (typeof fn !== 'function') throw new Error(`unknown $faker path: ${v.$faker}`);
    const out = fn();
    if (v.as) vars.set(v.as, out);
    return out;
  }
  if ('$var' in v) {
    if (!vars.has(v.$var)) throw new Error(`$var "${v.$var}" used before it was set`);
    return vars.get(v.$var);
  }
  if ('$secret' in v) {
    const s = process.env[v.$secret];
    if (s === undefined) throw new Error(`$secret ${v.$secret} is not set in the environment`);
    return s;
  }
  return value;
}

const str = (x: unknown) => String(x);

// After a click or key press, let the requests it started finish (a save, a fetch) before the
// next step — like a user waiting for the page. `waitForLoadState('networkidle')` can't do this:
// it is a page-load state and returns at once on an already-loaded SPA (a spike bug: the profile
// loaded before the settings save finished). So: count in-flight same-origin requests and wait
// until none have been active for 300 ms, capped at 3 s.
const traffic = new WeakMap<Page, { inflight: number; changed: number }>();

export function trackTraffic(page: Page, origin: string): void {
  const t = { inflight: 0, changed: Date.now() };
  traffic.set(page, t);
  const mine = (url: string) => url.startsWith(origin);
  const done = (r: { url(): string }) => { if (mine(r.url())) { t.inflight = Math.max(0, t.inflight - 1); t.changed = Date.now(); } };
  page.on('request', (r) => { if (mine(r.url())) { t.inflight++; t.changed = Date.now(); } });
  page.on('requestfinished', done);
  page.on('requestfailed', done);
}

async function settle(page: Page): Promise<void> {
  const t = traffic.get(page);
  if (!t) return;
  const deadline = Date.now() + 3_000;
  await page.waitForTimeout(50); // let the click's handlers start their requests
  while (Date.now() < deadline && (t.inflight > 0 || Date.now() - t.changed < 300)) {
    await page.waitForTimeout(50);
  }
}

export async function runStep(page: Page, step: Step, vars: Vars): Promise<void> {
  await act(page, step, vars);
  if (step.action === 'click' || step.action === 'press') await settle(page);
}

async function act(page: Page, step: Step, vars: Vars): Promise<void> {
  const target = () => locate(page, step.target);
  switch (step.action) {
    case 'goto': return void (await page.goto(step.url));
    case 'click': return target().click();
    case 'hover': return target().hover();
    case 'check': return target().check();
    case 'uncheck': return target().uncheck();
    case 'fill': return target().fill(str(resolve(step.value, vars)));
    case 'select': return void (await target().selectOption(str(resolve(step.value, vars))));
    case 'press': return step.target ? target().press(step.key) : page.keyboard.press(step.key);
    case 'wait_for': return target().waitFor({ state: step.state });
    case 'viewport': return page.setViewportSize(VIEWPORTS[step.preset as keyof typeof VIEWPORTS]);
    case 'upload': throw new Error('upload: $fixture files not supported yet');
    case 'helper': throw new Error(`helper "${step.name}": no helpers are registered`);
    case 'api': {
      const res = await page.request.fetch(step.path, { method: step.method, data: resolve(step.body, vars) as any });
      if (step.expect?.status !== undefined) expect(res.status(), `${step.method} ${step.path}`).toBe(step.expect.status);
      return;
    }
    case 'expect': return assert(page, step, vars);
    default: throw new Error(`unknown action: ${step.action}`);
  }
}

async function assert(page: Page, step: Step, vars: Vars): Promise<void> {
  const value = resolve(step.value, vars);
  if (step.assert === 'url') {
    const want = str(value);
    return expect(page).toHaveURL((url) => (url.pathname + url.search + url.hash).endsWith(want)
      || url.href.endsWith(want));
  }
  if (!step.target) throw new Error(`expect "${step.assert}" needs a target`);
  const loc = locate(page, step.target);
  switch (step.assert) {
    case 'visible': return expect(loc.first()).toBeVisible();
    case 'hidden': return expect(loc).toHaveCount(0);
    case 'hasText': return expect(loc.first()).toContainText(str(value));
    case 'hasValue': return expect(loc.first()).toHaveValue(str(value));
    case 'count': return expect(loc).toHaveCount(Number(value));
    case 'ariaSnapshot': return expect(loc.first()).toMatchAriaSnapshot(str(value));
    default: throw new Error(`unknown assert: ${step.assert}`);
  }
}
