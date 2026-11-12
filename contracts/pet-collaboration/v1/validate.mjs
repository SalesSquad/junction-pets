// PetCollaborationRequest v1 — reference shape and authorization-adapter guard.
// This module is NOT a credential verifier or a substitute for Chibi Rust/Cedar.
const ID = /^[A-Za-z0-9][A-Za-z0-9_:./-]{0,127}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const SHA = /^[a-f0-9]{40}$/;
const EFFECTS = new Set(['read', 'proposal', 'write']);
const DATA_CLASSES = new Set(['synthetic', 'public', 'tenant-private']);
const REQUEST_KEYS = new Set([
  'schemaVersion', 'kind', 'requestId', 'conversationId', 'parentRequestId',
  'tenantId', 'actorPetId', 'recipientPetId', 'capabilityId', 'sourceSha', 'authorityRef',
  'requestedEffect', 'createdAt', 'expiresAt', 'depth', 'context', 'budget',
]);
const CONTEXT_KEYS = new Set(['ref', 'digest', 'dataClass']);
const BUDGET_KEYS = new Set(['maxTokens', 'maxDepth']);

const isObject = (value) =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const validTime = (value) => {
  if (typeof value !== 'string' ||
      !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(value)) return false;
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return false;
  const canonical = value.replace(/(?:\.(\d{1,3}))?Z$/, (_, fraction) =>
    '.' + (fraction ?? '').padEnd(3, '0') + 'Z');
  return new Date(parsed).toISOString() === canonical;
};
const validInteger = (value, min, max) =>
  Number.isInteger(value) && value >= min && value <= max;
const noExtraKeys = (obj, keys) => Object.keys(obj).every((key) => keys.has(key));
const deny = (code) => Object.freeze({ ok: false, code });

/**
 * Shape checking for portable fixtures, NOT authorization.
 * Use a full Draft 2020-12 JSON Schema validator in other runtimes.
 * No untrusted request field may serve as proof of an entitlement.
 */
export function validateRequestShape(request) {
  if (!isObject(request) || !noExtraKeys(request, REQUEST_KEYS)) return false;
  if (request.schemaVersion !== 'pet-collaboration.v1' || request.kind !== 'request') return false;
  for (const key of [
    'requestId', 'conversationId', 'tenantId', 'actorPetId', 'recipientPetId',
    'capabilityId', 'authorityRef',
  ]) {
    if (typeof request[key] !== 'string' || !ID.test(request[key])) return false;
  }
  if (typeof request.sourceSha !== 'string' || !SHA.test(request.sourceSha)) return false;
  if (request.parentRequestId !== undefined &&
      (typeof request.parentRequestId !== 'string' || !ID.test(request.parentRequestId))) return false;
  if (request.actorPetId === request.recipientPetId) return false;
  if (!EFFECTS.has(request.requestedEffect)) return false;
  if (!validTime(request.createdAt) || !validTime(request.expiresAt)) return false;
  if (!validInteger(request.depth, 0, 8)) return false;
  if ((request.depth === 0 && request.parentRequestId !== undefined) ||
      (request.depth > 0 && request.parentRequestId === undefined)) return false;
  if (!isObject(request.context) || !noExtraKeys(request.context, CONTEXT_KEYS)) return false;
  if (typeof request.context.ref !== 'string' || !ID.test(request.context.ref) ||
      typeof request.context.digest !== 'string' || !DIGEST.test(request.context.digest) ||
      !DATA_CLASSES.has(request.context.dataClass)) return false;
  if (!isObject(request.budget) || !noExtraKeys(request.budget, BUDGET_KEYS)) return false;
  if (!validInteger(request.budget.maxTokens, 1, 1_000_000) ||
      !validInteger(request.budget.maxDepth, 0, 8)) return false;
  return request.depth <= request.budget.maxDepth;
}

/**
 * Fail-closed boundary adapter. Both callbacks MUST be injected by trusted host
 * code; verifyHostGrant must validate issuer/signature, session identity,
 * current consent, revocation, effective entitlements and recipient adoption.
 * reserveReplay must atomically reserve (tenantId, requestId) in durable storage.
 *
 * This only authorizes admission to a queue. Recheck Rust/Cedar immediately
 * before each privileged provider/tool call and after any consent change.
 */
