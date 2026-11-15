// Only the retained public run-003 receipt is supported. This is an allowlist,
// not a signature, source checkout verification or truth/identity attestation.
export const SOURCE = Object.freeze({
  commit: '2e8d16686eecc47d0bdea104b541b1af88691739',
  path: 'tools/earned-trust/verification/evidence/run-003/differential.json',
  digest: 'cb9164598c280eafdbc677c8ad68030a1579b6a0d489add6faab5d06f1052e8e',
  caseId: 'MP2283-metadata-generic-struct-resolver',
  base: '32258fdbee4bcd653c79f51b4376b5103c6f4d27',
  head: '9df83c38409c8bfad0517aebffe48211eda4a5b4',
});
export const MAX_BYTES = 256 * 1024;
export const REQUIREMENT = 'MP-2283: A consuming assembly receives a generated resolver for a generic value type defined in an external assembly. Require no analyzer/generator crash and the expected consumer resolver; build success alone is insufficient.';
export const LIMITS = Object.freeze([
  'OFFLINE REPLAY of a declared local receipt. No checks are executed here.',
  'SDK 9.0.100 / Roslyn 4.12 / net8.0 / Linux compiler compatibility experiment only.',
  'Original SDK 8.0.402 was not executed; original Windows/.NET 10 environment is unqualified.',
  'One frozen reproduction; no serialization round trip, full upstream regression or other issue qualification.',
  'Artifact hashes are reported fields; referenced logs, harness and source trees are not independently verified here.',
  'A matching import hash identifies retained bytes only; no source, runner, signature or human identity is authenticated.',
  'No real engineer acceptance, measured review-time savings, production, GitHub acceptance or release is established.',
]);
const accepted = new WeakSet();
const fail = message => { throw new Error(message); };
export async function importReceipt(bytes) {
  if (!(bytes instanceof Uint8Array) || !bytes.length || bytes.length > MAX_BYTES)
    fail('Choose a non-empty JSON file no larger than 256 KiB.');
  // Own a snapshot before the asynchronous hash; caller mutation cannot change it.
  const snapshot = bytes.slice();
  let raw, value;
  try {
    raw = new TextDecoder('utf-8', {fatal: true}).decode(snapshot);
    value = JSON.parse(raw);
  } catch { fail('Malformed UTF-8 or JSON. Choose the original differential.json.'); }
  if (!globalThis.crypto?.subtle) fail('SHA256 unavailable. Open the desk on localhost in a modern browser.');
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', snapshot)), b => b.toString(16).padStart(2, '0')).join('');
  if (digest !== SOURCE.digest) fail('Unsupported or altered input. Only exact run-003 differential.json bytes are accepted; packet.json is not supported.');
  const freeze = object => { if (object && typeof object === 'object') { Object.values(object).forEach(freeze); Object.freeze(object); } return object; };
  const model = freeze({digest, raw, value, status: 'REVIEW REQUIRED / NOT VERIFIED'});
  accepted.add(model);
  return model;
}
export function gates(model) {
  if (!accepted.has(model)) fail('Import the supported receipt first.');
  const rows = [];
  for (const revision of model.value.revisions) {
    rows.push([`${revision.role}: build exitCode`, revision.build.exitCode === 0 ? 'PASS' : 'FAIL', String(revision.build.exitCode)]);
    rows.push([`${revision.role}: frozen probe`, revision.status.toUpperCase(), `exit ${revision.exitCode}; ${JSON.stringify(revision.tests)}`]);
    rows.push([`${revision.role}: consumer resolver`, revision.generatedResolver.present ? 'PASS' : 'FAIL', JSON.stringify(revision.generatedResolver)]);
    rows.push([`${revision.role}: diagnostics`, revision.diagnostics.length ? 'FAIL' : 'PASS', revision.diagnostics.map(d => `${d.id}: ${d.severity}`).join(', ') || 'No diagnostics reported']);
  }
  for (const name of ['libraryCompiled', 'analyzerDidNotCrash', 'generatorDidNotCrash', 'noBlockingDiagnostics', 'generatedCodeCompiles', 'consumerResolverGenerated']) {
    rows.push([`Raw assertion: ${name}`, 'UNKNOWN', 'Per-revision observation assertions are not embedded in differential.json; inspect the referenced artifacts.']);
  }
  rows.push(
    ['Original SDK / compiler environment', 'UNKNOWN', 'originalSdkExecuted: false'],
    ['Source, log and harness identity', 'UNKNOWN', 'Referenced digests are not verified against local artifacts.'],
    ['Runner / reviewer authentication', 'UNKNOWN', 'signedRunner: false; freeform reviewer name only']);
  return rows;
}
function authored(value, label, max) {
  if (typeof value !== 'string') fail(`${label} is required.`);
  const text = value.trim();
  if (!text || text.length > max || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f<>\u202a-\u202e\u2066-\u2069]/u.test(text))
    fail(`${label} must be plain text, 1–${max} characters, without markup or control characters.`);
  return text;
}
export function declareDecision(model, input) {
  if (!accepted.has(model)) fail('Import the supported receipt first.');
  if (!['request-evidence', 'refuse', 'conditional-demonstration-approval'].includes(input?.decision)) fail('Choose an explicit decision.');
  if (input.acknowledged !== true) fail('Acknowledge the evidence and authentication limits.');
  return {
    schemaVersion: 1, type: 'unauthenticated-local-demo-review',
    declaredAt: new Date().toISOString(), timestampMeaning: 'Local device clock; unauthenticated.',
    evidenceStatus: model.status, sourceCommit: SOURCE.commit, caseId: SOURCE.caseId,
    requirement: REQUIREMENT, repository: model.value.repository,
    import: {expectedSourceFilename: SOURCE.path, sha256: model.digest, hashMeaning: 'Exact imported bytes only; no identity or source authenticity claim.'},
    reviewerDeclaration: {name: authored(input.name, 'Reviewer name', 120), decision: input.decision,
      rationale: authored(input.rationale, 'Rationale', 2000),
      scope: 'DEMO ONLY / UNAUTHENTICATED. Not GitHub acceptance, merge permission or release approval.',
      acknowledgedLimitations: true},
    gates: gates(model), limitations: [...LIMITS],
    counterexample: 'Green build ≠ resolver evidence: base build exits 0, base probe fails and consumer resolver is absent.',
    authentication: {reviewerAuthenticated: false, signed: false, sourceIdentityVerified: false},
  };
}
export function serializeDeclaration(record) {
  // Safe even if opened by a consumer that incorrectly embeds JSON in HTML.
  return JSON.stringify(record, null, 2).replace(/[<>&\u2028\u2029]/gu, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`) + '\n';
}
