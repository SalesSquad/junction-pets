import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { createTradeHttpServer } from '../src/server.mjs';
import { createTradeService } from '../src/core.mjs';

test('independent buyer agent signs trade and, with separate scripted synthetic consent, transfers and refunds EUR', { timeout: 20000 }, async () => {
  const service = createTradeService();
  const server = createTradeHttpServer(service);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try {
    const agent = fileURLToPath(new URL('../src/frontier-agent.mjs', import.meta.url));
    const { stdout } = await promisify(execFile)(process.execPath,
      [agent, 'happy', '--decision=approve', '--payment-decision=approve', '--refund-demo'],
      { env: { ...process.env, SUPPLIER_URL: `http://127.0.0.1:${server.address().port}` }, timeout: 10000 });
    const report = JSON.parse(stdout.trim().split('\n').at(-1));
    assert.equal(report.actor, 'INDEPENDENT_BUYER_PROCESS');
    assert.equal(report.payment.rail, 'IN_MEMORY_NO_BANK_OR_PSP');
    assert.equal(report.payment.refunded, true);
    assert.ok(report.payment.supplierCount >= 1);
    assert.ok(report.HTTP_requests.some((entry) => entry.path.endsWith('/settlement')));
    assert.equal(service.paymentJournalVerify().valid, true);
    assert.equal(service.demoWallet().buyerBalanceCents, 250000);
    assert.equal(service.audit().filter((entry) => entry.event === 'DEMO_MONEY_TRANSFER_SETTLED').length, 1);
    assert.equal(service.audit().filter((entry) => entry.event === 'DEMO_PAYMENT_REVERSED').length, 1);
  } finally { await new Promise((done) => server.close(done)); }
});
