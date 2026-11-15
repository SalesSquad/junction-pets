import test from 'node:test';
import assert from 'node:assert/strict';
import { isDeepStrictEqual } from 'node:util';
import { generateKeyPairSync, randomUUID } from 'node:crypto';
import { createTradeService, FIXTURE_POLICY, unsignedQuoteBody } from '../src/core.mjs';
import { createSyntheticSettlement } from '../src/settlement.mjs';
import { createDemoTrustRegistry, makeDemoMandatePayload, signDemoEnvelope } from '../src/trust-envelope.mjs';

const buyerId = 'helsinki-hotel-demo';
const clock = () => 50000;
const wire = value => JSON.parse(JSON.stringify(value));
const restoreTrade = service => createTradeService({ initialState: wire(service.exportState()), clock });
const failState = error => error.code === 'INVALID_COMPONENT_STATE';

function signedPortfolio() {
  const service = createTradeService({ clock, policy: { ...FIXTURE_POLICY, deliveryFeeCents: 1200, taxBps: 2500 } });
  const trust = createDemoTrustRegistry({ clock });
  const plan = service.planBasket({ buyerId, budgetCents: 250000, requirements: [
    { family: 'dairy-milk', lactoseFree: true, quantityLitres: 480, deliverBy: '2026-11-16' },
    { family: 'oat-drink', lactoseFree: true, quantityLitres: 240, deliverBy: '2026-11-16' },
  ] });
  const quote = service.quoteBasketPlan({ buyerId, planId: plan.id, optionId: 'cost' });
  service.approve({ buyerId, quoteId: quote.id, decision: 'approve' });
  const approved = service.quote(quote.id);
  const pair = generateKeyPairSync('ed25519');
  const publicJwk = pair.publicKey.export({ format: 'jwk' });
  const registration = trust.registerBuyerKey('stable-demo-session', { kty: publicJwk.kty, crv: publicJwk.crv, x: publicJwk.x });
  const body = unsignedQuoteBody(approved);
  const offer = trust.signOffer(approved, body);
  const mandate = signDemoEnvelope(pair.privateKey, registration.kid,
    makeDemoMandatePayload({ quote: approved, signedOffer: offer, now: clock(), nonce: randomUUID() }));
  const proof = trust.issueHandshake(approved, body, mandate, 'stable-demo-session');
  service.recordVerifiedHandshake({ quoteId: quote.id, verification: proof.verification });
  return { service, trust, quote: approved, body, proof, mandate, publicJwk, registration };
}

test('private component codecs preserve namespace, approval, signer and one-use mandates before commitment', () => {
  const fixture = signedPortfolio();
  const service = restoreTrade(fixture.service);
  const trust = createDemoTrustRegistry({ initialState: wire(fixture.trust.exportState()), clock });
  assert.deepEqual(service.exportState(), fixture.service.exportState());
  assert.ok(isDeepStrictEqual(trust.exportState(), fixture.trust.exportState()), 'private trust state round-trips');
  assert.equal(service.assertQuoteFresh(fixture.quote.id), true, 'persisted source epoch must retain quote freshness');
  assert.deepEqual(service.policy(), fixture.service.policy());
  assert.deepEqual(trust.publicKeys(), fixture.trust.publicKeys());
  assert.equal(trust.verifyHandshake(fixture.proof, fixture.quote, fixture.body).valid, true);
  assert.deepEqual(trust.signOffer(fixture.quote, fixture.body), fixture.proof.signedOffer);
  assert.deepEqual(trust.findHandshake(fixture.quote.id), fixture.proof);
  assert.throws(() => trust.issueHandshake(fixture.quote, fixture.body, fixture.mandate, 'stable-demo-session'), { code: 'MANDATE_REPLAY' });
  assert.equal(trust.registerBuyerKey('stable-demo-session', { kty: fixture.publicJwk.kty, crv: fixture.publicJwk.crv, x: fixture.publicJwk.x }).kid, fixture.registration.kid);
  const otherKey = generateKeyPairSync('ed25519').publicKey.export({ format: 'jwk' });
  assert.throws(() => trust.registerBuyerKey('stable-demo-session', { kty: otherKey.kty, crv: otherKey.crv, x: otherKey.x }), { code: 'BUYER_KEY_LOCKED' });
});

