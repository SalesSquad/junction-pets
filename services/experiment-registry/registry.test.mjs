import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {canonicalJson, sha256} from '../../lib/artifact.mjs';
import {compareAndRecord, compareRuns, planNext, readRecord, recordFailure, recordPolicy, recordRun, reviewCase, summarize, validateRun} from './registry.mjs';

const hex = c => c.repeat(64);
const shas = {dataset: hex('a'), cases: hex('b'), protocol: hex('c'), model1: hex('d'), model2: hex('e'), receipt: hex('f')};
const source = {repository: 'SalesSquad/junction-pets', commit: '634f1e0e6cb2de46bcf0a783532d46c23f513d11'};
const policy = {
  schemaVersion: 1, policyId: 'meta-vision-v1', taskId: 'meta.object-recognition',
  evaluationKind: 'real-vision', sampleSetSha256: shas.cases, protocolSha256: shas.protocol,
  frozenAt: '2026-11-13T00:00:00Z', minSamples: 200,
  allowedEvidenceLevels: ['synthetic-reproducible'], metrics: [
    {id: 'reacquisition-rate', unit: 'rate', direction: 'higher', role: 'primary', minimumImprovement: 0.001, maxRegression: 0},
    {id: 'false-identity-rate', unit: 'rate', direction: 'lower', role: 'safety', minimumImprovement: 0, maxRegression: 0, maxValue: 0.03},
    {id: 'id-switch-count', unit: 'count', direction: 'lower', role: 'secondary', minimumImprovement: 0, maxRegression: 0}
  ]
};
const digest = sha256(canonicalJson(policy));

function run(runId, overrides = {}) {
  const input = {
    schemaVersion: 1, runId, projectId: 'meta', taskId: 'meta.object-recognition',
    kind: 'model-evaluation', capturedAt: runId.includes('new') ? '2026-11-14T02:00:00Z' : '2026-11-14T01:00:00Z', status: 'succeeded', source,
    evidence: {level: 'synthetic-reproducible', ref: 'https://github.com/SalesSquad/junction-pets/pull/70', receiptSha256: shas.receipt},
    dataset: {sha256: shas.dataset, sampleSetSha256: shas.cases, split: 'holdout', sampleCount: 256, origin: 'synthetic'},
    evaluation: {kind: 'real-vision', protocolSha256: shas.protocol, independentHoldout: true},
    artifact: {type: 'model-checkpoint', sha256: runId.includes('new') ? shas.model2 : shas.model1},
    metrics: [
      {id: 'reacquisition-rate', value: runId.includes('new') ? 0.84 : 0.8, direction: 'higher', unit: 'rate', samples: 256},
      {id: 'false-identity-rate', value: 0.02, direction: 'lower', unit: 'rate', samples: 256},
      {id: 'id-switch-count', value: 2, direction: 'lower', unit: 'count', samples: 256}
    ],
    limitations: ['synthetic, no device attestation'], policySha256: digest
  };
  return {...input, ...overrides};
}

async function temporary(callback) {
  const root = await mkdtemp(join(tmpdir(), 'experiment-registry-'));
  try {return await callback(root);} finally {await rm(root, {recursive: true, force: true});}
}

test('model evaluation requires pinned comparable source, sample and policy', () => {
  assert.equal(validateRun(run('meta-base')).runId, 'meta-base');
  for (const changes of [
    {source: {...source, commit: 'short'}}, {dataset: null}, {policySha256: null},
    {artifact: null}, {evaluation: null}, {unexpected: 'raw video'}
  ]) assert.throws(() => validateRun(run('meta-base', changes)));
  assert.throws(() => validateRun(run('meta-base', {metrics: [
    {id: 'false-identity-rate', value: Number.NaN, unit: 'rate', direction: 'lower', samples: 256}
  ]})));
  assert.throws(() => validateRun(run('meta-base', {metrics: [
    {id: 'false-identity-rate', value: 1.2, unit: 'rate', direction: 'lower', samples: 256}
  ]})));
  assert.throws(() => validateRun(run('meta-base', {evidence: {...run('meta-base').evidence, ref: 'https://user:token@host.example/private'}})));
  assert.throws(() => validateRun(run('meta-base', {evidence: {...run('meta-base').evidence, ref: 'https://host.example/result?api_key=private'}})));
  assert.throws(() => validateRun(run('meta-base', {metrics: run('meta-base').metrics.map((m, i) => i === 0 ? {...m, samples: 999} : m)})));
  for (const unit of ['count', 'milliseconds', 'seconds', 'bytes', 'mse', 'ratio']) {
    assert.throws(() => validateRun(run('meta-base', {metrics: [{id: 'impossible-metric', unit, value: -3, samples: 256, direction: 'lower'}]})), /nonnegative/);
  }
  assert.throws(() => validateRun(run('meta-base', {metrics: [{id: 'id-switch-count', unit: 'count', value: 2.5, samples: 256, direction: 'lower'}]})), /safe integer/);
});

