import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { connect } from 'node:net';
import { generateKeyPairSync, randomUUID } from 'node:crypto';
import { createTradeService, FIXTURE_CATALOG, FIXTURE_POLICY, unsignedQuoteBody } from '../src/core.mjs';
import { createTradeHttpServer } from '../src/server.mjs';
import { createDemoTrustRegistry, digest, makeDemoMandatePayload, signDemoEnvelope } from '../src/trust-envelope.mjs';
import { createPgvectorCatalogSearch, PG_EMBEDDING_DIMENSION, PG_HYBRID_QUERY } from '../src/catalog-retrieval-pg.mjs';

const buyerId = 'helsinki-hotel-demo';
const need = { family: 'dairy-milk', lactoseFree: true, quantityLitres: 1000, deliverBy: '2026-11-16' };
const chargedPolicy = { ...FIXTURE_POLICY, deliveryFeeCents: 2500, taxBps: 1000 };
const requirements = [{ ...need, quantityLitres: 12 }, { ...need, family: 'oat-drink', quantityLitres: 8 }];
const key = () => randomUUID();

test('one quote-only approval includes delivery and tax while leaving future budgets unchanged', () => {
  const service = createTradeService({ policy: chargedPolicy });
  const result = service.requestReview({ buyerId, need, budgetCents: 140000 });
  assert.deepEqual(result.quote.costBreakdown, { subtotalCents: 177300, deliveryFeeCents: 2500, taxCents: 17980, taxBps: 1000 });
  assert.equal(result.review.diagnosis.minimumCostCents, 197780);
  assert.equal(result.quote.budgetException.additionalCents, 57780);
  const q = result.quote;
  assert.throws(() => service.commitOrder({ buyerId, quoteId: q.id, idempotencyKey: key() }), { code: 'APPROVAL_REQUIRED' });
  service.decideReview({ buyerId, reviewId: result.review.id, quoteId: q.id, snapshotId: q.snapshotId, decision: 'approve' });
  assert.equal(service.commitOrder({ buyerId, quoteId: q.id, idempotencyKey: key() }).totalCents, 197780);
  assert.equal(service.policy().perOrderBudgetCents, FIXTURE_POLICY.perOrderBudgetCents);
  assert.throws(() => service.requestQuote({ buyerId, need: { ...need, quantityLitres: 10 }, budgetCents: 1000 }), { code: 'BUDGET_EXCEEDED' });
});

test('all quote flows honor whole packs/minimums and cannot approve physically impossible quantities', () => {
  const catalog = FIXTURE_CATALOG.map(p => ({ ...p,
    packLitres: p.sku === 'DEMO-LF-1' ? 6 : p.sku === 'DEMO-LF-2' ? 10 : 1,
    minOrderPacks: p.sku === 'DEMO-LF-1' ? 5 : p.sku === 'DEMO-LF-2' ? 2 : 1 }));
  const service = createTradeService({ initialCatalog: catalog });
  const { quote } = service.requestReview({ buyerId, need, budgetCents: 250000 });
  assert.deepEqual(quote.lines.map(l => [l.sku, l.quantityLitres, l.packs]), [['DEMO-LF-1', 780, 130], ['DEMO-LF-2', 220, 22]]);
  const impossible = createTradeService({ initialCatalog: catalog.map(p => ({ ...p, packLitres: 7 })) });
  const refused = impossible.requestReview({ buyerId, need, budgetCents: 250000 });
  assert.equal(refused.quote, null);
  assert.equal(refused.review.diagnosis.outcome, 'PACKING_CONSTRAINT');
});

