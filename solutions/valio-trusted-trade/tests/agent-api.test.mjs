import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { request } from 'node:http';
import { createTradeService, FIXTURE_POLICY } from '../src/core.mjs';
import { createTradeHttpServer } from '../src/server.mjs';

const buyerId = FIXTURE_POLICY.buyerId;
const input = { buyerId, requirements: [{ family: 'dairy-milk', quantityLitres: 12, lactoseFree: true, deliverBy: '2026-11-16' }], budgetCents: 50000 };
async function fixture(t, options = {}) {
  const service = createTradeService();
  const server = createTradeHttpServer(service, options);
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(async () => { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); });
  const base = 'http://127.0.0.1:' + server.address().port;
  async function call(path, { token, body, key, headers = {} } = {}) {
    const response = await fetch(base + path, { method: body === undefined ? 'GET' : 'POST',
      headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: 'Bearer ' + token } : {}), ...(key ? { 'Idempotency-Key': key } : {}), ...headers },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const text = await response.text();
    return { status: response.status, body: JSON.parse(text), bytes: Buffer.byteLength(text), headers: response.headers };
  }
  const session = async () => (await call('/api/demo/session', { body: { buyerId } })).body.token;
  return { service, server, base, call, session };
}
const expectError = (reply, status, code) => {
  assert.equal(reply.status, status); assert.equal(reply.body.error.code, code);
  assert.equal(typeof reply.body.error.retryable, 'boolean');
  assert.equal(typeof reply.body.error.recovery.action, 'string');
};

test('creation key replays exact IDs and expiry once; changed input conflicts with actionable recovery', async t => {
  const { call, session, service } = await fixture(t); const token = await session();
  const first = await call('/api/agent/prepare', { token, body: input, key: 'prepare-key-0001' });
  assert.equal(first.status, 201);
  const replay = await call('/api/agent/prepare', { token, body: structuredClone(input), key: 'prepare-key-0001' });
  assert.deepEqual(replay.body, first.body); assert.equal(replay.headers.get('idempotency-replayed'), 'true');
  assert.equal(replay.body.quote.expiresAtMs, first.body.quote.expiresAtMs);
  const state = service.exportState(); assert.equal(state.quotes.length, 1); assert.equal(state.reviews.length, 1);
  const conflict = await call('/api/agent/prepare', { token, body: { ...input, budgetCents: 49999 }, key: 'prepare-key-0001' });
  expectError(conflict, 409, 'IDEMPOTENCY_CONFLICT');
  assert.equal(conflict.body.error.recovery.action, 'reconcile_original_command_before_using_a_new_key');
  assert.deepEqual((await call('/api/agent/runs/' + first.body.run.id, { token })).body.run, first.body.run);
});

test('run ownership, exact decisions and mandate gate fail closed; compact projection reduces bytes', async t => {
  const { call, session, service } = await fixture(t); const token = await session(), stranger = await session();
  const prepared = await call('/api/agent/prepare', { token, body: input, key: 'prepare-key-0002' });
  const path = '/api/agent/runs/' + prepared.body.run.id;
  expectError(await call(path, { token: stranger }), 403, 'BUYER_MISMATCH');
  expectError(await call(path + '/decision', { token: stranger, body: { buyerId, decision: 'approve', quoteId: prepared.body.quote.id, snapshotId: prepared.body.quote.snapshotId } }), 403, 'BUYER_MISMATCH');
  expectError(await call(path + '/decision', { token, body: { buyerId, decision: 'approve', quoteId: prepared.body.quote.id, snapshotId: 'forged' } }), 409, 'REVIEW_MISMATCH');
  expectError(await call(path + '/commit', { token, body: { buyerId, idempotencyKey: 'commit-key-0001' } }), 403, 'HANDSHAKE_REQUIRED');
  assert.equal(service.exportState().orders.length, 0);
  const compact = await call(path, { token }), full = await call(path + '?detail=full', { token });
  assert.equal(full.status, 200); assert.equal(compact.body.quote.id, full.body.quote.id);
  assert.ok(full.body.quote.sourceSnapshot); assert.equal(compact.body.quote.sourceSnapshot, undefined);
  t.diagnostic('workflow bytes compact=' + compact.bytes + ' full=' + full.bytes);
  assert.ok(compact.bytes < full.bytes * 0.8, 'compact response saves at least20%');
});

