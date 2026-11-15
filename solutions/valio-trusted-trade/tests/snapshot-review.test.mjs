import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { connect } from 'node:net';
import { createTradeService } from '../src/core.mjs';
import { createTradeHttpServer } from '../src/server.mjs';

const buyerId = 'helsinki-hotel-demo';
const need = { family: 'dairy-milk', quantityLitres: 1000, lactoseFree: true, deliverBy: '2026-11-16' };
const request = { buyerId, need, budgetCents: 140_000 };
const hasCode = (code) => (error) => error.code === code;
const decision = (result, extra = {}) => ({ buyerId, decision: 'approve',
  reviewId: result.review.id, quoteId: result.quote?.id, snapshotId: result.review.snapshotId, ...extra });

test('review and quote share the same scoped price/stock/policy snapshot', () => {
  const service = createTradeService();
  const result = service.requestReview(request);
  assert.equal(result.quote.snapshotId, result.review.snapshotId);
  assert.deepEqual(result.quote.sourceSnapshot, result.review.sourceSnapshot);
  assert.ok(result.review.sourceSnapshot.products.every((p) => p.family === need.family));
  assert.deepEqual(result.review.diagnosis.sourceVersions, result.review.sourceSnapshot.products.map(
    ({ sku, version, priceCents, unitsAvailable, family, lactoseFree, deliverBy }) =>
      ({ sku, version, priceCents, unitsAvailable, family, lactoseFree, deliverBy })));
  assert.equal(result.quote.totalCents, result.review.diagnosis.minimumCostCents);
  assert.equal(result.quote.budgetCents, 140_000);
  assert.deepEqual(result.quote.budgetException, { originalBudgetCents: 140_000,
    proposedBudgetCents: 177_300, additionalCents: 37_300, scope: 'THIS_QUOTE_ONLY' });
  assert.equal(result.quote.sourceSnapshot.stockReserved, false);
});

test('exception cannot use legacy approval, unconfirmed order or mismatched snapshot/quote', () => {
  const service = createTradeService();
  const result = service.requestReview(request);
  assert.throws(() => service.approve({ buyerId, quoteId: result.quote.id, decision: 'approve', boundReviewId: result.review.id }),
    hasCode('REVIEW_CONFIRMATION_REQUIRED'));
  assert.throws(() => service.commitOrder({ buyerId, quoteId: result.quote.id, idempotencyKey: 'unconfirmed-order' }),
    hasCode('APPROVAL_REQUIRED'));
  for (const extra of [{ snapshotId: 'forged' }, { quoteId: 'forged' }, { snapshotId: undefined }]) {
    assert.throws(() => service.decideReview(decision(result, extra)), hasCode('REVIEW_MISMATCH'));
  }
  assert.throws(() => service.decideReview(decision(result, { totalCents: 1 })), hasCode('INVALID_REVIEW_DECISION'));
});

test('approval accepts this one quote, preserves policy and replays exactly once', () => {
  const service = createTradeService();
  const policyBefore = service.policy();
  const result = service.requestReview(request);
  const approved = service.decideReview(decision(result));
  assert.equal(approved.quote.approval.totalCents, 177_300);
  assert.equal(approved.quote.approval.additionalBudgetCents, 37_300);
  assert.equal(approved.quote.approval.snapshotId, result.review.snapshotId);
  assert.equal(approved.quote.approval.reviewId, result.review.id);
  const orderRequest = { buyerId, quoteId: result.quote.id, idempotencyKey: 'snapshot-order-once' };
  const first = service.commitOrder(orderRequest);
  const stockAfter = service.catalog();
  assert.equal(service.commitOrder(orderRequest).id, first.id);
  assert.deepEqual(service.catalog(), stockAfter);
  assert.equal(first.snapshotId, result.review.snapshotId);
  assert.deepEqual(service.policy(), policyBefore);
  assert.throws(() => service.requestQuote({ ...request, need: { ...need, quantityLitres: 10 }, budgetCents: 1 }),
    hasCode('BUDGET_EXCEEDED'));
});

