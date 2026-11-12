import {createHash} from 'node:crypto';
import {authorizeAndReserve, validateRequestShape} from '../../contracts/pet-collaboration/v1/validate.mjs';

const ID = /^[A-Za-z0-9][A-Za-z0-9_:./-]{0,127}$/;
const SHA = /^[a-f0-9]{40}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const RECEIPT_KEYS = new Set([
  'schemaVersion', 'kind', 'requestId', 'tenantId', 'actorPetId',
  'recipientPetId', 'decisionRef', 'status', 'sourceSha', 'completedAt',
  'outputDigest', 'providerReceiptRef', 'toolReceiptRef',
  'hostAuthorization', 'externalEffects',
]);
const STATUSES = new Set(['completed', 'denied', 'failed', 'pending-approval']);
const denied = code => Object.freeze({ok: false, code});

function validTime(value) {
  if (typeof value !== 'string' ||
      !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(value)) return false;
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return false;
  const canonical = value.replace(/(?:\.(\d{1,3}))?Z$/, (_, fraction) =>
    '.' + (fraction ?? '').padEnd(3, '0') + 'Z');
  return new Date(parsed).toISOString() === canonical;
}

function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort()
      .map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  }
  return JSON.stringify(value);
}

export function receiptSha256(receipt) {
  return 'sha256:' + createHash('sha256').update(canonical(receipt), 'utf8').digest('hex');
}

/** JSON-schema-shape check, not authenticity, endorsement or authority. */
export function validateReceiptShape(receipt) {
  if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) return false;
  if (Object.keys(receipt).some(key => !RECEIPT_KEYS.has(key))) return false;
  if (receipt.schemaVersion !== 'pet-collaboration.v1' || receipt.kind !== 'receipt') return false;
  if (!['requestId', 'tenantId', 'actorPetId', 'recipientPetId', 'decisionRef']
    .every(key => typeof receipt[key] === 'string' && ID.test(receipt[key]))) return false;
  if (!STATUSES.has(receipt.status) || !SHA.test(receipt.sourceSha ?? '')) return false;
  if (!validTime(receipt.completedAt)) return false;
  if (typeof receipt.hostAuthorization !== 'boolean' || typeof receipt.externalEffects !== 'boolean') return false;
  if (receipt.outputDigest !== undefined && !DIGEST.test(receipt.outputDigest)) return false;
  if (receipt.providerReceiptRef !== undefined && !ID.test(receipt.providerReceiptRef)) return false;
  if (receipt.toolReceiptRef !== undefined && !ID.test(receipt.toolReceiptRef)) return false;
  if (receipt.status === 'completed' && (!receipt.hostAuthorization || !DIGEST.test(receipt.outputDigest ?? ''))) return false;
  return true;
}

function grantQuery(request, nowMs) {
  return {
    authorityRef: request.authorityRef, tenantId: request.tenantId,
    actorPetId: request.actorPetId, recipientPetId: request.recipientPetId,
    capabilityId: request.capabilityId, sourceSha: request.sourceSha,
    requestId: request.requestId, conversationId: request.conversationId,
    parentRequestId: request.parentRequestId ?? null, depth: request.depth,
    requestedEffect: request.requestedEffect,
    contextRef: request.context.ref, contextDigest: request.context.digest,
    dataClass: request.context.dataClass, nowMs,
  };
}

/**
 * The PRIVATE Chibi Rust/Cedar host must implement verifyHostGrant. We verify
 * the returned claim's complete binding before dispatch and once more after it.
 */
async function hostStillAllows(request, verifyHostGrant, nowMs, expectedDecisionRef) {
  try {
    const decision = await verifyHostGrant(grantQuery(request, nowMs));
    return decision?.allowed === true && decision.revoked === false &&
      decision.decisionRef === expectedDecisionRef &&
      decision.authorityRef === request.authorityRef &&
      decision.tenantId === request.tenantId &&
      decision.actorPetId === request.actorPetId &&
      decision.recipientPetId === request.recipientPetId &&
      decision.capabilityId === request.capabilityId &&
      decision.sourceSha === request.sourceSha &&
      decision.requestId === request.requestId &&
      decision.conversationId === request.conversationId &&
      decision.parentRequestId === (request.parentRequestId ?? null) &&
      decision.depth === request.depth &&
      decision.requestedEffect === request.requestedEffect &&
      decision.contextRef === request.context.ref &&
      decision.contextDigest === request.context.digest &&
      Array.isArray(decision.allowedDataClasses) &&
      decision.allowedDataClasses.includes(request.context.dataClass) &&
      validTime(decision.expiresAt) && Date.parse(decision.expiresAt) > nowMs &&
      Number.isInteger(decision.maxTokens) &&
      decision.maxTokens >= request.budget.maxTokens &&
      Number.isInteger(decision.maxDepth) &&
      decision.maxDepth >= request.budget.maxDepth;
  } catch {
    return false;
  }
}

function exactReceiptBinding(receipt, request, decisionRef, sourceSha) {
  return validateReceiptShape(receipt) &&
    receipt.requestId === request.requestId &&
    receipt.tenantId === request.tenantId &&
    receipt.actorPetId === request.actorPetId &&
    receipt.recipientPetId === request.recipientPetId &&
    receipt.decisionRef === decisionRef &&
    receipt.sourceSha === sourceSha &&
    !receipt.externalEffects;
}

