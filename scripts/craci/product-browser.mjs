import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium, firefox, webkit } from 'playwright';

// The caller supplies a pinned source checkout; this harness lives in tooling.
const configs = {
  stoa: {
    sha: 'bfb4e363879b9125b10ed8a8a14f77ea5ed8af70',
    server: 'solutions/stoa-blueprint-studio/src/server.mjs',
    factory: 'createServer',
    run: stoaSmoke,
  },
  valio: {
    sha: 'db003d1fd491381e7ce2409eefb1807a0c7ef0de',
    server: 'solutions/valio-trusted-trade/src/server.mjs',
    factory: 'createTradeHttpServer',
    run: valioSmoke,
  },
};
const engines = { chromium, firefox, webkit };
const sponsorSha = '4070c5f19eb921bc08e2f5a23e957086f76abcca03fafbb8b62ca30c8a60b58d';

async function textIs(page, selector, expected) {
  await page.waitForFunction(
    ({ selector, expected }) =>
      document.querySelector(selector)?.textContent.trim() === expected,
    { selector, expected },
  );
}

async function clickedPost(page, selector, path, { captureAuthorization = false } = {}) {
  const [response] = await Promise.all([
    page.waitForResponse(response =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === path,
    ),
    page.locator(selector).click(),
  ]);
  const result = {
    status: response.status(),
    body: await response.json(),
    payload: response.request().postDataJSON(),
  };
  // Only the explicit same-buyer replay probe needs this ephemeral header.
  // Do not add it to ordinary quote/mission result objects or test receipts.
  if (captureAuthorization) {
    result.authorization = (await response.request().allHeaders()).authorization ?? null;
  }
  return result;
}

async function getJson(page, base, path) {
  const response = await page.request.get(base + path);
  assert.equal(response.status(), 200);
  return response.json();
}

