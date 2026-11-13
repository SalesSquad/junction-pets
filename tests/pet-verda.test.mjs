import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewGpuRunPlan} from '../pets/verda/gpu-run-plan.mjs';

const fixture = () => ({
  schemaVersion: 1, kind: 'fictional-gpu-run-plan', runId: 'fictional-gpu-demo', mode: 'plan-only',
  resources: {gpuCount: 2, cpuCount: 8, memoryGiB: 32},
  limits: {gpuCount: 4, cpuCount: 16, memoryGiB: 64, wallTimeSeconds: 2000},
  execution: {timeoutSeconds: 600, maxRetries: 2, retryBackoffSeconds: 30,
    shutdownOwnerId: 'fictional-operator', stopCondition: 'timeout-or-complete'},
  credits: {unit: 'fictional-credit', perAttemptCeiling: 5, available: 20},
});
const run = input => reviewGpuRunPlan(JSON.stringify(input));
const codes = input => run(input).findings.map(f => f.code);

test('finite invented plan accounts for every attempt and backoff without approving execution', () => {
  const input = fixture(), before = JSON.stringify(input), result = run(input);
  assert.equal(result.status, 'consistent-declarations');
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.summary, {runId: 'fictional-gpu-demo', attempts: 3, computeSeconds: 1800,
    wallTimeSeconds: 1860, gpuSeconds: 3600, worstCaseFictionalCredits: 15, remainingFictionalCredits: 5});
  assert.deepEqual(result.boundary, {synthetic: true, capacityVerified: false, creditsVerified: false,
    executionAuthorized: false, executionStarted: false, spendIncurred: false});
  assert.deepEqual(result, run(input));
  assert.equal(JSON.stringify(input), before);
});

test('zero retries produce one attempt; backoff is counted only between retry attempts', () => {
  const input = fixture(); input.execution.maxRetries = 0; input.execution.retryBackoffSeconds = 3600;
  assert.equal(run(input).summary.attempts, 1);
  assert.equal(run(input).summary.wallTimeSeconds, 600);
  assert.equal(run(input).summary.worstCaseFictionalCredits, 5);
  input.execution.maxRetries = 2; input.execution.retryBackoffSeconds = 0;
  assert.equal(run(input).summary.wallTimeSeconds, 1800);
});

test('each requested resource is checked against its own declared limit, including a zero limit', () => {
  const input = fixture(); input.limits.gpuCount = 0; input.limits.cpuCount = 7; input.limits.memoryGiB = 31;
  assert.deepEqual(codes(input), ['gpuCount-exceeds-limit', 'cpuCount-exceeds-limit', 'memoryGiB-exceeds-limit']);
  assert.equal(run(input).status, 'needs-review');
  input.limits = {...input.resources, wallTimeSeconds: 1860};
  assert.equal(run(input).status, 'consistent-declarations');
});

test('unknown requested resources and unknown limits remain findings, never inferred capacity', () => {
  const input = fixture(); input.resources.gpuCount = null; input.limits.gpuCount = null;
  input.resources.cpuCount = null; input.limits.memoryGiB = null;
  assert.deepEqual(codes(input), ['unknown-gpuCount', 'unknown-gpuCount-limit', 'unknown-cpuCount', 'unknown-memoryGiB-limit']);
  assert.equal(run(input).summary.gpuSeconds, null);
  assert.equal(run(input).summary.computeSeconds, 1800);
  assert.equal(run(input).boundary.capacityVerified, false);
});

test('unknown retry or timeout metadata cannot produce a finite duration or fictional credit estimate', () => {
  for (const field of ['timeoutSeconds', 'maxRetries', 'retryBackoffSeconds']) {
    const input = fixture(); input.execution[field] = null;
    assert.ok(codes(input).includes(`unknown-${field}`));
    assert.equal(run(input).summary.wallTimeSeconds, null);
    if (field === 'maxRetries') {
      assert.equal(run(input).summary.attempts, null);
      assert.equal(run(input).summary.worstCaseFictionalCredits, null);
    }
  }
  const input = fixture(); delete input.execution.maxRetries;
  assert.throws(() => run(input), /execution fields/);
});

test('wall-time includes retry backoff and distinguishes unknown, zero and exceeded ceilings', () => {
  const input = fixture(); input.limits.wallTimeSeconds = 1800;
  assert.deepEqual(codes(input), ['wall-time-exceeds-limit']);
  input.limits.wallTimeSeconds = 0;
  assert.deepEqual(codes(input), ['wall-time-exceeds-limit']);
  input.limits.wallTimeSeconds = null;
  assert.deepEqual(codes(input), ['unknown-wall-time-limit']);
});

