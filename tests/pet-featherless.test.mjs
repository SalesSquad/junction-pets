import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {compareModelCandidates} from '../pets/featherless/model-selection.mjs';

const exampleText = readFileSync(new URL('../pets/featherless/example.json', import.meta.url), 'utf8');
const fixture = () => JSON.parse(exampleText);
const run = value => compareModelCandidates(JSON.stringify(value));
const first = value => run(value).candidates[0];
const boundary = result => {
  assert.equal(result.factsVerified, false);
  assert.equal(result.providerRequestExecuted, false);
  assert.equal(result.liveApiSuccess, false);
  assert.equal(result.authorization, false);
  assert.equal(result.throughputTokensPerSecond, null);
  assert.equal(result.rankingScope, 'eligible-supplied-protocol-only');
};
const invalid = value => {
  const result = run(value);
  assert.equal(result.status, 'invalid');
  assert.deepEqual(result.candidates, []);
  assert.deepEqual(result.ranking, []);
  boundary(result);
};

test('worked fictional comparison excludes unknown, failed and incomparable candidates', () => {
  const result = compareModelCandidates(exampleText);
  assert.equal(result.status, 'compared');
  assert.deepEqual(result.candidates.map(({status, rank}) => [status, rank]), [
    ['eligible', 1], ['eligible', 2], ['insufficient-evidence', null],
    ['incomparable', null], ['ineligible', null],
  ]);
  assert.deepEqual(result.ranking, [{id: 'fictional-cinder', rank: 1}, {id: 'fictional-oriole', rank: 2}]);
  assert.equal(result.candidates[2].checks.qualityPercent.reason, 'null');
  assert.equal(result.candidates[2].checks.p95LatencyMs.reason, 'missing');
  assert.equal(result.candidates[3].checks, null);
  assert.equal(result.candidates[4].checks.qualityPercent.status, 'not-met');
  boundary(result);
  assert.deepEqual(compareModelCandidates(exampleText), result);
});

test('quality-first ranking then latency then memory preserves ties and input-order independence', () => {
  const value = fixture();
  const candidate = (id, qualityPercent, p95LatencyMs, peakMemoryMiB) => ({
    id, protocol: {...value.protocol}, metrics: {qualityPercent, p95LatencyMs, peakMemoryMiB},
  });
  value.candidates = [
    candidate('fictional-z', 90, 50, 300), candidate('fictional-a', 90, 50, 300),
    candidate('fictional-b', 90, 50, 400), candidate('fictional-c', 90, 60, 100),
    candidate('fictional-d', 89, 1, 1),
  ];
  const expected = [
    {id: 'fictional-a', rank: 1}, {id: 'fictional-z', rank: 1}, {id: 'fictional-b', rank: 3},
    {id: 'fictional-c', rank: 4}, {id: 'fictional-d', rank: 5},
  ];
  assert.deepEqual(run(value).ranking, expected);
  value.candidates.reverse();
  assert.deepEqual(run(value).ranking, expected);
});

test('inclusive thresholds and zero are known values, never missing or a throughput estimate', () => {
  const value = fixture();
  value.candidates = [value.candidates[0]];
  value.candidates[0].metrics = {qualityPercent: 80, p95LatencyMs: 100, peakMemoryMiB: 600};
  assert.equal(first(value).status, 'eligible');
  for (const [key, number] of [['qualityPercent', 79.999], ['p95LatencyMs', 100.001], ['peakMemoryMiB', 600.001]]) {
    const changed = structuredClone(value);
    changed.candidates[0].metrics[key] = number;
    assert.equal(first(changed).checks[key].status, 'not-met');
  }
  value.requirements = {minQualityPercent: 0, maxP95LatencyMs: 0, maxPeakMemoryMiB: 0};
  value.candidates[0].metrics = {qualityPercent: 0, p95LatencyMs: 0, peakMemoryMiB: 0};
  assert.equal(first(value).status, 'eligible');
  for (const check of Object.values(first(value).checks)) assert.equal(check.value, 0);
  boundary(run(value));
});

test('each omitted, null or explicitly unknown metric stays unknown and unranked', () => {
  for (const key of ['qualityPercent', 'p95LatencyMs', 'peakMemoryMiB']) {
    for (const [value, reason] of [[undefined, 'missing'], [null, 'null'], ['unknown', 'declared-unknown']]) {
      const input = fixture();
      input.candidates = [input.candidates[0]];
      if (value === undefined) delete input.candidates[0].metrics[key];
      else input.candidates[0].metrics[key] = value;
      const result = first(input);
      assert.equal(result.status, 'insufficient-evidence');
      assert.equal(result.rank, null);
      assert.deepEqual(result.checks[key], {status: 'unknown', value: null, reason});
      assert.deepEqual(run(input).ranking, []);
    }
  }
});

test('a known requirement failure dominates unknowns without concealing either', () => {
  const value = fixture();
  value.candidates = [value.candidates[0]];
  value.candidates[0].metrics = {qualityPercent: 79, p95LatencyMs: null};
  const result = first(value);
  assert.equal(result.status, 'ineligible');
  assert.equal(result.rank, null);
  assert.equal(result.checks.qualityPercent.status, 'not-met');
  assert.equal(result.checks.p95LatencyMs.status, 'unknown');
  assert.equal(result.checks.peakMemoryMiB.reason, 'missing');
});

