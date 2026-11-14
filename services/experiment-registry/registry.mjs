import {link, mkdir, open, readFile, readdir, unlink} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {join} from 'node:path';
import {canonicalJson, safeHttps, sha256} from '../../lib/artifact.mjs';

const SHA = /^[a-f0-9]{64}$/;
const COMMIT = /^[a-f0-9]{40}$/;
const ID = /^[a-z][a-z0-9._-]{2,95}$/;
const KINDS = new Set(['model-evaluation', 'training', 'apple-check', 'gpu-probe', 'video-generation', 'synthetic-test', 'historical-result']);
const EVIDENCE = new Set(['synthetic-reproducible', 'local-receipt-unverified', 'source-reported']);

function fail(message) {throw new Error(message);}
function record(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${name} must be an object`);
  return value;
}
function keys(value, allowed, name) {
  const extras = Object.keys(value).filter(key => !allowed.includes(key));
  if (extras.length) fail(`${name} has unsupported fields: ${extras.join(',')}`);
}
function str(value, name, max = 180) {
  if (typeof value !== 'string' || !value || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) fail(`${name} must be a bounded single-line string`);
  return value;
}
function id(value, name) {if (typeof value !== 'string' || !ID.test(value)) fail(`${name} must be a safe identifier`);}
function digest(value, name) {if (typeof value !== 'string' || !SHA.test(value)) fail(`${name} must be SHA-256`);}
function date(value, name) {str(value, name, 40); if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(value) || !Number.isFinite(Date.parse(value))) fail(`${name} must be UTC ISO-8601`);}
function integer(value, name, minimum = 0) {if (!Number.isSafeInteger(value) || value < minimum) fail(`${name} must be integer >= ${minimum}`);}
function number(value, name) {if (typeof value !== 'number' || !Number.isFinite(value)) fail(`${name} must be finite number`);}
function safeRef(value, name) {
  str(value, name, 2048);
  if (!safeHttps(value) && !/^(?:docs|services|ops)\/[a-zA-Z0-9_./-]+$/.test(value)) fail(`${name} must be HTTPS or repo-relative`);
  if (value.split('/').includes('..')) fail(`${name} path traversal`);
  if (value.startsWith('https:') && new URL(value).search) fail(`${name} must not contain URL query secrets`);
}
function optHash(value, name) {if (value !== null) digest(value, name);}

export function validateRun(run) {
  record(run, 'run');
  keys(run, ['schemaVersion', 'runId', 'projectId', 'taskId', 'kind', 'capturedAt', 'status', 'source', 'evidence', 'dataset', 'evaluation', 'artifact', 'metrics', 'limitations', 'policySha256', 'planId'], 'run');
  if (run.schemaVersion !== 1) fail('unsupported run schemaVersion');
  for (const field of ['runId', 'projectId', 'taskId']) id(run[field], field);
  if (!KINDS.has(run.kind)) fail('unsupported run kind');
  date(run.capturedAt, 'capturedAt');
  if (!['succeeded', 'failed', 'incomplete'].includes(run.status)) fail('invalid run status');
  record(run.source, 'source');
  keys(run.source, ['repository', 'commit'], 'source');
  if (!/^[\w.-]+\/[\w.-]+$/.test(str(run.source.repository, 'source.repository', 120))) fail('invalid source.repository');
  if (!COMMIT.test(run.source.commit || '')) fail('source.commit requires full SHA-1 commit');
  record(run.evidence, 'evidence');
  keys(run.evidence, ['level', 'ref', 'receiptSha256'], 'evidence');
  if (!EVIDENCE.has(run.evidence.level)) fail('unsupported or unverified evidence level');
  safeRef(run.evidence.ref, 'evidence.ref');
  optHash(run.evidence.receiptSha256, 'evidence.receiptSha256');
  if (run.dataset !== null) {
    record(run.dataset, 'dataset');
    keys(run.dataset, ['sha256', 'sampleSetSha256', 'split', 'sampleCount', 'origin'], 'dataset');
    digest(run.dataset.sha256, 'dataset.sha256');
    digest(run.dataset.sampleSetSha256, 'dataset.sampleSetSha256');
    if (!['train', 'validation', 'holdout', 'shifted', 'hardware'].includes(run.dataset.split)) fail('invalid dataset split');
    integer(run.dataset.sampleCount, 'dataset.sampleCount', 1);
    if (!['synthetic', 'approved', 'unknown'].includes(run.dataset.origin)) fail('invalid dataset origin');
  }
  if (run.evaluation !== null) {
    record(run.evaluation, 'evaluation');
    keys(run.evaluation, ['kind', 'protocolSha256', 'independentHoldout'], 'evaluation');
    id(run.evaluation.kind, 'evaluation.kind');
    digest(run.evaluation.protocolSha256, 'evaluation.protocolSha256');
    if (typeof run.evaluation.independentHoldout !== 'boolean') fail('evaluation.independentHoldout must be boolean');
  }
  if (run.artifact !== null) {
    record(run.artifact, 'artifact');
    keys(run.artifact, ['type', 'sha256'], 'artifact');
    if (!['model-checkpoint', 'report', 'video', 'binary'].includes(run.artifact.type)) fail('invalid artifact type');
    digest(run.artifact.sha256, 'artifact.sha256');
  }
  if (!Array.isArray(run.metrics) || run.metrics.length > 100) fail('metrics must be bounded array');
  const seen = new Set();
  for (const metric of run.metrics) {
    record(metric, 'metric');
    keys(metric, ['id', 'value', 'unit', 'direction', 'samples'], 'metric');
    id(metric.id, 'metric.id');
    if (seen.has(metric.id)) fail('duplicate metric id');
    seen.add(metric.id);
    number(metric.value, `metric.${metric.id}`);
    if (!['rate', 'iou', 'milliseconds', 'seconds', 'bytes', 'count', 'mse', 'ratio'].includes(metric.unit)) fail('invalid metric unit');
    if (['rate', 'iou'].includes(metric.unit) && (metric.value < 0 || metric.value > 1)) fail('rate/IoU out of range');
    if (metric.value < 0) fail('metric values must be nonnegative');
    if (metric.unit === 'count' && !Number.isSafeInteger(metric.value)) fail('count metric must be a nonnegative safe integer');
    if (!['higher', 'lower'].includes(metric.direction)) fail('invalid metric direction');
    integer(metric.samples, 'metric.samples', 1);
  }
  if (!Array.isArray(run.limitations) || run.limitations.length > 20) fail('limitations must be bounded array');
  for (const limitation of run.limitations) str(limitation, 'limitation', 280);
  optHash(run.policySha256, 'policySha256');
  if (run.planId !== undefined && run.planId !== null) {
    id(run.planId, 'planId');
    if (!['training', 'model-evaluation'].includes(run.kind)) fail('only model runs can refer to a learning plan');
  }
  if (run.kind === 'model-evaluation' && (!run.dataset || !run.evaluation || !run.artifact || run.artifact.type !== 'model-checkpoint' || !run.metrics.length || !run.policySha256)) {
    fail('model-evaluation requires dataset, protocol, checkpoint, metrics and pinned policy');
  }
  if (run.kind === 'model-evaluation' && run.metrics.some(metric => metric.samples !== run.dataset.sampleCount)) fail('model-evaluation metrics must cover the exact sample set');
  return run;
}

async function immutable(root, collection, recordId, body) {
  id(recordId, 'recordId');
  const dir = join(root, collection);
  await mkdir(dir, {recursive: true});
  const filename = join(dir, `${recordId}.json`);
  const content = `${canonicalJson(body)}\n`;
  const temporary = join(dir, `.pending-${randomUUID()}`);
  const file = await open(temporary, 'wx', 0o600);
  try {await file.writeFile(content); await file.sync();} finally {await file.close();}
  try {
    try {await link(temporary, filename); return {created: true, sha256: sha256(content)};}
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const existing = JSON.parse(await readFile(filename, 'utf8'));
      if (canonicalJson(existing) !== canonicalJson(body)) fail(`immutable record conflict: ${collection}/${recordId}`);
      return {created: false, sha256: sha256(content)};
    }
  } finally {await unlink(temporary);}
}

export async function readRecord(root, collection, recordId) {
  id(recordId, 'recordId');
  return JSON.parse(await readFile(join(root, collection, `${recordId}.json`), 'utf8'));
}

export async function recordRun(root, run) {
  // Snapshot synchronously before any await: a caller must not mutate metadata
  // between validation and immutable persistence (including adding raw data).
  const input = structuredClone(run);
  validateRun(input);
  if (input.kind === 'model-evaluation') {
    // A model evaluation cannot backfill a policy after seeing its results.
    // Persist the frozen full policy before admitting the baseline itself.
    const frozen = validatePolicy(await readRecord(root, 'policies', `policy.${input.policySha256}`));
    if (sha256(canonicalJson(frozen)) !== input.policySha256 || frozen.taskId !== input.taskId || Date.parse(frozen.frozenAt) > Date.parse(input.capturedAt)) fail('model run requires matching preregistered frozen policy');
  }
  if (input.planId) {
    const plan = await readRecord(root, 'plans', input.planId);
    if (plan.taskId !== input.taskId || plan.status !== 'planned-not-dispatched' || Date.parse(input.capturedAt) < Date.parse(plan.createdAt)) fail('run cannot link to mismatched or future learning plan');
  }
  return immutable(root, 'runs', input.runId, input);
}

export async function recordFailure(root, failure) {
  failure = structuredClone(failure);
  record(failure, 'failure');
  keys(failure, ['schemaVersion', 'failureId', 'runId', 'caseSha256', 'failureCode', 'severity', 'observedAt'], 'failure');
  if (failure.schemaVersion !== 1) fail('invalid failure schemaVersion');
  id(failure.failureId, 'failureId'); id(failure.runId, 'runId'); id(failure.failureCode, 'failureCode');
  digest(failure.caseSha256, 'caseSha256'); date(failure.observedAt, 'observedAt');
  if (!['low', 'medium', 'high', 'critical'].includes(failure.severity)) fail('invalid failure severity');
  const source = validateRun(await readRecord(root, 'runs', failure.runId));
  const proposal = {
    schemaVersion: 1, proposalId: `case.${sha256(failure.failureId).slice(0,24)}`,
    failureId: failure.failureId, sourceRunId: source.runId, caseSha256: failure.caseSha256,
    failureCode: failure.failureCode, createdAt: failure.observedAt,
    status: 'quarantined-pending-review', trainAdmission: false, evaluationAdmission: false
  };
  // The derived proposal is deterministic, so retries are safe after an interrupted pair.
  const savedFailure = await immutable(root, 'failures', failure.failureId, failure);
  const savedProposal = await immutable(root, 'cases', proposal.proposalId, proposal);
  return {failure: savedFailure, case: savedProposal, proposalId: proposal.proposalId};
}

export async function reviewCase(root, review) {
  review = structuredClone(review);
  record(review, 'review');
  keys(review, ['schemaVersion', 'reviewId', 'proposalId', 'decision', 'reviewer', 'reviewedAt', 'evidenceSha256'], 'review');
  if (review.schemaVersion !== 1) fail('invalid review schemaVersion');
  id(review.reviewId, 'reviewId'); id(review.proposalId, 'proposalId'); id(review.reviewer, 'reviewer');
  date(review.reviewedAt, 'reviewedAt'); digest(review.evidenceSha256, 'evidenceSha256');
  if (!['approve-for-development', 'reject'].includes(review.decision)) fail('invalid review decision');
  await readRecord(root, 'cases', review.proposalId);
  return immutable(root, 'reviews', review.reviewId, review);
}

export async function planNext(root, plan) {
  plan = structuredClone(plan);
  record(plan, 'plan');
  keys(plan, ['schemaVersion', 'planId', 'proposalId', 'reviewId', 'taskId', 'objectiveMetric', 'createdAt', 'datasetRole'], 'plan');
  if (plan.schemaVersion !== 1) fail('invalid plan schemaVersion');
  for (const field of ['planId', 'proposalId', 'reviewId', 'taskId', 'objectiveMetric']) id(plan[field], field);
  date(plan.createdAt, 'createdAt');
  if (plan.datasetRole !== 'new-training-or-development-only') fail('failed-case data cannot be independently-held-out evaluation data');
  const proposal = await readRecord(root, 'cases', plan.proposalId);
  const review = await readRecord(root, 'reviews', plan.reviewId);
  if (review.proposalId !== proposal.proposalId || review.decision !== 'approve-for-development') fail('plan requires approved proposal review');
  const origin = await readRecord(root, 'runs', proposal.sourceRunId);
  if (plan.taskId !== origin.taskId) fail('plan task mismatch');
  if (!origin.metrics.some(metric => metric.id === plan.objectiveMetric)) fail('plan objective must be an observed metric');
  return immutable(root, 'plans', plan.planId, {...plan, status: 'planned-not-dispatched'});
}

export function validatePolicy(policy) {
  record(policy, 'policy');
  keys(policy, ['schemaVersion', 'policyId', 'taskId', 'evaluationKind', 'sampleSetSha256', 'protocolSha256', 'frozenAt', 'minSamples', 'allowedEvidenceLevels', 'metrics'], 'policy');
  if (policy.schemaVersion !== 1) fail('invalid policy schemaVersion');
  id(policy.policyId, 'policyId'); id(policy.taskId, 'taskId'); id(policy.evaluationKind, 'evaluationKind');
  digest(policy.sampleSetSha256, 'policy.sampleSetSha256'); digest(policy.protocolSha256, 'policy.protocolSha256');
  date(policy.frozenAt, 'policy.frozenAt'); integer(policy.minSamples, 'policy.minSamples', 1);
  if (!Array.isArray(policy.allowedEvidenceLevels) || !policy.allowedEvidenceLevels.length || policy.allowedEvidenceLevels.some(x => !EVIDENCE.has(x))) fail('policy evidence levels invalid');
  if (!Array.isArray(policy.metrics) || !policy.metrics.length) fail('policy metrics missing');
  const metrics = new Set();
  let primary = 0;
  let safety = 0;
  for (const spec of policy.metrics) {
    record(spec, 'policy.metric');
    keys(spec, ['id', 'unit', 'direction', 'role', 'minimumImprovement', 'maxRegression', 'maxValue', 'minValue'], 'policy.metric');
    id(spec.id, 'policy.metric.id');
    if (metrics.has(spec.id)) fail('duplicate policy metric');
    metrics.add(spec.id);
    if (!['rate', 'iou', 'milliseconds', 'seconds', 'bytes', 'count', 'mse', 'ratio'].includes(spec.unit)) fail('policy metric unit invalid');
    if (!['lower', 'higher'].includes(spec.direction)) fail('policy metric direction invalid');
    if (!['primary', 'safety', 'secondary'].includes(spec.role)) fail('policy metric role invalid');
    if (spec.role === 'primary') primary++;
    if (spec.role === 'safety') safety++;
    number(spec.minimumImprovement, 'minimumImprovement');
    number(spec.maxRegression, 'maxRegression');
    if (spec.minimumImprovement < 0 || spec.maxRegression < 0) fail('negative metric tolerances invalid');
    if (spec.role === 'safety' && spec.maxRegression !== 0) fail('safety metrics require zero regression');
    if (spec.maxValue !== undefined) number(spec.maxValue, 'maxValue');
    if (spec.minValue !== undefined) number(spec.minValue, 'minValue');
    if ((spec.maxValue !== undefined && spec.maxValue < 0) || (spec.minValue !== undefined && spec.minValue < 0)) fail('metric bounds must be nonnegative');
    if (spec.unit === 'count' && [spec.maxValue, spec.minValue].some(value => value !== undefined && !Number.isSafeInteger(value))) fail('count bounds must be safe integers');
    if (spec.maxValue !== undefined && spec.minValue !== undefined && spec.maxValue < spec.minValue) fail('metric bounds are reversed');
  }
  if (!primary) fail('at least one primary metric required');
  if (!safety) fail('at least one zero-regression safety metric required');
  return policy;
}

export async function recordPolicy(root, policy) {
  const input = structuredClone(policy);
  validatePolicy(input);
  const policySha256 = sha256(canonicalJson(input));
  return {policySha256, saved: await immutable(root, 'policies', `policy.${policySha256}`, input)};
}

export function compareRuns(baseline, candidate, policy) {
  validateRun(baseline); validateRun(candidate); validatePolicy(policy);
  const policySha256 = sha256(canonicalJson(policy));
  const comparisonId = `cmp.${sha256(`${baseline.runId}|${candidate.runId}|${policySha256}`).slice(0,24)}`;
  const incompatible = [];
  const reject = [];
  const match = (condition, reason) => {if (!condition) incompatible.push(reason);};
  match(baseline.runId !== candidate.runId, 'same-run');
  match(Date.parse(candidate.capturedAt) > Date.parse(baseline.capturedAt), 'candidate-not-newer-than-baseline');
  match(baseline.projectId === candidate.projectId, 'project-mismatch');
  match(baseline.kind === 'model-evaluation' && candidate.kind === 'model-evaluation', 'requires-model-evaluation');
  match(baseline.status === 'succeeded' && candidate.status === 'succeeded', 'run-not-succeeded');
  match(baseline.taskId === candidate.taskId && policy.taskId === baseline.taskId, 'task-mismatch');
  match(baseline.policySha256 === policySha256 && candidate.policySha256 === policySha256, 'policy-not-pinned');
  match(Date.parse(policy.frozenAt) <= Date.parse(baseline.capturedAt) && Date.parse(policy.frozenAt) <= Date.parse(candidate.capturedAt), 'policy-not-predeclared');
  match(baseline.evidence.level === candidate.evidence.level && policy.allowedEvidenceLevels.includes(baseline.evidence.level), 'evidence-class-mismatch');
  match(Boolean(baseline.dataset && candidate.dataset && baseline.evaluation && candidate.evaluation), 'missing-evaluation-provenance');
  if (baseline.dataset && candidate.dataset && baseline.evaluation && candidate.evaluation) {
    match(baseline.dataset.sha256 === candidate.dataset.sha256, 'dataset-digest-mismatch');
    match(baseline.dataset.origin === candidate.dataset.origin && baseline.dataset.origin !== 'unknown', 'dataset-origin-mismatch');
    match(baseline.dataset.sampleSetSha256 === candidate.dataset.sampleSetSha256 && baseline.dataset.sampleSetSha256 === policy.sampleSetSha256, 'sample-set-mismatch');
    match(baseline.dataset.split === candidate.dataset.split && ['holdout', 'shifted'].includes(baseline.dataset.split), 'split-not-independent-holdout');
    match(baseline.dataset.sampleCount === candidate.dataset.sampleCount && candidate.dataset.sampleCount >= policy.minSamples, 'insufficient-or-different-samples');
    match(baseline.evaluation.kind === candidate.evaluation.kind && baseline.evaluation.kind === policy.evaluationKind, 'evaluation-kind-mismatch');
    match(baseline.evaluation.protocolSha256 === candidate.evaluation.protocolSha256 && baseline.evaluation.protocolSha256 === policy.protocolSha256, 'evaluation-protocol-mismatch');
    match(baseline.evaluation.independentHoldout && candidate.evaluation.independentHoldout, 'holdout-not-independent');
  }
  match(baseline.artifact?.type === 'model-checkpoint' && candidate.artifact?.type === 'model-checkpoint', 'model-checkpoint-required');
  match(baseline.artifact?.sha256 !== candidate.artifact?.sha256, 'identical-model-checkpoint');
  const baseMetrics = new Map(baseline.metrics.map(x => [x.id, x]));
  const newMetrics = new Map(candidate.metrics.map(x => [x.id, x]));
  match(baseMetrics.size === policy.metrics.length && newMetrics.size === policy.metrics.length, 'untracked-metrics');
  const improvements = [];
  for (const spec of policy.metrics) {
    const old = baseMetrics.get(spec.id);
    const next = newMetrics.get(spec.id);
    if (!old || !next || old.unit !== spec.unit || next.unit !== spec.unit || old.direction !== spec.direction || next.direction !== spec.direction || old.samples !== next.samples || old.samples < policy.minSamples) {
      incompatible.push(`metric-incomparable:${spec.id}`);
      continue;
    }
    const delta = (next.value - old.value) * (spec.direction === 'higher' ? 1 : -1);
    if (delta < -spec.maxRegression) reject.push(`metric-regression:${spec.id}`);
    if (spec.maxValue !== undefined && next.value > spec.maxValue) reject.push(`metric-above-safety-bound:${spec.id}`);
    if (spec.minValue !== undefined && next.value < spec.minValue) reject.push(`metric-below-safety-bound:${spec.id}`);
    if (spec.role === 'primary' && delta > spec.minimumImprovement) improvements.push(spec.id);
  }
  if (!improvements.length && !incompatible.length) reject.push('no-primary-improvement');
  const status = incompatible.length ? 'incomparable' : reject.length ? 'rejected' : 'candidate-eligible-for-review';
  return {
    schemaVersion: 1, comparisonId, baselineRunId: baseline.runId, candidateRunId: candidate.runId,
    baselineSha256: sha256(canonicalJson(baseline)), candidateSha256: sha256(canonicalJson(candidate)),
    policySha256, status, reasons: [...new Set([...incompatible, ...reject])], improvedPrimaryMetrics: improvements,
    releaseAuthorized: false, effectsAuthorized: false, providerAttestationVerified: false
  };
}

export async function compareAndRecord(root, baselineId, candidateId, policy) {
  policy = structuredClone(policy);
  validatePolicy(policy);
  const policySha256 = sha256(canonicalJson(policy));
  const preregistered = validatePolicy(await readRecord(root, 'policies', `policy.${policySha256}`));
  if (canonicalJson(preregistered) !== canonicalJson(policy)) fail('comparison requires exact preregistered policy');
  const baseline = await readRecord(root, 'runs', baselineId);
  const candidate = await readRecord(root, 'runs', candidateId);
  const decision = compareRuns(baseline, candidate, preregistered);
  return {decision, saved: await immutable(root, 'comparisons', decision.comparisonId, decision)};
}

export async function summarize(root) {
  const out = {};
  for (const name of ['policies', 'runs', 'failures', 'cases', 'reviews', 'plans', 'comparisons']) {
    try {out[name] = (await readdir(join(root, name))).filter(x => x.endsWith('.json')).length;}
    catch (e) {if (e.code === 'ENOENT') out[name] = 0; else throw e;}
  }
  return {schemaVersion: 1, collections: out, externalProviderVerified: false};
}
