import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createServer as reservePort } from 'node:net';
import { resolve } from 'node:path';
import { chromium, firefox, webkit } from 'playwright';

// Actual HTTP/browser qualification of two fictional local products. No sponsor
// API, account, dataset, purchase or external navigation is part of this harness.
const products = {
  cala: { directory: 'solutions/cala-founder-opportunity-graph', port: 4174, mode: 'FICTIONAL_FIXTURE', journey: calaJourney },
  context: { directory: 'solutions/context-dev-live-web-decision', port: 4173, mode: 'SYNTHETIC_REPLAY', journey: contextJourney },
};
const engines = { chromium, firefox, webkit };
const sleep = ms => new Promise(done => setTimeout(done, ms));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const stableJSON = value => value === null || typeof value !== 'object' ? JSON.stringify(value)
  : Array.isArray(value) ? `[${value.map(stableJSON).join(',')}]`
    : `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableJSON(value[key])}`).join(',')}}`;

async function textIs(page, selector, expected) {
  await page.waitForFunction(({ selector, expected }) => document.querySelector(selector)?.textContent.trim() === expected, { selector, expected });
}
async function textIncludes(page, selector, expected) {
  await page.waitForFunction(({ selector, expected }) => document.querySelector(selector)?.textContent.includes(expected), { selector, expected });
}
async function focused(page, selector) {
  await page.waitForFunction(selector => document.activeElement === document.querySelector(selector), selector);
}
async function downloadText(page, selector, filename) {
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator(selector).click()]);
  assert.equal(download.suggestedFilename(), filename);
  assert.equal(await download.failure(), null);
  const stream = await download.createReadStream();
  assert.ok(stream, 'Actual browser download must be readable');
  const chunks = [];
  let length = 0;
  for await (const chunk of stream) {
    length += chunk.length;
    assert.ok(length <= 500_000, 'Unexpectedly large fictional export');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

async function calaSourceDigest(root) {
  // Independently reproduce the documented manifest, without importing the
  // product's build/digest implementation or trusting its declared metadata.
  const names = ['cala-contract.d.ts', 'cala-contract.mjs', 'core.mjs', 'fixture.mjs',
    'public/app.mjs', 'public/index.html', 'public/style.css', 'server.mjs'].sort();
  const entries = await Promise.all(names.map(async name => `${name}\0${sha256(await readFile(resolve(root, name)))}\n`));
  const actual = sha256(entries.join(''));
  const metadata = await readFile(resolve(root, 'source-meta.mjs'), 'utf8');
  const declared = metadata.match(/PRODUCT_SOURCE_DIGEST\s*=\s*'([a-f0-9]{64})'/)?.[1];
  assert.equal(declared, actual, 'Declared Cala metadata differs from independently hashed product bytes');
  return actual;
}

async function calaJourney(page, productRoot) {
  const productDigest = await calaSourceDigest(productRoot);
  await textIs(page, '#summary', '2 supported · 5 withheld');
  await textIncludes(page, '.fixture', 'FICTIONAL_FIXTURE');
  assert.equal(await page.locator('#candidates .candidate').count(), 7);
  assert.equal(await page.locator('#download').isDisabled(), true);

  const echo = page.locator('[data-id="inv-echo"]');
  await echo.focus();
  await echo.press('Enter');
  await textIs(page, '#detail-title', 'Echo Ventures');
  await focused(page, '#detail-title');
  await textIncludes(page, '#detail', 'Same-name collision: inv-echo-uk');
  assert.equal(await page.locator('#add').isDisabled(), true);
  assert.equal(await page.locator('#detail .round-path').count(), 0);

  await page.locator('[data-id="inv-tide"]').click();
  await textIs(page, '#detail-title', 'Tide Foundry');
  await textIncludes(page, '#detail .warnings', 'Contradiction');
  assert.equal(await page.locator('#detail .round-path').count(), 1);
  await textIncludes(page, '#detail .round-path', 'round-kite-seed-2026');
  assert.equal(await page.locator('[data-id="inv-tide"] .score').textContent(), '10');

  await page.locator('[data-id="inv-larch"]').click();
  await textIs(page, '#detail-title', 'Larch Seed Partners');
  assert.equal(await page.locator('#detail .round-path').count(), 1);
  await textIncludes(page, '#detail .round-path', 'round-moss-seed-2026');
  await textIncludes(page, '#detail .warnings', 'ISSUER records describe the company');
  const metrics = await page.locator('#detail .metrics dd').allTextContents();
  assert.deepEqual(metrics, ['1', 'UNKNOWN']);
  assert.equal(await page.locator('#detail details').count(), 3);
  const filing = page.locator('#detail details').filter({ hasText: 'Fictional announcement moss-filing' });
  assert.equal(await filing.getAttribute('open'), null);
  await filing.locator('summary').focus();
  await filing.locator('summary').press('Enter');
  assert.notEqual(await filing.getAttribute('open'), null);
  assert.match(await filing.textContent(), /NOT AN EXTRA ROUND/);
  assert.match(await filing.textContent(), /UNKNOWN/);
  await filing.locator('summary').press('Enter');
  assert.equal(await filing.getAttribute('open'), null);

  await page.locator('#add').focus();
  await page.locator('#add').press('Enter');
  await focused(page, '[data-note="inv-larch"]');
  const initialNote = 'CRACI synthetic review: read the issuer and filing records.';
  const finalNote = 'CRACI reviewed <script>inert note</script> & one economic round.';
  await page.locator('[data-note="inv-larch"]').fill(initialNote);
  assert.equal(await page.locator('#download').isDisabled(), true);
  await page.locator('[data-approve="inv-larch"]').focus();
  await page.locator('[data-approve="inv-larch"]').press('Space');
  assert.equal(await page.locator('#download').isEnabled(), true);
  await page.locator('[data-note="inv-larch"]').fill(finalNote);
  assert.equal(await page.locator('[data-approve="inv-larch"]').isChecked(), false);
  assert.equal(await page.locator('#download').isDisabled(), true);
  await page.locator('[data-approve="inv-larch"]').check();

  await page.locator('[data-id="inv-tide"]').click();
  await page.locator('#add').click();
  assert.equal(await page.locator('[data-note="inv-larch"]').inputValue(), finalNote);
  assert.equal(await page.locator('#shortlist script').count(), 0, 'Review text must stay inert after UI rerender');
  assert.equal(await page.locator('#download').isDisabled(), true, 'Every shortlisted candidate needs approval');
  await page.locator('[data-note="inv-tide"]').fill('CRACI: keep the contradictory round excluded.');
  await page.locator('[data-approve="inv-tide"]').check();
  const downloaded = await downloadText(page, '#download', 'roundlens-fictional-reviewed-shortlist.json');
  assert.ok(!downloaded.includes('<'), 'Export escapes HTML delimiters while retaining note content');
  const artifact = JSON.parse(downloaded);
  assert.equal(artifact.schema, 'roundlens.shortlist.v1');
  assert.equal(artifact.mode, 'FICTIONAL_FIXTURE');
  assert.equal(artifact.autoSend, false);
  assert.equal(artifact.baseSourceSha, 'a33f525171b6424d39dfc4c889b63e0fc5cb459e');
  assert.equal(artifact.productSourceDigest, productDigest);
  assert.deepEqual(artifact.goal, { sector: 'Climate software', geography: 'Nordics', stage: 'Seed', from: '2025-11-14', to: '2026-11-14' });
  assert.equal(artifact.asOf, '2026-11-14');
  assert.deepEqual(artifact.shortlist.map(row => row.entity.id), ['inv-larch', 'inv-tide']);
  for (const row of artifact.shortlist) {
    assert.equal(row.humanReview.state, 'APPROVED_BY_LOCAL_USER');
    assert.equal(row.economicRoundCount, 1);
    assert.equal(row.score, 10);
    assert.equal(row.totalFunding, 'UNKNOWN');
    assert.equal(row.rounds.length, 1);
  }
  const [larch, tide] = artifact.shortlist;
  assert.equal(larch.humanReview.note, finalNote);
  assert.equal(larch.rounds[0].key, '["co-moss","round-moss-seed-2026"]');
  assert.equal(larch.rounds[0].event.id, 'moss-round');
  assert.equal(larch.rounds[0].event.eventDate, '2026-08-12');
  assert.deepEqual(larch.rounds[0].citations.map(c => ({ id: c.id, originId: c.originId, url: c.url, publishedAt: c.publishedAt })), [
    { id: 'src-moss-round', originId: 'origin-moss-round', url: 'https://example.invalid/sources/moss-round', publishedAt: '2026-08-12' },
    { id: 'src-moss-filing', originId: 'origin-moss-filing', url: 'https://example.invalid/sources/moss-filing', publishedAt: '2026-08-12' },
  ]);
  assert.equal(tide.humanReview.note, 'CRACI: keep the contradictory round excluded.');
  assert.equal(tide.rounds[0].event.id, 'kite-round');
  assert.equal(tide.rounds[0].event.issuerId, 'co-kite');
  assert.equal(tide.rounds[0].citations[0].url, 'https://example.invalid/sources/kite-round');
  assert.ok(tide.warnings.some(w => w.includes('Contradiction')));

  await page.locator('[data-remove="inv-tide"]').click();
  await textIs(page, '#review-count', '1 selected');
  assert.equal(await page.locator('#download').isEnabled(), true);
  await page.locator('[name="sector"]').selectOption('Health software');
  await page.locator('#goal-form button').focus();
  await page.locator('#goal-form button').press('Enter');
  await textIs(page, '#summary', '0 supported · 7 withheld');
  await textIs(page, '#review-count', '0 selected');
  assert.equal(await page.locator('#download').isDisabled(), true);
  assert.equal(await page.locator('#add').isDisabled(), true);

  await page.locator('[name="sector"]').selectOption('Climate software');
  await page.locator('[name="from"]').fill('2026-08-12');
  await page.locator('[name="to"]').fill('2026-08-12');
  await page.locator('#goal-form button').click();
  await textIs(page, '#summary', '1 supported · 6 withheld');
  await textIs(page, '#detail-title', 'Larch Seed Partners');
  await page.locator('#add').click();
  await page.locator('[data-approve="inv-larch"]').check();
  assert.equal(await page.locator('#download').isEnabled(), true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await textIs(page, '#summary', '2 supported · 5 withheld');
  await textIs(page, '#review-count', '0 selected');
  assert.equal(await page.locator('#download').isDisabled(), true);
  return { mode: 'FICTIONAL_FIXTURE', eligibleInvestors: 2, filingAndIssuerDedup: 'passed', identityAbstention: 'passed',
    conflictingRoundExclusion: 'passed', keyboardCandidateAndDisclosure: 'passed', notesRevokeApproval: 'passed',
    allCandidatesRequireApproval: 'passed', exactDownloadedCitations: 3, productSourceDigest: productDigest,
    goalChangeClearsReview: 'passed', inclusiveEventDateFilter: 'passed', reloadClearsReview: 'passed', liveCala: false };
}

function contextInput(name) {
  const snapshot = (id, priceCents, inventory, leadDays) => ({ mode: 'SYNTHETIC_REPLAY', id,
    url: `https://${id}.example.invalid/stock/desk-lamp`, httpStatus: 200, jsonSuccess: true, partial: false,
    observedAt: '2026-11-14T09:00:00.000Z', cacheOriginAt: '2026-11-14T09:00:00.000Z', currency: 'EUR',
    priceCents, inventory, leadDays, confidence: 96, text: 'SYNTHETIC_REPLAY • fictional supplier listing. Desk lamp, ivory.' });
  const input = { mode: 'SYNTHETIC_REPLAY', asOf: '2026-11-14T09:01:00.000Z', snapshots: [snapshot('north', 1200, 80, 2), snapshot('coast', 1350, 65, 3)] };
  if (name === 'after' || name === 'failed') {
    input.asOf = '2026-11-14T09:03:00.000Z'; input.snapshots[0].inventory = 12;
    input.snapshots[0].text += ' SYNTHETIC_REPLAY stock correction: 12 units.';
  }
  if (name === 'cosmetic') input.snapshots[0].text += ' SYNTHETIC_REPLAY new banner: Weekend collection.';
  if (name === 'failed') input.snapshots[1].jsonSuccess = false;
  return input;
}

