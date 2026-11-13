import {canonicalJson, sha256} from './artifact.mjs';
import {collectionDigest, packageDigest} from './catalog.mjs';

export const EVALUATION_SCHEMA_VERSION = 1;
const COMMIT = /^[a-f0-9]{40}$/;
const HASH = /^[a-f0-9]{64}$/;
const LABEL = /^[a-z0-9][a-z0-9._:-]{0,127}$/;
const MAX_RESPONSE = 100_000;

function invariant(condition, reason) {
  if (!condition) throw new Error(reason);
}

function requiredText(value, label, min = 1, max = 1000) {
  invariant(typeof value === 'string' && value.trim().length >= min && value.length <= max, `Invalid ${label}`);
  return value;
}

function timestamp(value, label) {
  requiredText(value, label, 10, 50);
  invariant(!Number.isNaN(Date.parse(value)) && /^\d{4}-\d{2}-\d{2}T/.test(value), `Invalid ${label}`);
}

function strictKeys(value, allowed, label) {
  invariant(value !== null && typeof value === 'object' && !Array.isArray(value), `Invalid ${label}`);
  const extras = Object.keys(value).filter(key => !allowed.includes(key));
  invariant(!extras.length, `Unexpected ${label} fields: ${extras.join(',')}`);
}

function copyRubric(criterion, where) {
  requiredText(criterion, where, 8, 500);
  return criterion;
}

/** A deterministic manifest of authored prompts, not an executed evaluation. */
export function buildCaseManifest(packs, {sourceCommit = null} = {}) {
  invariant(Array.isArray(packs) && packs.length > 0, 'No packages for evaluation');
  invariant(sourceCommit === null || COMMIT.test(sourceCommit), 'A source commit must be an exact 40-character SHA');
  const sortedPackages = [...packs].sort((a, b) => a.pet.artIndex - b.pet.artIndex);
  const ids = new Set();
  const cases = [];
  for (const pack of sortedPackages) {
    const {pet, evals, instructions} = pack;
    invariant(pet?.id === evals?.petId && evals?.schemaVersion === 1, 'Pet/eval identity mismatch');
    invariant(typeof instructions === 'string' && instructions.length >= 600, 'Missing developer-visible pet instructions');
    const packageSha256 = packageDigest(pack);
    for (const current of evals.cases) {
      invariant(LABEL.test(current.id) && Array.isArray(current.mustInclude) && Array.isArray(current.mustNotClaim), 'Invalid evaluation case');
      invariant(current.mustInclude.length > 0 && current.mustNotClaim.length > 0, 'Each case needs positive and safety criteria');
      const id = `${pet.id}/${current.id}`;
      invariant(!ids.has(id), `Duplicate evaluation case: ${id}`);
      ids.add(id);
      const entry = {
        id,
        petId: pet.id,
        petSlug: pet.company.slug,
        packageVersion: pet.version,
        packageSha256,
        instructionsSha256: sha256(instructions),
        prompt: requiredText(current.prompt, `prompt ${id}`, 10, 3000),
        mustInclude: current.mustInclude.map((criterion, i) => copyRubric(criterion, `${id}.mustInclude[${i}]`)),
        mustNotClaim: current.mustNotClaim.map((criterion, i) => copyRubric(criterion, `${id}.mustNotClaim[${i}]`)),
      };
      invariant(new Set(entry.mustInclude).size === entry.mustInclude.length, `Duplicate positive criterion: ${id}`);
      invariant(new Set(entry.mustNotClaim).size === entry.mustNotClaim.length, `Duplicate safety criterion: ${id}`);
      cases.push({...entry, caseSha256: sha256(canonicalJson(entry))});
    }
  }
  cases.sort((a, b) => a.id.localeCompare(b.id));
  const base = {
    schemaVersion: EVALUATION_SCHEMA_VERSION,
    source: {repository: 'SalesSquad/junction-pets', commit: sourceCommit, collectionSha256: collectionDigest(sortedPackages)},
    authoredCases: cases.length,
    executedCases: 0,
    evidenceLevel: 'definitions-only',
    cases,
  };
  return {...base, manifestSha256: sha256(canonicalJson(base))};
}

/** Compare against the actual local package bytes, not a manifest's self-reported hash. */
export function verifyCaseManifest(manifest, packs, {expectedSourceCommit = null} = {}) {
  invariant(manifest?.schemaVersion === 1, 'Invalid manifest schema');
  invariant(manifest?.source?.repository === 'SalesSquad/junction-pets', 'Wrong manifest repository');
  invariant(expectedSourceCommit === null || COMMIT.test(expectedSourceCommit), 'Invalid expected source commit');
  if (expectedSourceCommit) invariant(manifest.source.commit === expectedSourceCommit, 'Stale source commit');
  const rebuilt = buildCaseManifest(packs, {sourceCommit: manifest.source.commit});
  invariant(canonicalJson(rebuilt) === canonicalJson(manifest), 'Manifest no longer matches source definitions');
  return rebuilt;
}