async function stoaSmoke(page, base) {
  await textIs(page, '#answer-value', '3');
  await textIs(page, '#source-badge', 'SYNTHETIC · NOT VERIFIED');
  assert.equal(await page.locator('#evidence-list .evidence-item').count(), 3);
  assert.equal(await page.locator('#blueprint .text-cited').count(), 3);

  async function ask(question) {
    await page.locator('#question').fill(question);
    const [response] = await Promise.all([
      page.waitForResponse(response =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === '/api/ask' &&
        response.request().postDataJSON().question === question,
      ),
      page.locator('#ask-button').click(),
    ]);
    assert.equal(response.status(), 200);
    const result = (await response.json()).result;
    await page.waitForFunction(
      () => !document.querySelector('#ask-button').disabled,
    );
    return result;
  }

  async function importDxf(bytes, filename, expectedCount) {
    const [response] = await Promise.all([
      page.waitForResponse(response =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === '/api/import-dxf',
      ),
      page.locator('#drawing-file').setInputFiles({
        name: filename, mimeType: 'application/dxf', buffer: bytes,
      }),
    ]);
    assert.equal(response.status(), 201);
    const drawing = (await response.json()).drawing;
    assert.equal(drawing.sha256, createHash('sha256').update(bytes).digest('hex'));
    await textIs(page, '#source-filename', filename);
    await textIs(page, '#source-badge', 'LOCAL IMPORT · VERIFY SOURCE');
    await textIs(page, '#answer-value', String(expectedCount));
    assert.equal(
      await page.locator('#evidence-list .evidence-item').count(), expectedCount,
    );
    return drawing;
  }

  const area = await ask('What is the area of room A-101?');
  assert.equal(area.status, 'supported');
  assert.equal(area.answer, '13.69 m²');
  assert.equal(area.evidence.length, 3);
  await textIs(page, '#answer-value', '13.69 m²');
  const outline = area.evidence.find(e => e.layer === 'ROOM_OUTLINE');
  assert.ok(outline);
  assert.match(outline.entityId, /^e\d+$/);

  // Change selection twice, proving the citation control updates the drawing.
  await page.locator('#evidence-list .evidence-item').nth(1).click();
  assert.match(
    await page.locator('#evidence-list .evidence-item').nth(1).getAttribute('class'),
    /\bselected\b/,
  );
  await page.locator('#evidence-list .evidence-item').first().click();
  assert.equal(
    await page.locator(
      `#blueprint polygon[data-entity-id="${outline.entityId}"]`,
    ).getAttribute('stroke-width'),
    '5',
  );

  const unsupported = await ask('How many doors are there?');
  assert.equal(unsupported.status, 'abstained');
  assert.deepEqual(unsupported.evidence, []);
  await textIs(page, '#answer-value', 'Not proven.');
  await textIs(page, '#answer-count', '0 CITATIONS');
  assert.equal(await page.locator('#evidence-list .evidence-item').count(), 0);
  assert.equal(
    await page.locator('#blueprint .is-cited, #blueprint .text-cited').count(), 0,
  );

  // Independent synthetic source: one rectangular 4 × 3 metre room.
  const groups = [
    0, 'SECTION', 2, 'HEADER', 9, '$INSUNITS', 70, 6, 0, 'ENDSEC',
    0, 'SECTION', 2, 'ENTITIES',
    0, 'LWPOLYLINE', 8, 'ROOM_OUTLINE', 70, 1,
    10, 0, 20, 0, 10, 4, 20, 0, 10, 4, 20, 3, 10, 0, 20, 3,
    0, 'TEXT', 8, 'ROOM_TEXT', 1, 'Stanza', 10, 2, 20, 2.1,
    0, 'TEXT', 8, 'ROOM_TEXT', 1, 'T-101', 10, 2, 20, 1.5,
    0, 'TEXT', 8, 'ROOM_TEXT', 1, '12.00 m²', 10, 2, 20, 0.9,
    0, 'ENDSEC', 0, 'EOF',
  ];
  const bytes = Buffer.from(groups.join('\n') + '\n');
  const imported = await importDxf(bytes, 'craci-smoke.dxf', 1);
  const importedArea = await ask('What is the area of room T-101?');
  assert.equal(importedArea.answer, '12.00 m²');
  assert.equal(importedArea.source.sha256, imported.sha256);
  await textIs(page, '#answer-value', '12.00 m²');

  await page.locator('#demo-button').click();
  await textIs(page, '#source-badge', 'SYNTHETIC · NOT VERIFIED');
  await textIs(page, '#answer-value', '3');

  let sponsor = 'not-requested';
  if (process.env.STOA_SPONSOR_DXF) {
    const sponsorBytes = await readFile(process.env.STOA_SPONSOR_DXF);
    assert.equal(createHash('sha256').update(sponsorBytes).digest('hex'), sponsorSha,
      'Sponsor source differs from the independently pinned DXF');
    await importDxf(sponsorBytes, 'site1102_bldg2242_floor10281.dxf', 9);
    const count = await ask('How many rooms labelled Stanza?');
    assert.equal(count.status, 'supported');
    assert.equal(count.answer, '9');
    assert.equal(count.evidence.length, 9);
    assert.equal(count.source.sha256, sponsorSha);
    const sponsorArea = await ask('What is the area of room 5.02?');
    assert.equal(sponsorArea.status, 'supported');
    assert.equal(sponsorArea.answer, '15.84 m²');
    assert.equal(sponsorArea.evidence.length, 3);
    assert.equal(sponsorArea.source.sha256, sponsorSha);
    await textIs(page, '#answer-value', '15.84 m²');
    sponsor = { status: 'passed', sha256: sponsorSha };
  }
  const health = await getJson(page, base, '/api/health');
  assert.equal(health.externalInference, false);
  return { syntheticImport: 'passed', citationInteraction: 'passed', sponsor };
}