test('typed catalog/search limits, stale opaque cursors and invalid query shapes are refused', async t => {
  const { call, session, service } = await fixture(t); const token = await session();
  const first = await call('/api/catalog?limit=1&family=dairy-milk&lactoseFree=true');
  assert.equal(first.status, 200); assert.equal(first.body.products.length, 1); assert.ok(first.body.page.nextCursor);
  const second = await call('/api/catalog?limit=1&family=dairy-milk&lactoseFree=true&cursor=' + first.body.page.nextCursor);
  assert.equal(second.status, 200); assert.notEqual(second.body.products[0].sku, first.body.products[0].sku);
  service.simulatePriceChange({ sku: first.body.products[0].sku, priceCents: 200 });
  expectError(await call('/api/catalog?limit=1&family=dairy-milk&lactoseFree=true&cursor=' + first.body.page.nextCursor), 409, 'CURSOR_STALE');
  const search = await call('/api/products/search?q=milk&limit=1', { token });
  assert.equal(search.status, 200); assert.ok(search.body.candidates.length <= 1);
  for (const [path, code] of [
    ['/api/catalog?limit=0', 'INVALID_LIMIT'], ['/api/catalog?cursor=bogus', 'INVALID_CURSOR'],
    ['/api/catalog?unknown=1', 'INVALID_QUERY'], ['/api/catalog?limit=1&limit=2', 'INVALID_QUERY'],
    ['/api/catalog?lactoseFree=yes', 'INVALID_QUERY'], ['/api/catalog?deliverBy=2026-02-30', 'INVALID_QUERY'],
    ['/api/products/search?q=milk&limit=11', 'INVALID_SEARCH_LIMIT'],
    ['/api/products/search?q=milk&q=oat', 'INVALID_QUERY'], ['/api/products/search?q=milk&cursor=bogus', 'INVALID_QUERY'],
  ]) expectError(await call(path, { token }), 400, code);
});

test('append-only audit cursor pins high-water mark across later source events', async t => {
  const { call, service } = await fixture(t);
  for (let i = 0; i < 3; i++) service.simulatePriceChange({ sku: 'DEMO-LF-1', priceCents: 200 + i });
  const first = await call('/api/audit?limit=1'); assert.equal(first.body.page.through, 3);
  const original = service.audit();
  service.simulatePriceChange({ sku: 'DEMO-LF-1', priceCents: 205 });
  const seen = [...first.body.receipts]; let cursor = first.body.page.nextCursor;
  while (cursor) {
    const page = await call('/api/audit?limit=1&cursor=' + cursor);
    assert.equal(page.status, 200); assert.equal(page.body.page.through, 3);
    seen.push(...page.body.receipts); cursor = page.body.page.nextCursor;
  }
  assert.deepEqual(seen, original);
  assert.equal((await call('/api/audit')).body.page.through, 4);
  expectError(await call('/api/audit?tail=1&cursor=' + first.body.page.nextCursor), 400, 'INVALID_QUERY');
});

test('authenticated stalled JSON upload hits bounded deadline; health, Host and Origin remain guarded', async t => {
  const { call, session, base } = await fixture(t, { jsonUploadTimeoutMs: 80 });
  const token = await session(); const started = Date.now();
  const stalled = await new Promise((resolve, reject) => {
    const req = request(base + '/api/agent/prepare', { method: 'POST', headers: {
      Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', 'Content-Length': '1000', 'Idempotency-Key': 'stalled-key-0001',
    } }, response => {
      let text = ''; response.on('data', chunk => { text += chunk; });
      response.on('end', () => resolve({ status: response.statusCode, body: JSON.parse(text) }));
    });
    req.on('error', reject); req.setTimeout(2000, () => req.destroy(Error('test upload deadline exceeded')));
    req.write('{"buyerId":');
  });
  expectError(stalled, 408, 'UPLOAD_TIMEOUT'); assert.ok(Date.now() - started < 1500);
  assert.equal((await call('/api/health')).status, 200);
  const hostileHost = await new Promise((resolve, reject) => {
    const req = request(base + '/api/health', { headers: { Host: 'attacker.example' } }, response => {
      let text = ''; response.on('data', chunk => { text += chunk; });
      response.on('end', () => resolve({ status: response.statusCode, body: JSON.parse(text) }));
    });
    req.on('error', reject); req.end();
  });
  expectError(hostileHost, 403, 'HOST_REFUSED');
  expectError(await call('/api/health', { headers: { Origin: 'https://attacker.example' } }), 403, 'ORIGIN_REFUSED');
});