export async function authorizeAndReserve(request, {
  authenticatedTenantId,
  authenticatedActorPetId,
  verifyHostGrant,
  reserveReplay,
  nowMs = Date.now(),
  maxTtlMs = 300_000,
} = {}) {
  if (!validateRequestShape(request)) return deny('INVALID_SHAPE');
  if (!ID.test(authenticatedTenantId ?? '') || !ID.test(authenticatedActorPetId ?? '')) {
    return deny('NO_AUTHENTICATED_IDENTITY');
  }
  if (request.tenantId !== authenticatedTenantId ||
      request.actorPetId !== authenticatedActorPetId) return deny('IDENTITY_MISMATCH');
  if (!Number.isFinite(nowMs) || !Number.isFinite(maxTtlMs) || maxTtlMs <= 0) {
    return deny('INVALID_HOST_CLOCK');
  }
  const created = Date.parse(request.createdAt);
  const expires = Date.parse(request.expiresAt);
  if (created > nowMs + 30_000 || created > expires ||
      expires <= nowMs || expires - created > maxTtlMs) return deny('EXPIRED_OR_INVALID_TTL');
  if (typeof verifyHostGrant !== 'function' || typeof reserveReplay !== 'function') {
    return deny('HOST_INTEGRATION_UNAVAILABLE');
  }
  let decision;
  try {
    decision = await verifyHostGrant({
      authorityRef: request.authorityRef,
      tenantId: request.tenantId,
      actorPetId: request.actorPetId,
      recipientPetId: request.recipientPetId,
      capabilityId: request.capabilityId,
      sourceSha: request.sourceSha,
      requestId: request.requestId,
      conversationId: request.conversationId,
      parentRequestId: request.parentRequestId ?? null,
      depth: request.depth,
      requestedEffect: request.requestedEffect,
      contextRef: request.context.ref,
      contextDigest: request.context.digest,
      dataClass: request.context.dataClass,
      nowMs,
    });
  } catch {
    return deny('HOST_POLICY_UNAVAILABLE');
  }
  if (!isObject(decision) || decision.allowed !== true || decision.revoked !== false ||
      (typeof decision.decisionRef !== 'string' || !ID.test(decision.decisionRef)) ||
      decision.authorityRef !== request.authorityRef ||
      decision.tenantId !== request.tenantId ||
      decision.actorPetId !== request.actorPetId ||
      decision.recipientPetId !== request.recipientPetId ||
      decision.capabilityId !== request.capabilityId ||
      decision.sourceSha !== request.sourceSha ||
      decision.requestId !== request.requestId ||
      decision.conversationId !== request.conversationId ||
      decision.parentRequestId !== (request.parentRequestId ?? null) ||
      decision.depth !== request.depth ||
      decision.requestedEffect !== request.requestedEffect ||
      decision.contextRef !== request.context.ref ||
      decision.contextDigest !== request.context.digest ||
      !Array.isArray(decision.allowedDataClasses) ||
      !decision.allowedDataClasses.includes(request.context.dataClass) ||
      !validTime(decision.expiresAt) ||
      Date.parse(decision.expiresAt) <= nowMs ||
      Date.parse(decision.expiresAt) < expires ||
      !validInteger(decision.maxTokens, 1, 1_000_000) ||
      !validInteger(decision.maxDepth, 0, 8) ||
      request.budget.maxTokens > decision.maxTokens ||
      request.depth > decision.maxDepth ||
      request.budget.maxDepth > decision.maxDepth) return deny('HOST_POLICY_DENIED');

  try {
    const reservation = await reserveReplay({
      tenantId: request.tenantId,
      requestId: request.requestId,
      authorityRef: request.authorityRef,
      sourceSha: request.sourceSha,
      conversationId: request.conversationId,
      contextRef: request.context.ref,
      decisionRef: decision.decisionRef,
    });
    if (!isObject(reservation) || reservation.reserved !== true) return deny('REPLAY_OR_RESERVATION_FAILED');
  } catch {
    return deny('REPLAY_OR_RESERVATION_FAILED');
  }
  return Object.freeze({
    ok: true,
    code: 'AUTHORIZED_AND_RESERVED',
    requestId: request.requestId,
    decisionRef: decision.decisionRef,
  });
}