test('even below the automatic threshold a budget exception needs an explicit review decision', () => {
  const service = createTradeService();
  const result = service.requestReview({ ...request, need: { ...need, quantityLitres: 10 }, budgetCents: 1000 });
  assert.equal(result.quote.totalCents, 1740);
  assert.equal(result.quote.approvalRequired, true);
  assert.throws(() => service.commitOrder({ buyerId, quoteId: result.quote.id, idempotencyKey: 'small-exception' }),
    hasCode('APPROVAL_REQUIRED'));
  service.decideReview(decision(result));
  assert.equal(service.commitOrder({ buyerId, quoteId: result.quote.id, idempotencyKey: 'small-exception' }).totalCents, 1740);
});

test('source change after approval invalidates commitment and new review never inherits approval', () => {
  const service = createTradeService();
  const result = service.requestReview(request);
  service.decideReview(decision(result));
  service.simulatePriceChange({ sku: 'DEMO-LF-1', priceCents: 175 });
  assert.throws(() => service.commitOrder({ buyerId, quoteId: result.quote.id, idempotencyKey: 'stale-snapshot' }),
    hasCode('QUOTE_STALE'));
  const fresh = service.requestReview(request);
  assert.notEqual(fresh.review.snapshotId, result.review.snapshotId);
  assert.notEqual(fresh.quote.id, result.quote.id);
  assert.equal(fresh.quote.approval, null);
  assert.equal(fresh.quote.budgetException.additionalCents, 38_080);
  assert.throws(() => service.commitOrder({ buyerId, quoteId: fresh.quote.id, idempotencyKey: 'fresh-unapproved' }),
    hasCode('APPROVAL_REQUIRED'));
});

test('source revision includes relevant unselected products but excludes another family', () => {
  const service = createTradeService();
  const result = service.requestReview(request);
  service.simulatePriceChange({ sku: 'DEMO-OAT-1', priceCents: 163 });
  service.decideReview(decision(result));
  service.simulatePriceChange({ sku: 'DEMO-LF-3', priceCents: 210 });
  assert.throws(() => service.commitOrder({ buyerId, quoteId: result.quote.id, idempotencyKey: 'revised-category' }),
    hasCode('QUOTE_STALE'));
});

test('shortage and policy-ceiling reviews have no approvable quote', () => {
  const service = createTradeService();
  const shortage = service.requestReview({ ...request, need: { ...need, quantityLitres: 2000 } });
  assert.equal(shortage.quote, null);
  assert.equal(shortage.review.diagnosis.missingLitres, 320);
  assert.equal(shortage.review.diagnosis.minimumCostCents, null);
  assert.throws(() => service.decideReview(decision(shortage)), hasCode('REVIEW_BLOCKED'));
  const limit = service.requestReview({ ...request, need: { ...need, family: 'oat-drink', quantityLitres: 1600 } });
  assert.equal(limit.quote, null);
  assert.equal(limit.review.diagnosis.outcome, 'POLICY_LIMIT_EXCEEDED');
  assert.throws(() => service.decideReview(decision(limit)), hasCode('REVIEW_BLOCKED'));
});

test('rejection is terminal and exact expiry refuses both decision and order without sleeps', () => {
  let now = 1_800_000_000_000;
  const service = createTradeService({ clock: () => now });
  const rejected = service.requestReview(request);
  service.decideReview(decision(rejected, { decision: 'reject' }));
  assert.throws(() => service.decideReview(decision(rejected)), hasCode('ALREADY_DECIDED'));
  assert.throws(() => service.commitOrder({ buyerId, quoteId: rejected.quote.id, idempotencyKey: 'rejected-snapshot' }),
    hasCode('APPROVAL_REJECTED'));
  const expired = service.requestReview(request);
  service.decideReview(decision(expired));
  now = expired.quote.expiresAtMs;
  assert.throws(() => service.decideReview(decision(expired)), hasCode('QUOTE_EXPIRED'));
  assert.throws(() => service.commitOrder({ buyerId, quoteId: expired.quote.id, idempotencyKey: 'expired-snapshot' }),
    hasCode('QUOTE_EXPIRED'));
});