async function contextCase(page, name) {
  const winner = name === 'failed' ? null : name === 'after' ? 'coast' : 'north';
  // Before and cosmetic intentionally share a verdict. Wait for the selected
  // control to commit after async hashing, not just the unchanged heading.
  await page.waitForFunction(name => document.querySelector(`[data-case="${name}"]`)?.getAttribute('aria-pressed') === 'true', name);
  await textIs(page, '#result h2', winner === 'coast' ? 'Review Coast Trading' : winner === 'north' ? 'Review North Supply' : 'Pause the sourcing decision');
  const packet = JSON.parse(await page.locator('#inspector').textContent());
  const input = contextInput(name);
  assert.equal(packet.label, 'SYNTHETIC_REPLAY');
  assert.deepEqual(packet.input, input);
  assert.equal(packet.result.mode, 'SYNTHETIC_REPLAY');
  assert.equal(packet.result.winner, winner);
  assert.equal(packet.result.actionAuthorized, false);
  assert.equal(await page.locator(`[data-case="${name}"]`).getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('[data-case][aria-pressed="true"]').count(), 1);
  assert.equal(await page.locator('#cards .card').count(), 2);
  if (name === 'failed') {
    assert.equal(packet.result.status, 'REFUSE');
    assert.equal(packet.result.reason, 'failed-or-partial-output');
    assert.deepEqual(packet.result.candidates, []);
    assert.equal(Object.hasOwn(packet.result, 'inputHash'), false);
    assert.equal(await page.locator('#cards .selected').count(), 0);
    await textIncludes(page, '#rows', 'Refused');
  } else {
    assert.equal(packet.result.status, 'REVIEW');
    assert.equal(packet.result.reason, 'human-review-required');
    assert.equal(packet.result.inputHash, sha256(stableJSON(input)));
    assert.equal(packet.result.policyHash, sha256(stableJSON({ quantity: 40, budgetCents: 60000, maxLeadDays: 5, minConfidence: 90, ttlMs: 300000 })));
    assert.equal(packet.result.asOf, input.asOf);
    assert.deepEqual(packet.result.candidates.map(c => c.id), ['coast', 'north']);
    for (const candidate of packet.result.candidates) {
      const source = input.snapshots.find(s => s.id === candidate.id);
      assert.equal(candidate.totalCents, candidate.id === 'north' ? 48000 : 54000);
      assert.equal(candidate.inventory, source.inventory);
      assert.equal(candidate.evidenceHash, sha256(stableJSON(source)));
      assert.deepEqual(candidate.constraints, name === 'after' && candidate.id === 'north' ? ['insufficient-stock'] : []);
    }
    const rowCells = await page.locator('#rows tr').evaluateAll(rows => rows.map(row => [...row.querySelectorAll('td')].map(td => td.textContent)));
    assert.deepEqual(rowCells, [
      ['north', '€480.00', name === 'after' ? '12' : '80', '2 days', name === 'after' ? 'insufficient-stock' : 'Eligible'],
      ['coast', '€540.00', '65', '3 days', 'Eligible'],
    ]);
  }
  return packet;
}

