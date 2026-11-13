import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewExperimentPlan} from '../pets/ignite-next/experiment-plan.mjs';

const example = () => JSON.parse(readFileSync(new URL('../pets/ignite-next/example.json', import.meta.url), 'utf8'));
const review = plan => reviewExperimentPlan(JSON.stringify(plan));
const boundary = result => {
  assert.equal(result.basis, 'invented-declarations');
  assert.equal(result.experimentPerformed, false);
  assert.equal(result.marketValidationEstablished, false);
  assert.equal(result.hypothesisProven, false);
  assert.equal(result.authorization, false);
};

test('invented experiment links its risky assumption to a measurable bounded proposal, not a result', () => {
  const result = review(example());
  assert.equal(result.status, 'ready-for-review');
  assert.deepEqual(result.issues, []);
  assert.equal(result.card.assumptionId, 'operator-demand');
  assert.equal(result.card.metric.unit, 'ratio');
  assert.equal(result.card.metric.baseline, 0.25);
  assert.deepEqual(result.card.customerEvidence.map(row => row.id), ['fictional-interview']);
  assert.equal(result.card.customerEvidence[0].kind, 'invented-interview');
  assert.equal(result.card.evidenceAuthenticity, 'not-verified');
  assert.equal(result.card.budget.maxCredits, 0);
  boundary(result);
});

test('success and stop rules require opposite directions and a strictly undecided interval', () => {
  for (const [success, stop, expected] of [
    [{operator: 'at-least', value: 0.6}, {operator: 'at-most', value: 0.2}, 'ready-for-review'],
    [{operator: 'at-most', value: 0.2}, {operator: 'at-least', value: 0.6}, 'ready-for-review'],
    [{operator: 'at-least', value: 0.2}, {operator: 'at-most', value: 0.2}, 'needs-review'],
    [{operator: 'at-least', value: 0.2}, {operator: 'at-most', value: 0.6}, 'needs-review'],
    [{operator: 'at-most', value: 0.6}, {operator: 'at-most', value: 0.2}, 'needs-review'],
    [{operator: 'at-most', value: 0.6}, {operator: 'at-least', value: 0.2}, 'needs-review'],
  ]) {
    const plan = example(); plan.metric.success = success; plan.metric.stop = stop;
    const result = review(plan);
    assert.equal(result.status, expected);
    assert.equal(result.issues.includes('overlapping-or-unseparated-rules'), expected === 'needs-review');
    boundary(result);
  }
});

test('explicit unknown baseline or rules remain unknown, while omitted fields are invalid', () => {
  for (const field of ['baseline', 'success', 'stop']) {
    const plan = example(); plan.metric[field] = null;
    const result = review(plan);
    assert.equal(result.status, 'needs-review');
    assert.ok(result.issues.includes('unknown-' + field));
    assert.equal(result.card.metric[field], null);
    delete plan.metric[field];
    assert.equal(review(plan).status, 'invalid');
  }
});

test('metric units and inclusive numeric domains preserve known zero without coercion', () => {
  for (const [unit, baseline, success, stop] of [['count', 0, 3, 0], ['ratio', 0, 1, 0], ['ms', 0, 1000000000, 0]]) {
    const plan = example(); Object.assign(plan.metric, {unit, baseline, success: {operator: 'at-least', value: success}, stop: {operator: 'at-most', value: stop}});
    const result = review(plan);
    assert.equal(result.status, 'ready-for-review');
    assert.equal(result.card.metric.baseline, 0);
  }
  for (const [unit, value] of [['count', 1.5], ['count', 1000001], ['ratio', 1.1], ['ms', 1000000001], ['ratio', -1], ['ratio', '0.5']]) {
    const plan = example(); plan.metric.unit = unit; plan.metric.baseline = value;
    assert.equal(review(plan).status, 'invalid');
  }
  assert.equal(reviewExperimentPlan(JSON.stringify(example()).replace('"baseline":0.25', '"baseline":1e309')).status, 'invalid');
});

test('effort and resource ceilings distinguish unknown, zero and bounded values without spending', () => {
  for (const key of ['maxHours', 'maxCredits']) {
    const plan = example(); plan.budget[key] = null;
    assert.ok(review(plan).issues.includes('unknown-' + key));
    delete plan.budget[key];
    assert.equal(review(plan).status, 'invalid');
  }
  const zero = example(); zero.budget.maxHours = 0;
  assert.ok(review(zero).issues.includes('no-effort-budget'));
  zero.budget.maxHours = 168; zero.budget.maxCredits = 10000;
  assert.equal(review(zero).status, 'ready-for-review');
  for (const [key, value] of [['maxHours', 169], ['maxHours', -1], ['maxCredits', 10001], ['maxCredits', '0']]) {
    const plan = example(); plan.budget[key] = value;
    assert.equal(review(plan).status, 'invalid');
  }
});

