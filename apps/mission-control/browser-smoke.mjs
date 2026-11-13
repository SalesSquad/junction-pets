/** Explicit optional Chromium smoke test. Synthetic records never qualify runtime. */
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import assert from 'node:assert/strict';

const here = fileURLToPath(new URL('./', import.meta.url));
const pages = new Set(['/', '/index.html', '/style.css', '/app.js', '/status-model.mjs', '/server-projection.mjs']);
const SHA = 'a'.repeat(40); // Synthetic source fixture, not hosted source attestation.
const fixture = {
  schemaVersion: 1,
  generatedAt: new Date().toISOString(),
  source: {repository: 'SalesSquad/junction-pets', verification: 'unverified', commit: SHA},
  pets: Array.from({length: 34}, (_, index) => ({
    slug: `junction-test-${index}`,
    company: {name: index === 0 ? 'Acme Demo' : `Company ${index}`, slug: `test-${index}`, role: index < 18 ? 'challenge' : 'technology'},
    agent: {id: `junction-dev-test-${index}`, instructions: 'ops/AGENTS.md', petInstructions: `pets/test-${index}/AGENTS.md`},
    cloud: {provider: 'codex-cloud', desiredName: `junction-test-${index}`, state: index === 0 ? 'ready' : 'unprovisioned', environmentId: null, verifiedAt: null},
    development: {state: 'content-ready'},
    evaluation: {defined: 6, executed: 0, passed: 0, failed: 0},
    runtime: {state: 'unverified', publicationState: 'not-published'},
    nextAction: 'Provision the environment and attach an actual provider receipt',
  })),
};

const backendFixture = {
  schemaVersion: 1,
  kind: 'junction-fleet-control/server-projection/v1',
  generatedAt: new Date().toISOString(),
  source: {repository: 'SalesSquad/junction-pets', commit: SHA},
  summary: {total: 34, cloudReady: 1}, // Deliberately untrusted browser report.
  pets: fixture.pets.map((pet, i) => ({
    petSlug: pet.slug,
    developerAgentId: pet.agent.id,
    desiredEnvironment: pet.cloud.desiredName,
    cloud: i === 0
      ? {state: 'ready', environmentId: 'env.fake.01', sourceCommit: SHA, verifiedAt: new Date().toISOString()}
      : {state: 'unprovisioned'},
    ci: {state: 'missing'}, evaluation: {state: 'missing'},
    grant: {state: 'unverified'}, runtimeExecutionAllowed: false,
  })),
};

const server = createServer(async (request, response) => {
  const path = new URL(request.url || '/', 'http://localhost').pathname;
  if (path === '/fleet-projection.json') {
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify(backendFixture));
    return;
  }
  if (path === '/status.json') {
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify(fixture));
    return;
  }
  if (!pages.has(path)) {
    response.writeHead(404).end();
    return;
  }
  try {
    const name = path === '/' ? 'index.html' : path.slice(1);
    const content = await readFile(join(here, name));
    response.setHeader('Content-Type', name.endsWith('.css') ? 'text/css' : name.endsWith('.mjs') || name.endsWith('.js') ? 'text/javascript' : 'text/html');
    response.end(content);
  } catch {
    response.writeHead(500).end();
  }
});

let browser;
try {
  const {chromium} = await import('playwright');
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const {port} = server.address();
  browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || '/usr/bin/chromium',
    args: ['--no-sandbox'],
  });
  for (const viewport of [{width: 1440, height: 900}, {width: 390, height: 844}]) {
    const page = await browser.newPage({viewport});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}`, {waitUntil: 'networkidle'});
    await page.getByText('Every companion.').waitFor();
    assert.equal(await page.locator('.pet-row').count(), 34, '34 lanes visible');
    assert.equal(await page.locator('#metric-evals').textContent(), '0/204', 'authored is not executed');
    assert.equal(await page.locator('#metric-cloud').textContent(), '00', 'backend ready claim cannot turn static UI green');
    assert.match(await page.locator('#projection-status').textContent(), /NOT browser-attested/);
    assert.match(await page.locator('.pet-row').first().textContent(), /Backend reports ready.*unverified in browser/);
    assert.equal(await page.locator('.pet-row .state-pill.critical').count(), 1, 'unverified provider claim is visible');
    await page.locator('#search').fill('Acme Demo');
    assert.equal(await page.locator('.pet-row').count(), 1, 'search narrows one lane');
    await page.locator('.pet-row').click();
    assert.equal(await page.locator('dialog[open]').count(), 1, 'detail opens');
    assert.match(await page.locator('#detail-content').textContent(), /No verified environment ID/);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('dialog[open]').count(), 0, 'Escape closes dialog');
    await page.locator('#search').fill('');
    await page.locator('[data-mode="needs-setup"]').click();
    assert.equal(await page.locator('.pet-row').count(), 33, 'status filter excludes unsupported ready claim');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(overflow <= 1, `no horizontal overflow at ${viewport.width}px: ${overflow}`);
    assert.deepEqual(errors, [], `no browser script errors at ${viewport.width}px`);
    await page.close();
  }
  console.log('MISSION_CONTROL_BROWSER_SMOKE_OK: Chromium 1440×900 + 390×844, 34 lanes, search, dialog, fail-closed cloud, filters, zero overflow. Synthetic fixture only.');
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
