import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {reviewPerceptionCoverage} from '../pets/scailab/perception-coverage.mjs';

const fixture = () => ({
  schemaVersion: 1, fictional: true, scenarioId: 'invented-warehouse',
  requiredWeather: ['clear', 'rain'], requiredOcclusion: ['none', 'partial'],
  minimumSamples: {synthetic: 5, real: 2}, realEvaluationSplit: 'held-out',
  strata: ['clear', 'rain'].flatMap(weather => ['none', 'partial'].map(occlusion => ({
    weather, occlusion, syntheticSamples: 5, realSamples: 2,
  }))),
});
const review = input => reviewPerceptionCoverage(JSON.stringify(input));

test('complete fictional declarations cover the required Cartesian matrix, not measured performance', () => {
  const result = review(fixture());
  assert.equal(result.status, 'declared-coverage-complete');
  assert.deepEqual(result.summary, {requiredStrata: 4, declaredStrata: 4, missingStrata: 0,
    unknownStrata: 0, belowMinimumStrata: 0, coveredDeclaredStrata: 4});
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.boundary, {fictional: true, countsUserDeclared: true,
    realDataInspected: false, mlPerformanceMeasured: false, simToRealTransferVerified: false,
    safetyValidated: false, providerExecuted: false});
});

test('required cross-product detects a missing weather/occlusion cell despite both axes being represented', () => {
  const input = fixture();
  input.strata.pop();
  const result = review(input);
  assert.equal(result.status, 'needs-attention');
  assert.equal(result.summary.requiredStrata, 4);
  assert.equal(result.summary.missingStrata, 1);
  assert.deepEqual(result.strata[3], {weather: 'rain', occlusion: 'partial',
    syntheticSamples: null, realSamples: null, status: 'missing'});
  assert.deepEqual(result.findings, [{code: 'missing-stratum', weather: 'rain', occlusion: 'partial'}]);
});

test('synthetic volume cannot compensate for zero real samples and minimum counts are inclusive', () => {
  const input = fixture();
  input.strata[0].syntheticSamples = 1000000;
  input.strata[0].realSamples = 0;
  input.strata[1].syntheticSamples = 4;
  const result = review(input);
  assert.equal(result.summary.belowMinimumStrata, 2);
  assert.equal(result.summary.coveredDeclaredStrata, 2);
  assert.deepEqual(result.findings.map(f => f.code), ['real-below-minimum', 'synthetic-below-minimum']);
  assert.equal(result.strata[0].realSamples, 0);
  assert.equal(result.strata[2].status, 'covered-declared');
});

test('unknown sample counts stay unknown while a known deficient count still produces its own finding', () => {
  const input = fixture();
  input.strata[0].syntheticSamples = null;
  input.strata[0].realSamples = 0;
  input.strata[1].realSamples = null;
  const result = review(input);
  assert.equal(result.summary.unknownStrata, 2);
  assert.equal(result.summary.belowMinimumStrata, 0);
  assert.equal(result.strata[0].status, 'unknown');
  assert.deepEqual(result.findings.map(f => f.code),
    ['synthetic-count-unknown', 'real-below-minimum', 'real-count-unknown']);
});

test('unknown or overlapping real evaluation split blocks a complete declaration verdict', () => {
  for (const [split, code] of [[null, 'real-split-unknown'], ['training-overlap', 'real-split-training-overlap']]) {
    const input = fixture();
    input.realEvaluationSplit = split;
    const result = review(input);
    assert.equal(result.status, 'needs-attention');
    assert.equal(result.summary.coveredDeclaredStrata, 4);
    assert.deepEqual(result.findings, [{code}]);
    assert.equal(result.boundary.simToRealTransferVerified, false);
  }
});

test('axis and row order do not affect deterministic output; non-text objects are never inspected', () => {
  const original = fixture();
  const reordered = fixture();
  reordered.requiredWeather.reverse();
  reordered.requiredOcclusion.reverse();
  reordered.strata.reverse();
  assert.deepEqual(review(reordered), review(original));
  let invoked = false;
  const hostile = {toString() {invoked = true; throw Error('must not call');}};
  assert.throws(() => reviewPerceptionCoverage(hostile), TypeError);
  assert.equal(invoked, false);
});

test('duplicate, unrequested and malformed strata fail closed alongside unsupported keys', () => {
  const cases = [
    input => input.strata.push({...input.strata[0]}),
    input => {input.strata[0].weather = 'snow';},
    input => {input.strata[0].occlusion = 'invisible';},
    input => input.requiredWeather.push('clear'),
    input => {input.requiredOcclusion = [];},
    input => {input.strata[0].accuracy = 0.99;},
    input => {input.minimumSamples.safety = true;},
    input => {input.apiToken = 'fictional-not-a-secret';},
    input => {delete input.strata[0].realSamples;},
  ];
  for (const mutate of cases) {const input = fixture(); mutate(input); assert.throws(() => review(input), TypeError);}
});

test('bounded JSON, safe integer counts and positive thresholds are enforced', () => {
  for (const value of [-1, 1.5, 1000001, '2', true]) {
    const input = fixture(); input.strata[0].realSamples = value;
    assert.throws(() => review(input), TypeError);
  }
  for (const value of [0, null, 1.1, 1000001]) {
    const input = fixture(); input.minimumSamples.synthetic = value;
    assert.throws(() => review(input), TypeError);
  }
  for (const text of ['{', 'null', '[]', ' '.repeat(32769),
    JSON.stringify(fixture()).replace('"syntheticSamples":5', '"syntheticSamples":1e999')]) {
    assert.throws(() => reviewPerceptionCoverage(text), TypeError);
  }
  const many = fixture(); many.strata = Array(13).fill(many.strata[0]);
  assert.throws(() => review(many), TypeError);
});

test('invented example reports one missing, one unknown and one below-minimum stratum', async () => {
  const raw = await readFile(new URL('../pets/scailab/examples/fictional-coverage.json', import.meta.url), 'utf8');
  const result = reviewPerceptionCoverage(raw);
  assert.equal(result.scenarioId, 'invented-loading-bay');
  assert.equal(result.status, 'needs-attention');
  assert.deepEqual(result.summary, {requiredStrata: 4, declaredStrata: 3, missingStrata: 1,
    unknownStrata: 1, belowMinimumStrata: 1, coveredDeclaredStrata: 1});
  assert.deepEqual(result.findings.map(f => f.code),
    ['real-count-unknown', 'real-below-minimum', 'missing-stratum']);
});

test('fictional marker and schema are mandatory; returned records are independent across calls', () => {
  for (const mutate of [input => {input.fictional = false;}, input => {input.schemaVersion = 2;},
    input => {input.scenarioId = 'x'.repeat(65);}]) {
    const input = fixture(); mutate(input); assert.throws(() => review(input), TypeError);
  }
  const raw = JSON.stringify(fixture());
  const result = reviewPerceptionCoverage(raw);
  result.strata[0].realSamples = 999;
  result.boundary.simToRealTransferVerified = true;
  const fresh = reviewPerceptionCoverage(raw);
  assert.equal(fresh.strata[0].realSamples, 2);
  assert.equal(fresh.boundary.simToRealTransferVerified, false);
});
