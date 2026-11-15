/** Optional real-browser qualification; no external provider or commerce writes. */
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
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const base = 'http://127.0.0.1:' + server.address().port;
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    page.setDefaultTimeout(10_000);
    const errors = [];
    const external = [];
    const decisions = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('request', (request) => {
      if (new URL(request.url()).origin !== base) external.push(request.url());
      if (request.method() === 'POST' && /\/api\/reviews\/[^/]+\/decision$/.test(new URL(request.url()).pathname)) {
        decisions.push(request.postDataJSON());
      }
    });
    const card = page.locator('#exception-card');
    const approve = page.locator('#approve-exception');
    const find = page.locator('#find');
    const refresh = page.locator('#refresh-review');
    const waitCard = () => card.waitFor({ state: 'visible' });
    try {
      await page.goto(base);
      await page.selectOption('#budget', '140000');
      await find.click();
      await waitCard();
      await page.waitForFunction(() => !document.querySelector('#approve-exception').disabled);
      assert.equal((await page.locator('#exception-delta').textContent()).replace(/\D/g, ''), '37300');
      assert.ok(await page.locator('#order').isDisabled());
      assert.equal(await approve.getAttribute('aria-hidden'), null);
      assert.match(await page.locator('#exception-constraints').textContent(), /Lactose-free requirement preserved/);
      assert.ok(await page.locator('#snapshot-summary').isVisible());
      await approve.focus();
      assert.equal(await page.evaluate(() => document.activeElement.id), 'approve-exception');
      if (process.env.VALIO_REVIEW_SCREENSHOT_DIR) {
        await card.screenshot({ path: join(process.env.VALIO_REVIEW_SCREENSHOT_DIR, 'valio-review-' + viewport.width + '.png') });
      }

      // An input edit while a review response is in flight must also invalidate consent.
      let releaseResponse;
      let markResponse;
      const held = new Promise((done) => { releaseResponse = done; });
      const responseReady = new Promise((done) => { markResponse = done; });
      await page.route('**/api/reviews', async (route) => {
        const response = await route.fetch();
        markResponse();
        await held;
        await route.fulfill({ response });
      });
      await find.click();
      await responseReady;
      await page.selectOption('#budget', '150000');
      releaseResponse();
      await page.waitForFunction(() => !document.querySelector('#find').disabled);
      assert.ok(await approve.isDisabled());
      await page.unroute('**/api/reviews');
      await page.selectOption('#budget', '140000');
      await refresh.click();
      await page.waitForFunction(() => !document.querySelector('#approve-exception').disabled);

      // A form change disables consent to the previous displayed terms.
      await page.selectOption('#budget', '150000');
      assert.ok(await approve.isDisabled());
      assert.ok(await page.locator('#order').isDisabled());
      await page.selectOption('#budget', '140000');
      await refresh.click();
      await page.waitForFunction(() => !document.querySelector('#approve-exception').disabled);

      // A real fixture price mutation invalidates the prior quote at the server.
      await page.locator('#reprice').click();
      await page.waitForFunction(() => document.querySelector('#exception-status').textContent.includes('Source information changed'));
      assert.ok(await approve.isDisabled());
      await refresh.click();
      await page.waitForFunction(() => !document.querySelector('#approve-exception').disabled);
      await page.locator('#reject-exception').click();
      await page.waitForFunction(() => document.querySelector('#exception-status').textContent.includes('rejected'));
      assert.ok(await page.locator('#order').isDisabled());
      assert.ok(await approve.isDisabled());

      await refresh.click();
      await page.waitForFunction(() => !document.querySelector('#approve-exception').disabled);
      const displayedSnapshot = await page.locator('#review-source-id').textContent();
      const displayedQuote = await page.locator('#quote-id').textContent();
      await approve.click();
      await page.waitForFunction(() => !document.querySelector('#order').disabled);
      const confirmed = decisions.at(-1);
      assert.equal(confirmed.snapshotId, displayedSnapshot);
      assert.equal(confirmed.quoteId, displayedQuote);
      assert.equal(confirmed.decision, 'approve');
      assert.equal(service.policy().perOrderBudgetCents, 250_000);
      await page.locator('#order').click();
      await page.waitForFunction(() => document.querySelector('#policy-title').textContent.includes('committed'));
      assert.ok(await find.isDisabled());
      const afterCommit = service.catalog();
      await page.locator('#replay').click();
      await page.waitForFunction(() => document.querySelector('#decision-status').textContent.includes('idempotentReplay=true'));
      assert.deepEqual(service.catalog(), afterCommit);
      await page.locator('#cancel').click();
      await page.waitForFunction(() => !document.querySelector('#find').disabled);

      await page.selectOption('#need-mode', 'typed');
      await page.fill('#quantity', '2000');
      await page.selectOption('#budget', '250000');
      await find.click();
      await waitCard();
      await page.waitForFunction(() => document.querySelector('#exception-title').textContent.includes('stock is missing'));
      assert.match(await page.locator('#exception-constraints').textContent(), /320 L of compatible stock missing/);
      assert.ok(await approve.isHidden());
      assert.equal(service.audit().filter((item) => item.event === 'ORDER_SIMULATED').length, 1);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      assert.deepEqual(errors, []);
      assert.deepEqual(external, []);
      console.log(JSON.stringify({ viewport, outcome: 'PASS', javascriptErrors: errors.length,
        externalRequests: external.length, simulatedOrders: 1, policyUnchanged: true,
        checks: ['exact budget gap', 'keyboard focus', 'in-flight input invalidation', 'edited input invalidation', 'stale source refusal',
          'terminal rejection', 'exact quote/snapshot consent', 'commit/replay/cancel', 'shortage abstention', 'no overflow'] }));
    } finally {
      await context.close();
      await new Promise((done) => server.close(done));
    }
  }
} finally { await browser.close(); }
