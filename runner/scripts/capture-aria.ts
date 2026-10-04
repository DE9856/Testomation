// Spike utility: capture aria snapshots of the target app's pages as prompt context.
// Usage: node --experimental-strip-types scripts/capture-aria.ts <outDir>
// Env: TESTO_TARGET_URL (default http://localhost:4100), ALICE_PASSWORD (default alice-pass-1).
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium, type Page } from '@playwright/test';

const base = process.env.TESTO_TARGET_URL ?? 'http://localhost:4100';
const out = process.argv[2] ?? 'aria';
mkdirSync(out, { recursive: true });

async function snap(page: Page, name: string, path: string, ready?: string) {
  await page.goto(base + path);
  if (ready) await page.getByText(ready).first().waitFor();
  else await page.waitForLoadState('networkidle');
  const yaml = await page.locator('body').ariaSnapshot();
  writeFileSync(join(out, `${name}.yaml`), `# ${path}\n${yaml}\n`);
  console.log(`${name.padEnd(20)} ${path.padEnd(32)} ${yaml.length} chars`);
}

const browser = await chromium.launch();
const page = await browser.newPage();
const slug = (await (await fetch(`${base}/api/articles?limit=1`)).json()).articles[0].slug;

await snap(page, 'home', '/#/', 'Read more');
await snap(page, 'login', '/#/login');
await snap(page, 'register', '/#/register');
await snap(page, 'article', `/#/article/${slug}`, 'Comment from');

await page.goto(base + '/#/login');
await page.getByPlaceholder('Email').fill('alice@conduit.test');
await page.getByPlaceholder('Password').fill(process.env.ALICE_PASSWORD ?? 'alice-pass-1');
await page.getByRole('button', { name: 'Login' }).click();
await page.getByText('Your Feed').waitFor();

await snap(page, 'home-logged-in', '/#/', 'Read more');
await snap(page, 'editor', '/#/editor');
await snap(page, 'settings', '/#/settings');
await snap(page, 'profile-alice', '/#/profile/alice', 'Read more');
await snap(page, 'article-logged-in', `/#/article/${slug}`, 'Comment from');
await browser.close();