test('full comparison policy must be immutable and preregistered before the first model run', async () => temporary(async root => {
  await assert.rejects(recordRun(root, run('meta-base')), /ENOENT/);
  const path = join(root, 'frozen-policy.json');
  await writeFile(path, JSON.stringify(policy));
  const result = spawnSync(process.execPath, [join(import.meta.dirname, 'cli.mjs'), 'record-policy', '--root', root, '--input', path], {encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  const created = JSON.parse(result.stdout);
  assert.equal(created.policySha256, digest);
  assert.equal(created.saved.created, true);
  assert.equal((await recordPolicy(root, policy)).saved.created, false);
  assert.deepEqual(await readRecord(root, 'policies', `policy.${digest}`), policy);
  await recordRun(root, run('meta-base'));
  const changed = {...policy, metrics: policy.metrics.map((entry, i) => i === 0 ? {...entry, minimumImprovement: 0.01} : entry)};
  const other = await recordPolicy(root, changed);
  assert.notEqual(other.policySha256, digest);
  assert.equal((await readRecord(root, 'runs', 'meta-base')).policySha256, digest);
  assert.equal((await summarize(root)).collections.policies, 2);
}));

test('immutable event replays are idempotent and conflicting payloads fail', async () => temporary(async root => {
  await recordPolicy(root, policy);
  const baseline = run('meta-base');
  const first = await recordRun(root, baseline);
  assert.equal(first.created, true);
  assert.equal((await recordRun(root, baseline)).created, false);
  await assert.rejects(recordRun(root, {...baseline, limitations: ['changed']}), /immutable record conflict/);
  assert.deepEqual((await readRecord(root, 'runs', 'meta-base')).metrics, baseline.metrics);
  assert.equal((await readFile(join(root, 'runs', 'meta-base.json'), 'utf8')).endsWith('\n'), true);
}));

test('simultaneous identical imports preserve one immutable record', async () => temporary(async root => {
  await recordPolicy(root, policy);
  const output = await Promise.all(Array.from({length: 10}, () => recordRun(root, run('meta-base'))));
  assert.equal(output.filter(x => x.created).length, 1);
  assert.equal((await summarize(root)).collections.runs, 1);
}));

test('caller mutation after async admission cannot write unvalidated private fields', async () => temporary(async root => {
  await recordPolicy(root, policy);
  const input = run('meta-base');
  const pending = recordRun(root, input);
  input.rawVideo = 'private input must never be written';
  input.metrics[0].value = 1;
  await pending;
  const persisted = await readRecord(root, 'runs', 'meta-base');
  assert.equal('rawVideo' in persisted, false);
  assert.equal(persisted.metrics[0].value, 0.8);
  const failure = {schemaVersion: 1, failureId: 'failure.03', runId: 'meta-base', caseSha256: shas.cases, failureCode: 'wrong-object', severity: 'high', observedAt: '2026-11-14T02:00:00Z'};
  const pendingFailure = recordFailure(root, failure);
  failure.rawTranscript = 'private text';
  await pendingFailure;
  assert.equal('rawTranscript' in await readRecord(root, 'failures', 'failure.03'), false);
}));

test('failures generate quarantined cases, with review-gated next experiment', async () => temporary(async root => {
  await recordPolicy(root, policy);
  await recordRun(root, run('meta-base'));
  const failure = {schemaVersion: 1, failureId: 'failure.01', runId: 'meta-base', caseSha256: shas.cases, failureCode: 'lookalike-identity', severity: 'high', observedAt: '2026-11-14T02:00:00Z'};
  const initial = await recordFailure(root, failure);
  assert.equal((await recordFailure(root, failure)).failure.created, false);
  const proposed = await readRecord(root, 'cases', initial.proposalId);
  assert.equal(proposed.trainAdmission, false);
  assert.equal(proposed.evaluationAdmission, false);
  assert.equal(proposed.status, 'quarantined-pending-review');
  const plan = {schemaVersion: 1, planId: 'plan.01', proposalId: initial.proposalId, reviewId: 'review.01', taskId: 'meta.object-recognition', objectiveMetric: 'false-identity-rate', createdAt: '2026-11-14T03:00:00Z', datasetRole: 'new-training-or-development-only'};
  await assert.rejects(planNext(root, plan), /ENOENT/);
  const review = {schemaVersion: 1, reviewId: 'review.01', proposalId: initial.proposalId, decision: 'approve-for-development', reviewer: 'independent-reviewer', reviewedAt: '2026-11-14T02:30:00Z', evidenceSha256: shas.receipt};
  await reviewCase(root, review);
  await assert.rejects(planNext(root, {...plan, datasetRole: 'current-holdout'}), /cannot be independently-held-out/);
  await assert.rejects(planNext(root, {...plan, taskId: 'another-task'}), /plan task mismatch/);
  await assert.rejects(planNext(root, {...plan, objectiveMetric: 'invented-metric'}), /observed metric/);
  assert.equal((await planNext(root, plan)).created, true);
  assert.equal((await readRecord(root, 'plans', plan.planId)).status, 'planned-not-dispatched');
  const resumed = run('meta-new', {kind: 'training', planId: plan.planId, capturedAt: '2026-11-14T03:30:00Z', policySha256: null});
  assert.equal((await recordRun(root, resumed)).created, true);
  assert.equal((await readRecord(root, 'runs', resumed.runId)).planId, plan.planId);
  await assert.rejects(recordRun(root, {...resumed, runId: 'meta-new2', taskId: 'other-task'}), /mismatched or future learning plan/);
  await assert.rejects(recordRun(root, {...resumed, runId: 'meta-new3', capturedAt: '2026-11-14T02:00:00Z'}), /mismatched or future learning plan/);
  assert.deepEqual((await summarize(root)).collections, {policies: 1, runs: 2, failures: 1, cases: 1, reviews: 1, plans: 1, comparisons: 0});
}));

test('rejected review cannot generate an experiment', async () => temporary(async root => {
  await recordPolicy(root, policy);
  await recordRun(root, run('meta-base'));
  const found = await recordFailure(root, {schemaVersion: 1, failureId: 'failure.02', runId: 'meta-base', caseSha256: shas.cases, failureCode: 'wrong-object', severity: 'high', observedAt: '2026-11-14T02:00:00Z'});
  await reviewCase(root, {schemaVersion: 1, reviewId: 'review.reject', proposalId: found.proposalId, decision: 'reject', reviewer: 'independent-reviewer', reviewedAt: '2026-11-14T02:30:00Z', evidenceSha256: shas.receipt});
  await assert.rejects(planNext(root, {schemaVersion: 1, planId: 'plan.reject', proposalId: found.proposalId, reviewId: 'review.reject', taskId: 'meta.object-recognition', objectiveMetric: 'false-identity-rate', createdAt: '2026-11-14T03:00:00Z', datasetRole: 'new-training-or-development-only'}), /approved proposal review/);
}));

test('improving model becomes only advisory eligible, never released', () => {
  const result = compareRuns(run('meta-base'), run('meta-new'), policy);
  assert.equal(result.status, 'candidate-eligible-for-review');
  assert.deepEqual(result.improvedPrimaryMetrics, ['reacquisition-rate']);
  assert.equal(result.releaseAuthorized, false);
  assert.equal(result.effectsAuthorized, false);
  assert.equal(result.providerAttestationVerified, false);
});

test('safety regression blocks even if primary improves', () => {
  const next = run('meta-new');
  next.metrics[1].value = 0.021;
  assert.equal(compareRuns(run('meta-base'), next, policy).status, 'rejected');
  assert.ok(compareRuns(run('meta-base'), next, policy).reasons.includes('metric-regression:false-identity-rate'));
});

test('absolute safety bound blocks candidate even if neither model regresses', () => {
  const old = run('meta-base'); const next = run('meta-new');
  old.metrics[1].value = 0.04; next.metrics[1].value = 0.035;
  assert.equal(compareRuns(old, next, policy).status, 'rejected');
});

test('no primary improvement and secondary regression are rejected', () => {
  const flat = run('meta-new'); flat.metrics[0].value = 0.8;
  assert.equal(compareRuns(run('meta-base'), flat, policy).status, 'rejected');
  const secondary = run('meta-new'); secondary.metrics[2].value = 3;
  assert.equal(compareRuns(run('meta-base'), secondary, policy).status, 'rejected');
});

test('same checkpoint and cross-project claims never qualify as learning', () => {
  const duplicateModel = run('meta-new', {artifact: run('meta-base').artifact});
  assert.equal(compareRuns(run('meta-base'), duplicateModel, policy).status, 'incomparable');
  const otherProject = run('meta-new', {projectId: 'verda'});
  assert.equal(compareRuns(run('meta-base'), otherProject, policy).status, 'incomparable');
  const olderCandidate = run('meta-new', {capturedAt: '2026-11-13T23:30:00Z'});
  assert.equal(compareRuns(run('meta-base'), olderCandidate, policy).status, 'incomparable');
  assert.ok(compareRuns(run('meta-base'), olderCandidate, policy).reasons.includes('candidate-not-newer-than-baseline'));
});

test('dataset, split, protocol, evidence and metrics must match', () => {
  const wrong = [
    {dataset: {...run('meta-new').dataset, sha256: hex('1')}},
    {dataset: {...run('meta-new').dataset, sampleSetSha256: hex('2')}},
    {dataset: {...run('meta-new').dataset, split: 'validation'}},
    {dataset: {...run('meta-new').dataset, origin: 'unknown'}},
    {evaluation: {...run('meta-new').evaluation, protocolSha256: hex('3')}},
    {evaluation: {...run('meta-new').evaluation, independentHoldout: false}},
    {evidence: {...run('meta-new').evidence, level: 'source-reported'}},
    {policySha256: hex('4')},
    {metrics: run('meta-new').metrics.slice(0, 2)},
    {metrics: [...run('meta-new').metrics, {id: 'new-hidden-metric', value: 5, unit: 'count', direction: 'lower', samples: 256}]},
    {metrics: run('meta-new').metrics.map((m, i) => i === 0 ? {...m, direction: 'lower'} : m)},
    {kind: 'apple-check', dataset: null, evaluation: null, policySha256: null}
  ];
  for (const changes of wrong) {
    const candidate = run('meta-new', changes);
    const result = compareRuns(run('meta-base'), candidate, policy);
    assert.equal(result.status, 'incomparable', JSON.stringify(changes));
  }
  assert.throws(() => compareRuns(run('meta-base'), run('meta-new', {dataset: {...run('meta-new').dataset, sampleCount: 155}}), policy), /exact sample set/);
});

test('post-hoc policies cannot make a model eligible', () => {
  const manipulated = {...policy, frozenAt: '2026-11-15T00:00:00Z'};
  assert.equal(compareRuns(run('meta-base'), run('meta-new'), manipulated).status, 'incomparable');
});

test('comparison is immutable/idempotent and CLI non-eligible uses nonzero exit', async () => temporary(async root => {
  await recordPolicy(root, policy);
  await recordRun(root, run('meta-base')); await recordRun(root, run('meta-new'));
  const good = await compareAndRecord(root, 'meta-base', 'meta-new', policy);
  assert.equal(good.saved.created, true);
  assert.equal((await compareAndRecord(root, 'meta-base', 'meta-new', policy)).saved.created, false);
  const p = join(root, 'policy.json');
  await writeFile(p, `${JSON.stringify(policy)}\n`);
  const cli = join(import.meta.dirname, 'cli.mjs');
  const result = spawnSync(process.execPath, [cli, 'compare', '--root', root, '--baseline', 'meta-base', '--candidate', 'meta-new', '--policy', p], {encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  const flat = run('meta-new2'); flat.metrics[0].value = 0.8;
  await recordRun(root, flat);
  const denied = spawnSync(process.execPath, [cli, 'compare', '--root', root, '--baseline', 'meta-base', '--candidate', 'meta-new2', '--policy', p], {encoding: 'utf8'});
  assert.equal(denied.status, 2, denied.stderr);
  assert.equal(JSON.parse(denied.stdout).decision.status, 'rejected');
  assert.equal((await summarize(root)).collections.comparisons, 2);
}));

test('candidate ingestion automatically writes comparison and blocks unsafe candidates', async () => temporary(async root => {
  await recordPolicy(root, policy);
  await recordRun(root, run('meta-base'));
  const p = join(root, 'frozen-policy.json');
  const input = join(root, 'candidate.json');
  await writeFile(p, JSON.stringify(policy));
  await writeFile(input, JSON.stringify(run('meta-new')));
  const cli = join(import.meta.dirname, 'cli.mjs');
  const unguarded = spawnSync(process.execPath, [cli, 'record-run', '--root', root, '--input', input], {encoding: 'utf8'});
  assert.equal(unguarded.status, 2, unguarded.stderr);
  assert.equal(JSON.parse(unguarded.stdout).admission.status, 'not-compared');
  assert.equal((await summarize(root)).collections.comparisons, 0);
  const invoke = () => spawnSync(process.execPath, [cli, 'record-run', '--root', root, '--input', input, '--baseline', 'meta-base', '--policy', p], {encoding: 'utf8'});
  let output = invoke();
  assert.equal(output.status, 0, output.stderr);
  assert.equal(JSON.parse(output.stdout).comparison.decision.status, 'candidate-eligible-for-review');
  assert.equal(JSON.parse(invoke().stdout).saved.created, false);
  assert.equal((await summarize(root)).collections.comparisons, 1);
  const unsafe = run('meta-new-unsafe'); unsafe.metrics[1].value = 0.04;
  await writeFile(input, JSON.stringify(unsafe));
  output = invoke();
  assert.equal(output.status, 2, output.stderr);
  assert.equal(JSON.parse(output.stdout).comparison.decision.status, 'rejected');
  assert.equal((await readRecord(root, 'runs', unsafe.runId)).metrics[1].value, 0.04);
}));