/**
 * Portable read-only bridge across the public Junction -> PRIVATE Chibi host.
 *
 * All callbacks are host-injected, never issued by a pet or LLM:
 *   verifyHostGrant, reserveReplay, transport, verifyHostReceipt.
 * This module cannot independently verify private host cryptographic keys.
 */
export async function dispatchPetRequest(request, {
  authenticatedTenantId,
  authenticatedActorPetId,
  sourceSha,
  verifyHostGrant,
  reserveReplay,
  transport,
  verifyHostReceipt,
  signal,
  timeoutMs = 5000,
  nowMs = Date.now,
} = {}) {
  if (!validateRequestShape(request)) return denied('INVALID_REQUEST');
  if (!SHA.test(sourceSha ?? '')) return denied('UNBOUND_SOURCE');
  if (request.sourceSha !== sourceSha) return denied('SOURCE_MISMATCH');
  if (request.requestedEffect !== 'read') return denied('HUMAN_APPROVAL_REQUIRED');
  if (!ID.test(authenticatedTenantId ?? '') || !ID.test(authenticatedActorPetId ?? '')) return denied('NO_HOST_IDENTITY');
  if (request.tenantId !== authenticatedTenantId || request.actorPetId !== authenticatedActorPetId) {
    return denied('IDENTITY_MISMATCH');
  }
  if (typeof verifyHostGrant !== 'function' || typeof reserveReplay !== 'function' ||
      typeof transport !== 'function' || typeof verifyHostReceipt !== 'function') {
    return denied('HOST_INTEGRATION_UNAVAILABLE');
  }
  if (typeof nowMs !== 'function' || !Number.isSafeInteger(timeoutMs) ||
      timeoutMs < 1 || timeoutMs > 60_000) return denied('INVALID_BRIDGE_CONFIG');
  if (signal !== undefined && !(signal instanceof AbortSignal)) return denied('INVALID_ABORT_SIGNAL');
  if (signal?.aborted) return denied('CANCELLED');

  const admitted = await authorizeAndReserve(request, {
    authenticatedTenantId, authenticatedActorPetId,
    verifyHostGrant, reserveReplay, nowMs: nowMs(),
  });
  if (!admitted.ok) return denied(admitted.code);
  // A grant can be revoked between queue admission and the provider/tool call.
  if (!await hostStillAllows(request, verifyHostGrant, nowMs(), admitted.decisionRef)) return denied('REVOKED_BEFORE_DISPATCH');
  if (signal?.aborted) return denied('CANCELLED');

  const controller = new AbortController();
  const onCancel = () => controller.abort('cancelled');
  signal?.addEventListener('abort', onCancel, {once: true});
  const timeout = setTimeout(() => controller.abort('timeout'), timeoutMs);
  if (signal?.aborted) onCancel();
  const payload = {
    schemaVersion: request.schemaVersion,
    request, decisionRef: admitted.decisionRef,
    sourceSha, idempotencyKey: request.tenantId + '/' + request.requestId,
  };
  // Only a host-owned transport closure can add private auth out-of-band.
  const task = Promise.resolve().then(() => transport(payload, {signal: controller.signal}))
    .then(receipt => ({kind: 'receipt', receipt}), () => ({kind: 'transport-error'}));
  const interrupted = new Promise(resolve => {
    if (controller.signal.aborted) return resolve({kind: 'aborted'});
    controller.signal.addEventListener('abort', () => resolve({kind: 'aborted'}), {once: true});
  });
  const outcome = await Promise.race([task, interrupted]);
  clearTimeout(timeout);
  signal?.removeEventListener('abort', onCancel);
  if (outcome.kind === 'aborted') return denied(signal?.aborted ? 'CANCELLED' : 'TIMEOUT');
  if (outcome.kind !== 'receipt') return denied('HOST_TRANSPORT_FAILED');

  // A revoked grant hides a completed response, even if transport returned it.
  if (!await hostStillAllows(request, verifyHostGrant, nowMs(), admitted.decisionRef)) {
    return denied('REVOKED_AFTER_DISPATCH');
  }
  const receipt = outcome.receipt;
  if (!exactReceiptBinding(receipt, request, admitted.decisionRef, sourceSha)) {
    return denied('HOST_RECEIPT_INVALID');
  }
  const digest = receiptSha256(receipt);
  let attestation;
  try {
    attestation = await verifyHostReceipt({receipt, receiptSha256: digest, sourceSha, requestId: request.requestId});
  } catch {
    return denied('HOST_ATTESTATION_UNAVAILABLE');
  }
  // This is a required *injected* proof contract; actual crypto lives only in Chibi.
  if (attestation?.verified !== true || attestation.issuer !== 'chibi-host' ||
      attestation.receiptSha256 !== digest || attestation.sourceSha !== sourceSha ||
      attestation.requestId !== request.requestId ||
      !ID.test(attestation.verificationRef ?? '')) {
    return denied('HOST_ATTESTATION_INVALID');
  }
  if (signal?.aborted) return denied('CANCELLED');
  if (receipt.status !== 'completed') {
    return Object.freeze({ok: false, code: 'HOST_' + receipt.status.toUpperCase().replaceAll('-', '_'),
      receipt, hostVerificationRef: attestation.verificationRef});
  }
  return Object.freeze({
    ok: true, code: 'HOST_RECEIPT_ATTESTED', receipt,
    hostVerificationRef: attestation.verificationRef,
  });
}
