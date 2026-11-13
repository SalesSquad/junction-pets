import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import {dispatchPetRequest, receiptSha256, validateReceiptShape} from './bridge.mjs';

const RECEIPT_SCHEMA = JSON.parse(readFileSync(
  new URL('../../contracts/pet-collaboration/v1/receipt.schema.json', import.meta.url), 'utf8'));
const ajvReceipt = new Ajv2020({strict: false, validateFormats: false, allErrors: true}).compile(RECEIPT_SCHEMA);
const idempotencyKey = r => 'sha256:' + createHash('sha256')
  .update(JSON.stringify([r.tenantId, r.requestId]), 'utf8').digest('hex');
const SOURCE = '4'.repeat(40);
const NOW = Date.parse('2026-11-12T15:00:00Z');

function request() {
  return {
    schemaVersion: 'pet-collaboration.v1', kind: 'request',
    requestId: 'req.01', conversationId: 'turn.01',
    tenantId: 'tenant.alpha', actorPetId: 'junction.openai-codex',
    recipientPetId: 'junction.mariadb', capabilityId: 'query-review',
    authorityRef: 'host.grant.01', sourceSha: SOURCE, requestedEffect: 'read',
    createdAt: '2026-11-12T14:59:59Z', expiresAt: '2026-11-12T15:02:00Z',
    depth: 0, context: {ref: 'context.synthetic.1', digest: 'sha256:' + 'a'.repeat(64), dataClass: 'synthetic'},
    budget: {maxTokens: 600, maxDepth: 2},
  };
}

function grant(r, overrides = {}) {
  return {
    allowed: true, revoked: false, decisionRef: 'host.decision.01',
    authorityRef: r.authorityRef, tenantId: r.tenantId,
    actorPetId: r.actorPetId, recipientPetId: r.recipientPetId,
    capabilityId: r.capabilityId, sourceSha: r.sourceSha,
    requestId: r.requestId, conversationId: r.conversationId,
    parentRequestId: r.parentRequestId ?? null, depth: r.depth,
    requestedEffect: r.requestedEffect, contextRef: r.context.ref,
    contextDigest: r.context.digest,
    allowedDataClasses: [r.context.dataClass],
    expiresAt: '2026-11-12T15:03:00Z', maxTokens: 1000, maxDepth: 4,
    ...overrides,
  };
}

function receipt(r, overrides = {}) {
  return {
    schemaVersion: 'pet-collaboration.v1', kind: 'receipt',
    requestId: r.requestId, tenantId: r.tenantId,
    actorPetId: r.actorPetId, recipientPetId: r.recipientPetId,
    decisionRef: 'host.decision.01', status: 'completed', executionKind: 'model',
    sourceSha: SOURCE, completedAt: '2026-11-12T15:00:10Z',
    outputDigest: 'sha256:' + 'b'.repeat(64),
    providerReceiptRef: 'provider.req.01',
    hostAttestation: {issuer: 'chibi-host', attestationRef: 'host.attest.01', signatureRef: 'host.sig.01'},
    hostAuthorization: true, externalEffects: false,
    ...overrides,
  };
}

function host(r) {
  const used = new Set();
  const counters = {calls: 0, dispatches: 0, attestations: 0};
  const adapters = {
    authenticatedTenantId: r.tenantId,
    authenticatedActorPetId: r.actorPetId,
    sourceSha: SOURCE, nowMs: () => NOW, timeoutMs: 500,
    verifyHostGrant: async () => {counters.calls++; return grant(r);},
    reserveReplay: async ({tenantId, requestId}) => {
      const key = JSON.stringify([tenantId, requestId]);
      if (used.has(key)) return {reserved: false};
      used.add(key);
      return {reserved: true};
    },
    transport: async ({idempotencyKey: actualKey}) => {
      counters.dispatches++;
      assert.equal(actualKey, idempotencyKey(r));
      return receipt(r);
    },
    verifyHostReceipt: async ({receipt: row, receiptSha256: digest, sourceSha, requestId}) => {
      counters.attestations++;
      return {verified: true, issuer: 'chibi-host', receiptSha256: digest, sourceSha, requestId,
        verificationRef: 'host.proof.01'};
    },
  };
  return {adapters, counters};
}