function judgeList(items, rubrics, kind, caseId) {
  invariant(Array.isArray(items) && items.length === rubrics.length, `Missing ${kind} adjudications for ${caseId}`);
  return items.map((item, i) => {
    strictKeys(item, ['criterion', kind === 'mustInclude' ? 'met' : 'violated', 'evidence'], `adjudication ${kind}[${i}]`);
    invariant(item.criterion === rubrics[i], `Changed or reordered ${kind} criterion in ${caseId}`);
    const outcomeKey = kind === 'mustInclude' ? 'met' : 'violated';
    invariant(typeof item[outcomeKey] === 'boolean', `No boolean ${outcomeKey} for ${caseId}`);
    requiredText(item.evidence, `adjudication evidence for ${caseId}`, 12, 2000);
    return item;
  });
}

/**
 * Validate an independently supplied transcript and semantic review.
 * A structurally correct review is NOT authenticated provider or reviewer proof.
 */
export function assessSubmittedResponse(manifest, submission) {
  invariant(manifest?.schemaVersion === 1 && Array.isArray(manifest.cases), 'Invalid case manifest');
  strictKeys(submission, ['schemaVersion', 'caseId', 'caseSha256', 'sourceCommit', 'runId', 'execution', 'response', 'adjudication'], 'submission');
  invariant(submission.schemaVersion === 1, 'Invalid submission schema');
  const target = manifest.cases.find(item => item.id === submission.caseId);
  invariant(Boolean(target), 'Unknown evaluation case');
  invariant(HASH.test(submission.caseSha256) && submission.caseSha256 === target.caseSha256, 'Stale or forged case digest');
  invariant(manifest.source.commit !== null && submission.sourceCommit === manifest.source.commit, 'Unbound or stale source commit');
  invariant(LABEL.test(submission.runId), 'Invalid run ID');

  strictKeys(submission.execution, ['kind', 'provider', 'model', 'invocationId', 'completedAt'], 'execution');
  invariant(['synthetic', 'model-response'].includes(submission.execution.kind), 'Unsupported execution kind');
  requiredText(submission.execution.provider, 'provider', 1, 100);
  requiredText(submission.execution.model, 'model', 1, 100);
  requiredText(submission.execution.invocationId, 'invocation ID', 5, 160);
  timestamp(submission.execution.completedAt, 'execution time');
  if (submission.execution.kind === 'synthetic') invariant(submission.execution.provider === 'synthetic', 'Synthetic execution cannot claim provider work');
  else invariant(submission.execution.provider !== 'synthetic', 'Model response must identify a non-synthetic provider');

  strictKeys(submission.response, ['text', 'sha256'], 'response');
  requiredText(submission.response.text, 'response text', 1, MAX_RESPONSE);
  invariant(submission.response.sha256 === sha256(submission.response.text), 'Response SHA mismatch');
  const review = submission.adjudication;
  strictKeys(review, ['reviewerId', 'method', 'reviewedAt', 'responseSha256', 'mustInclude', 'mustNotClaim'], 'adjudication');
  requiredText(review.reviewerId, 'reviewer ID', 2, 140);
  invariant(['human', 'model'].includes(review.method), 'Unknown adjudication method');
  timestamp(review.reviewedAt, 'review time');
  invariant(Date.parse(review.reviewedAt) >= Date.parse(submission.execution.completedAt), 'Adjudication predates execution');
  invariant(review.responseSha256 === submission.response.sha256, 'Adjudication is not bound to response');
  const positives = judgeList(review.mustInclude, target.mustInclude, 'mustInclude', target.id);
  const negatives = judgeList(review.mustNotClaim, target.mustNotClaim, 'mustNotClaim', target.id);
  const unmet = positives.filter(item => !item.met).map(item => item.criterion);
  const violated = negatives.filter(item => item.violated).map(item => item.criterion);
  const passedReview = unmet.length === 0 && violated.length === 0;
  return {
    caseId: target.id,
    sourceCommit: submission.sourceCommit,
    caseSha256: target.caseSha256,
    responseSha256: submission.response.sha256,
    runId: submission.runId,
    assessment: passedReview ? 'candidate-pass' : 'fail',
    synthetic: submission.execution.kind === 'synthetic',
    reviewerMethod: review.method,
    evidenceLevel: 'supplied-unverified',
    providerInvocationVerified: false,
    qualified: false,
    unmetCriteria: unmet,
    violatedSafetyCriteria: violated,
  };
}

export function assessSubmissions(manifest, submissions) {
  invariant(Array.isArray(submissions), 'Submissions must be an array');
  const seen = new Set();
  const assessments = submissions.map(submission => {
    invariant(!seen.has(submission.caseId), 'Duplicate case response; use a separate run receipt');
    seen.add(submission.caseId);
    return assessSubmittedResponse(manifest, submission);
  });
  return {
    schemaVersion: 1,
    sourceCommit: manifest.source.commit,
    authoredCases: manifest.cases.length,
    submittedResponses: submissions.length,
    modelExecutionsVerified: 0,
    qualifiedPasses: 0,
    reviewCandidates: assessments.filter(row => row.assessment === 'candidate-pass').length,
    reviewFailures: assessments.filter(row => row.assessment === 'fail').length,
    evidenceLevel: 'supplied-unverified',
    assessments,
  };
}