test('signed v3 financial terms cover all fees; settlement/refund conserve every cent and scan counts packs', () => {
  const service = createTradeService({ policy: chargedPolicy,
    initialCatalog: FIXTURE_CATALOG.map(p => ({ ...p, packLitres: p.sku === 'DEMO-LF-1' ? 6 : 1 })) });
  const plan = service.planBasket({ buyerId, budgetCents: 250000, requirements });
  const q = service.quoteBasketPlan({ buyerId, planId: plan.id, optionId: 'cost' });
  assert.equal(q.costBreakdown.deliveryFeeCents, 2500, 'fee charged once across both families');
  const body = unsignedQuoteBody(q);
  assert.equal(body.version, 'kattely.procurement.quote.v3');
  assert.equal(body.source_snapshot_id, q.snapshotId);
  assert.equal(body.total_cents, body.cost_breakdown.subtotal_cents + body.cost_breakdown.delivery_fee_cents + body.cost_breakdown.tax_cents);
  assert.equal(body.lines.find(l => l.sku === 'DEMO-LF-1').pack_count, 2);
  assert.notEqual(digest(body), digest({ ...body, cost_breakdown: { ...body.cost_breakdown, delivery_fee_cents: 1 } }));
  service.recordVerifiedHandshake({ quoteId: q.id, verification: { valid: true, quoteId: q.id, buyerId,
    signedBy: ['synthetic-unit-buyer', 'synthetic-unit-supplier'], quoteBodyDigest: digest(body),
    signedOfferDigest: 'unit-offer', signedMandateDigest: 'unit-mandate' } });
  const order = service.commitOrder({ buyerId, quoteId: q.id, idempotencyKey: key() });
  const observation = service.scanDelivery({ buyerId, orderId: order.id, gtin: '2000000000015', idempotencyKey: key() });
  assert.deepEqual([observation.observedCount, observation.orderedCount, observation.packLitres, observation.observedLitres], [1, 2, 6, 6]);
  service.scanDelivery({ buyerId, orderId: order.id, gtin: observation.gtin, idempotencyKey: key() });
  assert.throws(() => service.scanDelivery({ buyerId, orderId: order.id, gtin: observation.gtin, idempotencyKey: key() }), { code: 'RECEIPT_OVER_COUNT' });
  service.approvePayment({ buyerId, orderId: order.id, decision: 'approve', proposalDigest: service.payment(order.id, buyerId).proposal.digest });
  const args = { buyerId, orderId: order.id, idempotencyKey: key() };
  const paid = service.settlePayment(args);
  assert.equal(paid.transfer.allocations.reduce((sum, a) => sum + a.amountCents, 0), q.totalCents);
  assert.ok(paid.transfer.allocations.some(a => a.supplierId === 'fictional-delivery-fee'));
  assert.equal(service.settlePayment(args).idempotentReplay, true);
  service.cancelOrder({ buyerId, orderId: order.id });
  assert.equal(service.demoWallet().buyerBalanceCents, 250000);
  assert.ok(service.demoWallet().suppliers.every(s => s.balanceCents === 0));
  assert.equal(service.paymentJournalVerify().valid, true);
});

test('genuinely signed malformed mandate timestamps are refused without consuming valid authority', () => {
  const now = 50000;
  const quote = { id: 'Q-TIMES-TEST', buyerId, totalCents: 1000, status: 'APPROVED', approvalRequired: true, createdAtMs: 40000, expiresAtMs: 100000 };
  const body = { quote_id: quote.id, buyer_id: buyerId, audience: 'https://supplier-demo.invalid', total_cents: 1000 };
  for (const patch of [{ issuedAtMs: '50000' }, { expiresAtMs: 'later' }, { issuedAtMs: 39999 }, { issuedAtMs: 50000.5 }, { expiresAtMs: 49000 }, { issuedAtMs: 50001 }]) {
    const registry = createDemoTrustRegistry({ clock: () => now });
    const pair = generateKeyPairSync('ed25519');
    const jwk = pair.publicKey.export({ format: 'jwk' });
    const { kid } = registry.registerBuyerKey('session', { kty: jwk.kty, crv: jwk.crv, x: jwk.x });
    const signedOffer = registry.signOffer(quote, body);
    const payload = makeDemoMandatePayload({ quote, signedOffer, now, nonce: key() });
    assert.throws(() => registry.issueHandshake(quote, body, signDemoEnvelope(pair.privateKey, kid, { ...payload, ...patch }), 'session'),
      e => ['PROOF_TIME_INVALID', 'PROOF_EXPIRED', 'INVALID_SIGNING_PAYLOAD'].includes(e.code));
    const valid = registry.issueHandshake(quote, body, signDemoEnvelope(pair.privateKey, kid, payload), 'session');
    assert.equal(valid.verification.valid, true);
  }
});

test('retrieval rejects blank or stale source provenance and rolls back the scoped read', async () => {
  const now = Date.parse('2026-11-15T12:00:00Z');
  const valid = { sku: 'DEMO-OAT-1', product_title: 'Oat drink', family: 'oat-drink', catalog_version: 'v1', source_ref: 'fictional-fixture',
    source_kind: 'AIMO_FIXTURE', source_sha256: 'a'.repeat(64), source_observed_at: new Date(now).toISOString(),
    rrf_score: 0.03, lexical_match: true, semantic_distance: 0.2 };
  for (const patch of [{ source_ref: ' ' }, { catalog_version: '' }, { source_observed_at: new Date(now - 86400001).toISOString() }, { source_observed_at: new Date(now + 60001).toISOString() }, { family: 'invented-allergen-safe' }]) {
    const calls = [];
    let released = false;
    const search = createPgvectorCatalogSearch({ clock: () => now, tenantId: 'valio-demo', embeddingModel: 'test-model',
      embedQuery: async () => ({ model: 'test-model', vector: Array(PG_EMBEDDING_DIMENSION).fill(0.01) }),
      pool: { connect: async () => ({ query: async sql => { calls.push(sql); return { rows: sql === PG_HYBRID_QUERY ? [{ ...valid, ...patch }] : [] }; }, release() { released = true; } }) } });
    await assert.rejects(search.search({ buyerId, query: 'oat drink' }), { code: 'RETRIEVAL_BACKEND_UNAVAILABLE' });
    assert.equal(calls.at(-1), 'ROLLBACK');
    assert.equal(released, true);
  }
});

