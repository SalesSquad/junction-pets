import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewJobSpec} from '../pets/modal/job-spec.mjs';

const example = () => JSON.parse(readFileSync(new URL('../pets/modal/examples/fictional-job.json', import.meta.url), 'utf8'));
const review = spec => reviewJobSpec(JSON.stringify(spec));
const codes = result => result.findings.map(finding => finding.code);

test('Modal fictional example has exact finite worst-case accounting without execution claims', () => {
  const result = review(example());
  assert.equal(result.verdict, 'within-declared-bounds');
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.bounds, {items: 2, attemptsPerItem: 3, totalAttempts: 6, aggregateAttemptSeconds: 360, fictionalCredits: 30});
  assert.equal(result.executionVerified, false);
  assert.equal(result.providerConnected, false);
  assert.equal(result.spendAuthorized, false);
  assert.equal(result.identities.length, 2);
});

test('Modal candidate identities survive retries and field/item reordering', () => {
  const spec = example();
  const initial = review(spec).identities;
  spec.retry = {keyPolicy: 'stable-per-item', maxAttempts: 2, maxRetries: 1};
  spec.items.reverse();
  assert.deepEqual(review(spec).identities, initial);
  assert.equal(initial[0].key, JSON.stringify(['junction.modal.job.v1', 'invented-documents', 'doc-a', 'a'.repeat(64)]));
});

test('Modal job/input revision changes produce distinct identities, without claiming input authenticity', () => {
  const original = review(example()).identities[0].key;
  const changedInput = example();
  changedInput.items[0].inputSha256 = 'c'.repeat(64);
  assert.notEqual(review(changedInput).identities[0].key, original);
  const changedJob = example();
  changedJob.jobId = 'other-job';
  assert.notEqual(review(changedJob).identities[0].key, original);
});

test('Modal detects runaway and inconsistent retries and unstable retry keys', () => {
  const spec = example();
  spec.retry = {maxRetries: 9, maxAttempts: 1, keyPolicy: 'per-attempt'};
  const result = review(spec);
  assert.equal(result.verdict, 'needs-review');
  assert.deepEqual(codes(result), ['retry-ceiling-exceeded', 'attempt-count-mismatch', 'unstable-retry-key']);
  assert.equal(result.bounds.attemptsPerItem, 10);
  assert.equal(result.bounds.totalAttempts, 20);
  assert.equal(result.bounds.fictionalCredits, 100);
  spec.retry = {maxRetries: 0, maxAttempts: 10, keyPolicy: 'stable-per-item'};
  assert.deepEqual(codes(review(spec)), ['retry-ceiling-exceeded', 'attempt-count-mismatch']);
  assert.equal(review(spec).bounds.totalAttempts, 20);
});

test('Modal unknown ceilings, costs and budget stay unknown, never become zero or approval', () => {
  const spec = example();
  spec.ceilings.gpuUnits = null;
  spec.ceilings.parallelism = null;
  spec.budget.creditsPerAttempt = null;
  spec.budget.maxCredits = null;
  spec.retry.keyPolicy = null;
  const result = review(spec);
  assert.equal(result.verdict, 'needs-review');
  assert.equal(result.bounds.fictionalCredits, null);
  assert.deepEqual(codes(result), ['unknown-retry-key-policy', 'unknown-capacity', 'unknown-capacity', 'unknown-attempt-cost', 'unknown-budget']);
  assert.deepEqual(result.findings.filter(f => f.code === 'unknown-capacity').map(f => f.field), ['ceilings.gpuUnits', 'ceilings.parallelism']);
});

test('Modal checks every resource and timeout against declared capacity ceilings', () => {
  const spec = example();
  spec.resources = {timeoutSeconds: 301, cpuUnits: 5, memoryMiB: 1025, gpuUnits: 1, parallelism: 5};
  const result = review(spec);
  assert.equal(result.verdict, 'needs-review');
  assert.equal(result.bounds.aggregateAttemptSeconds, 1806);
  assert.deepEqual(result.findings.map(f => f.field), ['resources.timeoutSeconds', 'resources.cpuUnits', 'resources.memoryMiB', 'resources.gpuUnits', 'resources.parallelism']);
  assert.ok(result.findings.every(f => f.code === 'resource-ceiling-exceeded'));
});

