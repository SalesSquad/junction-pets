/** One changed-path browser journey; existing installed Playwright required. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createObservationServer } from '../meta-spatial/observation-server.mjs';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const output = resolve(process.argv[2] ?? '/tmp/lens-learning-browser');
await mkdir(output, { recursive: true });
const server = createObservationServer({ mode: 'synthetic', maxCalls: 1 });
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const origin = 'http://127.0.0.1:' + server.address().port;
const errors = [], checks = [];
let browser;
const started = Date.now();
try {
  const executablePath = process.env.CHROMIUM_PATH ?? (process.platform === 'linux' ? '/usr/bin/chromium' : undefined);
  browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', (route) => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  const button = (action) => page.locator('[data-learning-action="' + action + '"]').first();
  const ready = async () => page.waitForFunction(() => !document.querySelector('[data-learning-action="consent"]').disabled);
  const click = async (action) => { await button(action).click(); await ready(); };
  const advice = async (action) => page.waitForFunction((expected) =>
    document.querySelector('#learningAdviceTitle').dataset.learningRecommendation === expected, action);
  const saved = async () => page.evaluate(() => JSON.parse(localStorage.getItem('chibi-lens.learning.synthetic.v1')));
  const confirm = async () => {
    await page.locator('#primaryAction').click();
    await page.locator('#confirmCheckbox').check();
    await page.locator('#commitConfirmation').click();
    await page.locator('#confirmDialog').waitFor({ state: 'hidden' });
  };
  await page.goto(origin);
  await button('consent').waitFor();
  await click('consent');
  await page.locator('#learningStyle').selectOption('detailed');
  await click('teach');
  await click('approve');
  await advice('explain');
  checks.push('explicit-teach-and-approve');

  await confirm(); await confirm();
  await page.locator('#primaryAction').click();
  await page.waitForFunction(() => document.documentElement.dataset.taskStatus === 'interrupted');
  await click('checkpoint');
  await page.locator('#secondaryAction').click();
  await page.waitForFunction(() => document.documentElement.dataset.taskStatus === 'active');
  assert.equal((await page.locator('#countBadge').innerText()).replace(/\s/g, ''), '2/3');
  checks.push('original-resume-pause-checkpoint-and-return');

  await page.locator('#learningStyle').selectOption('quiet');
  await click('teach'); await advice('stay_silent');
  await page.locator('.learning-more > summary').click();
  await page.locator('#learningTemplate').selectOption('travel-kit');
  await click('next-episode'); await advice('stay_silent');
  assert.equal((await page.locator('#countBadge').innerText()).replace(/\s/g, ''), '0/3');
  await page.reload(); await button('consent').waitFor(); await advice('stay_silent');
  checks.push('correction-persists-next-episode-and-reload');

  await page.locator('.learning-more > summary').click();
  await page.locator('#learningGoal').selectOption('learn'); await ready();
  await click('ask'); await advice('explain');
  await page.locator('#learningResult').selectOption('assisted');
  await click('record-outcome');
  checks.push('goal-and-explicit-assisted-practice');
  await click('set-reminder'); await advice('one_step');
  await click('ack-reminder'); await advice('stay_silent');
  await click('handoff');
  await page.locator('#learningPanel').screenshot({ path: resolve(output, 'lens-learning-desktop.png') });
  checks.push('context-reminder-and-unsent-specialist-proposal');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#learningPanel').screenshot({ path: resolve(output, 'lens-learning-mobile.png') });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  checks.push('mobile-no-horizontal-overflow');

  await click('forget-all');
  await page.reload(); await button('consent').waitFor();
  await click('consent'); await advice('one_step');
  assert.equal(await page.locator('#learningMemories').innerText().then((text) => /Approved|Confirmed|Detailed help|Quiet/.test(text)), false);
  checks.push('forget-survives-reload-and-restarts-without-preference');
  assert.deepEqual(errors, []);
  const source = {};
  const root = fileURLToPath(new URL('../../', import.meta.url));
  for (const path of ['apps/meta-resume-web/learning-core.mjs', 'apps/meta-resume-web/learning-panel.mjs',
    'apps/meta-resume-web/learning-panel.css', 'apps/meta-resume-web/app.mjs',
    'apps/meta-resume-web/index.html', 'services/lens-learning/browser-check.mjs']) {
    source[path] = createHash('sha256').update(await readFile(resolve(root, path))).digest('hex');
  }
  const receipt = { schema: 'lens.learning-browser-report/v1', evidenceMode: 'SYNTHETIC',
    browser: await browser.version(), durationMs: Date.now() - started, checks, errors,
    source, providerCalls: 0, privateHostVerified: false, physicalDeviceVerified: false };
  await writeFile(resolve(output, 'browser-report.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
} finally {
  if (browser) await browser.close();
  await new Promise((done) => server.close(done));
}
