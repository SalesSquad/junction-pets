/**
 * Read-only Fleet Control projection for the Junction 34-pet fleet.
 *
 * Trust boundary: adapter methods are injected by a privileged server-side host.
 * No serialized JSON flag, plugin registration receipt or editable manifest may
 * promote its own readiness. The module never creates environments or grants.
 */
import {EXPECTED_COMPANIES} from '../../lib/catalog.mjs';

export const REPOSITORY = 'SalesSquad/junction-pets';
export const EXPECTED_PETS = 34;
const SHA = /^[a-f0-9]{40}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const SLUG = /^junction-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const TENANT_ID = /^[A-Za-z0-9][A-Za-z0-9_:./-]{0,127}$/;
const ENV_ID = /^[A-Za-z0-9_.:-]{5,160}$/;
const UTC = /^\d{4}-\d{2}-\d{2}T.*Z$/;

const isRecord = x => x !== null && typeof x === 'object' && !Array.isArray(x);
const exactSha = x => typeof x === 'string' && SHA.test(x);
const validUtc = x => typeof x === 'string' && UTC.test(x) && Number.isFinite(Date.parse(x));
const safeString = (x, max = 160) => typeof x === 'string' && x.length > 0 && x.length <= max && !/[\u0000-\u001f\u007f]/.test(x);
function safeEvidenceUrl(x) {
  if (typeof x !== 'string') return null;
  try {
    const url = new URL(x);
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.port || x.length > 600) return null;
    return url.href;
  } catch { return null; }
}
const status = (state, reason, details = {}) => ({state, reason, ...details});
const validTimeBound = (time, now, maxAgeMs) => validUtc(time) && Date.parse(time) <= now.valueOf() + 60000 &&
  Date.parse(time) >= now.valueOf() - maxAgeMs;

export function validateFleet(manifests, sourceCommit) {
  if (!exactSha(sourceCommit)) throw new Error('Exact canonical GitHub source commit required');
  if (!Array.isArray(manifests) || manifests.length !== EXPECTED_PETS) throw new Error('Expected 34 environment manifests');
  const names = new Set(), ids = new Set();
  for (const item of manifests) {
    if (!isRecord(item) || !SLUG.test(item.petSlug) || item.provider !== 'codex-cloud' ||
        item.repository !== REPOSITORY || item.desiredName !== item.petSlug ||
        item.agentId !== 'junction-dev-' + item.petSlug.slice('junction-'.length) ||
        !isRecord(item.provisioning)) throw new Error('Invalid pet environment manifest');
    if (names.has(item.petSlug) || ids.has(item.agentId)) throw new Error('Duplicate pet environment');
    names.add(item.petSlug); ids.add(item.agentId);
    const p = item.provisioning;
    if (p.state === 'unprovisioned' && (p.environmentId !== null || p.verifiedAt !== null || p.evidenceUrl !== null)) {
      throw new Error('Unprovisioned environment has a claimed ID');
    }
    if (p.environmentId !== null && p.environmentId !== undefined && !ENV_ID.test(p.environmentId)) {
      throw new Error('Malformed environment ID');
    }
  }
  for (const company of EXPECTED_COMPANIES) {
    if (!names.has('junction-' + company)) throw new Error('Missing canonical company environment: ' + company);
  }
  return true;
}

/**
 * Only the host provider adapter may authenticate an environment receipt.
 * The editable manifest state "ready" is never sufficient.
 */