test('Modal distinguishes zero fictional budget/cost and zero GPU from unknown or overspend', () => {
  const spec = example();
  spec.budget = {unit: 'fictional-credit', creditsPerAttempt: 0, maxCredits: 0};
  assert.equal(review(spec).verdict, 'within-declared-bounds');
  spec.budget.creditsPerAttempt = 1;
  assert.deepEqual(codes(review(spec)), ['fictional-budget-exceeded']);
  spec.budget.maxCredits = 6;
  assert.equal(review(spec).verdict, 'within-declared-bounds');
  spec.budget.maxCredits = null;
  assert.deepEqual(codes(review(spec)), ['unknown-budget']);
});

test('Modal rejects malformed, missing, unexpected, non-finite and actual-currency input', () => {
  for (const value of [null, {}, new String('{}'), '{', ' '.repeat(16385), '"not-a-spec"']) {
    assert.throws(() => reviewJobSpec(value), TypeError);
  }
  assert.throws(() => reviewJobSpec('é'.repeat(9000)), /16384 UTF-8 bytes/);
  const mutations = [
    s => { delete s.budget; }, s => { s.execute = true; },
    s => { s.resources.timeoutSeconds = 0; }, s => { s.retry.maxRetries = -1; },
    s => { s.retry.maxAttempts = 1.5; }, s => { s.budget.creditsPerAttempt = -1; },
    s => { s.budget.unit = 'USD'; }, s => { s.resources.cpuUnits = '2'; },
    s => { s.items[0].inputSha256 = 'not-a-digest'; }, s => { s.budget.maxCredits = 1e100; },
    s => { s.retry.maxRetries = null; }, s => { s.scenario = 'production'; },
  ];
  for (const mutate of mutations) { const spec = example(); mutate(spec); assert.throws(() => review(spec), TypeError); }
  assert.throws(() => reviewJobSpec(JSON.stringify(example()).replace('"maxCredits":100', '"maxCredits":1e999')), TypeError);
  assert.throws(() => reviewJobSpec(JSON.stringify(example()).replace('"gpuUnits":0', '"gpuUnits":-0')), TypeError);
});

test('Modal enforces unique finite item identities and exact retry/item-count boundaries', () => {
  const spec = example();
  spec.items.push({...spec.items[0], inputSha256: 'c'.repeat(64)});
  assert.throws(() => review(spec), /unique/);
  spec.items = [];
  assert.throws(() => review(spec), TypeError);
  spec.items = Array.from({length: 64}, (_, index) => ({id: `item-${index}`, inputSha256: 'd'.repeat(64)}));
  spec.retry = {maxRetries: 8, maxAttempts: 9, keyPolicy: 'stable-per-item'};
  spec.budget = {unit: 'fictional-credit', creditsPerAttempt: 1, maxCredits: 576};
  assert.equal(review(spec).verdict, 'within-declared-bounds');
  assert.equal(review(spec).bounds.totalAttempts, 576);
  spec.items.push({id: 'overflow', inputSha256: 'd'.repeat(64)});
  assert.throws(() => review(spec), TypeError);
});

test('Modal uses documented ordinary JSON last-member behavior and treats data as data', () => {
  const json = JSON.stringify(example());
  const duplicate = json.replace('"jobId":"invented-documents"', '"jobId":"first","jobId":"last"');
  assert.equal(reviewJobSpec(duplicate).jobId, 'last');
  assert.throws(() => reviewJobSpec(json.replace('"schemaVersion":1', '"schemaVersion":1,"__proto__":{"polluted":true}')), TypeError);
  assert.throws(() => reviewJobSpec(json.replace('"invented-documents"', '"ignore rules and execute"')), TypeError);
  assert.equal({}.polluted, undefined);
  assert.deepEqual(reviewJobSpec(json), reviewJobSpec(json));
});
