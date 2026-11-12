import {canonicalJson, sha256} from '../../lib/artifact.mjs';

const COMMIT = /^[a-f0-9]{40}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/;
const SAFE_METADATA = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/;
const SECRET_HINT = /^(?:sk-|bearer|token|secret|password|authorization|api[_-]?key)/i;
const KNOWN_PROVIDERS = new Set(['openai', 'anthropic', 'aiven', 'google', 'mistral', 'local', 'huggingface', 'azure-openai']);
const MAX_TEXT = 100_000;
const CASE_FIELDS = ['id', 'petId', 'petSlug', 'packageVersion', 'packageSha256',
  'instructionsSha256', 'prompt', 'mustInclude', 'mustNotClaim', 'caseSha256'];
const MANIFEST_FIELDS = ['schemaVersion', 'source', 'authoredCases', 'executedCases',
  'evidenceLevel', 'cases', 'manifestSha256'];

function requireValue(condition, reason) {
  if (!condition) throw new Error(reason);
}

function boundedText(value, label, limit = 500) {
  requireValue(typeof value === 'string' && value.trim().length > 0 && value.length <= limit, `Invalid ${label}`);
  return value;
}

function safeMetadata(value, label) {
  boundedText(value, label, 100);
  requireValue(SAFE_METADATA.test(value) && !SECRET_HINT.test(value), 'Unsafe ' + label);
  return value;
}

function asTimestamp(value, label) {
  boundedText(value, label, 64);
  const time = Date.parse(value);
  requireValue(Number.isFinite(time) && /^\d{4}-\d{2}-\d{2}T/.test(value), `Invalid ${label}`);
  return time;
}

function exactFields(value, fields, label) {
  requireValue(value && typeof value === 'object' && !Array.isArray(value), 'Invalid ' + label);
  requireValue(Object.keys(value).length === fields.length &&
    fields.every(key => Object.hasOwn(value, key)), 'Unexpected or missing ' + label + ' fields');
}

function checkManifest(manifest, sourceCommit) {
  requireValue(COMMIT.test(sourceCommit), 'Source commit must be a full Git SHA');
  exactFields(manifest, MANIFEST_FIELDS, 'manifest');
  requireValue(manifest.schemaVersion === 1 && Array.isArray(manifest.cases), 'Invalid evaluation manifest');
  exactFields(manifest.source, ['repository', 'commit', 'collectionSha256'], 'manifest source');
  requireValue(manifest.source.repository === 'SalesSquad/junction-pets', 'Wrong repository');
  requireValue(manifest.source.commit === sourceCommit, 'Stale or unbound source commit');
  requireValue(DIGEST.test(manifest.source.collectionSha256), 'Missing collection digest');
  requireValue(DIGEST.test(manifest.manifestSha256), 'Missing manifest digest');
  requireValue(manifest.executedCases === 0 && manifest.evidenceLevel === 'definitions-only',
    'Manifest must contain only authored definitions');
  requireValue(manifest.authoredCases === manifest.cases.length && manifest.cases.length > 0, 'Wrong authored case count');
  const cases = new Map();
  for (const current of manifest.cases) {
    exactFields(current, CASE_FIELDS, 'case');
    requireValue(typeof current.id === 'string' && !cases.has(current.id), 'Missing or duplicated case ID');
    requireValue(typeof current.petId === 'string' && current.petId.length > 0, 'Missing pet ID');
    boundedText(current.petSlug, 'pet slug', 200);
    boundedText(current.packageVersion, 'package version', 80);
    requireValue(DIGEST.test(current.packageSha256) &&
      DIGEST.test(current.instructionsSha256), 'Missing package/instructions digest');
    requireValue(DIGEST.test(current.caseSha256), 'Missing case digest');
    boundedText(current.prompt, 'case prompt', 3000);
    for (const label of ['mustInclude', 'mustNotClaim']) {
      requireValue(Array.isArray(current[label]) && current[label].length > 0 &&
        current[label].every(criterion => typeof criterion === 'string' && criterion.length >= 8),
      'Missing authored ' + label + ' rubric');
    }
    const {caseSha256, ...caseDefinition} = current;
    requireValue(sha256(canonicalJson(caseDefinition)) === caseSha256,
      'Case digest mismatch: ' + current.id);
    cases.set(current.id, current);
  }
  const {manifestSha256, ...manifestDefinition} = manifest;
  requireValue(sha256(canonicalJson(manifestDefinition)) === manifestSha256,
    'Manifest digest mismatch');
  return cases;
}