async function valioMissionSmoke(page, base) {
  // Frontier V3 adds a distinct landing journey; preserve the classic safety
  // controls while testing the new form, planning and commitment boundary.
  await page.waitForFunction(() =>
    document.querySelector('#buyer-context')?.textContent.includes('Demo capability'));
  assert.equal(await page.locator('#commit-button').isDisabled(), true);
  await page.locator('#dairy').fill('480');
  await page.locator('#oat').fill('240');
  await page.locator('#budget').fill('1750');

  const planned = await clickedPost(page, '#plan-button', '/api/plans');
  assert.equal(planned.status, 201);
  const plan = planned.body.plan;
  assert.equal(plan.totalLitres, 720);
  assert.equal(plan.options.length, 3);
  await page.waitForFunction(() =>
    document.querySelectorAll('#option-grid .option-card').length === 3);
  await page.waitForFunction(() =>
    document.querySelector('#quote-button')?.disabled === false);
  assert.equal(await page.locator('#commit-button').isDisabled(), true);

  const fixed = await clickedPost(page, '#quote-button', '/api/plans/' + plan.id + '/quotes');
  assert.equal(fixed.status, 201);
  assert.ok(fixed.body.quote.totalCents > 0);
  assert.equal(fixed.body.quote.planId, plan.id);
  assert.equal(await page.locator('#commit-button').isDisabled(), true);
  const audit = (await getJson(page, base, '/api/audit')).receipts;
  assert.equal(audit.some(row => row.event === 'ORDER_SIMULATED'), false);
  const missionOverflow = await page.evaluate(() =>
    Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) - window.innerWidth);
  assert.ok(missionOverflow <= 1, 'Mission horizontal overflow: ' + missionOverflow + 'px');
  return { missionPlanning: 'passed', fixedQuote: 'passed', unsignedOrderBlocked: 'passed', missionOverflow };
}

