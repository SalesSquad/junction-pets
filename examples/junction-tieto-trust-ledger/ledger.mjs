/**
 * Tieto #351 reference concept, created during Junction 2026.
 * Pure-data gate: it DOES NOT run tests, authenticate receipts, or approve code.
 */
const SHA = /^[a-f0-9]{40}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const OUTCOMES = new Set(['pass', 'fail', 'not-run']);

function requireShape(value, fields, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).length !== fields.length ||
      fields.some(field => !Object.hasOwn(value, field))) {
    throw new TypeError(`Invalid ${label} shape`);
  }
}

function requiredString(value, label, max = 500) {
  if (typeof value !== 'string' || !value.trim() || value.length > max) {
    throw new TypeError(`Invalid ${label}`);
  }
}

function ensureUnique(values, label) {
  if (new Set(values).size !== values.length) throw new TypeError(`Duplicate ${label}`);
}

function ensureSha(value, label) {
  if (typeof value !== 'string' || !SHA.test(value)) throw new TypeError(`Invalid ${label}`);
}

/**
 * @param {object} record JSON-compatible, caller-supplied source/claims/receipts.
 * @returns {object} deterministic recommendation for a NAMED human reviewer.
 */
export function evaluateLedger(record) {
  requireShape(record, ['schemaVersion', 'sample', 'requirement', 'reviewer', 'claims', 'checks'], 'root');
  if (record.schemaVersion !== 1) throw new TypeError('Unsupported schema');
  const sample = record.sample;
  requireShape(sample, ['repository', 'issueUrl', 'baseSha', 'headSha', 'license'], 'sample');
  requiredString(sample.repository, 'repository', 200);
  requiredString(sample.issueUrl, 'issueUrl', 500);
  if (!sample.issueUrl.startsWith('https://github.com/')) throw new TypeError('Invalid issue URL');
  requiredString(sample.license, 'license', 80);
  ensureSha(sample.baseSha, 'base SHA');
  ensureSha(sample.headSha, 'head SHA');
  if (sample.baseSha === sample.headSha) throw new TypeError('Same base and head');

  requireShape(record.requirement, ['id', 'summary'], 'requirement');
  requiredString(record.requirement.id, 'requirement ID', 80);
  requiredString(record.requirement.summary, 'requirement summary');
  requireShape(record.reviewer, ['name', 'decision'], 'reviewer');
  if (record.reviewer.name !== null) requiredString(record.reviewer.name, 'reviewer name', 150);
  if (!['pending', 'accept', 'reject'].includes(record.reviewer.decision)) throw new TypeError('Invalid human decision');
  if (!Array.isArray(record.claims) || !record.claims.length || record.claims.length > 20 ||
      !Array.isArray(record.checks) || record.checks.length > 40) throw new TypeError('Invalid claim/check count');

  for (const claim of record.claims) {
    requireShape(claim, ['id', 'requirementId', 'summary', 'paths', 'checkIds'], 'claim');
    requiredString(claim.id, 'claim ID', 80);
    requiredString(claim.requirementId, 'claim requirement ID', 80);
    requiredString(claim.summary, 'claim summary');
    if (!Array.isArray(claim.paths) || !claim.paths.length || claim.paths.length > 10 ||
        !Array.isArray(claim.checkIds) || claim.checkIds.length > 10) throw new TypeError('Invalid claim paths/checks');
    claim.paths.forEach(path => requiredString(path, 'review path', 300));
    claim.checkIds.forEach(id => requiredString(id, 'check ID', 80));
    ensureUnique(claim.checkIds, 'claim check IDs');
  }
  ensureUnique(record.claims.map(claim => claim.id), 'claim IDs');

  for (const check of record.checks) {
    requireShape(check, ['id', 'requirementId', 'baseSha', 'headSha', 'baseOutcome', 'headOutcome', 'evidenceClass', 'logSha256'], 'check');
    requiredString(check.id, 'check ID', 80);
    requiredString(check.requirementId, 'check requirement ID', 80);
    ensureSha(check.baseSha, 'check base SHA');
    ensureSha(check.headSha, 'check head SHA');
    if (!OUTCOMES.has(check.baseOutcome) || !OUTCOMES.has(check.headOutcome)) throw new TypeError('Invalid check outcome');
    if (!['synthetic', 'self-reported-run'].includes(check.evidenceClass)) throw new TypeError('Invalid evidence class');
    if (check.logSha256 !== null && (typeof check.logSha256 !== 'string' || !DIGEST.test(check.logSha256))) {
      throw new TypeError('Invalid log SHA-256');
    }
  }
  ensureUnique(record.checks.map(check => check.id), 'check IDs');

  const byCheck = new Map(record.checks.map(check => [check.id, check]));
  const claimResults = record.claims.map(claim => {
    const reasons = new Set();
    if (claim.requirementId !== record.requirement.id) reasons.add('WRONG_REQUIREMENT');
    if (!claim.checkIds.length) reasons.add('MISSING_CHECK');
    let hasReviewableReceipt = false;
    for (const checkId of claim.checkIds) {
      const check = byCheck.get(checkId);
      if (!check) { reasons.add('MISSING_CHECK'); continue; }
      if (check.requirementId !== record.requirement.id) reasons.add('WRONG_REQUIREMENT');
      if (check.baseSha !== sample.baseSha || check.headSha !== sample.headSha) reasons.add('STALE_SOURCE_SHA');
      if (check.baseOutcome !== 'fail' || check.headOutcome !== 'pass') reasons.add('NON_DISCRIMINATING_CHECK');
      if (check.evidenceClass === 'synthetic') reasons.add('SYNTHETIC_ONLY');
      else if (!check.logSha256) reasons.add('MISSING_LOG_DIGEST');
      else hasReviewableReceipt = true;
    }
    const refusalReasons = [...reasons].sort();
    return {
      id: claim.id,
      requirementId: claim.requirementId,
      status: refusalReasons.length ? 'REFUSED_EVIDENCE' : hasReviewableReceipt ? 'READY_FOR_HUMAN' : 'REFUSED_EVIDENCE',
      refusalReasons,
      humanReviewPaths: [...claim.paths],
    };
  });

  const allReviewable = claimResults.every(item => item.status === 'READY_FOR_HUMAN');
  let humanDecision = 'AWAITING_HUMAN';
  if (record.reviewer.decision === 'reject') humanDecision = record.reviewer.name ? 'HUMAN_REJECTION_RECORDED' : 'REVIEWER_ID_MISSING';
  if (record.reviewer.decision === 'accept') {
    humanDecision = !record.reviewer.name ? 'REVIEWER_ID_MISSING' :
      !allReviewable ? 'UNSUPPORTED_ACCEPTANCE_REFUSED' : 'HUMAN_ACCEPTANCE_RECORDED_UNAUTHENTICATED';
  }
  const refused = claimResults.filter(item => item.refusalReasons.length);
  return {
    schemaVersion: 1,
    source: {repository: sample.repository, baseSha: sample.baseSha, headSha: sample.headSha},
    requirementId: record.requirement.id,
    claims: claimResults,
    refusals: refused.map(item => ({claimId: item.id, reasons: item.refusalReasons})),
    humanReviewSet: claimResults.map(item => ({claimId: item.id, paths: item.humanReviewPaths})),
    reviewer: {declaredName: record.reviewer.name, declaredDecision: record.reviewer.decision, outcome: humanDecision},
    metrics: {claims: claimResults.length, reviewable: claimResults.length - refused.length, refused: refused.length},
    boundaries: {
      checksExecutedHere: false, logContentsVerified: false, receiptSignaturesVerified: false,
      reviewerIdentityVerified: false, codeChangeApproved: false,
      explanation: 'Caller-supplied check outcomes and hashes are untrusted until a human independently validates the referenced runs.'
    }
  };
}
