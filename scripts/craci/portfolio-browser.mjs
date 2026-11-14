import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { createServer as createPortReservation } from 'node:net';
import { resolve } from 'node:path';
import { chromium, firefox, webkit } from 'playwright';

// Source and harness checkouts stay separate. These are synthetic local products;
// none of the journeys authorizes an external provider, purchase or real user.
const products = {
  sbank: { server: 'solutions/s-pankki-economic-trainer/server.mjs', run: sbankJourney },
  hostinger: { server: 'solutions/hostinger-manipulation-radar/server.mjs', run: hostingerJourney },
  espoo: { server: 'solutions/espoo-proofmatch/serve.mjs', run: espooJourney },
};
const engines = { chromium, firefox, webkit };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function textIs(page, selector, expected) {
  await page.waitForFunction(({ selector, expected }) =>
    document.querySelector(selector)?.textContent.trim() === expected,
  { selector, expected });
}

async function includesText(page, selector, expected) {
  await page.waitForFunction(({ selector, expected }) =>
    document.querySelector(selector)?.textContent.includes(expected),
  { selector, expected });
}

async function moneyIs(page, selector, cents, suffix = '') {
  assert.ok(Number.isSafeInteger(cents) && cents >= 0);
  await page.waitForFunction(({ selector, cents, suffix }) => {
    let value = (document.querySelector(selector)?.textContent ?? '').trim();
    if (suffix) {
      if (!value.endsWith(suffix)) return false;
      value = value.slice(0, -suffix.length).trim();
    }
    // The public UI contract is en-FI EUR formatting. Expected cents above are
    // independent arithmetic; do not discard signs or decimal separators.
    const expected = new Intl.NumberFormat('en-FI', { style: 'currency', currency: 'EUR' }).format(cents / 100);
    const normaliseSpaces = text => text.replace(/\s+/g, ' ').trim();
    return normaliseSpaces(value) === normaliseSpaces(expected);
  }, { selector, cents, suffix });
}