test('every protocol field is compared exactly; mismatches yield no threshold checks or rank', () => {
  for (const key of ['taskSet', 'runtime', 'precision', 'concurrency', 'sampleCount']) {
    const value = fixture();
    value.candidates = [value.candidates[0]];
    value.candidates[0].protocol[key] = typeof value.protocol[key] === 'number' ? value.protocol[key] + 1 : 'other';
    const result = first(value);
    assert.equal(result.status, 'incomparable', key);
    assert.equal(result.rank, null, key);
    assert.equal(result.checks, null, key);
    assert.deepEqual(result.protocolDifferences, [key]);
    assert.deepEqual(run(value).ranking, []);
  }
});

test('unsupported throughput, live success, endorsement and execution claims reject the whole input', () => {
  for (const key of ['throughputTokensPerSecond', 'liveApiSuccess', 'providerRequestExecuted', 'officiallyEndorsed']) {
    for (const target of [v => v, v => v.requirements, v => v.protocol, v => v.candidates[0], v => v.candidates[0].metrics]) {
      const value = fixture();
      target(value)[key] = true;
      invalid(value);
    }
  }
  const value = fixture();
  value.kind = 'live-api-results';
  invalid(value);
});

test('malformed numeric and nested declarations are not silently converted into unknowns', () => {
  for (const malformed of [-1, 101, '92', true, {}, []]) {
    const value = fixture(); value.candidates[0].metrics.qualityPercent = malformed; invalid(value);
  }
  for (const key of ['p95LatencyMs', 'peakMemoryMiB']) for (const malformed of [-1, 1_000_000_001, '1', false, {}, []]) {
    const value = fixture(); value.candidates[0].metrics[key] = malformed; invalid(value);
  }
  for (const mutate of [
    v => {v.requirements.minQualityPercent = null;}, v => {delete v.requirements.maxP95LatencyMs;},
    v => {v.requirements.maxPeakMemoryMiB = 'unknown';}, v => {v.protocol.sampleCount = 1.5;},
    v => {v.protocol.concurrency = 0;}, v => {v.candidates[0].protocol = null;},
    v => {v.protocol.runtime = 'unknown';}, v => {v.candidates[0].protocol.taskSet = 'unknown';},
    v => {v.candidates[0].metrics = null;}, v => {delete v.candidates[0].metrics;},
  ]) { const value = fixture(); mutate(value); invalid(value); }
  assert.equal(compareModelCandidates(exampleText.replace('"qualityPercent": 92', '"qualityPercent": 1e400')).status, 'invalid');
});

test('bounded JSON text only: malformed roots and executable objects are rejected without hooks', () => {
  let calls = 0;
  const object = {toString() {calls++; return exampleText;}, toJSON() {calls++; return fixture();}};
  for (const value of [object, new String(exampleText), null, undefined, true, 1, Symbol('input'), () => exampleText]) {
    const result = compareModelCandidates(value);
    assert.equal(result.status, 'invalid'); boundary(result);
  }
  assert.equal(calls, 0);
  for (const text of ['', '{', 'null', '[]', '{}', '[1]', exampleText + ' trailing']) {
    assert.equal(compareModelCandidates(text).status, 'invalid');
  }
  const poisoned = JSON.parse(exampleText);
  Object.defineProperty(poisoned.candidates[0].metrics, '__proto__', {value: {liveApiSuccess: true}, enumerable: true});
  invalid(poisoned);
});

test('size, count, identity and protocol bounds fail closed while exact boundaries work', () => {
  assert.equal(compareModelCandidates(exampleText + ' '.repeat(32768 - Buffer.byteLength(exampleText))).status, 'compared');
  assert.equal(compareModelCandidates(exampleText + ' '.repeat(32769 - Buffer.byteLength(exampleText))).status, 'invalid');
  const value = fixture();
  value.candidates = Array.from({length: 20}, (_, index) => ({...structuredClone(value.candidates[0]), id: `fictional-${index}`}));
  assert.equal(run(value).candidates.length, 20);
  value.candidates.push({...structuredClone(value.candidates[0]), id: 'fictional-extra'}); invalid(value);
  for (const mutate of [
    v => {v.candidates = [];}, v => {v.candidates[1].id = v.candidates[0].id;},
    v => {v.candidates[0].id = 'real-model';}, v => {v.candidates[0].id = 'fictional-' + 'x'.repeat(71);},
    v => {v.protocol.taskSet = 'x'.repeat(81);}, v => {v.protocol.sampleCount = 1_000_001;},
    v => {v.protocol.concurrency = 1001;},
  ]) {const changed = fixture(); mutate(changed); invalid(changed);}
});

test('ordinary JSON duplicate members use the final value; absent competitors are not invented', () => {
  const duplicate = exampleText.replace('"schemaVersion": 1', '"schemaVersion": 2, "schemaVersion": 1');
  assert.deepEqual(compareModelCandidates(duplicate), compareModelCandidates(exampleText));
  const value = fixture();
  value.candidates = [value.candidates[2], value.candidates[3], value.candidates[4]];
  const result = run(value);
  assert.equal(result.status, 'compared');
  assert.deepEqual(result.ranking, []);
  assert.equal(Object.hasOwn(result, 'bestModel'), false);
  boundary(result);
});
