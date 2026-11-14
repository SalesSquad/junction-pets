/** One bounded local browser journey. Uses an already-installed Playwright. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = dirname(fileURLToPath(import.meta.url));
const output = resolve(process.argv[2] ?? '/tmp/chibi-resume-browser-check');
const files = new Map([
  ['/', ['index.html', 'text/html']], ['/index.html', ['index.html', 'text/html']],
  ...['app.mjs', 'fixture.mjs', 'state.mjs', 'webmcp.mjs'].map((name) => [`/${name}`, [name, 'text/javascript']]),
  ['/styles.css', ['styles.css', 'text/css']],
]);
await mkdir(output, { recursive: true });
const server = createServer(async (request, response) => {
  const file = files.get(new URL(request.url, 'http://localhost').pathname);
  if (request.method !== 'GET' || !file) { response.writeHead(404); response.end(); return; }
  try {
    response.setHeader('Content-Type', `${file[1]}; charset=utf-8`);
    response.setHeader('Cache-Control', 'no-store');
    response.end(await readFile(resolve(root, file[0])));
  } catch { response.writeHead(500); response.end(); }
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
const started = new Date().toISOString();
const observations = [];
try {
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? '/usr/bin/chromium', headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1120 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', (route) => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  const revision = async (expected) => page.waitForFunction((value) => document.documentElement.dataset.revision === String(value), expected);
  const confirm = async () => {
    await page.locator('#primaryAction').click();
    assert.equal(await page.locator('#commitConfirmation').isDisabled(), true);
    await page.locator('#confirmCheckbox').focus();
    await page.keyboard.press('Space');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');
    await page.locator('#confirmDialog').waitFor({ state: 'hidden' });
  };
  await page.goto(origin);
  await revision(0);
  assert.equal(await page.evaluate(() => typeof document.modelContext), 'undefined');
  await confirm(); await revision(1);
  await confirm(); await revision(2);
  await page.locator('#primaryAction').click(); await revision(3);
  assert.match(await page.locator('#evidenceSummary').textContent(), /11:00/);
  await page.locator('#primaryAction').click(); await revision(4);
  assert.match(await page.locator('#evidenceSummary').textContent(), /Rejected as task evidence/);
  assert.equal((await page.locator('#countBadge').textContent()).replaceAll(' ', ''), '2/3');
  assert.match(await page.locator('#packingList').textContent(), /Proposed · waiting for your confirmation/);
  observations.push('Camera and microphone confirmed by keyboard; interruption retained them; historical sighting and fresh rejected lookalike did not complete charger; empty-evidence proposal at revision 4.');
  await page.reload(); await revision(4);
  assert.equal((await page.locator('#countBadge').textContent()).replaceAll(' ', ''), '2/3');
  await page.locator('#toast').waitFor({ state: 'hidden', timeout: 9000 });
  await page.screenshot({ path: resolve(output, 'resume-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 600, height: 600 });
  await page.goto(`${origin}/?display=1`); await revision(4);
  await page.locator('#toast').waitFor({ state: 'hidden', timeout: 9000 });
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight,
    buttonBottom: document.querySelector('#primaryAction').getBoundingClientRect().bottom,
    surfaceHeight: document.querySelector('#displaySurface').getBoundingClientRect().height,
  }));
  assert.equal(dimensions.width, 600);
  assert.equal(dimensions.height, 600);
  assert.equal(dimensions.surfaceHeight, 600);
  assert.ok(dimensions.buttonBottom <= 580, 'Primary control must fit the compact display');
  await page.screenshot({ path: resolve(output, 'resume-display-600.png') });
  observations.push('Browser refresh restored local progress; actual Chromium compact surface is 600×600 with its action visible and no document overflow.');
  await page.locator('#primaryAction').click(); await page.keyboard.press('Escape'); await revision(4);
  await confirm(); await revision(5);
  assert.equal(await page.locator('html').getAttribute('data-task-status'), 'completed');
  await page.setViewportSize({ width: 1440, height: 1120 });
  await page.goto(origin); await revision(5);
  await page.getByRole('button', { name: 'Correct Microphone confirmation' }).click(); await revision(6);
  assert.equal((await page.locator('#countBadge').textContent()).replaceAll(' ', ''), '1/3');
  await page.locator('#revokeButton').click();
  assert.match(await page.locator('#captureStatus').textContent(), /generation 2/);
  assert.equal((await page.locator('#countBadge').textContent()).replaceAll(' ', ''), '1/3');
  await page.locator('#secondaryAction').click(); await revision(7);
  assert.match(await page.locator('#primaryAction').textContent(), /without observations/);
  await page.locator('#primaryAction').click(); await revision(8);
  assert.equal((await page.locator('#countBadge').textContent()).replaceAll(' ', ''), '1/3');
  observations.push('Escape did not confirm; explicit checkbox+keyboard confirmation completed step 3; correcting microphone cleared it and later confirmation; capture revoke advanced generation without clearing camera; offline resume remained usable.');
  assert.deepEqual(errors, []);
  const receipt = {
    workId: 'META-EXEC-20261114/U1', startedAt: started, completedAt: new Date().toISOString(),
    result: 'pass', environment: `Linux Node ${process.version}; headless Chromium ${browser.version()}`,
    scope: 'one local synthetic browser journey', observations,
    dimensions, pageErrors: errors,
    notVerified: ['Physical glasses', 'Meta Display Simulator extension', 'Native WebMCP assistant execution', 'Live camera or microphone', 'Chibi host, identity or persistence', 'Cross-device synchronization', 'Production deployment'],
  };
  await writeFile(resolve(output, 'browser-receipt.json'), `${JSON.stringify(receipt, null, 2)}\n`);
  console.log(JSON.stringify(receipt, null, 2));
} finally {
  if (browser) await browser.close();
  await new Promise((done) => server.close(done));
}