test('a declared sample size is a plan, not observations, statistical power or market validation', () => {
  for (const [value, issue] of [[null, 'unknown-sample-size'], [0, 'no-planned-observations']]) {
    const plan = example(); plan.metric.sampleSize = value;
    assert.ok(review(plan).issues.includes(issue));
    boundary(review(plan));
  }
  for (const value of [-1, 0.5, 10001, true]) {
    const plan = example(); plan.metric.sampleSize = value;
    assert.equal(review(plan).status, 'invalid');
  }
  const max = example(); max.metric.sampleSize = 10000;
  assert.equal(review(max).status, 'ready-for-review');
});

test('customer evidence must be explicitly linked; missing, dangling and duplicate identities stay distinct', () => {
  const empty = example(); empty.assumption.customerEvidenceIds = [];
  const result = review(empty);
  assert.equal(result.status, 'needs-review');
  assert.ok(result.issues.includes('no-linked-customer-evidence'));
  assert.deepEqual(result.card.customerEvidence, []);
  for (const mutate of [
    p => { p.assumption.customerEvidenceIds = ['undeclared']; },
    p => { p.assumption.customerEvidenceIds.push(p.assumption.customerEvidenceIds[0]); },
    p => { p.customerEvidence.push({...p.customerEvidence[0]}); },
    p => { delete p.assumption.customerEvidenceIds; },
  ]) {
    const plan = example(); mutate(plan); assert.equal(review(plan).status, 'invalid');
  }
  empty.customerEvidence = [];
  assert.equal(review(empty).status, 'needs-review');
});

test('extra execution, funding, validation and nested claims cannot become accepted evidence', () => {
  for (const mutate of [
    p => { p.marketValidated = true; }, p => { p.experimentPerformed = true; },
    p => { p.budget.charged = 0; }, p => { p.metric.measuredResult = 0.8; },
    p => { p.customerEvidence[0].verified = true; }, p => { p.assumption.proven = true; },
    p => { p.customerEvidence[0].kind = 'real-customer'; }, p => { p.assumption.category = 'funding-guaranteed'; },
    p => { p.metric.success.operator = 'equal'; }, p => { p.kind = 'completed-experiment'; },
    p => { p.metric.unit = 'USD'; }, p => { p.schemaVersion = 2; },
  ]) {
    const plan = example(); mutate(plan); const result = review(plan);
    assert.equal(result.status, 'invalid'); assert.equal(result.card, null); boundary(result);
  }
});

test('strict identifiers, bounded text and category distinctions reject malformed shapes', () => {
  for (const mutate of [
    p => { p.assumption.id += '\n'; }, p => { p.metric.id = ''; },
    p => { p.assumption.statement = ' '; }, p => { p.assumption.statement = 'x'.repeat(241); },
    p => { p.customerEvidence[0].statement = 'private\u0000data'; },
    p => { p.customerEvidence[0].id = '../other'; }, p => { p.metric = []; },
  ]) {
    const plan = example(); mutate(plan); assert.equal(review(plan).status, 'invalid');
  }
  for (const category of ['technical', 'customer', 'delivery']) {
    const plan = example(); plan.assumption.category = category;
    assert.equal(review(plan).card.category, category);
  }
});

test('bounded JSON text and collection limits reject executable input and excess data', () => {
  let calls = 0;
  for (const value of [null, {}, [], 1, new String('{}'), {toJSON() { calls++; }}]) assert.equal(reviewExperimentPlan(value).status, 'invalid');
  assert.equal(calls, 0);
  for (const text of ['', '{', 'null', '[]', ' '.repeat(32769)]) assert.equal(reviewExperimentPlan(text).status, 'invalid');
  const plan = example();
  plan.customerEvidence = Array.from({length: 16}, (_, i) => ({id: 'note-' + i, kind: 'invented-interview', statement: 'Fictional note.'}));
  plan.assumption.customerEvidenceIds = plan.customerEvidence.map(row => row.id);
  assert.equal(review(plan).status, 'ready-for-review');
  plan.customerEvidence.push({id: 'excess', kind: 'invented-interview', statement: 'Fictional note.'});
  assert.equal(review(plan).status, 'invalid');
});

test('ordinary duplicate JSON members use the last member and do not authenticate the input', () => {
  const original = JSON.stringify(example());
  const duplicate = original.replace('"schemaVersion":1', '"schemaVersion":0,"schemaVersion":1');
  assert.deepEqual(reviewExperimentPlan(duplicate), reviewExperimentPlan(original));
  const reversed = original.replace('"schemaVersion":1', '"schemaVersion":1,"schemaVersion":0');
  assert.equal(reviewExperimentPlan(reversed).status, 'invalid');
});

test('output is deterministic across evidence order, isolates calls and does not invent unused customer evidence', () => {
  const plan = example();
  plan.customerEvidence.push({id: 'unused', kind: 'invented-observation', statement: 'Fictional unlinked note.'});
  const original = JSON.stringify(plan), result = review(plan);
  plan.customerEvidence.reverse(); plan.assumption.customerEvidenceIds.reverse();
  assert.deepEqual(review(plan), result);
  assert.equal(result.card.customerEvidence.length, 1);
  result.card.customerEvidence[0].statement = 'forged';
  result.card.metric.success.value = 0;
  assert.notEqual(reviewExperimentPlan(original).card.customerEvidence[0].statement, 'forged');
  assert.equal(reviewExperimentPlan(original).card.metric.success.value, 0.6);
});
