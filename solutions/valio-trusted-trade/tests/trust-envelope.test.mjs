import test from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync, randomUUID } from 'node:crypto';
import { createDemoTrustRegistry, canonical, digest, makeDemoMandatePayload, signDemoEnvelope } from '../src/trust-envelope.mjs';

const buyer = 'fictional-buyer';
const quote = { id: 'Q-TEST-00001', buyerId: buyer, totalCents: 1000,
  status: 'APPROVED', approvalRequired: true, createdAtMs: 40000, expiresAtMs: 100000 };
const body = { quote_id: quote.id, buyer_id: buyer, audience: 'https://supplier-demo.invalid', total_cents: 1000 };

function buyerKey(registry, session) {
  const pair = generateKeyPairSync('ed25519');
  const jwk = pair.publicKey.export({ format: 'jwk' });
  const registration = registry.registerBuyerKey(session, { kty: jwk.kty, crv: jwk.crv, x: jwk.x });
  return { ...pair, kid: registration.kid };
}

test('stable canonical signed digests do not depend on JSON field insertion order', () => {
  assert.equal(digest({ b: 2, a: [3, { z: 'yes', x: true }] }), digest({ a: [3, { x: true, z: 'yes' }], b: 2 }));
  assert.throws(() => canonical({ amount: 1.5 }), (error) => error.code === 'INVALID_SIGNING_PAYLOAD');
});

test('two independent private keys produce verifiable quote-bound one-use demo mandates', () => {
  const registry = createDemoTrustRegistry({ clock: () => 50000 });
  const buyerSession = 'session-abc';
  const agent = buyerKey(registry, buyerSession);
  const signedOffer = registry.signOffer(quote, body);
  const signedMandate = signDemoEnvelope(agent.privateKey, agent.kid,
    makeDemoMandatePayload({ quote, signedOffer, now: 50000, nonce: randomUUID() }));
  const result = registry.issueHandshake(quote, body, signedMandate, buyerSession);
  assert.equal(result.verification.valid, true);
  assert.deepEqual(result.verification.signedBy, [signedOffer.protected.kid, agent.kid]);
  assert.equal(registry.verifyHandshake(result, quote, body).valid, true);
  assert.equal(registry.publicKeys().keys.length, 2);
  assert.throws(() => registry.issueHandshake(quote, body, signedMandate, buyerSession), (error) => error.code === 'MANDATE_REPLAY');
  assert.throws(() => registry.registerBuyerKey(buyerSession, generateKeyPairSync('ed25519').publicKey.export({ format: 'jwk' })), (error) => error.code === 'BUYER_KEY_LOCKED');
});

test('tampered signatures, quote amounts, audience and unrelated buyer key fail closed', () => {
  const registry = createDemoTrustRegistry({ clock: () => 50000 });
  const signingAgent = buyerKey(registry, 'session-a');
  buyerKey(registry, 'session-b');
  const signedOffer = registry.signOffer(quote, body);
  const mandate = signDemoEnvelope(signingAgent.privateKey, signingAgent.kid,
    makeDemoMandatePayload({ quote, signedOffer, now: 50000, nonce: randomUUID() }));
  assert.throws(() => registry.issueHandshake(quote, body, mandate, 'session-b'), (error) => error.code === 'BUYER_KEY_MISMATCH');
  assert.throws(() => registry.issueHandshake(quote, body, { ...mandate, payload: { ...mandate.payload, maxTotalCents: 1 } }, 'session-a'), (error) => error.code === 'SIGNATURE_INVALID');
  const valid = registry.issueHandshake(quote, body, mandate, 'session-a');
  assert.throws(() => registry.verifyHandshake(valid, { ...quote, totalCents: 2000 }, body), (error) => error.code === 'PROOF_BINDING_INVALID');
  assert.throws(() => registry.verifyHandshake(valid, quote, { ...body, audience: 'https://different.invalid' }), (error) => error.code === 'PROOF_BINDING_INVALID');
  const forged = structuredClone(valid);
  forged.signedOffer.signature = 'AAAA';
  assert.throws(() => registry.verifyHandshake(forged, quote, body), (error) => error.code === 'SIGNATURE_INVALID');
});

test('bounded procurement proof expires with the underlying quote', () => {
  let now = 50000;
  const registry = createDemoTrustRegistry({ clock: () => now });
  const signingAgent = buyerKey(registry, 'session-expires');
  const signedOffer = registry.signOffer(quote, body);
  const mandate = signDemoEnvelope(signingAgent.privateKey, signingAgent.kid,
    makeDemoMandatePayload({ quote, signedOffer, now, nonce: randomUUID() }));
  const proof = registry.issueHandshake(quote, body, mandate, 'session-expires');
  now = quote.expiresAtMs;
  assert.throws(() => registry.verifyHandshake(proof, quote, body), (error) => error.code === 'PROOF_EXPIRED');
});