async function valioSmoke(page, base, { frontier = false } = {}) {
  const initial = (await getJson(page, base, '/api/catalog')).products;
  const amounts = products =>
    Object.fromEntries(products.map(p => [p.sku, p.unitsAvailable]));
  await page.locator('#request-text')
    .fill('I need 1,000 litres of lactose-free milk by Monday.');
  await page.locator('#budget').selectOption('250000');

  const quoted = await clickedPost(page, '#find', '/api/quotes');
  assert.equal(quoted.status, 201);
  const quote = quoted.body.quote;
  assert.equal(quote.totalCents, 177300);
  assert.equal(quote.requested.quantityLitres, 1000);
  assert.equal(quote.approvalRequired, true);
  assert.deepEqual(
    quote.lines.map(x => [x.sku, x.quantityLitres, x.unitPriceCents]),
    [['DEMO-LF-1', 780, 174], ['DEMO-LF-2', 220, 189]],
  );
  await textIs(page, '#quote-status', 'AWAITING HUMAN APPROVAL');
  assert.equal((await page.locator('#quote-total').textContent()).replace(/\D/g, ''), '177300');
  assert.equal(await page.locator('#order').isDisabled(), true);
  assert.equal(await page.locator('#approve').isEnabled(), true);

  const approved = await clickedPost(page, '#approve', `/api/quotes/${quote.id}/approval`);
  assert.equal(approved.status, 200);
  assert.equal(approved.body.quote.status, 'APPROVED');
  await textIs(page, '#quote-status', 'APPROVED');
  assert.equal(await page.locator('#order').isEnabled(), true);

  const committed = await clickedPost(page, '#order', '/api/orders', { captureAuthorization: frontier });
  assert.equal(committed.status, 201);
  const order = committed.body.order;
  assert.equal(order.status, 'SIMULATED_COMMITTED');
  assert.equal(order.idempotentReplay, false);
  assert.equal(order.totalCents, 177300);
  await textIs(page, '#policy-title', 'Simulation committed · no purchase');
  assert.equal(await page.locator('#order').isDisabled(), true);

  // Frontier V3 requires the synthetic buyer capability on every write.
  // Prove an anonymous replay is refused, then replay the exact original
  // payload with the SAME buyer capability (not a fresh authorization).
  let replayAuthorization;
  if (frontier) {
    // Do not retain the synthetic capability on an object that an assertion
    // could accidentally serialize. Never include it in an error message.
    replayAuthorization = committed.authorization;
    delete committed.authorization;
    const unboundReplay = await page.request.post(base + '/api/orders', {
      data: committed.payload,
    });
    assert.equal(unboundReplay.status(), 403);
    assert.equal((await unboundReplay.json()).error.code, 'BUYER_CAPABILITY_REQUIRED');
    assert.ok(/^Bearer [0-9a-f-]{36}$/i.test(replayAuthorization ?? ''),
      'Expected a same-buyer synthetic bearer capability');
  }
  const replayResponse = await page.request.post(base + '/api/orders', {
    data: committed.payload,
    ...(frontier ? { headers: { Authorization: replayAuthorization } } : {}),
  });
  assert.equal(replayResponse.status(), 201);
  const replay = (await replayResponse.json()).order;
  assert.equal(replay.id, order.id);
  assert.equal(replay.idempotentReplay, true);
  const afterOrder = (await getJson(page, base, '/api/catalog')).products;
  assert.equal(amounts(afterOrder)['DEMO-LF-1'], 0);
  assert.equal(amounts(afterOrder)['DEMO-LF-2'], 680);
  let audit = (await getJson(page, base, '/api/audit')).receipts;
  assert.equal(audit.filter(x => x.event === 'ORDER_SIMULATED').length, 1);

  const cancelled = await clickedPost(page, '#cancel', `/api/orders/${order.id}/cancel`);
  assert.equal(cancelled.status, 200);
  assert.equal(cancelled.body.order.status, 'SIMULATED_CANCELLED');
  await textIs(page, '#policy-title', 'Simulated order cancelled');
  assert.equal(await page.locator('#cancel').isDisabled(), true);
  assert.deepEqual(
    amounts((await getJson(page, base, '/api/catalog')).products), amounts(initial),
  );

  const freshResponse = await clickedPost(page, '#find', '/api/quotes');
  assert.equal(freshResponse.status, 201);
  const fresh = freshResponse.body.quote;
  const freshApproval = await clickedPost(page, '#approve', `/api/quotes/${fresh.id}/approval`);
  assert.equal(freshApproval.status, 200);
  await textIs(page, '#quote-status', 'APPROVED');
  const repriced = await clickedPost(page, '#reprice', '/api/demo/reprice');
  assert.equal(repriced.status, 200);
  await textIs(page, '#quote-status', 'PRICE CHANGED');
  assert.equal(await page.locator('#order').isDisabled(), true);

  await page.locator('#budget').selectOption('150000');
  const refused = await clickedPost(page, '#find', '/api/quotes');
  assert.equal(refused.status, 409);
  assert.equal(refused.body.error.code, 'BUDGET_EXCEEDED');
  await page.locator('#alert').waitFor({ state: 'visible' });
  assert.match(await page.locator('#alert').textContent(), /BUDGET_EXCEEDED/);
  assert.equal(await page.locator('#quote-content').isHidden(), true);
  audit = (await getJson(page, base, '/api/audit')).receipts;
  assert.equal(audit.filter(x => x.event === 'ORDER_SIMULATED').length, 1);
  assert.equal(audit.filter(x => x.event === 'ORDER_CANCELLED_SIMULATED').length, 1);
  await page.locator('#refresh-audit').click();
  await page.getByText('ORDER CANCELLED SIMULATED', { exact: true }).waitFor();
  return { approvalGate: 'passed', actualPayloadReplay: 'passed', cancellation: 'passed', stalePriceGate: 'passed', budgetGate: 'passed' };
}

