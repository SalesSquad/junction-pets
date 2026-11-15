/** Optional local-browser qualification; synthetic commerce only. */
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { join } from 'node:path';
import { createTradeService } from '../src/core.mjs';
import { createTradeHttpServer } from '../src/server.mjs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const browser = await chromium.launch({ headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {}) });
try {
  for (const viewport of [{ width: 1440, height: 1050 }, { width: 390, height: 844 }]) {
    const service = createTradeService();
    const server = createTradeHttpServer(service);
    server.listen(0, '127.0.0.1'); await once(server, 'listening');
    const base = 'http://127.0.0.1:' + server.address().port;
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    page.setDefaultTimeout(12000);
    const errors = [], external = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (new URL(r.url()).origin !== base) external.push(r.url()); });
    const enabled = id => page.waitForFunction(id => !document.getElementById(id).disabled, id);
    const text = (id, value) => page.waitForFunction(({ id, value }) => document.getElementById(id).textContent.includes(value), { id, value });
    const click = async id => { await enabled(id); await page.locator('#' + id).click(); };
    try {
      await page.goto(base + '/mission');
      await text('buyer-context', 'Demo capability');
      await click('plan-button');
      await click('quote-button');
      await click('approve-button');
      await click('handshake-button');
      await text('crypto-title', 'Server + browser verified');
      const oldId = await page.locator('#selected-id').textContent();
      await click('shock');
      await text('timeline-status', 'SELF-HEALED');
      assert.equal(await page.locator('#commit-button').isDisabled(), true);
      await click('quote-button');
      await click('approve-button');
      await click('handshake-button');
      await text('crypto-title', 'Server + browser verified');
      assert.notEqual(await page.locator('#selected-id').textContent(), oldId);
      if (process.env.VALIO_REVIEW_SCREENSHOT_DIR) await page.screenshot({ path: join(process.env.VALIO_REVIEW_SCREENSHOT_DIR, 'valio-unified-mission-' + viewport.width + '.png'), fullPage: true });
      await click('commit-button');
      await text('timeline-status', 'RECEIPT RECORDED');
      assert.equal(await page.locator('#payment-send-button').isDisabled(), true);
      assert.equal(await page.locator('#plan-button').isDisabled(), true, 'active receipt and refund cannot be replaced');
      await click('replay-button');
      await text('timeline-events', 'Replay refused new side effects');
      const balance = service.demoWallet().buyerBalanceCents;
      await click('payment-approve-button');
      await click('payment-send-button');
      await text('payment-status', 'BALANCED');
      assert.ok(service.demoWallet().buyerBalanceCents < balance);
      const journalSize = service.paymentJournal().length;
      await click('payment-replay-button');
      await text('timeline-events', 'Duplicate transfer safely blocked');
      assert.equal(service.paymentJournal().length, journalSize);
      await click('payment-refund-button');
      await text('payment-status', 'REVERSED');
      await enabled('plan-button');
      assert.equal(service.demoWallet().buyerBalanceCents, balance);
      assert.equal(service.paymentJournalVerify().valid, true);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const unnamed = await page.locator('.side-nav a').evaluateAll(links => links.filter(a => !a.getAttribute('aria-label')?.trim()).length);
      assert.equal(unnamed, 0);
      assert.deepEqual(errors, []);
      assert.deepEqual(external, []);
      if (viewport.width === 1440) {
        const recipe = await context.newPage();
        await recipe.setContent('<html><body style="margin:40px;font:48px Arial;background:white;color:black"><p>12 L lactose-free milk</p><p>8 L oat drink</p></body></html>');
        const image = await recipe.screenshot();
        const session = await (await context.request.post(base + '/api/demo/session', { data: { buyerId: 'helsinki-hotel-demo' } })).json();
        const response = await context.request.post(base + '/api/scan/ocr', { data: image,
          headers: { Authorization: 'Bearer ' + session.token, 'Content-Type': 'image/png' } });
        const observation = await response.json();
        assert.equal(response.status(), 200, JSON.stringify(observation));
        assert.equal(observation.requiresHumanConfirmation, true);
        assert.deepEqual(observation.candidates.map(c => [c.family, c.quantityLitres]), [['dairy-milk', 12], ['oat-drink', 8]]);
        await recipe.close();
        console.log(JSON.stringify({ localTesseract: 'PASS', generatedRecipeOnly: true, humanConfirmationRequired: true }));
      }
      console.log(JSON.stringify({ viewport, outcome: 'PASS', browserEd25519: true, stockRecovery: true,
        exactReapproval: true, orderAndPaymentReplay: true, refund: true, activeReceiptPreserved: true, javascriptErrors: errors.length, externalRequests: external.length }));
    } finally { await context.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  }
} finally { await browser.close(); }