async function citationsResolve(page, selector) {
  const links = await page.locator(selector).evaluateAll(nodes => nodes.map(n => ({
    href: n.getAttribute('href'),
    targetExists: Boolean(document.getElementById(n.getAttribute('href')?.slice(1))),
  })));
  assert.ok(links.length > 0, 'Expected actual source citations');
  assert.ok(links.every(x => /^#source-row-\d+$/.test(x.href) && x.targetExists),
    'Every displayed citation must have a rendered transaction target');
  return links.map(x => Number(x.href.slice('#source-row-'.length)));
}

async function sbankJourney(page) {
  // Independent fixture arithmetic: latest checking 3,227.45 + savings 650;
  // initial reserves 350 + 150 + 120. Do not use the product calculator as oracle.
  await moneyIs(page, '#balance', 387745);
  await moneyIs(page, '#available', 325745);
  await textIs(page, '#dataset-label', 'FICTIONAL DEMO · LOCAL DATA');
  assert.equal(await page.locator('#transaction-rows tr').count(), 16);
  await moneyIs(page, '#runway-result .runway-metric:first-child strong', 297245);
  await moneyIs(page, '#runway-result .runway-metric:nth-child(2) strong', 22731);
  assert.equal(await page.locator('#runway-chart .runway-column').count(), 14);

  await page.locator('[data-prompt="How much did I spend on taxis?"]').click();
  await moneyIs(page, '#answer .answer-text', 1250, ' net spending, using 1 matching source rows.');
  assert.deepEqual(await citationsResolve(page, '#answer a.source-pill'), [9]);
  await page.locator('#answer a.source-pill').click();
  await page.waitForFunction(() => location.hash === '#source-row-9');
  assert.match(await page.locator('#source-row-9').getAttribute('class'), /highlight-row/);

  await page.locator('#regular').fill('100.01');
  await page.locator('#irregular').fill('50.02');
  await page.locator('#emergency').fill('25.03');
  await page.locator('#reserves-form button[type="submit"]').click();
  await moneyIs(page, '#available', 370239);
  await textIs(page, '#reserve-error', '');
  await page.locator('#runway-days').selectOption('7');
  await page.locator('#runway-daily').fill('10.01');
  await page.locator('#runway-onetime').fill('12.34');
  await page.locator('#runway-form button[type="submit"]').click();
  await moneyIs(page, '#runway-result .runway-metric:first-child strong', 361998);
  await moneyIs(page, '#runway-result .runway-metric:nth-child(2) strong', 52715);
  assert.equal(await page.locator('#runway-chart .runway-column').count(), 7);
  await citationsResolve(page, '#runway-note a');

  await page.locator('#runway-days').selectOption('30');
  await page.locator('#runway-daily').fill('200.00');
  await page.locator('#runway-onetime').fill('0.00');
  await page.locator('#runway-form button[type="submit"]').click();
  await moneyIs(page, '#runway-result .runway-metric:first-child strong', 0);
  await includesText(page, '#runway-result', 'not affordable within this exercise');
  assert.equal(await page.locator('#runway-chart .runway-column').count(), 30);
  assert.equal(await page.locator('#runway-chart .runway-column.empty').count(), 12);

  await page.locator('#question').fill("What is next year's inflation?");
  await page.locator('#ask-form button[type="submit"]').click();
  await textIs(page, '#answer .answer-title', 'NOT ENOUGH INFORMATION');
  assert.equal(await page.locator('#answer a.source-pill').count(), 0);

  // New, entirely authored three-row fixture exercises the actual file input.
  const rows = [
    ['2026-11-01', 'SALARY', '1000.00', '1000.00', 'salary', 1001],
    ['2026-11-02', 'TAXIS', '-12.34', '987.66', 'card', 1002],
    ['2026-11-03', 'TAXIS', '2.34', '990.00', 'refund', 1003],
  ].map(([day, category, amount, balance, type, line]) => ({
    customer_id: 'CRACI_SYNTHETIC_CUSTOMER', bank_account_id: 'CRACI_SYNTHETIC_ACCOUNT',
    tx_date: day, tx_timestamp: `${day}T12:00:00Z`, category,
    tx_amount_eur: amount, balance_after_eur: balance,
    transaction_type: type, sourceLine: line,
  }));
  await page.locator('#dataset-upload').setInputFiles({
    name: 'craci-authored-transactions.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(rows)),
  });
  await textIs(page, '#dataset-label', 'LOCAL FILE · 3 ROWS · SOURCE UNVERIFIED');
  await moneyIs(page, '#balance', 99000);
  await moneyIs(page, '#available', 81494);
  await page.locator('[data-prompt="How much did I spend on taxis?"]').click();
  await moneyIs(page, '#answer .answer-text', 1000, ' net spending, using 2 matching source rows.');
  assert.deepEqual(await citationsResolve(page, '#answer a.source-pill'), [1002, 1003]);
  assert.equal(await page.locator('#transaction-rows tr').count(), 3);

  const invalid = rows.map((row, index) => ({
    ...row, customer_id: index === 0 ? 'ANOTHER_SYNTHETIC_CUSTOMER' : row.customer_id,
  }));
  await page.locator('#dataset-upload').setInputFiles({
    name: 'craci-invalid-mixed-customers.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(invalid)),
  });
  await includesText(page, '#upload-error', 'Multiple customers');
  await textIs(page, '#dataset-label', 'LOCAL FILE · 3 ROWS · SOURCE UNVERIFIED');
  await moneyIs(page, '#balance', 99000);
  assert.deepEqual(await citationsResolve(page, '#answer a.source-pill'), [1002, 1003]);

  await page.locator('#regular').fill('9000.00');
  await page.locator('#irregular').fill('0.00');
  await page.locator('#emergency').fill('0.00');
  await page.locator('#reserves-form button[type="submit"]').click();
  await moneyIs(page, '#available', 0);
  await page.locator('[data-prompt="What can I safely spend this week?"]').click();
  await includesText(page, '#answer .answer-note', 'Reserves exceed observed balances');
  await includesText(page, '#answer .answer-note', 'spending room is zero');
  return {
    fixtureBalanceCents: 387745, decimalReservesCents: 17506,
    independentSevenDayRemainingCents: 361998, roundedDownDailyLimitCents: 52715,
    centArithmetic: 'passed', renderedCitationTargets: 'passed',
    scenarioShortfall: 'passed', unsupportedQuestion: 'refused',
    browserFileImport: 'passed', mixedCustomers: 'refused-with-prior-data-intact',
    overreservedBudget: 'zero-room-with-warning',
  };
}

async function readDownload(download) {
  assert.equal(await download.failure(), null);
  const stream = await download.createReadStream();
  assert.ok(stream, 'Download must be readable');
  const chunks = [];
  let length = 0;
  for await (const chunk of stream) {
    length += chunk.length;
    assert.ok(length <= 2_000_000, 'Unexpectedly large synthetic report');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

async function hostingerJourney(page) {
  await textIs(page, '#event-count', '8');
  await textIs(page, '#group-count', '1');
  await textIs(page, '#review-count', '1');
  await textIs(page, '#detail .score-total', '100rule points / 100');
  assert.equal(await page.locator('#detail .events-table tbody tr').count(), 8);
  assert.match(await page.locator('#detail .events-table').textContent(), /launch-1/);
  await page.locator('.sensitivity label').filter({ hasText: 'Remove synchronized window' }).locator('input').check();
  await textIs(page, '.sensitivity .whatif', '75/100 → Review gate not met (-25 points)');
  // Removing the timing premise must change admissibility, not just the score.
  await textIs(page, '#review-count', '1');
  await page.locator('.disposition select').selectOption('Needs investigation');
  await includesText(page, '#notice', 'browser only');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await textIs(page, '#event-count', '8');
  await page.waitForFunction(() => document.querySelector('.disposition select')?.value === 'Needs investigation');
  await textIs(page, '.sensitivity .whatif', '100/100 → Analyst review (+0 points)');

  const [download] = await Promise.all([
    page.waitForEvent('download'), page.locator('#export').click(),
  ]);
  assert.equal(download.suggestedFilename(), 'synthetic-radar-swarm.json');
  const report = await readDownload(download);
  assert.equal(report.schema, 'radar-report-v1');
  assert.equal(report.synthetic, true);
  assert.equal(report.hostinger, 'NOT VERIFIED');
  assert.equal(report.scenario, 'swarm');
  assert.equal(report.eventCount, 8);
  assert.equal(report.findings.length, 1);
  assert.equal(report.findings[0].score, 100);
  assert.equal(report.findings[0].review, true);
  assert.equal(report.dispositions['launch-1'], 'Needs investigation');
  assert.deepEqual(report.findings[0].events.map(e => e.id),
    Array.from({ length: 8 }, (_, i) => `launch-${i + 1}`));

  await page.locator('#scenario').selectOption('wire');
  await textIs(page, '#event-count', '8');
  await textIs(page, '#review-count', '0');
  await textIs(page, '#detail .score-total', '20rule points / 100');
  await includesText(page, '#detail', 'Attributed syndication');
  await page.locator('#scenario').selectOption('sparse');
  await textIs(page, '#event-count', '2');
  await textIs(page, '#review-count', '0');
  await textIs(page, '#detail h2', 'Insufficient evidence');
  assert.equal(await page.locator('#detail .events-table tbody tr').count(), 2);

  await page.locator('#scenario').selectOption('mixed');
  await textIs(page, '#event-count', '23');
  await textIs(page, '#group-count', '3');
  await textIs(page, '#review-count', '1');
  await page.locator('#sort').selectOption('time');
  await page.locator('#findings button').nth(2).click();
  await textIs(page, '#detail .scoreline .eyebrow', 'EVIDENCE / community-1');
  assert.equal(await page.locator('#detail .events-table tbody tr').count(), 8);
  assert.equal(await page.locator('#findings button[aria-pressed="true"]').count(), 1);

  const [response] = await Promise.all([
    page.waitForResponse(r => new URL(r.url()).pathname === '/api/benchmark'),
    page.locator('#refresh').click(),
  ]);
  assert.equal(response.status(), 200);
  const benchmark = await response.json();
  assert.equal(benchmark.mode, 'SYNTHETIC');
  assert.equal(benchmark.splits.development.cases, 8);
  assert.equal(benchmark.splits.heldOut.cases, 12);
  const held = benchmark.splits.heldOut.radar;
  assert.deepEqual([held.tp, held.fp, held.tn, held.fn], [4, 1, 6, 1]);
  await page.locator('#benchmark tbody tr').filter({ hasText: 'Held-out · radar · 12 cases' }).waitFor();
  assert.equal(await page.locator('#benchmark tbody tr').count(), 4);
  return {
    observedEventLedger: 'passed', timingPremiseAblation: 'passed',
    localDispositionPersistence: 'passed', actualDownloadedReport: 'passed',
    attributedSyndication: 'not-flagged', sparseEvidence: 'insufficient',
    mixedClusterSelection: 'passed', heldOutAuthoredSyntheticCases: 12,
    knownFalsePositive: 1, knownFalseNegative: 1,
  };
}

async function espooJourney(page) {
  await textIs(page, '#count', '5 fictional candidates · all visible');
  assert.deepEqual(await page.locator('#candidates button').evaluateAll(nodes => nodes.map(n => n.dataset.candidate)),
    ['mira', 'devon', 'jules', 'ren', 'ari']);
  assert.equal(await page.locator('#slot option').count(), 4);
  assert.equal(await page.locator('#slot').inputValue(), '2026-11-15T09:00:00Z');
  await page.locator('#detail a[href="#evidence-M-01"]').first().click();
  assert.equal(await page.locator('#evidence-M-01').getAttribute('open'), '');
  let focusFailure;
  try {
    await page.waitForFunction(() => document.activeElement === document.querySelector('#evidence-M-01 summary'));
    assert.equal(await page.evaluate(() => location.hash), '#evidence-M-01');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#evidence-M-01')?.open === false);
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#evidence-M-01')?.open === true);
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#evidence-M-01 summary')), true);
  } catch (error) {
    // Focus is independent of the meeting state machine. Keep its failure,
    // inspect the actual browser state and continue the remaining journey;
    // the complete viewport still fails below, even if later checks pass.
    const observed = await page.evaluate(() => ({
      activeTag: document.activeElement?.tagName,
      activeId: document.activeElement?.id,
      activeMarkup: document.activeElement?.outerHTML.slice(0, 300),
      sourceOpen: document.querySelector('#evidence-M-01')?.open,
      hash: location.hash,
    }));
    focusFailure = { check: 'evidence-summary-focus', error: error.message, observed };
  }
  await includesText(page, '#evidence-M-01', 'not externally verified');

  await page.locator('#proposal-form button[type="submit"]').click();
  await textIs(page, '#meeting-list .badge', 'SIMULATED · PENDING');
  assert.equal(await page.locator('#slot').count(), 0);
  assert.equal(await page.locator('#proposal-form button[type="submit"]').count(), 0);
  assert.equal(await page.locator('#meeting-list [data-actor="employer"][data-action="accept"]').count(), 0);
  await page.locator('#meeting-list [data-actor="candidate"][data-action="accept"]').click();
  await textIs(page, '#meeting-list .badge', 'SIMULATED · ACCEPTED');
  assert.equal(await page.locator('#meeting-list [data-action="accept"]').count(), 0);
  await page.locator('#meeting-list [data-actor="employer"][data-action="cancel"]').click();
  await textIs(page, '#meeting-list .badge', 'SIMULATED · CANCELLED');
  assert.equal(await page.locator('#slot option').count(), 4);
  assert.equal(await page.locator('#slot').inputValue(), '2026-11-15T09:00:00Z');

  await page.locator('#proposal-form button[type="submit"]').click();
  await page.locator('#meeting-list [data-actor="candidate"][data-action="decline"]').click();
  assert.deepEqual(await page.locator('#meeting-list .badge').allTextContents(),
    ['SIMULATED · CANCELLED', 'SIMULATED · DECLINED']);
  assert.equal(await page.locator('#slot option').count(), 4);

  await page.locator('#candidates [data-candidate="ari"]').click();
  assert.ok((await page.locator('#detail .skill-status').allTextContents()).includes('RELATED'));
  await page.locator('#proposal-form button[type="submit"]').click();
  await page.locator('#candidates [data-candidate="mira"]').click();
  // Ari's 09:00 pending proposal holds the same employer's time for Mira.
  assert.equal(await page.locator('#slot option').count(), 3);
  assert.equal(await page.locator('#slot').inputValue(), '2026-11-15T09:15:00Z');
  await page.locator('#proposal-form button[type="submit"]').click();
  assert.equal(await page.locator('#meeting-list .draft-note').count(), 4);

  await page.locator('#candidates [data-candidate="ren"]').click();
  await includesText(page, '#detail', 'No portfolio supplied. Ability is unknown');
  assert.equal(await page.locator('#slot').count(), 0);
  assert.equal(await page.locator('#candidates button').count(), 5);
  assert.equal(await page.locator('#candidates [data-candidate="ren"]').isEnabled(), true);
  await page.locator('#role').selectOption('host');
  await page.locator('#candidates [data-candidate="jules"]').click();
  assert.equal(await page.locator('#slot option').count(), 3);
  assert.equal(await page.locator('#slot').inputValue(), '2026-11-15T09:45:00Z');
  await page.locator('#reset').click();
  assert.equal(await page.locator('#meeting-list .draft-note').count(), 0);
  await includesText(page, '#status', 'All local proposals and time holds cleared');
  await page.locator('#proposal-form button[type="submit"]').click();
  assert.equal(await page.locator('#meeting-list .draft-note').count(), 1);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await textIs(page, '#count', '5 fictional candidates · all visible');
  assert.equal(await page.locator('#meeting-list .draft-note').count(), 0);
  await includesText(page, '#meeting-list', 'No proposals yet');
  const coverage = {
    allCandidatesVisible: 5, linkedEvidenceAndFocus: focusFailure ? 'failed' : 'passed',
    distinctProposeAndRespond: 'passed', duplicateProposalGate: 'passed',
    cancellationAndDeclineReleaseTime: 'passed', employerTimeCollision: 'passed',
    unknownPortfolioStillSelectable: 'passed', quarterHourAlignment: 'passed',
    resetAndReloadMemoryBoundary: 'passed', identityAndConsent: 'simulation-only',
  };
  if (focusFailure) {
    const error = new Error('Evidence summary did not retain focus after the citation click; independent meeting checks completed.');
    error.coverage = coverage;
    error.failedChecks = [focusFailure];
    throw error;
  }
  return coverage;
}

async function availablePort() {
  const reservation = createPortReservation();
  await new Promise((resolve, reject) => {
    reservation.once('error', reject);
    reservation.listen(0, '127.0.0.1', resolve);
  });
  const port = reservation.address().port;
  await new Promise((resolve, reject) => reservation.close(error => error ? reject(error) : resolve()));
  return port;
}

async function startProduct(root, serverPath) {
  const port = await availablePort();
  const base = `http://127.0.0.1:${port}`;
  const child = spawn(process.execPath, [resolve(root, serverPath)], {
    cwd: root, stdio: ['ignore', 'pipe', 'pipe'],
    env: { PATH: process.env.PATH, PORT: String(port), LUMO_PORT: String(port), NODE_ENV: 'test', TZ: 'UTC' },
  });
  let diagnostics = '';
  let spawnError;
  child.on('error', error => { spawnError = error; });
  const record = chunk => { diagnostics = (diagnostics + chunk.toString()).slice(-4000); };
  child.stdout.on('data', record);
  child.stderr.on('data', record);
  async function close() {
    if (child.exitCode !== null || child.signalCode !== null) return;
    const exited = new Promise(resolve => child.once('exit', resolve));
    child.kill('SIGTERM');
    const stopped = await Promise.race([exited.then(() => true), sleep(3000).then(() => false)]);
    if (!stopped) {
      child.kill('SIGKILL');
      await Promise.race([exited, sleep(3000).then(() => { throw new Error('Product child did not stop'); })]);
    }
  }
  try {
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      if (spawnError) throw spawnError;
      assert.equal(child.exitCode, null, `Product server exited: ${diagnostics}`);
      try {
        const response = await fetch(base, { signal: AbortSignal.timeout(800) });
        if (response.ok) { await response.arrayBuffer(); return { base, close }; }
      } catch { /* Startup is asynchronous; bounded below. */ }
      await sleep(100);
    }
    throw new Error(`Product server did not become ready: ${diagnostics}`);
  } catch (error) {
    await close();
    throw error;
  }
}

async function main() {
  const product = process.env.CRACI_PRODUCT || process.argv[2];
  const engineName = process.env.CRACI_BROWSER || process.argv[3];
  assert.ok(Object.hasOwn(products, product), 'CRACI_PRODUCT must be sbank, hostinger or espoo');
  assert.ok(Object.hasOwn(engines, engineName), 'CRACI_BROWSER must be chromium, firefox or webkit');
  assert.ok(process.env.SOURCE_DIR, 'SOURCE_DIR is required');
  assert.match(process.env.EXPECTED_SOURCE_SHA ?? '', /^[0-9a-f]{40}$/, 'A lowercase full EXPECTED_SOURCE_SHA is required');
  const root = resolve(process.env.SOURCE_DIR);
  const head = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  assert.equal(head, process.env.EXPECTED_SOURCE_SHA, 'Product HEAD differs from independently pinned source');
  const output = resolve(process.env.CRACI_BROWSER_OUTPUT || 'craci-portfolio-browser-results');
  await mkdir(output, { recursive: true });
  const browser = await engines[engineName].launch({ headless: true });
  try {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      const label = `${product}-${engineName}-${viewport.width}`;
      const started = Date.now();
      const errors = [], unexpectedNetwork = [];
      let server, context, page;
      let failed = false, tracing = false;
      try {
        server = await startProduct(root, products[product].server);
        context = await browser.newContext({ viewport, serviceWorkers: 'block', acceptDownloads: true });
        context.setDefaultTimeout(15000);
        await context.route('**/*', async route => {
          if (new URL(route.request().url()).origin === server.base) await route.continue();
          else { unexpectedNetwork.push(route.request().url()); await route.abort(); }
        });
        await context.tracing.start({ screenshots: true, snapshots: true });
        tracing = true;
        page = await context.newPage();
        page.on('pageerror', error => errors.push(error.message));
        const response = await page.goto(server.base, { waitUntil: 'domcontentloaded' });
        assert.equal(response.status(), 200);
        const coverage = await products[product].run(page);
        const overflow = await page.evaluate(() =>
          Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) - innerWidth);
        assert.ok(overflow <= 1, `Horizontal overflow: ${overflow}px`);
        assert.deepEqual(errors, [], 'Uncaught browser exceptions');
        assert.deepEqual(unexpectedNetwork, [], 'Unexpected external network requests');
        await page.screenshot({ path: `${output}/${label}.png`, fullPage: true });
        console.log(JSON.stringify({ label, sourceSha: head, status: 'passed', durationMs: Date.now() - started, overflow, coverage }));
      } catch (error) {
        failed = true;
        process.exitCode = 1;
        console.error(JSON.stringify({ label, sourceSha: head, status: 'failed', durationMs: Date.now() - started,
          error: error.stack || String(error), pageErrors: errors, unexpectedNetwork,
          coverage: error.coverage, failedChecks: error.failedChecks }));
        await page?.screenshot({ path: `${output}/${label}-failure.png`, fullPage: true }).catch(() => {});
      } finally {
        const cleanupErrors = [];
        if (context) {
          if (tracing) {
            try { await context.tracing.stop({ path: `${output}/${label}${failed ? '-failure' : ''}.zip` }); }
            catch (error) { cleanupErrors.push(`trace: ${error.message}`); }
          }
          try { await context.close(); }
          catch (error) { cleanupErrors.push(`browser-context: ${error.message}`); }
        }
        try { await server?.close(); }
        catch (error) { cleanupErrors.push(`product-server: ${error.message}`); }
        if (cleanupErrors.length) {
          process.exitCode = 1;
          console.error(JSON.stringify({ label, sourceSha: head, status: 'failed', phase: 'cleanup', errors: cleanupErrors }));
        }
      }
    }
  } finally { await browser.close(); }
}

await main().catch(error => {
  process.exitCode = 1;
  console.error(JSON.stringify({ status: 'failed', phase: 'setup-or-cleanup', error: error.stack || String(error) }));
});