test('trade, payment and nested delivery replay survive repeated JSON restores and exact refund', () => {
  const fixture = signedPortfolio();
  let service = restoreTrade(fixture.service);
  const commit = { buyerId, quoteId: fixture.quote.id, idempotencyKey: 'state-codec-order-001' };
  const order = service.commitOrder(commit);
  const scan = { buyerId, orderId: order.id, gtin: '2000000000015', idempotencyKey: 'state-codec-scan-001' };
  const firstScan = service.scanDelivery(scan);
  service.approvePayment({ buyerId, orderId: order.id, decision: 'approve', proposalDigest: service.payment(order.id, buyerId).proposal.digest });
  const pay = { buyerId, orderId: order.id, idempotencyKey: 'state-codec-payment-001' };
  const firstPayment = service.settlePayment(pay);
  service = restoreTrade(service);
  const stock = service.catalog();
  assert.equal(service.commitOrder(commit).id, order.id);
  assert.deepEqual(service.catalog(), stock);
  assert.equal(service.scanDelivery(scan).receiptId, firstScan.receiptId);
  assert.equal(service.scanDelivery({ ...scan, idempotencyKey: 'state-codec-scan-002' }).observedCount, 2);
  assert.equal(service.settlePayment(pay).transfer.id, firstPayment.transfer.id);
  assert.equal(service.paymentJournalVerify().valid, true);
  assert.ok(service.demoWallet().buyerBalanceCents < 250000);
  service.cancelOrder({ buyerId, orderId: order.id });
  service = restoreTrade(service);
  const count = service.paymentJournal().length;
  assert.equal(service.demoWallet().buyerBalanceCents, 250000);
  assert.equal(service.cancelOrder({ buyerId, orderId: order.id }).status, 'SIMULATED_CANCELLED');
  assert.equal(service.paymentJournal().length, count);
  assert.equal(service.settlePayment(pay).transfer.status, 'SIMULATED_REFUNDED');
  assert.equal(service.scanDelivery(scan).receiptId, firstScan.receiptId);
  assert.equal(service.auditVerify().valid, true);
  assert.equal(service.paymentJournalVerify().valid, true);
  service.requestQuote({ buyerId, need: { family: 'oat-drink', lactoseFree: true, quantityLitres: 2, deliverBy: '2026-11-16' } });
  const ids = [...service.audit().map(e => e.id), ...service.exportState().quotes.map(([id]) => id)];
  assert.equal(new Set(ids).size, ids.length, 'restored global serial must never repeat generated IDs');
});

test('exports and accepted restore inputs are detached private plain JSON values', () => {
  const service = createTradeService({ clock });
  const snapshot = wire(service.exportState());
  const restored = createTradeService({ initialState: snapshot, clock });
  snapshot.catalog[0][1].priceCents = 1;
  snapshot.policy.buyerId = 'changed';
  assert.equal(restored.catalog()[0].priceCents, service.catalog()[0].priceCents);
  assert.equal(restored.policy().buyerId, buyerId);
  const trust = createDemoTrustRegistry({ clock });
  const state = trust.exportState();
  state.registeredKeys[0][1].x = 'changed';
  assert.notEqual(trust.publicKeys().keys[0].x, 'changed');
});

test('private codecs refuse unknown versions, incomplete/duplicate maps and inconsistent evidence', () => {
  const trade = createTradeService({ clock }).exportState();
  const trust = createDemoTrustRegistry({ clock }).exportState();
  const settlement = trade.settlement;
  const constructors = [
    [trade, state => createTradeService({ initialState: state, clock })],
    [trust, state => createDemoTrustRegistry({ initialState: state, clock })],
    [settlement, state => createSyntheticSettlement({ initialState: state, clock,
      getOrder: () => assert.fail('empty restore must not look up orders'), record() {}, TradeError: Error })],
  ];
  for (const [state, make] of constructors) {
    for (const invalid of [null, {}, { ...state, version: 2 }, { ...state, kind: 'wrong' }, { ...state, extra: true }]) assert.throws(() => make(invalid), failState);
    const missing = wire(state); delete missing[Object.keys(missing).find(key => !['kind', 'version'].includes(key))];
    assert.throws(() => make(missing), failState);
  }
  const duplicate = wire(trade); duplicate.catalog.push(duplicate.catalog[0]);
  assert.throws(() => createTradeService({ initialState: duplicate, clock }), failState);
  const badSerial = wire(signedPortfolio().service.exportState()); badSerial.serial = 0;
  assert.throws(() => createTradeService({ initialState: badSerial, clock }), failState);
  const badAudit = wire(trade); badAudit.audit.push({ prevHash: 'GENESIS', hash: 'not-a-valid-entry' });
  assert.throws(() => createTradeService({ initialState: badAudit, clock }), failState);
  const badFunds = wire(trade); badFunds.settlement.balances[0][1]++;
  assert.throws(() => createTradeService({ initialState: badFunds, clock }), failState);
  const badKey = wire(trust); badKey.supplierKid = 'demo-supplier-invalid';
  assert.throws(() => createDemoTrustRegistry({ initialState: badKey, clock }), failState);
});