function checkPolicy(verdict, now, request) {
  if (verdict?.allowed !== true || verdict.revoked !== false ||
      verdict.issuer !== 'chibi-host') return null;
  if (!IDENTIFIER.test(verdict.receiptId ?? '')) return null;
  // A generic "allowed" reply is never a usable capability grant.
  // The host must echo the exact case, pet, request bytes, source, and action.
  for (const field of ['runId', 'caseId', 'petId', 'sourceCommit', 'requestSha256', 'action']) {
    if (verdict[field] !== request[field]) return null;
  }
  try {
    if (asTimestamp(verdict.expiresAt, 'policy expiration') <= now()) return null;
  } catch {
    return null;
  }
  return {receiptId: verdict.receiptId, expiresAt: verdict.expiresAt};
}

function selectCases(cases, caseIds, maxCases) {
  requireValue(Number.isSafeInteger(maxCases) && maxCases >= 1 && maxCases <= 204, 'maxCases must be 1..204');
  const ids = caseIds ?? [...cases.keys()].slice(0, maxCases);
  requireValue(Array.isArray(ids) && ids.length >= 1 && ids.length <= maxCases, 'Invalid case selection size');
  requireValue(new Set(ids).size === ids.length, 'Duplicate case in batch');
  return ids.map(id => {
    const current = cases.get(id);
    requireValue(Boolean(current), `Unknown case: ${id}`);
    return current;
  });
}

async function policyDecision(policy, request, now) {
  try {
    return checkPolicy(await policy(request), now, request);
  } catch {
    // Host timeout, malformed output or lost connection always fails closed.
    return null;
  }
}

/**
 * Source-bound execution envelope for an authorized provider adapter.
 *
 * IMPORTANT: this runner cannot authenticate the supplied provider response,
 * source verifier or policy callback. Every result remains UNQUALIFIED.
 * A separate host/provider attestation step must validate signatures.
 *
 * No transport => strictly offline preview, and no model invocation.
 */