async function providerStatus(manifest, sourceCommit, providerAdapter, now, maxAgeMs) {
  const recorded = manifest.provisioning;
  const id = recorded.environmentId;
  if (recorded.state === 'unprovisioned') return status('unprovisioned', 'No published environment ID recorded');
  if (!id || !ENV_ID.test(id)) return status('unverified', 'Missing immutable provider environment ID');
  if (!providerAdapter || typeof providerAdapter.readEnvironment !== 'function' ||
      typeof providerAdapter.verifyReceipt !== 'function') {
    return status('unverified', 'No authenticated provider reader/verifier');
  }
  try {
    const observed = await providerAdapter.readEnvironment({environmentId: id, petSlug: manifest.petSlug, repository: REPOSITORY});
    const receipt = observed?.receipt;
    const exact = observed?.environmentId === id && observed?.petSlug === manifest.petSlug &&
      observed?.repository === REPOSITORY && observed?.provider === 'codex-cloud' &&
      observed?.published === true && observed?.state === 'ready' &&
      isRecord(receipt) && receipt.environmentId === id &&
      receipt.petSlug === manifest.petSlug && receipt.repository === REPOSITORY &&
      receipt.provider === 'codex-cloud' && receipt.sourceCommit === sourceCommit &&
      exactSha(receipt.sourceCommit) && validTimeBound(receipt.issuedAt, now, maxAgeMs) &&
      safeString(receipt.receiptId) && safeEvidenceUrl(receipt.evidenceUrl);
    if (!exact) return status('unverified', 'Provider observation or source-bound receipt mismatch');
    const trusted = await providerAdapter.verifyReceipt({receipt, observation: observed, sourceCommit});
    if (trusted !== true) return status('unverified', 'Provider receipt failed independent verification');
    return status('ready', 'Authenticated provider observation and exact-source receipt', {
      environmentId: id,
      evidenceUrl: safeEvidenceUrl(receipt.evidenceUrl),
      sourceCommit,
      verifiedAt: receipt.issuedAt
    });
  } catch {
    return status('blocked', 'Provider reader failed; retry independently');
  }
}

/**
 * Offline evidence is never treated as signed CI/model verification.
 * The authoritative server must inject its own verifier for each receipt kind.
 */
async function evidenceStatus(receipt, petSlug, sourceCommit, verifier, kind) {
  if (!receipt) return status('missing', 'No ' + kind + ' receipt');
  if (!isRecord(receipt) || receipt.petSlug !== petSlug ||
      !exactSha(receipt.sourceCommit) || receipt.sourceCommit !== sourceCommit) {
    return status('stale', kind + ' evidence does not bind current source SHA');
  }
  if (!DIGEST.test(receipt.artifactSha256 || '') || !safeString(receipt.receiptId) ||
      !safeEvidenceUrl(receipt.evidenceUrl) || !['pass', 'fail'].includes(receipt.result)) {
    return status('unverified', 'Malformed ' + kind + ' receipt');
  }
  if (typeof verifier !== 'function') return status('unverified', 'No independent ' + kind + ' verifier');
  try {
    if (await verifier(receipt, {petSlug, sourceCommit, kind}) !== true) {
      return status('unverified', kind + ' receipt failed independent verification');
    }
    return status(receipt.result === 'pass' ? 'verified-pass' : 'verified-fail',
      'Exact-source ' + kind + ' receipt independently verified', {
        receiptId: receipt.receiptId,
        evidenceUrl: safeEvidenceUrl(receipt.evidenceUrl),
        sourceCommit
      });
  } catch {
    return status('blocked', kind + ' verifier unavailable');
  }
}

/**
 * A Chibi host verifier is required; an "active":true field alone is never a grant.
 * An independently confirmed revocation must block runtime readiness.
 */
async function grantStatus(manifest, grantAdapter, sourceCommit, authenticatedTenantId, now) {
  // This tenant comes from the trusted host session, never from a pet manifest
  // or a grant readback. Without it no entitlement can become host-verified.
  if (typeof authenticatedTenantId !== 'string' || !TENANT_ID.test(authenticatedTenantId)) {
    return status('unverified', 'No authenticated Chibi tenant scope');
  }
  if (!grantAdapter || typeof grantAdapter.readGrant !== 'function' ||
      typeof grantAdapter.verifyReceipt !== 'function') return status('unverified', 'No Chibi grant verifier');
  try {
    const expected = {tenantId: authenticatedTenantId, petSlug: manifest.petSlug, sourceCommit};
    const observed = await grantAdapter.readGrant(expected);
    // A permissive verifier must never turn an unrelated tenant/source/pet
    // into a valid entitlement or even a verified revocation.
    if (!isRecord(observed) || !['active', 'revoked'].includes(observed.state) ||
        observed.tenantId !== expected.tenantId || observed.petSlug !== expected.petSlug ||
        observed.sourceCommit !== expected.sourceCommit || !safeString(observed.receiptId)) {
      return status('unverified', 'Chibi grant is missing exact tenant/pet/source binding');
    }
    if (observed.state === 'active' &&
        (!validUtc(observed.expiresAt) || Date.parse(observed.expiresAt) <= now.valueOf())) {
      return status('unverified', 'Chibi active grant is missing or past its expiration');
    }
    const verified = await grantAdapter.verifyReceipt(observed, expected);
    if (verified !== true) return status('unverified', 'Host grant receipt failed verification');
    return observed.state === 'revoked'
      ? status('revoked', 'Authenticated host grant revocation; execution denied')
      : status('host-verified', 'Authenticated tenant-scoped unexpired host grant');
  } catch {
    return status('blocked', 'Chibi grant reader unavailable; execution denied');
  }
}