test('valid host-injected read-only receipt can be admitted and attested by injected verifier', async () => {
  const r = request(), h = host(r);
  const result = await dispatchPetRequest(r, h.adapters);
  assert.equal(result.ok, true);
  assert.equal(result.code, 'HOST_RECEIPT_ATTESTED');
  assert.equal(result.receipt.sourceSha, SOURCE);
  assert.equal(h.counters.dispatches, 1);
  assert.equal(h.counters.attestations, 1);
  assert.ok(h.counters.calls >= 3);
  assert.equal(validateReceiptShape(result.receipt), true);
  assert.equal(ajvReceipt(result.receipt), true, JSON.stringify(ajvReceipt.errors));
  assert.match(receiptSha256(result.receipt), /^sha256:[a-f0-9]{64}$/);
});

test('host-dependent paths deny by default with missing credential/verifier/endpoint', async () => {
  const r = request(), h = host(r);
  for (const key of ['verifyHostGrant', 'reserveReplay', 'transport', 'verifyHostReceipt']) {
    const partial = {...h.adapters};
    delete partial[key];
    const outcome = await dispatchPetRequest(r, partial);
    assert.deepEqual(outcome, {ok: false, code: 'HOST_INTEGRATION_UNAVAILABLE'});
  }
  assert.equal((await dispatchPetRequest(r, {...h.adapters, sourceSha: 'not-a-commit'})).code, 'UNBOUND_SOURCE');
  assert.equal(h.counters.dispatches, 0);
});

test('tenant and actor identities are host-controlled, never taken from pet request', async () => {
  const r = request(), h = host(r);
  assert.equal((await dispatchPetRequest(r, {...h.adapters, authenticatedTenantId: 'tenant.other'})).code, 'IDENTITY_MISMATCH');
  assert.equal((await dispatchPetRequest(r, {...h.adapters, authenticatedActorPetId: 'junction.nvidia'})).code, 'IDENTITY_MISMATCH');
  assert.equal((await dispatchPetRequest(r, {...h.adapters, authenticatedActorPetId: null})).code, 'NO_HOST_IDENTITY');
  assert.equal(h.counters.dispatches, 0);
});

test('read-only bridge requires human approval for proposals or writes', async () => {
  const r = request(), h = host(r);
  for (const effect of ['proposal', 'write']) {
    assert.equal((await dispatchPetRequest({...r, requestedEffect: effect}, h.adapters)).code, 'HUMAN_APPROVAL_REQUIRED');
  }
  assert.equal(h.counters.dispatches, 0);
});

test('replay reservation preserves tenant/request idempotency', async () => {
  const r = request(), h = host(r);
  assert.equal((await dispatchPetRequest(r, h.adapters)).ok, true);
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'REPLAY_OR_RESERVATION_FAILED');
  assert.equal(h.counters.dispatches, 1);
});

test('grant revocation before transport aborts dispatch', async () => {
  const r = request(), h = host(r);
  h.adapters.verifyHostGrant = async () => {
    h.counters.calls++;
    return grant(r, h.counters.calls >= 2 ? {revoked: true} : {});
  };
  const result = await dispatchPetRequest(r, h.adapters);
  assert.equal(result.code, 'REVOKED_BEFORE_DISPATCH');
  assert.equal(h.counters.dispatches, 0);
});

test('grant revocation after transport prevents any output receipt leakage', async () => {
  const r = request(), h = host(r);
  h.adapters.verifyHostGrant = async () => {
    h.counters.calls++;
    return grant(r, h.counters.calls >= 3 ? {revoked: true} : {});
  };
  const result = await dispatchPetRequest(r, h.adapters);
  assert.deepEqual(result, {ok: false, code: 'REVOKED_AFTER_DISPATCH'});
  assert.equal(h.counters.dispatches, 1);
  assert.equal(h.counters.attestations, 0);
});

