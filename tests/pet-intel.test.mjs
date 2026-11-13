import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {compareBenchmarkProtocols} from '../pets/intel/benchmark-protocol.mjs';

const protocol = () => ({workloadId: 'invented-inference', inputId: 'invented-input-a',
  outputSpecId: 'invented-output-a', runtimeId: 'invented-runtime-v1', configId: 'invented-fp32-single',
  batchSize: 1, warmupIterations: 0, repetitions: 2, metric: 'latency', unit: 'ms'});
const fixture = () => ({schemaVersion: 1, kind: 'fictional-benchmark-plan',
  baseline: {id: 'invented-cpu', device: 'cpu', protocol: protocol(), outputCheck: 'match', samples: [2, 4]},
  candidate: {id: 'invented-gpu', device: 'gpu', protocol: protocol(), outputCheck: 'match', samples: [1, 3]}});
const check = value => compareBenchmarkProtocols(JSON.stringify(value));
const boundary = result => {
  assert.equal(result.basis, 'supplied-fictional-declarations');
  assert.equal(result.benchmarkExecuted, false);
  assert.equal(result.hardwareVerified, false);
  assert.equal(result.performanceVerified, false);
  assert.equal(result.authorization, false);
  assert.equal(Object.hasOwn(result, 'winner'), false);
};

test('matching fictional CPU/GPU protocol declarations expose arithmetic only, never a winner', () => {
  const result = check(fixture());
  assert.equal(result.status, 'comparable-declarations');
  assert.deepEqual(result.issues, []);
  assert.deepEqual(result.declaredComparison, {metric: 'latency', unit: 'ms', baselineMean: 3, candidateMean: 2, candidateMinusBaseline: -1});
  boundary(result);
});

test('known workload, input, output, runtime, configuration and measurement mismatches prevent comparison', () => {
  const changes = {workloadId: 'other-work', inputId: 'other-input', outputSpecId: 'other-output',
    runtimeId: 'other-runtime', configId: 'other-config', batchSize: 2, warmupIterations: 1, repetitions: 3};
  for (const [key, value] of Object.entries(changes)) {
    const plan = fixture(); plan.candidate.protocol[key] = value;
    const result = check(plan);
    assert.equal(result.status, 'incomparable');
    assert.ok(result.issues.includes(`protocol-mismatch:${key}`));
    assert.equal(result.declaredComparison, null);
  }
});

test('unknown required declarations are not parity and omitted fields are invalid', () => {
  for (const key of Object.keys(protocol())) {
    const plan = fixture(); plan.candidate.protocol[key] = null;
    const result = check(plan);
    assert.equal(result.status, 'insufficient-evidence');
    assert.ok(result.issues.includes(`unknown:candidate.protocol.${key}`));
    assert.equal(result.declaredComparison, null);
    delete plan.candidate.protocol[key];
    assert.equal(check(plan).status, 'invalid');
  }
});

test('declared incorrect outputs block comparison; missing correctness remains unknown', () => {
  const plan = fixture(); plan.candidate.outputCheck = 'mismatch';
  assert.equal(check(plan).status, 'incomparable');
  assert.equal(check(plan).declaredComparison, null);
  plan.candidate.outputCheck = null;
  assert.equal(check(plan).status, 'insufficient-evidence');
  assert.ok(check(plan).issues.includes('unknown:candidate.outputCheck'));
  delete plan.candidate.outputCheck;
  assert.equal(check(plan).status, 'invalid');
});

test('seconds normalize to milliseconds; incompatible units and metrics cannot produce a ranking', () => {
  const plan = fixture(); plan.candidate.protocol.unit = 's'; plan.candidate.samples = [0.001, 0.003];
  assert.deepEqual(check(plan).declaredComparison, {metric: 'latency', unit: 'ms', baselineMean: 3, candidateMean: 2, candidateMinusBaseline: -1});
  plan.candidate.protocol.metric = 'throughput'; plan.candidate.protocol.unit = 'items/s';
  assert.equal(check(plan).status, 'incomparable');
  assert.equal(check(plan).declaredComparison, null);
  plan.baseline.protocol.metric = 'throughput'; plan.baseline.protocol.unit = 'items/s';
  assert.equal(check(plan).declaredComparison.unit, 'items/s');
  plan.candidate.protocol.unit = 'ms';
  assert.equal(check(plan).status, 'invalid');
  plan.candidate.protocol.unit = 'cycles';
  assert.equal(check(plan).status, 'invalid');
});

