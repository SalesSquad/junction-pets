import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { createTradeService } from '../src/core.mjs';
import { createTradeHttpServer } from '../src/server.mjs';

const buyerId = 'helsinki-hotel-demo';
const need = { family: 'dairy-milk', lactoseFree: true, quantityLitres: 1000, deliverBy: '2026-11-16' };
async function fixture(run, service = createTradeService()) {
  const server = createTradeHttpServer(service);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const call = async (path, body, token) => {
    const response = await fetch(base + path, { method: body === undefined ? 'GET' : 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: response.status, ...await response.json() };
  };
  const session = () => call('/api/demo/session', { buyerId }).then((x) => x.token);
  try { await run({ base, call, session, service }); }
  finally { await new Promise((resolve) => server.close(resolve)); }
}
const quote = (call, token, extra = {}) => call('/api/quotes', { buyerId, need, ...extra }, token).then((x) => { assert.equal(x.status, 201); return x.quote; });
const approve = (call, token, q, decision = 'approve') => call(`/api/quotes/${q.id}/approval`, { buyerId, decision }, token);
const order = (call, token, q, extra = {}) => call('/api/orders', { buyerId, quoteId: q.id, idempotencyKey: 'boundary-order-key', ...extra }, token);

test('HTTP refuses forged capabilities, forged buyers and another demo session owning a quote', async () => fixture(async ({ call, session }) => {
  const token = await session();
  const q = await quote(call, token);
  assert.equal((await order(call, 'forged', q)).error.code, 'BUYER_CAPABILITY_REQUIRED');
  assert.equal((await order(call, token, q, { buyerId: 'forged-buyer' })).error.code, 'BUYER_MISMATCH');
  assert.equal((await approve(call, await session(), q)).error.code, 'BUYER_MISMATCH');
  assert.equal((await order(call, await session(), q)).error.code, 'BUYER_MISMATCH');
}));

test('HTTP refuses altered quantity/price/authority even on replay; exact retry deducts once', async () => fixture(async ({ call, session, service }) => {
  const token = await session();
  const q = await quote(call, token);
  assert.equal((await approve(call, token, q)).status, 200);
  for (const extra of [{ quantityLitres: 1 }, { totalCents: 1 }, { approval: true }]) assert.equal((await order(call, token, q, extra)).error.code, 'ORDER_TERMS_FORBIDDEN');
  const first = await order(call, token, q);
  assert.equal(first.status, 201);
  const stock = service.catalog();
  const replay = await order(call, token, q);
  assert.equal(replay.order.id, first.order.id);
  assert.equal(replay.order.idempotentReplay, true);
  assert.deepEqual(service.catalog(), stock);
  assert.equal((await order(call, token, q, { quantityLitres: 2 })).error.code, 'ORDER_TERMS_FORBIDDEN');
  assert.equal((await order(call, token, q, { idempotencyKey: 'different-order-key' })).error.code, 'ALREADY_COMMITTED');
  const next = await quote(call, token, { need: { ...need, quantityLitres: 1 } });
  assert.equal((await order(call, token, next)).error.code, 'IDEMPOTENCY_CONFLICT');
}));

test('HTTP enforces approval and terminal rejection, and records refusal reasons', async () => fixture(async ({ call, session }) => {
  const token = await session();
  const q = await quote(call, token);
  assert.equal((await order(call, token, q)).error.code, 'APPROVAL_REQUIRED');
  assert.equal((await approve(call, token, q, 'reject')).status, 200);
  assert.equal((await order(call, token, q)).error.code, 'APPROVAL_REJECTED');
  assert.equal((await approve(call, token, q)).error.code, 'ALREADY_DECIDED');
  assert.ok((await call('/api/audit')).receipts.some((x) => x.detail.reason === 'APPROVAL_REQUIRED'));
}));

test('competing quote stock consumption and price changes invalidate prior approvals', async () => fixture(async ({ call, session }) => {
  const token = await session();
  const first = await quote(call, token);
  const competitor = await quote(call, token);
  await approve(call, token, first);
  await approve(call, token, competitor);
  assert.equal((await order(call, token, competitor)).status, 201);
  assert.equal((await order(call, token, first, { idempotencyKey: 'stock-order-key' })).error.code, 'QUOTE_STALE');
  const fresh = await quote(call, token, { need: { ...need, quantityLitres: 1 } });
  const line = fresh.lines[0];
  await call('/api/demo/reprice', { sku: line.sku, priceCents: line.unitPriceCents + 1 }, token);
  assert.equal((await order(call, token, fresh, { idempotencyKey: 'price-order-key' })).error.code, 'QUOTE_STALE');
}));

test('quote expiry uses injected clock with no sleeps', async () => {
  let now = 1800000000000;
  await fixture(async ({ call, session }) => {
    const token = await session();
    const q = await quote(call, token);
    await approve(call, token, q);
    now = q.expiresAtMs;
    assert.equal((await order(call, token, q)).error.code, 'QUOTE_EXPIRED');
  }, createTradeService({ clock: () => now }));
});

test('typed oat need, no substitutions, strict quantities and exact UNSIGNED interoperability body', async () => fixture(async ({ call, session }) => {
  const token = await session();
  const q = await quote(call, token, { need: { ...need, family: 'oat-drink', quantityLitres: 12 } });
  assert.deepEqual(q.lines.map((x) => x.sku), ['DEMO-OAT-1']);
  const exported = await call(`/api/quotes/${q.id}/body`);
  assert.equal(exported.signature, 'UNSIGNED');
  assert.deepEqual(exported.body, { version: 'kattely.procurement.quote.v3', quote_id: q.id, supplier_id: 'supplier-demo', buyer_id: buyerId, audience: 'https://supplier-demo.invalid', currency: 'EUR', issued_at: Math.floor(q.createdAtMs / 1000), expires_at: Math.floor(q.expiresAtMs / 1000), lines: [{ sku: 'DEMO-OAT-1', quantity: 12, unit: 'L', unit_price_cents: 162, stock_version: 1, supplier_id: 'fictional-oatworks', pack_litres: 1, pack_count: 12, min_order_packs: 1 }], source_snapshot_id: q.snapshotId, cost_breakdown: { subtotal_cents: 1944, delivery_fee_cents: 0, tax_cents: 0, tax_bps: 0 }, total_cents: 1944 });
  for (const invalid of [{ ...need, quantityLitres: 1.5 }, { ...need, family: 'juice' }, { ...need, priceCents: 1 }, { ...need, deliverBy: '2027-01-01' }]) {
    assert.equal((await call('/api/quotes', { buyerId, need: invalid }, token)).status, 400);
  }
  assert.equal((await call('/api/quotes', { buyerId, need, requestText: '1 L lactose-free milk' }, token)).error.code, 'INVALID_NEED');
  assert.equal((await call('/api/quotes', { buyerId, need, budgetCents: 1 }, token)).error.code, 'BUDGET_EXCEEDED');
}));

test('independent Node process discovers API and actually executes success/refusal/replay/stale and oat scenarios over HTTP', async () => {
  for (const scenario of ['success', 'refusal', 'replay', 'stale', 'oat', 'reject']) {
    await fixture(async ({ base, service }) => {
      const { stdout } = await promisify(execFile)(process.execPath, [fileURLToPath(new URL('../src/buyer-agent.mjs', import.meta.url)), scenario === 'oat' || scenario === 'reject' ? 'success' : scenario, scenario === 'oat' ? '--oat' : '--decision=' + (scenario === 'reject' ? 'reject' : 'approve'), ...(scenario === 'oat' ? ['--decision=approve'] : [])], { env: { ...process.env, SUPPLIER_URL: base }, timeout: 10000 });
      const report = JSON.parse(stdout.trim().split('\n').at(-1));
      assert.equal(report.mode, 'SYNTHETIC');
      assert.ok(report.requests.some((x) => x.path === '/.well-known/trusted-trade'));
      const committed = service.audit().filter((x) => x.event === 'ORDER_SIMULATED');
      assert.equal(committed.length, ['success', 'replay', 'oat'].includes(scenario) ? 1 : 0);
      if (scenario !== 'reject') assert.ok(report.processing_ms > 0);
    });
  }
});