test('tampered host receipt and fake attestation fail closed', async () => {
  const r = request(), h1 = host(r);
  h1.adapters.transport = async () => receipt(r, {recipientPetId: 'junction.nvidia'});
  assert.equal((await dispatchPetRequest(r, h1.adapters)).code, 'HOST_RECEIPT_INVALID');

  const h2 = host(r);
  h2.adapters.verifyHostReceipt = async () =>
    ({verified: true, issuer: 'chibi-host', receiptSha256: 'sha256:' + '0'.repeat(64),
      sourceSha: SOURCE, requestId: r.requestId, verificationRef: 'host.fake'});
  assert.equal((await dispatchPetRequest(r, h2.adapters)).code, 'HOST_ATTESTATION_INVALID');
});

test('no raw tokens, extra context or self-awarded grants can enter wire shape', async () => {
  const r = request(), h = host(r);
  r.context.payload = 'SECRET-PRIVATE-CONTENT';
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'INVALID_REQUEST');
  delete r.context.payload;
  r.token = 'PRIVATE-TOKEN';
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'INVALID_REQUEST');
  assert.equal(h.counters.dispatches, 0);
});

test('cancellation before dispatch fails without reserving replay', async () => {
  const r = request(), h = host(r), controller = new AbortController();
  controller.abort();
  assert.equal((await dispatchPetRequest(r, {...h.adapters, signal: controller.signal})).code, 'CANCELLED');
  assert.equal(h.counters.dispatches, 0);
});

test('timeout bounds an unresponsive host transport', async () => {
  const r = request(), h = host(r);
  h.adapters.transport = async () => new Promise(() => {});
  const result = await dispatchPetRequest(r, {...h.adapters, timeoutMs: 15});
  assert.equal(result.code, 'TIMEOUT');
  assert.equal(h.counters.attestations, 0);
});

test('in-flight cancellation never reports an authorized response', async () => {
  const r = request(), h = host(r), controller = new AbortController();
  h.adapters.transport = async (_payload, {signal}) => new Promise(resolve => {
    signal.addEventListener('abort', () => resolve(receipt(r)), {once: true});
  });
  const work = dispatchPetRequest(r, {...h.adapters, signal: controller.signal, timeoutMs: 200});
  await new Promise(resolve => setTimeout(resolve, 5));
  controller.abort();
  const result = await work;
  assert.equal(result.code, 'CANCELLED');
  assert.equal(h.counters.attestations, 0);
});

test('host transport and attestation failures redact diagnostic exceptions', async () => {
  const r = request(), h1 = host(r);
  h1.adapters.transport = async () => {throw new Error('PRIVATE-BEARER-TOKEN');};
  const failed = await dispatchPetRequest(r, h1.adapters);
  assert.deepEqual(failed, {ok: false, code: 'HOST_TRANSPORT_FAILED'});
  assert.ok(!JSON.stringify(failed).includes('PRIVATE-BEARER-TOKEN'));
  const h2 = host(r);
  h2.adapters.verifyHostReceipt = async () => {throw new Error('PRIVATE-SIGNATURE');};
  const attestation = await dispatchPetRequest(r, h2.adapters);
  assert.deepEqual(attestation, {ok: false, code: 'HOST_ATTESTATION_UNAVAILABLE'});
});

test('receipt validation rejects impossible dates and unauthorized external effects', async () => {
  const r = request(), h1 = host(r);
  h1.adapters.transport = async () => receipt(r, {completedAt: '2026-02-30T15:00:10Z'});
  assert.equal((await dispatchPetRequest(r, h1.adapters)).code, 'HOST_RECEIPT_INVALID');
  const h2 = host(r);
  h2.adapters.transport = async () => receipt(r, {externalEffects: true});
  assert.equal((await dispatchPetRequest(r, h2.adapters)).code, 'HOST_RECEIPT_INVALID');
});