test('unknown credit amounts stay null, a zero budget is not unknown, and retry costs cannot disappear', () => {
  const input = fixture(); input.credits.available = null;
  assert.deepEqual(codes(input), ['unknown-available-credits']);
  assert.equal(run(input).summary.remainingFictionalCredits, null);
  input.credits.available = 0;
  assert.deepEqual(codes(input), ['fictional-credits-exceed-available']);
  assert.equal(run(input).summary.remainingFictionalCredits, -15);
  input.credits.perAttemptCeiling = 0;
  assert.equal(run(input).status, 'consistent-declarations');
  assert.equal(run(input).summary.remainingFictionalCredits, 0);
  assert.equal(run(input).boundary.creditsVerified, false);
  input.credits.perAttemptCeiling = null;
  assert.deepEqual(codes(input), ['unknown-attempt-credit-ceiling']);
  assert.equal(run(input).summary.worstCaseFictionalCredits, null);
});

test('missing shutdown owner or stop declaration is never repaired by a finite budget', () => {
  const input = fixture(); input.execution.shutdownOwnerId = null; input.execution.stopCondition = null;
  assert.deepEqual(codes(input), ['unknown-shutdown-owner', 'unknown-stop-condition']);
  assert.equal(run(input).status, 'needs-review');
  input.execution.stopCondition = 'keep-running';
  assert.throws(() => run(input), /stopCondition/);
});

test('execution requests, claimed grants, real currencies and unbounded numeric values are rejected', () => {
  for (const mutate of [x => {x.mode = 'execute';}, x => {x.execution.authorized = true;},
    x => {x.kind = 'real-gpu-run-plan';}, x => {x.credits.unit = 'EUR';},
    x => {x.credits.available = '20';}, x => {x.execution.maxRetries = -1;},
    x => {x.execution.timeoutSeconds = 0;}, x => {x.resources.gpuCount = 0;},
    x => {x.execution.retryBackoffSeconds = 0.5;}, x => {x.runId = 'real-account-7';},
    x => {x.execution.shutdownOwnerId = 'fictional-' + 'a'.repeat(60);},
  ]) {const input = fixture(); mutate(input); assert.throws(() => run(input), TypeError);}
  const text = JSON.stringify(fixture());
  assert.throws(() => reviewGpuRunPlan(text.replace('"available":20', '"available":1e999')), TypeError);
  assert.throws(() => reviewGpuRunPlan(text.replace('"maxRetries":2', '"maxRetries":-0')), TypeError);
});

test('upper numeric bounds have exact arithmetic and overflow beyond the declared domain fails', () => {
  const input = fixture();
  input.resources = {gpuCount: 64, cpuCount: 256, memoryGiB: 4096};
  input.limits = {...input.resources, wallTimeSeconds: 604800};
  input.execution.timeoutSeconds = 86400; input.execution.maxRetries = 8; input.execution.retryBackoffSeconds = 3600;
  input.credits.perAttemptCeiling = 1000000; input.credits.available = 100000000;
  assert.deepEqual(run(input).summary, {runId: 'fictional-gpu-demo', attempts: 9, computeSeconds: 777600,
    wallTimeSeconds: 806400, gpuSeconds: 49766400, worstCaseFictionalCredits: 9000000, remainingFictionalCredits: 91000000});
  assert.deepEqual(codes(input), ['wall-time-exceeds-limit']);
  for (const [object, key] of [[input.resources, 'gpuCount'], [input.resources, 'cpuCount'], [input.resources, 'memoryGiB'],
    [input.limits, 'wallTimeSeconds'], [input.execution, 'timeoutSeconds'], [input.execution, 'maxRetries'],
    [input.execution, 'retryBackoffSeconds'], [input.credits, 'perAttemptCeiling'], [input.credits, 'available']]) {
    object[key]++; assert.throws(() => run(input), TypeError); object[key]--;
  }
});

test('closed bounded JSON accepts only plain parsed data with documented duplicate-member semantics', () => {
  for (const text of [null, {}, new String('{}'), '{', '[]', ' '.repeat(12289), 'é'.repeat(7000)]) {
    assert.throws(() => reviewGpuRunPlan(text), TypeError);
  }
  const text = JSON.stringify(fixture()).replace('"mode":"plan-only"', '"mode":"execute","mode":"plan-only"');
  assert.equal(reviewGpuRunPlan(text).status, 'consistent-declarations');
  assert.throws(() => reviewGpuRunPlan(text.replace('"schemaVersion":1', '"schemaVersion":1,"__proto__":{}')), TypeError);
  assert.equal({}.executionAuthorized, undefined);
});

test('checked-in invented GPU example remains a planning card, not an available Verda run', () => {
  const result = reviewGpuRunPlan(readFileSync(new URL('../pets/verda/examples/fictional-gpu-run.json', import.meta.url), 'utf8'));
  assert.equal(result.status, 'consistent-declarations');
  assert.equal(result.boundary.executionStarted, false);
  assert.equal(result.boundary.spendIncurred, false);
});