async function fixture(run) {
  const service = createTradeService();
  const server = createTradeHttpServer(service);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = 'http://127.0.0.1:' + server.address().port;
  const call = async (path, body, token) => {
    const response = await fetch(base + path, { method: body === undefined ? 'GET' : 'POST',
      headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: response.status, ...await response.json() };
  };
  try { await run({ server, service, base, call, session: async () => (await call('/api/demo/session', { buyerId })).token }); }
  finally { await new Promise((done) => server.close(done)); }
}

test('HTTP review ownership, decision identifiers and forged authority fields are enforced', async () => fixture(async ({ call, session }) => {
  const token = await session();
  const other = await session();
  assert.equal((await call('/api/reviews', request)).error.code, 'BUYER_CAPABILITY_REQUIRED');
  const result = await call('/api/reviews', request, token);
  assert.equal(result.status, 201);
  const path = '/api/reviews/' + result.review.id + '/decision';
  const body = { buyerId, decision: 'approve', snapshotId: result.review.snapshotId, quoteId: result.quote.id };
  assert.equal((await call(path, body, other)).error.code, 'BUYER_MISMATCH');
  assert.equal((await call(path, { ...body, snapshotId: 'wrong-version' }, token)).error.code, 'REVIEW_MISMATCH');
  assert.equal((await call(path, { ...body, budgetCents: 999999 }, token)).error.code, 'INVALID_REVIEW_DECISION');
  assert.equal((await call('/api/quotes/' + result.quote.id + '/approval', { buyerId, decision: 'approve' }, token)).error.code, 'REVIEW_CONFIRMATION_REQUIRED');
  assert.equal((await call(path, body, token)).quote.status, 'APPROVED');
  assert.equal((await call('/api/orders', { buyerId, quoteId: result.quote.id, idempotencyKey: 'foreign-review-order' }, other)).error.code, 'BUYER_MISMATCH');
  assert.equal((await call('/api/orders', { buyerId, quoteId: result.quote.id, idempotencyKey: 'http-exact-review' }, token)).status, 201);
}));

test('discovery documents the review contract and generated snapshot agrees with source', async () => fixture(async ({ call }) => {
  const metadata = await call('/.well-known/trusted-trade');
  assert.equal(metadata.endpoints.reviews, '/api/reviews');
  const spec = await call(metadata.openapi);
  assert.ok(spec.paths['/api/reviews'].post.security);
  assert.deepEqual(spec.components.schemas.ReviewDecision.required, ['buyerId', 'decision', 'snapshotId', 'quoteId']);
  const { readFile } = await import('node:fs/promises');
  const generated = JSON.parse(await readFile(new URL('../openapi.yaml', import.meta.url), 'utf8'));
  delete spec.status;
  assert.deepEqual(spec, generated);
}));

test('malformed request target returns a bounded 400 and the same server stays healthy', async () => fixture(async ({ server, base }) => {
  const response = await new Promise((resolve, reject) => {
    const socket = connect(server.address().port, '127.0.0.1');
    let data = '';
    socket.setTimeout(3000, () => socket.destroy(new Error('Malformed request probe timed out')));
    socket.on('connect', () => socket.write('GET //[ HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n'));
    socket.on('data', (chunk) => { data += chunk; });
    socket.on('end', () => resolve(data));
    socket.on('error', reject);
  });
  assert.match(response, /HTTP\/1\.1 400/);
  assert.match(response, /INVALID_URL/);
  const health = await fetch(base + '/api/health');
  assert.equal(health.status, 200);
  assert.equal((await health.json()).status, 'ok');
}));

test('normal low-value review preserves automatic buying only within the original budget and policy', () => {
  const service = createTradeService();
  const result = service.requestReview({ ...request, need: { ...need, quantityLitres: 10 }, budgetCents: 2000 });
  assert.equal(result.quote.budgetException, null);
  assert.equal(result.quote.approvalRequired, false);
  assert.equal(result.quote.totalCents, 1740);
  assert.equal(service.commitOrder({ buyerId, quoteId: result.quote.id, idempotencyKey: 'bounded-auto-review' }).totalCents, 1740);
});