test('cancellation during delayed host attestation withholds an otherwise valid receipt', async () => {
  const r = request(), h = host(r), controller = new AbortController();
  const originalVerifier = h.adapters.verifyHostReceipt;
  h.adapters.verifyHostReceipt = async args => {
    await new Promise(resolve => setTimeout(resolve, 25));
    return originalVerifier(args);
  };
  const pending = dispatchPetRequest(r, {...h.adapters, signal: controller.signal});
  await new Promise(resolve => setTimeout(resolve, 5));
  controller.abort();
  const result = await pending;
  assert.deepEqual(result, {ok: false, code: 'CANCELLED'});
});

test('source SHA must match the request, host grant and durable reservation', async () => {
  const r = request(), h1 = host(r);
  assert.equal((await dispatchPetRequest({...r, sourceSha: '5'.repeat(40)}, h1.adapters)).code, 'SOURCE_MISMATCH');
  assert.equal(h1.counters.dispatches, 0);

  const h2 = host(r);
  h2.adapters.verifyHostGrant = async () => grant(r, {sourceSha: '5'.repeat(40)});
  assert.equal((await dispatchPetRequest(r, h2.adapters)).code, 'HOST_POLICY_DENIED');
  assert.equal(h2.counters.dispatches, 0);

  const h3 = host(r);
  const originalReserve = h3.adapters.reserveReplay;
  let reservation;
  h3.adapters.reserveReplay = async query => {
    reservation = query;
    return originalReserve(query);
  };
  assert.equal((await dispatchPetRequest(r, h3.adapters)).ok, true);
  assert.equal(reservation.sourceSha, SOURCE);
  assert.equal(reservation.tenantId, r.tenantId);
  assert.equal(reservation.requestId, r.requestId);
});

test('recheck rejects source-scoped grant swapping before provider dispatch', async () => {
  const r = request(), h = host(r);
  h.adapters.verifyHostGrant = async () => {
    h.counters.calls++;
    return grant(r, h.counters.calls >= 2 ? {sourceSha: '5'.repeat(40)} : {});
  };
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'REVOKED_BEFORE_DISPATCH');
  assert.equal(h.counters.dispatches, 0);
});

test('every successful receipt fixture conforms to actual Ajv Draft 2020-12 schema', () => {
  const r = request();
  const model = receipt(r);
  const tool = receipt(r, {executionKind: 'tool', toolReceiptRef: 'tool.req.01'});
  delete tool.providerReceiptRef;
  const combined = receipt(r, {executionKind: 'model-and-tool', toolReceiptRef: 'tool.req.01'});
  const deterministic = receipt(r, {executionKind: 'none'});
  delete deterministic.providerReceiptRef;
  const denied = receipt(r, {status: 'denied', executionKind: 'none', hostAuthorization: false});
  for (const field of ['outputDigest', 'providerReceiptRef', 'hostAttestation']) delete denied[field];
  const failed = {...denied, status: 'failed'};
  for (const [name, row] of Object.entries({model, tool, combined, deterministic, denied, failed})) {
    assert.equal(ajvReceipt(row), true, name + ': ' + JSON.stringify(ajvReceipt.errors));
    assert.equal(validateReceiptShape(row), true, name);
  }
});

