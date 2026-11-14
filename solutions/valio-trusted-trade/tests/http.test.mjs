import test, { after, before } from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createTradeHttpServer } from '../src/server.mjs';
import { createTradeService } from '../src/core.mjs';

let server;
let base;
let token;
before(async () => {
  server = createTradeHttpServer(createTradeService());
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  base = `http://127.0.0.1:${server.address().port}`;
  token = (await (await fetch(`${base}/api/demo/session`, { method: 'POST', body: JSON.stringify({ buyerId: 'helsinki-hotel-demo' }) })).json()).token;
});
after(async () => { if (server) await new Promise((resolve) => server.close(resolve)); });
const get = async (path) => {
  const response = await fetch(`${base}${path}`);
  return { status: response.status, body: response.headers.get('content-type')?.startsWith('application/json') ? await response.json() : await response.text() };
};
const post = async (path, body) => {
  const response = await fetch(`${base}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify(body) });
  return { status: response.status, body: await response.json() };
};

test('health and static responsive application are available with CSP', async () => {
  const health = await get('/api/health');
  assert.equal(health.status, 200);
  assert.equal(health.body.mode, 'SIMULATED');
  const html = await fetch(base);
  assert.equal(html.status, 200);
  assert.match(await html.text(), /DEMONSTRATION ONLY/);
  assert.match(html.headers.get('content-security-policy'), /script-src 'self'/);
  for (const route of ['/app.js', '/style.css']) {
    const asset = await get(route);
    assert.equal(asset.status, 200);
    assert.ok(asset.body.length > 200);
  }
});

test('structured open HTTP workflow supports buyer approval and safe idempotency', async () => {
  const quote = await post('/api/quotes', { buyerId: 'helsinki-hotel-demo', requestText: '1000 L lactose-free milk', budgetCents: 250000 });
  assert.equal(quote.status, 201);
  const q = quote.body.quote;
  assert.equal(q.approvalRequired, true);
  const blocked = await post('/api/orders', { quoteId: q.id, buyerId: 'helsinki-hotel-demo', idempotencyKey: 'http-quote-0001' });
  assert.equal(blocked.status, 403);
  assert.equal(blocked.body.error.code, 'APPROVAL_REQUIRED');
  const approved = await post(`/api/quotes/${q.id}/approval`, { buyerId: 'helsinki-hotel-demo', decision: 'approve', approver: 'Demo approver' });
  assert.equal(approved.status, 200);
  assert.equal(approved.body.quote.status, 'APPROVED');
  const created = await post('/api/orders', { quoteId: q.id, buyerId: 'helsinki-hotel-demo', idempotencyKey: 'http-quote-0001' });
  const replay = await post('/api/orders', { quoteId: q.id, buyerId: 'helsinki-hotel-demo', idempotencyKey: 'http-quote-0001' });
  assert.equal(created.status, 201);
  assert.equal(replay.body.order.id, created.body.order.id);
  assert.equal(replay.body.order.idempotentReplay, true);
  const cancelled = await post(`/api/orders/${created.body.order.id}/cancel`, { buyerId: 'helsinki-hotel-demo' });
  assert.equal(cancelled.body.order.status, 'SIMULATED_CANCELLED');
  const audit = await get('/api/audit');
  assert.ok(audit.body.receipts.some((x) => x.event === 'ORDER_CANCELLED_SIMULATED'));
});

test('URL quote binding is authoritative over malicious posted quoteId', async () => {
  const q1 = (await post('/api/quotes', { buyerId: 'helsinki-hotel-demo', requestText: '1000 L lactose-free milk' })).body.quote;
  const q2 = (await post('/api/quotes', { buyerId: 'helsinki-hotel-demo', requestText: '1000 L lactose-free milk' })).body.quote;
  const approval = await post(`/api/quotes/${q1.id}/approval`, { quoteId: q2.id, buyerId: 'helsinki-hotel-demo', decision: 'approve' });
  assert.equal(approval.status, 200);
  assert.equal(approval.body.quote.id, q1.id);
  assert.equal((await get(`/api/quotes/${q2.id}`)).body.quote.approval, null);
});

test('over-budget baskets, unknown routes and JSON parsing have explicit error codes', async () => {
  const refused = await post('/api/quotes', { buyerId: 'helsinki-hotel-demo', requestText: '1000 L lactose-free milk', budgetCents: 150000 });
  assert.equal(refused.status, 409);
  assert.equal(refused.body.error.code, 'BUDGET_EXCEEDED');
  assert.equal((await get('/api/not-a-route')).body.error.code, 'NOT_FOUND');
  const malformed = await fetch(`${base}/api/orders`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{ broken' });
  assert.equal(malformed.status, 400);
  assert.equal((await malformed.json()).error.code, 'INVALID_JSON');
  const oversized = await fetch(`${base}/api/quotes`, { method: 'POST', body: 'x'.repeat(17000) });
  assert.equal(oversized.status, 413);
  assert.equal((await oversized.json()).error.code, 'PAYLOAD_TOO_LARGE');
});