async function main() {
  const [product, engineName] = process.argv.slice(2);
  assert.equal(process.argv.length, 4, 'Usage: product-browser.mjs stoa|valio chromium|firefox|webkit');
  assert.ok(Object.hasOwn(configs, product), 'Product must be stoa or valio');
  assert.ok(Object.hasOwn(engines, engineName), 'Unknown browser engine');
  const cfg = configs[product];
  const root = resolve(process.env.PRODUCT_SOURCE_ROOT || process.cwd());
  const expectedSha = process.env.CRACI_SOURCE_SHA ?? cfg.sha;
  assert.match(expectedSha, /^[0-9a-fA-F]{40}$/, 'CRACI_SOURCE_SHA must be a full commit SHA');
  const head = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  assert.equal(head, expectedSha.toLowerCase(), 'Checkout HEAD differs from caller-pinned source');
  const output = resolve(process.env.CRACI_BROWSER_OUTPUT || 'craci-browser-results');
  await mkdir(output, { recursive: true });
  const serverModule = await import(pathToFileURL(resolve(root, cfg.server)).href);
  assert.equal(typeof serverModule[cfg.factory], 'function');
  const browser = await engines[engineName].launch({ headless: true });
  try {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      const label = `${product}-${engineName}-${viewport.width}`;
      const server = serverModule[cfg.factory]();
      let context;
      let page;
      let tracing = false;
      let failed = false;
      const started = Date.now();
      const errors = [];
      const unexpectedNetwork = [];
      try {
        await new Promise((resolve, reject) => {
          server.once('error', reject);
          server.listen(0, '127.0.0.1', resolve);
        });
        const base = `http://127.0.0.1:${server.address().port}`;
        context = await browser.newContext({ viewport, serviceWorkers: 'block' });
        context.setDefaultTimeout(15000);
        await context.route('**/*', async route => {
          if (new URL(route.request().url()).origin !== base) {
            unexpectedNetwork.push(route.request().url());
            await route.abort();
          } else {
            await route.continue();
          }
        });
        await context.tracing.start({ screenshots: true, snapshots: true });
        tracing = true;
        page = await context.newPage();
        page.on('pageerror', error => errors.push(error.message));
        const document = await page.goto(base, { waitUntil: 'domcontentloaded' });
        assert.equal(document.status(), 200);
        let mission = null;
        if (product === 'valio') {
          // Older source serves the classic form at /. Frontier V3 introduces
          // Mission Control at / and preserves the classic form at /classic.
          const classic = await page.request.get(base + '/classic');
          if (classic.status() === 200) {
            assert.equal(await page.locator('#mission-form').count(), 1,
              'New Valio source must present Mission Control at /');
            mission = await valioMissionSmoke(page, base);
            await page.screenshot({ path: output + '/' + label + '-mission.png', fullPage: true });
            const legacyDocument = await page.goto(base + '/classic', { waitUntil: 'domcontentloaded' });
            assert.equal(legacyDocument.status(), 200);
          } else {
            assert.equal(await page.locator('#request-text').count(), 1,
              'Legacy Valio source must expose the classic request form at /');
          }
        }
        const coverage = await cfg.run(page, base, { frontier: Boolean(mission) });
        if (mission) coverage.mission = mission;
        const overflow = await page.evaluate(() =>
          Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) - window.innerWidth,
        );
        assert.ok(overflow <= 1, `Horizontal overflow: ${overflow}px`);
        assert.deepEqual(errors, [], 'Uncaught browser exceptions');
        assert.deepEqual(unexpectedNetwork, [], 'Unexpected external requests');
        await page.screenshot({ path: `${output}/${label}.png`, fullPage: true });
        console.log(JSON.stringify({ label, sourceSha: head, status: 'passed', durationMs: Date.now() - started, overflow, coverage }));
      } catch (error) {
        failed = true;
        process.exitCode = 1;
        console.error(JSON.stringify({ label, sourceSha: head, status: 'failed', durationMs: Date.now() - started, error: error.stack || String(error), pageErrors: errors, unexpectedNetwork }));
        if (page) {
          await page.screenshot({ path: `${output}/${label}-failure.png`, fullPage: true }).catch(() => {});
        }
      } finally {
        if (context) {
          if (tracing) {
            await context.tracing.stop({ path: `${output}/${label}${failed ? '-failure' : ''}.zip` }).catch(error => {
              process.exitCode = 1;
              console.error(JSON.stringify({ label, status: 'failed', phase: 'trace-save', error: error.message }));
            });
          }
          await context.close();
        }
        if (server.listening) {
          const closed = new Promise((resolve, reject) => {
            server.close(error => error ? reject(error) : resolve());
          });
          server.closeAllConnections?.();
          await closed;
        }
      }
    }
  } finally {
    await browser.close();
  }
}

await main().catch(error => {
  process.exitCode = 1;
  console.error(JSON.stringify({ status: 'failed', phase: 'setup-or-cleanup', error: error.stack || String(error) }));
});