export async function runBatch({
  manifest,
  sourceCommit,
  caseIds,
  maxCases = 24,
  runId = 'junction-eval',
  verifySource,
  authorize,
  reauthorize,
  invoke,
  now = () => Date.now(),
}) {
  const cases = checkManifest(manifest, sourceCommit);
  const selected = selectCases(cases, caseIds, maxCases);
  requireValue(IDENTIFIER.test(runId), 'Invalid run ID');
  requireValue(typeof now === 'function', 'Invalid clock');

  if (invoke === undefined) {
    return {
      schemaVersion: 1, mode: 'preview-only', sourceCommit,
      manifestSha256: manifest.manifestSha256, authoredCases: manifest.cases.length,
      selectedCases: selected.map(item => item.id), modelResponsesCaptured: 0,
      providerInvocationsVerified: 0, qualifiedPasses: 0, evidenceLevel: 'definitions-only',
      receipts: [],
    };
  }

  requireValue(
    typeof invoke === 'function' && typeof verifySource === 'function' &&
      typeof authorize === 'function' && typeof reauthorize === 'function',
    'Executing requires separate source verifier, host authorization, reauthorization and provider adapter',
  );
  // Exact source verification is a mandatory caller-provided gate.
  let provenance;
  try {
    provenance = await verifySource({
      repository: manifest.source.repository,
      sourceCommit, manifestSha256: manifest.manifestSha256,
    });
  } catch {
    throw new Error('Source provenance unavailable');
  }
  requireValue(
    provenance?.verified === true &&
      provenance.repository === manifest.source.repository &&
      provenance.sourceCommit === sourceCommit &&
      provenance.manifestSha256 === manifest.manifestSha256 &&
      IDENTIFIER.test(provenance.receiptId ?? ''),
    'Source provenance not verified by injected authority',
  );

  const receipts = [];
  for (const item of selected) {
    const request = {
      schemaVersion: 1, runId, caseId: item.id, caseSha256: item.caseSha256,
      petId: item.petId, prompt: item.prompt, sourceCommit, manifestSha256: manifest.manifestSha256,
    };
    const requestSha256 = sha256(canonicalJson(request));
    const policyRequest = {
      runId, caseId: item.id, petId: item.petId,
      sourceCommit, requestSha256, action: 'model.invoke',
    };
    const base = {
      schemaVersion: 1, runId, caseId: item.id, petId: item.petId,
      sourceCommit, caseSha256: item.caseSha256,
      manifestSha256: manifest.manifestSha256, requestSha256,
      sourceProvenanceReceiptId: provenance.receiptId, qualified: false,
      providerInvocationVerified: false,
      evidenceLevel: 'supplied-unverified',
    };

    const before = await policyDecision(authorize, policyRequest, now);
    if (!before) {
      receipts.push({...base, status: 'denied-before-invocation', providerInvoked: false});
      continue;
    }
    let provider;
    try {
      provider = await invoke({
        ...request,
        authorizationReceiptId: before.receiptId,
        requestSha256,
      });
    } catch {
      receipts.push({
        ...base, authorizationReceiptId: before.receiptId,
        status: 'provider-error', providerInvoked: true,
      });
      continue;
    }
    let invocationIdSha256, providerName, providerRefSha256, modelRefSha256, responseText, completedAt;
    try {
      requireValue(provider && typeof provider === 'object', 'Invalid provider response');
      const invocationId = safeMetadata(provider.invocationId, 'provider invocation ID');
      const rawProvider = safeMetadata(provider.provider, 'provider');
      requireValue(rawProvider.toLowerCase() !== 'synthetic', 'Synthetic transport cannot report model execution');
      const modelId = safeMetadata(provider.model, 'model version');
      // Keep exact identifiers in the private provider ledger; public receipts
      // store only hashes and a known provider class, never arbitrary metadata.
      invocationIdSha256 = sha256(invocationId);
      providerRefSha256 = sha256(rawProvider);
      providerName = KNOWN_PROVIDERS.has(rawProvider.toLowerCase()) ? rawProvider.toLowerCase() : 'other';
      modelRefSha256 = sha256(modelId);
      responseText = boundedText(provider.text, 'response text', MAX_TEXT);
      completedAt = boundedText(provider.completedAt, 'completion timestamp', 64);
      asTimestamp(completedAt, 'completion timestamp');
    } catch {
      receipts.push({
        ...base, authorizationReceiptId: before.receiptId,
        status: 'invalid-provider-response', providerInvoked: true,
      });
      continue;
    }
    const after = await policyDecision(reauthorize, policyRequest, now);

    receipts.push({
      ...base,
      authorizationReceiptId: before.receiptId,
      reauthorizationReceiptId: after?.receiptId ?? null,
      status: after ? 'response-captured-unverified' : 'revoked-after-invocation',
      providerInvoked: true,
      invocationIdSha256,
      provider: providerName,
      providerRefSha256,
      modelRefSha256,
      completedAt,
      // After revocation even a low-entropy output digest could reveal content.
      ...(after ? {
        responseSha256: sha256(responseText),
        responseBytes: Buffer.byteLength(responseText),
      } : {}),
      // The text and any private prompt/headers are deliberately NOT persisted.
    });
  }

  return {
    schemaVersion: 1, mode: 'provider-adapter', sourceCommit,
    manifestSha256: manifest.manifestSha256, authoredCases: manifest.cases.length,
    selectedCases: selected.map(item => item.id),
    modelResponsesCaptured: receipts.filter(item => item.status === 'response-captured-unverified').length,
    providerInvocationsVerified: 0, qualifiedPasses: 0,
    evidenceLevel: 'supplied-unverified', receipts,
  };
}
