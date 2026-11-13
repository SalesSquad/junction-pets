import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {checkEvaluationPlan} from '../pets/google-deepmind/evaluation-plan.mjs';

const example = readFileSync(new URL('../pets/google-deepmind/example.json', import.meta.url), 'utf8');
const fixture = () => JSON.parse(example);
const check = plan => checkEvaluationPlan(JSON.stringify(plan));
const coverageFor = (result, id = 'visual-grounding') => result.coverage.find(row => row.capabilityId === id);
const visualOnly = () => ({...fixture(), capabilities: [fixture().capabilities[0]]});
const boundary = result => {
  assert.equal(result.basis, 'invented-declarations');
  assert.equal(result.trainingPerformed, false);
  assert.equal(result.actualEvaluationPerformed, false);
  assert.equal(result.modelPerformanceVerified, false);
  assert.equal(result.authorization, false);
};

test('invented example exposes planned coverage and the missing audio capability', () => {
  const result = checkEvaluationPlan(example);
  assert.equal(result.status, 'needs-review');
  assert.deepEqual(result.declaredSplits, {training: 1, heldOut: 2, unknown: 0});
  assert.deepEqual(result.leakageGroups, []);
  assert.deepEqual(coverageFor(result), {
    capabilityId: 'visual-grounding', targetHeldOutGroups: 2,
    declaredTrainingRecords: 1, declaredHeldOutRecords: 2, declaredUnknownSplitRecords: 0,
    eligibleHeldOutGroups: 2, planCoverage: 'covered', evaluationStatus: 'not-run',
  });
  assert.equal(coverageFor(result, 'sound-cue').planCoverage, 'uncovered');
  assert.deepEqual(result.untestedCapabilities, ['sound-cue', 'visual-grounding']);
  boundary(result);
});

test('a fully covered plan is never training, a model evaluation or a performance result', () => {
  const result = check(visualOnly());
  assert.equal(result.status, 'consistent-plan');
  assert.deepEqual(result.issues, []);
  assert.deepEqual(result.untestedCapabilities, ['visual-grounding']);
  assert.equal(coverageFor(result).evaluationStatus, 'not-run');
  boundary(result);
});

test('either a repeated source or scene detects training/held-out leakage', () => {
  for (const key of ['sourceId', 'sceneId']) {
    const plan = visualOnly();
    plan.records[1][key] = plan.records[0][key];
    const result = check(plan);
    assert.equal(result.status, 'needs-review');
    assert.equal(result.leakageGroups.length, 1);
    assert.deepEqual(result.leakageGroups[0].trainingRecordIds, ['training-storyboard']);
    assert.deepEqual(result.leakageGroups[0].heldOutRecordIds, ['heldout-storyboard-a']);
    assert.equal(coverageFor(result).eligibleHeldOutGroups, 1);
    assert.equal(coverageFor(result).planCoverage, 'insufficient');
  }
});

test('transitive source/scene links reveal leakage even through an unknown-split bridge', () => {
  const plan = visualOnly();
  plan.records.push({...plan.records[0], id: 'bridge', split: 'unknown', sceneId: plan.records[1].sceneId});
  const result = check(plan);
  assert.deepEqual(result.leakageGroups[0].recordIds,
    ['bridge', 'heldout-storyboard-a', 'training-storyboard']);
  assert.ok(result.issues.includes('unknown-split:bridge'));
  assert.equal(coverageFor(result).eligibleHeldOutGroups, 1);
});

test('repeated held-out source/scene groups cannot inflate independent coverage', () => {
  for (const key of ['sourceId', 'sceneId']) {
    const plan = visualOnly();
    plan.records[2][key] = plan.records[1][key];
    const result = check(plan);
    assert.equal(coverageFor(result).declaredHeldOutRecords, 2);
    assert.equal(coverageFor(result).eligibleHeldOutGroups, 1);
    assert.equal(coverageFor(result).planCoverage, 'insufficient');
    assert.deepEqual(result.leakageGroups, []);
  }
});

test('training, unknown splits and unknown group provenance never supply held-out coverage', () => {
  for (const split of ['training', 'unknown']) {
    const plan = visualOnly();
    plan.records.forEach(record => { record.split = split; });
    assert.equal(coverageFor(check(plan)).eligibleHeldOutGroups, 0);
  }
  for (const key of ['sourceId', 'sceneId']) {
    const plan = visualOnly();
    plan.records[1][key] = null;
    const result = check(plan);
    assert.equal(coverageFor(result).eligibleHeldOutGroups, 1);
    assert.ok(result.issues.includes('unknown-provenance:heldout-storyboard-a'));
    delete plan.records[1][key];
    assert.equal(check(plan).status, 'invalid');
  }
  const plan = visualOnly();
  plan.records.push({...plan.records[1], id: 'unassigned-copy', split: 'unknown'});
  assert.equal(coverageFor(check(plan)).eligibleHeldOutGroups, 1);
});