test('sample counts must match planned repetitions; null samples, empty samples and zero warmup differ', () => {
  const plan = fixture();
  assert.equal(check(plan).status, 'comparable-declarations');
  plan.candidate.samples = [];
  assert.equal(check(plan).status, 'insufficient-evidence');
  assert.ok(check(plan).issues.includes('sample-count:candidate'));
  plan.candidate.samples = null;
  assert.ok(check(plan).issues.includes('unknown:candidate.samples'));
  assert.equal(check(plan).declaredComparison, null);
  plan.candidate.protocol.repetitions = 0;
  assert.equal(check(plan).status, 'invalid');
});

test('zero metrics and ties stay finite arithmetic; negatives and unsupported numeric values fail', () => {
  const plan = fixture(); plan.baseline.samples = [0, 0]; plan.candidate.samples = [0, 0];
  assert.deepEqual(check(plan).declaredComparison, {metric: 'latency', unit: 'ms', baselineMean: 0, candidateMean: 0, candidateMinusBaseline: 0});
  for (const value of [-1, 1000000001, '2', null, true]) {
    plan.candidate.samples = [value, 2];
    assert.equal(check(plan).status, 'invalid');
  }
  assert.equal(compareBenchmarkProtocols(JSON.stringify(fixture()).replace('[1,3]', '[1e309,3]')).status, 'invalid');
});

test('closed shapes reject unsupported execution claims, non-fictional input and duplicate run IDs', () => {
  const mutations = [
    p => { p.executed = true; }, p => { p.kind = 'measured-benchmark'; },
    p => { p.baseline.passed = true; }, p => { p.candidate.protocol.speedup = 10; },
    p => { p.candidate.id = p.baseline.id; }, p => { p.baseline.device = 'real-hardware'; },
    p => { p.baseline.protocol.configId = 'invented-config\n'; },
    p => { p.baseline.protocol.batchSize = 0; }, p => { p.baseline.protocol.warmupIterations = -1; },
    p => { p.baseline.protocol.repetitions = 65; }, p => { p.schemaVersion = 2; },
  ];
  for (const mutate of mutations) { const p = fixture(); mutate(p); assert.equal(check(p).status, 'invalid'); }
});

test('bounded JSON text rejects malformed input and executable hooks without coercion', () => {
  let called = 0;
  for (const value of [null, {}, [], 3, new String('{}'), {toString() { called++; return '{}'; }}]) {
    assert.equal(compareBenchmarkProtocols(value).status, 'invalid');
  }
  assert.equal(called, 0);
  for (const value of ['', '{', 'null', '[]', ' '.repeat(65537)]) assert.equal(compareBenchmarkProtocols(value).status, 'invalid');
  const p = fixture(); p.baseline.samples = Array(65).fill(1);
  assert.equal(check(p).status, 'invalid');
  p.baseline.samples.pop(); p.baseline.protocol.repetitions = 64;
  p.candidate.samples = Array(64).fill(1); p.candidate.protocol.repetitions = 64;
  assert.equal(check(p).status, 'comparable-declarations');
});

test('ordinary JSON duplicate member semantics use the last value, not a signature assertion', () => {
  const text = JSON.stringify(fixture());
  assert.deepEqual(compareBenchmarkProtocols(text.replace('"batchSize":1', '"batchSize":99,"batchSize":1')), check(fixture()));
  assert.equal(compareBenchmarkProtocols(text.replace('"batchSize":1', '"batchSize":1,"batchSize":99')).status, 'incomparable');
});

test('property order and invocation history cannot change the independent result', () => {
  const plan = fixture(), expected = check(plan);
  plan.baseline.protocol = Object.fromEntries(Object.entries(plan.baseline.protocol).reverse());
  assert.deepEqual(check(plan), expected);
  expected.issues.push('forged'); expected.declaredComparison.baselineMean = 1000;
  assert.equal(check(plan).declaredComparison.baselineMean, 3);
  assert.deepEqual(check(plan).issues, []);
});

test('invented example is executable offline and never hardware or benchmark evidence', () => {
  const text = readFileSync(new URL('../pets/intel/example.json', import.meta.url), 'utf8');
  const result = compareBenchmarkProtocols(text);
  assert.equal(result.status, 'comparable-declarations');
  assert.equal(result.declaredComparison.candidateMean, 2);
  boundary(result);
});