/**
 * Result contains ONLY public-safe selected fields. Never spread provider,
 * grant or CI payloads into output, even if they contain secrets or tokens.
 */
export async function collectFleetStatus({
  manifests, sourceCommit, providerAdapter, ciReceipts = {}, evalReceipts = {},
  ciVerifier, evalVerifier, grantAdapter, authenticatedTenantId,
  now = new Date(), maxReceiptAgeMs = 86400000
}) {
  validateFleet(manifests, sourceCommit);
  if (!(now instanceof Date) || !Number.isFinite(now.valueOf()) ||
      !Number.isInteger(maxReceiptAgeMs) || maxReceiptAgeMs < 60000) throw new Error('Invalid clock/receipt age');
  const rows = await Promise.all(manifests.map(async manifest => {
    const slug = manifest.petSlug;
    const [cloud, ci, evaluation, grant] = await Promise.all([
      providerStatus(manifest, sourceCommit, providerAdapter, now, maxReceiptAgeMs),
      evidenceStatus(ciReceipts[slug], slug, sourceCommit, ciVerifier, 'ci'),
      evidenceStatus(evalReceipts[slug], slug, sourceCommit, evalVerifier, 'model-eval'),
      grantStatus(manifest, grantAdapter, sourceCommit, authenticatedTenantId, now)
    ]);
    // A development Cloud environment and grant observation are NOT execution permission.
    // Only the private Chibi PEP/PDP can authorize an individual runtime tool call.
    const runtimeAllowed = false;
    return {
      petSlug: slug,
      developerAgentId: manifest.agentId,
      desiredEnvironment: manifest.desiredName,
      cloud, ci, evaluation, grant,
      runtimeExecutionAllowed: runtimeAllowed,
      nextAction: cloud.state === 'unprovisioned' ? 'Provision and independently verify named Codex Cloud environment' :
        cloud.state !== 'ready' ? 'Recheck cloud environment, publication, source receipt and provider verifier' :
        grant.state !== 'host-verified' ? 'Check scoped host consent/grant; do not execute' :
        ci.state !== 'verified-pass' || evaluation.state !== 'verified-pass' ?
        'Run and independently verify exact-source CI and model evaluations' :
        'Ready for a separate authorized host execution check'
    };
  }));
  return {
    schemaVersion: 1,
    kind: 'junction-fleet-control/server-projection/v1',
    generatedAt: now.toISOString(),
    // This module validates SHA syntax only. The caller must separately prove
    // that the commit exists and was read from the authenticated GitHub source.
    source: {repository: REPOSITORY, commit: sourceCommit,
      verification: 'not-independently-verified',
      trustBoundary: 'caller-supplied-sha-format-only'},
    summary: {
      total: EXPECTED_PETS,
      cloudReady: rows.filter(row => row.cloud.state === 'ready').length,
      cloudUnprovisioned: rows.filter(row => row.cloud.state === 'unprovisioned').length,
      runtimeEligible: rows.filter(row => row.runtimeExecutionAllowed).length,
      ciVerifiedPasses: rows.filter(row => row.ci.state === 'verified-pass').length,
      evalVerifiedPasses: rows.filter(row => row.evaluation.state === 'verified-pass').length
    },
    pets: rows
  };
}