test('all required modalities must coexist in a tagged record, not merely across a group', () => {
  const plan = visualOnly();
  plan.records[1].modalities = ['text'];
  plan.records[2].modalities = ['image'];
  plan.records[2].sourceId = plan.records[1].sourceId;
  const result = check(plan);
  assert.equal(coverageFor(result).eligibleHeldOutGroups, 0);
  assert.equal(coverageFor(result).planCoverage, 'uncovered');
  for (const modalities of [[], null]) {
    const changed = visualOnly();
    changed.records[1].modalities = modalities;
    assert.equal(coverageFor(check(changed)).eligibleHeldOutGroups, 1);
    assert.notEqual(check(changed).status, 'invalid');
  }
});

test('zero, null and absent coverage targets remain distinct', () => {
  const plan = visualOnly();
  plan.capabilities[0].minHeldOutGroups = 0;
  assert.equal(coverageFor(check(plan)).planCoverage, 'not-requested');
  assert.equal(check(plan).status, 'needs-review');
  plan.capabilities[0].minHeldOutGroups = null;
  assert.equal(coverageFor(check(plan)).planCoverage, 'unknown-target');
  delete plan.capabilities[0].minHeldOutGroups;
  assert.equal(check(plan).status, 'invalid');
  plan.capabilities[0].minHeldOutGroups = 1;
  plan.records = [];
  assert.equal(coverageFor(check(plan)).eligibleHeldOutGroups, 0);
  assert.deepEqual(check(plan).declaredSplits, {training: 0, heldOut: 0, unknown: 0});
});

test('extra claims, wrong shapes, duplicate IDs and dangling capability references are rejected', () => {
  const mutations = [
    plan => { plan.modelAccuracy = 1; },
    plan => { plan.kind = 'measured-evaluation'; },
    plan => { plan.schemaVersion = 2; },
    plan => { plan.capabilities[0].passed = true; },
    plan => { plan.records[1].actualTraining = false; },
    plan => { plan.records[1].id = plan.records[0].id; },
    plan => { plan.capabilities.push({...plan.capabilities[0]}); },
    plan => { plan.records[1].capabilityIds = ['not-declared']; },
    plan => { plan.records[1].split = 'test-passed'; },
    plan => { plan.records[1].modalities = ['depth']; },
    plan => { plan.records[1].modalities = ['image', 'image']; },
    plan => { plan.records[1].capabilityIds.push('visual-grounding'); },
    plan => { plan.records[1].sourceId = 'unknown'; },
    plan => { plan.records[1].sceneId = 'room-green\n'; },
  ];
  for (const mutate of mutations) {
    const plan = fixture(); mutate(plan);
    const result = check(plan);
    assert.equal(result.status, 'invalid');
    assert.equal(result.declaredSplits, null);
    assert.deepEqual(result.coverage, []);
    boundary(result);
  }
});

test('bounded JSON-only input rejects malformed, oversized and unsupported numeric data without hooks', () => {
  let calls = 0;
  for (const input of [null, 0, {}, [], new String(example), {toJSON() { calls++; }}]) {
    assert.equal(checkEvaluationPlan(input).status, 'invalid');
  }
  assert.equal(calls, 0);
  for (const text of ['', '{', 'null', '[]', ' '.repeat(65537), example + ' trailing']) {
    assert.equal(checkEvaluationPlan(text).status, 'invalid');
  }
  for (const value of [-1, 0.5, 201, '2', true]) {
    const plan = visualOnly(); plan.capabilities[0].minHeldOutGroups = value;
    assert.equal(check(plan).status, 'invalid');
  }
  assert.equal(checkEvaluationPlan(example.replace('"minHeldOutGroups": 2', '"minHeldOutGroups": 1e309')).status, 'invalid');
  const plan = visualOnly();
  plan.records = Array.from({length: 201}, (_, i) => ({...plan.records[1], id: `record-${i}`}));
  assert.equal(check(plan).status, 'invalid');
  plan.records.pop();
  assert.notEqual(check(plan).status, 'invalid');
});

test('ordinary JSON duplicate-member semantics are explicit: the last member wins', () => {
  const text = JSON.stringify(visualOnly()).replace('"split":"held-out"', '"split":"training","split":"held-out"');
  assert.deepEqual(checkEvaluationPlan(text), check(visualOnly()));
  const reversed = JSON.stringify(visualOnly()).replace('"split":"held-out"', '"split":"held-out","split":"training"');
  assert.equal(checkEvaluationPlan(reversed).declaredSplits.training, 2);
  assert.equal(coverageFor(checkEvaluationPlan(reversed)).eligibleHeldOutGroups, 1);
});

test('input ordering does not affect output and returned values are isolated between calls', () => {
  const plan = fixture(), original = JSON.stringify(plan);
  const expected = check(plan);
  plan.capabilities.reverse(); plan.records.reverse();
  plan.records.forEach(record => { record.modalities.reverse(); record.capabilityIds.reverse(); });
  assert.deepEqual(check(plan), expected);
  assert.deepEqual(checkEvaluationPlan(original), expected);
  expected.coverage[0].evaluationStatus = 'forged';
  expected.untestedCapabilities.length = 0;
  const fresh = checkEvaluationPlan(original);
  assert.equal(fresh.coverage[0].evaluationStatus, 'not-run');
  assert.equal(fresh.untestedCapabilities.length, 2);
});