async function contextMemo(page, packet) {
  await page.locator('#review').focus();
  await page.locator('#review').press('Enter');
  assert.equal(await page.locator('#memo-section').isVisible(), true);
  await focused(page, '#memo-section');
  const visibleMemo = await page.locator('#memo').textContent();
  assert.match(visibleMemo, /^SYNTHETIC_REPLAY\nSUPPLYPULSE — HUMAN-ONLY SOURCING MEMO\n/);
  assert.ok(visibleMemo.includes(`Candidate for review: ${packet.result.winner ?? 'none'}`));
  assert.ok(visibleMemo.includes(`Input: ${packet.result.inputHash ?? 'rejected'}`));
  assert.ok(visibleMemo.includes(`Policy: ${packet.result.policyHash ?? 'not evaluated'}`));
  assert.ok(visibleMemo.includes('No purchase, monitoring, webhook or outbound action is authorized.'));
  const text = await downloadText(page, '#download', 'SupplyPulse-SYNTHETIC_REPLAY-memo.txt');
  assert.equal(text, visibleMemo, 'Downloaded memo must be the current visibly reviewed result');
  return sha256(text);
}

async function contextJourney(page) {
  const first = await contextCase(page, 'after');
  assert.equal(await page.locator('#memo-section').isHidden(), true);
  const reviewedAfter = await contextMemo(page, first);
  await page.locator('[data-case="before"]').focus();
  await page.locator('[data-case="before"]').press('Enter');
  const before = await contextCase(page, 'before');
  assert.equal(await page.locator('#memo-section').isHidden(), true, 'Changing scenario closes the previous review');
  await page.locator('#evidence summary').focus();
  await page.locator('#evidence summary').press('Enter');
  assert.notEqual(await page.locator('#evidence').getAttribute('open'), null);
  await page.locator('#evidence summary').press('Enter');
  assert.equal(await page.locator('#evidence').getAttribute('open'), null);
  await page.locator('[data-case="cosmetic"]').click();
  const cosmetic = await contextCase(page, 'cosmetic');
  assert.notEqual(cosmetic.result.inputHash, before.result.inputHash);
  assert.equal(cosmetic.result.policyHash, before.result.policyHash);
  assert.equal(cosmetic.result.winner, before.result.winner);
  const reviewedCosmetic = await contextMemo(page, cosmetic);
  assert.notEqual(reviewedCosmetic, reviewedAfter);
  await page.locator('[data-case="failed"]').click();
  const failed = await contextCase(page, 'failed');
  assert.equal(await page.locator('#memo-section').isHidden(), true);
  const reviewedRefusal = await contextMemo(page, failed);
  assert.notEqual(reviewedRefusal, reviewedCosmetic);
  // Exercise actual successive controls; do not mutate application globals or
  // inject synthetic DOM events in place of a user interaction.
  for (const name of ['before', 'failed', 'cosmetic', 'after']) await page.locator(`[data-case="${name}"]`).click();
  await contextCase(page, 'after');
  assert.equal(await page.locator('#memo-section').isHidden(), true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  const recovered = await contextCase(page, 'after');
  assert.equal(await page.locator('#memo-section').isHidden(), true);
  const recoveredMemo = await contextMemo(page, recovered);
  assert.equal(recoveredMemo, reviewedAfter);
  return { mode: 'SYNTHETIC_REPLAY', beforeWinner: 'north', afterWinner: 'coast', quantity: 40,
    independentlyCheckedTotalsCents: [48000, 54000], sourceAndPolicyHashes: 'passed', cosmeticChangeKeepsDecision: 'passed',
    http200FailedJSON: 'whole-comparison-refused', keyboardReplayEvidenceAndReview: 'passed',
    scenarioChangeClosesReview: 'passed', actualMemoDownloads: 4, downloadMatchesCurrentReview: 'passed',
    reloadRecovery: 'passed', liveContextAPI: false, externalActions: false };
}

async function assertPortFree(port) {
  const reservation = reservePort();
  await new Promise((done, reject) => { reservation.once('error', reject); reservation.listen(port, '127.0.0.1', done); });
  await new Promise((done, reject) => reservation.close(error => error ? reject(error) : done()));
}

async function startServer(root, product) {
  await assertPortFree(product.port);
  const base = `http://127.0.0.1:${product.port}`;
  const child = spawn(process.execPath, [resolve(root, product.directory, 'server.mjs')], {
    cwd: root, stdio: ['ignore', 'pipe', 'pipe'],
    env: { PATH: process.env.PATH, PORT: String(product.port), NODE_ENV: 'test', TZ: 'UTC' },
  });
  let logs = '', spawnError;
  child.on('error', error => { spawnError = error; });
  const capture = bytes => { logs = (logs + bytes.toString()).slice(-64_000); };
  child.stdout.on('data', capture); child.stderr.on('data', capture);
  async function close() {
    if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
    const exited = new Promise(done => child.once('exit', done));
    child.kill('SIGTERM');
    if (!await Promise.race([exited.then(() => true), sleep(2500).then(() => false)])) {
      child.kill('SIGKILL');
      await Promise.race([exited, sleep(2500).then(() => { throw Error('Owned product server did not stop'); })]);
    }
  }
  try {
    const deadline = Date.now() + 15_000;
    while (Date.now() < deadline) {
      if (spawnError) throw spawnError;
      assert.equal(child.exitCode, null, `Owned server exited: ${logs}`);
      assert.equal(child.signalCode, null, `Owned server stopped: ${logs}`);
      try {
        const response = await fetch(base, { signal: AbortSignal.timeout(800) });
        if (response.ok) { await response.arrayBuffer(); return { base, close, logs: () => logs }; }
      } catch { /* Only retry bounded local startup. */ }
      await sleep(100);
    }
    throw Error(`Owned server startup timed out: ${logs}`);
  } catch (error) { await close(); throw error; }
}

async function main() {
  const productName = process.env.CRACI_PRODUCT;
  const engineName = process.env.CRACI_BROWSER;
  assert.ok(Object.hasOwn(products, productName), 'CRACI_PRODUCT must be cala or context');
  assert.ok(Object.hasOwn(engines, engineName), 'CRACI_BROWSER must be chromium, firefox or webkit');
  assert.ok(process.env.SOURCE_DIR, 'SOURCE_DIR is required');
  assert.match(process.env.EXPECTED_SOURCE_SHA ?? '', /^[a-f0-9]{40}$/, 'Full lowercase EXPECTED_SOURCE_SHA is required');
  const root = resolve(process.env.SOURCE_DIR), product = products[productName];
  const head = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  assert.equal(head, process.env.EXPECTED_SOURCE_SHA, 'Product checkout HEAD differs from the pinned source');
  const dirt = execFileSync('git', ['-C', root, 'status', '--porcelain', '--untracked-files=all', '--', product.directory], { encoding: 'utf8' });
  assert.equal(dirt, '', 'Product files must match the clean pinned checkout');
  const output = resolve(process.env.CRACI_BROWSER_OUTPUT || 'craci-new-products-browser-results');
  await mkdir(output, { recursive: true });
  const harnessSha256 = sha256(await readFile(new URL(import.meta.url)));
  const browser = await engines[engineName].launch({ headless: true });
  const results = [];
  try {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      const label = `${productName}-${engineName}-${viewport.width}`, started = Date.now();
      const pageErrors = [], deniedRequests = [], events = [];
      const result = { schema: 'craci.new-products-browser.v1', label, product: productName, browser: engineName,
        browserVersion: browser.version(), nodeVersion: process.version, sourceSha: head, harnessSha256,
        viewport, mode: product.mode, liveSponsorAPI: false, status: 'failed' };
      let server, context, page;
      try {
        server = await startServer(root, product);
        context = await browser.newContext({ viewport, acceptDownloads: true, serviceWorkers: 'block' });
        context.setDefaultTimeout(15_000);
        await context.route('**/*', async route => {
          const request = route.request(), url = new URL(request.url());
          const item = { method: request.method(), url: `${url.origin}${url.pathname}` };
          if (events.length < 200) events.push(item);
          if (url.origin === server.base && ['GET', 'HEAD'].includes(request.method())) await route.continue();
          else { deniedRequests.push(item); await route.abort(); }
        });
        page = await context.newPage();
        page.on('pageerror', error => pageErrors.push(error.message));
        const response = await page.goto(server.base, { waitUntil: 'domcontentloaded' });
        assert.equal(response.status(), 200);
        result.coverage = await product.journey(page, resolve(root, product.directory));
        result.overflowPixels = await page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth);
        assert.ok(result.overflowPixels <= 1, `Horizontal page overflow: ${result.overflowPixels}px`);
        assert.deepEqual(pageErrors, [], 'Uncaught product browser exception');
        assert.deepEqual(deniedRequests, [], 'Unexpected external or write request');
        result.screenshot = `${label}.png`;
        await page.screenshot({ path: resolve(output, result.screenshot), fullPage: true });
        result.status = 'passed';
      } catch (error) {
        result.error = error.stack || String(error);
        result.screenshot = `${label}-failure.png`;
        await page?.screenshot({ path: resolve(output, result.screenshot), fullPage: true }).catch(() => {});
      } finally {
        const cleanupErrors = [];
        try { await context?.close(); } catch (error) { cleanupErrors.push(`context: ${error.message}`); }
        try { await server?.close(); } catch (error) { cleanupErrors.push(`server: ${error.message}`); }
        if (cleanupErrors.length) { result.status = 'failed'; result.cleanupErrors = cleanupErrors; }
        result.durationMs = Date.now() - started;
        result.pageErrors = pageErrors; result.deniedRequests = deniedRequests;
        await writeFile(resolve(output, `${label}.server.log`), server?.logs() ?? 'Server did not start.\n');
        await writeFile(resolve(output, `${label}.log`), events.map(event => JSON.stringify(event)).join('\n') + '\n');
        await writeFile(resolve(output, `${label}.json`), JSON.stringify(result, null, 2) + '\n');
        results.push(result);
        if (result.status !== 'passed') process.exitCode = 1;
        console.log(JSON.stringify(result));
      }
    }
  } finally { await browser.close(); }
  await writeFile(resolve(output, `${productName}-${engineName}.json`), JSON.stringify({
    schema: 'craci.new-products-browser-run.v1', sourceSha: head, harnessSha256,
    status: results.length === 2 && results.every(result => result.status === 'passed') ? 'passed' : 'failed', results,
  }, null, 2) + '\n');
}

await main().catch(error => {
  process.exitCode = 1;
  console.error(JSON.stringify({ schema: 'craci.new-products-browser.v1', status: 'failed', phase: 'setup-or-cleanup', error: error.stack || String(error) }));
});