test('conditional receipt gaps reject before even a permissive host verifier is called', async () => {
  const mutators = {
    'missing execution kind': row => {delete row.executionKind;},
    'missing signed host claim': row => {delete row.hostAttestation;},
    'missing signature reference': row => {delete row.hostAttestation.signatureRef;},
    'wrong attestation issuer': row => {row.hostAttestation.issuer = 'pet-self-signed';},
    'unexpected attestation property': row => {row.hostAttestation.privateToken = 'LEAK';},
    'missing model request evidence': row => {delete row.providerReceiptRef;},
    'missing tool request evidence': row => {row.executionKind = 'tool'; delete row.providerReceiptRef;},
    'combined execution missing tool evidence': row => {row.executionKind = 'model-and-tool';},
    'completed without host authorization': row => {row.hostAuthorization = false;},
    'denied receipt claims model execution': row => {row.status = 'denied';},
  };
  for (const [name, mutate] of Object.entries(mutators)) {
    const r = request(), h = host(r), row = receipt(r);
    mutate(row);
    assert.equal(ajvReceipt(row), false, name + ' must fail schema');
    assert.equal(validateReceiptShape(row), false, name + ' must fail bridge');
    h.adapters.transport = async () => row;
    assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'HOST_RECEIPT_INVALID', name);
    assert.equal(h.counters.attestations, 0, name + ' reached untrusted verifier');
  }
});

test('schema-valid external tool effect still violates read-only bridge policy', async () => {
  const r = request(), h = host(r);
  const row = receipt(r, {executionKind: 'model-and-tool', toolReceiptRef: 'tool.req.01', externalEffects: true});
  assert.equal(ajvReceipt(row), true, JSON.stringify(ajvReceipt.errors));
  h.adapters.transport = async () => row;
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'HOST_RECEIPT_INVALID');
  assert.equal(h.counters.attestations, 0);
});

test('hashing tenant and request as a tuple avoids slash separator collisions', async () => {
  const a = request(), b = request(), keys = [], reservations = new Set();
  a.tenantId = 'tenant/a'; a.requestId = 'b';
  b.tenantId = 'tenant'; b.requestId = 'a/b';
  assert.equal(a.tenantId + '/' + a.requestId, b.tenantId + '/' + b.requestId,
    'old separator encoding would collide');
  const reserveReplay = async ({tenantId, requestId}) => {
    const tuple = JSON.stringify([tenantId, requestId]);
    if (reservations.has(tuple)) return {reserved: false};
    reservations.add(tuple);
    return {reserved: true};
  };
  for (const r of [a, b]) {
    const h = host(r);
    h.adapters.reserveReplay = reserveReplay;
    h.adapters.transport = async ({idempotencyKey: key}) => {
      keys.push(key);
      return receipt(r);
    };
    assert.equal((await dispatchPetRequest(r, h.adapters)).ok, true);
  }
  assert.equal(reservations.size, 2);
  assert.equal(keys.length, 2);
  assert.match(keys[0], /^sha256:[a-f0-9]{64}$/);
  assert.match(keys[1], /^sha256:[a-f0-9]{64}$/);
  assert.notEqual(keys[0], keys[1]);
  assert.equal(keys[0], idempotencyKey(a));
  assert.equal(keys[1], idempotencyKey(b));
});

test('post-dispatch source-swapped recheck denies before host receipt attestation', async () => {
  const r = request(), h = host(r);
  h.adapters.verifyHostGrant = async () => {
    h.counters.calls++;
    return grant(r, h.counters.calls >= 3 ? {sourceSha: '5'.repeat(40)} : {});
  };
  assert.equal((await dispatchPetRequest(r, h.adapters)).code, 'REVOKED_AFTER_DISPATCH');
  assert.equal(h.counters.dispatches, 1);
  assert.equal(h.counters.attestations, 0);
});

test('grant revoked while waiting on detached receipt verifier is denied before return', async () => {
  const r = request(), h = host(r);
  const verify = h.adapters.verifyHostReceipt;
  h.adapters.verifyHostGrant = async () => {
    h.counters.calls++;
    return grant(r, h.counters.calls >= 4 ? {revoked: true} : {});
  };
  h.adapters.verifyHostReceipt = async args => {
    await new Promise(resolve => setTimeout(resolve, 5));
    return verify(args);
  };
  assert.deepEqual(await dispatchPetRequest(r, h.adapters),
    {ok: false, code: 'REVOKED_AFTER_DISPATCH'});
  assert.equal(h.counters.dispatches, 1);
  assert.equal(h.counters.attestations, 1);
  assert.ok(h.counters.calls >= 4);
});
