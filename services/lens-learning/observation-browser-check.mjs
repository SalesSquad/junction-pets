/** One observation/learning integration journey against the actual synthetic server. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createObservationServer } from '../meta-spatial/observation-server.mjs';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const output = resolve(process.argv[2] ?? '/tmp/lens-observation-browser');
await mkdir(output, { recursive: true });
const server = createObservationServer({ mode: 'synthetic', maxCalls: 3 });
await new Promise((done, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', done); });
const origin = 'http://127.0.0.1:' + server.address().port;
const errors = [], checks = [], responseStatuses = [];
let browser, releaseHeld = () => {}, failure = null;
const started = Date.now();
try {
  const executablePath = process.env.CHROMIUM_PATH ?? (process.platform === 'linux' ? '/usr/bin/chromium' : undefined);
  browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', (route) => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  const button = (action) => page.locator('[data-learning-action="' + action + '"]').first();
  const ready = () => page.waitForFunction(() => !document.querySelector('[data-learning-action="consent"]').disabled);
  const click = async (action) => { await button(action).click(); await ready(); };
  const current = (expected) => page.waitForFunction((value) =>
    document.querySelector('#learningObservation').dataset.observationContext === value, expected ? 'current' : 'none');
  const storage = () => page.evaluate(() => ({
    learning: localStorage.getItem('chibi-lens.learning.synthetic.camera-packing.v1'),
    task: localStorage.getItem('chibi-resume.synthetic.camera-bag-v1'),
  }));
  const loadSample = async () => {
    await page.waitForFunction(() => !document.querySelector('#observationSample').disabled);
    await page.locator('#observationSample').click();
    await page.waitForFunction(() => !document.querySelector('#observationAnalyze').disabled);
  };
  const analyze = async () => {
    const response = page.waitForResponse((r) => r.url() === origin + '/api/observe' && r.request().method() === 'POST');
    await page.locator('#observationAnalyze').click();
    const data = await (await response).json();
    responseStatuses.push(data.status);
    assert.equal(data.status, 'proposed');
    await current(true);
  };
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
  await click('teach'); await click('approve-memory');
  const original = await storage();
  await loadSample(); await analyze();
  assert.match(await page.locator('#learningObservation').innerText(), /SYNTHETIC VIEW/);
  assert.equal(await page.locator('#learningObservation .learning-observation-summary').count(), 1);
  assert.deepEqual(await storage(), original);
  assert.equal((await page.locator('#countBadge').innerText()).replace(/\s/g, ''), '0/3');
  checks.push('fresh-view-and-approved-preference-without-persistent-or-task-mutation');

  await confirm(); await current(false);
  assert.equal((await page.locator('#countBadge').innerText()).replace(/\s/g, ''), '1/3');
  checks.push('actual-user-task-progress-invalidates-prior-visual-context');
  await page.locator('#learningStyle').selectOption('quiet'); await click('teach');
  await loadSample(); await analyze();
  assert.match(await page.locator('#learningObservation').innerText(), /holding back until you ask/);
  assert.equal(await page.locator('#learningObservation .learning-observation-summary').count(), 0);
  const quietStorage = await storage();
  await click('ask'); await current(true);
  assert.equal(await page.locator('#learningObservation .learning-observation-summary').count(), 1);
  assert.deepEqual(await storage(), quietStorage);
  await page.locator('#learningPanel').screenshot({ path: resolve(output, 'lens-observation-learning.png') });
  checks.push('confirmed-quiet-preference-and-explicit-ask-share-the-current-view');

  await page.locator('#revokeButton').click(); await current(false);
  assert.equal(await page.locator('#observationAnalyze').isDisabled(), true);
  assert.equal((await page.locator('#countBadge').innerText()).replace(/\s/g, ''), '1/3');
  checks.push('capture-revocation-clears-context-without-erasing-user-confirmations');

  // Restart via the real UI; advance to revision2 so the real observation gate
  // admits a changed task. No force flag or synthetic response rewrite is used.
  await page.locator('[data-action="reset"]').first().click(); await current(false);
  await confirm(); await confirm();
  await loadSample();
  let responseSeen;
  const held = new Promise((done) => { releaseHeld = done; });
  const seen = new Promise((done) => { responseSeen = done; });
  await page.route(origin + '/api/observe', async (route) => {
    const response = await route.fetch({ timeout: 10_000 });
    const data = await response.json();
    responseStatuses.push(data.status);
    responseSeen(data);
    await held;
    await route.fulfill({ response });
  }, { times: 1 });
  await page.locator('#observationAnalyze').click();
  let deadline;
  const observed = await Promise.race([seen, new Promise((_, reject) => {
    deadline = setTimeout(() => reject(new Error('Held observation response did not arrive')), 12_000);
  })]).finally(() => clearTimeout(deadline));
  assert.equal(observed.status, 'proposed');
  await click('forget-all'); await click('consent');
  const afterForget = await storage();
  assert.deepEqual(JSON.parse(afterForget.learning).memories, []);
  const delivered = page.waitForResponse((r) => r.url() === origin + '/api/observe');
  releaseHeld(); await delivered;
  await page.waitForFunction(() => !document.querySelector('#observationAnalyze').disabled);
  await current(false);
  assert.deepEqual(await storage(), afterForget);
  assert.equal((await page.locator('#countBadge').innerText()).replace(/\s/g, ''), '2/3');
  checks.push('pre-forget-network-response-cannot-revive-context-in-a-new-episode');
  assert.deepEqual(responseStatuses, ['proposed', 'proposed', 'proposed']);
  assert.deepEqual(errors, []);
} catch (error) {
  failure = error?.stack ?? String(error); process.exitCode = 1;
} finally {
  releaseHeld();
  const browserVersion = browser ? await browser.version() : null;
  try { if (browser) await browser.close(); }
  finally { await new Promise((done) => server.close(done)); }
  const source = {}, root = fileURLToPath(new URL('../../', import.meta.url));
  for (const path of ['apps/meta-resume-web/learning-observation.mjs', 'apps/meta-resume-web/learning-core.mjs',
    'apps/meta-resume-web/learning-panel.mjs', 'apps/meta-resume-web/learning-panel.css',
    'apps/meta-resume-web/observation-client.mjs', 'apps/meta-resume-web/state.mjs', 'apps/meta-resume-web/fixture.mjs',
    'apps/meta-resume-web/app.mjs', 'apps/meta-resume-web/index.html',
    'services/meta-spatial/observation-server.mjs', 'services/lens-learning/observation-browser-check.mjs']) {
    source[path] = createHash('sha256').update(await readFile(resolve(root, path))).digest('hex');
  }
  const receipt = { schema: 'lens.learning-observation-browser/v1', evidenceMode: 'SYNTHETIC',
    status: failure ? 'failed' : 'passed', browser: browserVersion, durationMs: Date.now() - started,
    checks, errors, failure, responseStatuses, source, providerCalls: 0,
    privateHostVerified: false, physicalDeviceVerified: false };
  await writeFile(resolve(output, 'observation-browser-report.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
}