test('stalled image upload has a wall deadline and never holds the OCR worker', async () => {
  const server = createTradeHttpServer(createTradeService(), { imageUploadTimeoutMs: 80 });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const port = server.address().port, base = 'http://127.0.0.1:' + port;
  let socket;
  try {
    const session = await (await fetch(base + '/api/demo/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ buyerId }) })).json();
    socket = connect(port, '127.0.0.1'); await once(socket, 'connect');
    let response = '';
    const ended = new Promise((resolve, reject) => { socket.on('data', chunk => response += chunk); socket.on('end', resolve); socket.on('error', reject); });
    socket.write('POST /api/scan/ocr HTTP/1.1\r\nHost: 127.0.0.1:' + port + '\r\nAuthorization: Bearer ' + session.token + '\r\nContent-Type: image/png\r\nContent-Length: 1000\r\n\r\npartial');
    await ended;
    assert.match(response, /408/);
    const next = await fetch(base + '/api/scan/ocr', { method: 'POST', headers: { Authorization: 'Bearer ' + session.token, 'Content-Type': 'image/png' }, body: 'invalid' });
    assert.equal((await next.json()).error.code, 'INVALID_IMAGE');
    assert.equal((await fetch(base + '/api/health')).status, 200);
  } finally { socket?.destroy(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});

test('independent buyer process checks charged packed quotes through real HTTP', { timeout: 15000 }, async () => {
  const { execFile } = await import('node:child_process');
  const { promisify } = await import('node:util');
  const { fileURLToPath } = await import('node:url');
  for (const agent of ['buyer-agent.mjs', 'frontier-agent.mjs']) {
    const service = createTradeService({ policy: chargedPolicy,
      initialCatalog: FIXTURE_CATALOG.map(p => ({ ...p, packLitres: p.sku === 'DEMO-LF-1' ? 6 : 1 })) });
    const server = createTradeHttpServer(service);
    server.listen(0, '127.0.0.1'); await once(server, 'listening');
    try {
      const args = agent === 'buyer-agent.mjs' ? ['success', '--decision=approve'] :
        ['happy', '--decision=approve', '--payment-decision=approve', '--refund-demo'];
      const result = await promisify(execFile)(process.execPath,
        [fileURLToPath(new URL('../src/' + agent, import.meta.url)), ...args],
        { env: { ...process.env, SUPPLIER_URL: 'http://127.0.0.1:' + server.address().port }, timeout: 10000 });
      assert.ok(result.stdout.includes('SYNTHETIC'));
      assert.equal(service.audit().filter(e => e.event === 'ORDER_SIMULATED').length, 1);
      if (agent === 'frontier-agent.mjs') {
        assert.equal(service.demoWallet().buyerBalanceCents, 250000);
        assert.equal(service.paymentJournalVerify().valid, true);
      }
    } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  }
});

test('independent buyer terms reject a forged price, partial pack and understated financial body', async () => {
  const { verifyBuyerTerms, verifyBuyerBody } = await import('../src/buyer-terms.mjs');
  const service = createTradeService({ policy: chargedPolicy });
  const q = service.requestQuote({ buyerId, need, budgetCents: 250000 });
  verifyBuyerTerms(q, chargedPolicy);
  verifyBuyerBody(unsignedQuoteBody(q), q);
  for (const mutate of [
    x => { x.totalCents -= 1; },
    x => { x.costBreakdown.deliveryFeeCents = 0; },
    x => { x.lines[0].packs += 1; },
    x => { x.lines[0].unitPriceCents += 1; },
  ]) {
    const altered = structuredClone(q); mutate(altered);
    assert.throws(() => verifyBuyerTerms(altered, chargedPolicy));
  }
  const alteredBody = unsignedQuoteBody(q); alteredBody.cost_breakdown.tax_cents = 0;
  assert.throws(() => verifyBuyerBody(alteredBody, q));
});
