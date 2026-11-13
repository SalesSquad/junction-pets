import test from 'node:test';
import assert from 'node:assert/strict';
import { example, inspectEvidence, checkClaim } from '../pets/mariadb/explain-example.mjs';

test('synthetic inventory plan distinguishes supplied plan, estimates and unknowns', () => {
  const result = inspectEvidence(example);
  assert.deepEqual(result.facts.rows, { kind: 'estimate', value: 10000 });
  assert.deepEqual(result.facts.filtered, { kind: 'estimate', value: 2 });
  assert.deepEqual(result.facts.key, { kind: 'supplied-plan', value: null });
  assert.deepEqual(result.facts.r_rows, { kind: 'unknown', value: null });
  assert.equal(result.executionVerified, false);
  assert.deepEqual(result.indexGain, { kind: 'unknown', value: null });
  assert.equal(checkClaim(example, { field: 'rows', kind: 'estimate', value: 10000 }), true);
  assert.equal(checkClaim(example, { field: 'rows', kind: 'supplied-observation', value: 10000 }), false);
  assert.equal(checkClaim(example, { field: 'key', kind: 'supplied-plan', value: 'idx_warehouse' }), false);
});

test('supplied ANALYZE observations stay synthetic; zero differs from null and omission', () => {
  const input = structuredClone(example);
  input.format = 'ANALYZE';
  input.row.r_rows = 0;
  input.row.r_filtered = null;
  assert.deepEqual(inspectEvidence(input).facts.r_rows, { kind: 'supplied-observation', value: 0 });
  assert.deepEqual(inspectEvidence(input).facts.r_filtered, { kind: 'unknown', value: null });
  assert.equal(checkClaim(input, { field: 'r_rows', kind: 'supplied-observation', value: 0 }), true);
  assert.equal(checkClaim(input, { field: 'r_filtered', kind: 'supplied-observation', value: 0 }), false);
  assert.equal(inspectEvidence(input).executionVerified, false);
});

test('reject unsupported execution, speedup, index gain and invented field claims', () => {
  for (const field of ['executionVerified', 'indexGain', 'speedup', 'elapsedMs', '__proto__', 'constructor']) {
    assert.equal(checkClaim(example, { field, kind: 'supplied-observation', value: true }), false);
  }
  assert.equal(checkClaim(example, { field: 'rows', kind: 'estimate', value: 1 }), false);
  assert.throws(() => checkClaim(example, { field: 'rows', kind: 'estimate', value: 10000, executed: true }));
});

test('reject malformed, ambiguous and smuggled evidence without numeric coercion', () => {
  for (const value of [-1, NaN, Infinity, '10000', null, undefined]) {
    const input = structuredClone(example); input.row.rows = value;
    assert.throws(() => inspectEvidence(input));
  }
  for (const value of [-1, 101, '2', Infinity]) {
    const input = structuredClone(example); input.row.filtered = value;
    assert.throws(() => inspectEvidence(input));
  }
  for (const mutate of [
    x => { x.row.r_rows = 20; },
    x => { x.provenance = 'measured'; },
    x => { x.row.speedup = 10; },
    x => { x.format = 'ANALYZE FORMAT=JSON'; },
    x => { x.row.possible_keys = 'idx_warehouse'; },
  ]) { const input = structuredClone(example); mutate(input); assert.throws(() => inspectEvidence(input)); }
});

test('classification and claim checks do not mutate or share input data', () => {
  const input = structuredClone(example), before = structuredClone(input);
  const result = inspectEvidence(input);
  result.facts.possible_keys.value.push('invented');
  checkClaim(input, { field: 'rows', kind: 'estimate', value: 10000 });
  assert.deepEqual(input, before);
  delete input.row.filtered;
  assert.deepEqual(inspectEvidence(input).facts.filtered, { kind: 'unknown', value: null });
});

test('claim equality rejects serialization collisions and never calls toJSON', () => {
  for (const value of [NaN, Infinity, -Infinity]) {
    assert.equal(checkClaim(example, { field: 'r_rows', kind: 'unknown', value }), false);
    assert.equal(checkClaim(example, { field: 'key', kind: 'supplied-plan', value }), false);
  }
  let calls = 0;
  const value = { toJSON() { calls++; return 10000; } };
  assert.equal(checkClaim(example, { field: 'rows', kind: 'estimate', value }), false);
  assert.equal(calls, 0);
  assert.equal(checkClaim(example, { field: 'rows', kind: 'estimate', value: '10000' }), false);
  assert.equal(checkClaim(example, { field: 'rows', kind: 'estimate', value: new Number(10000) }), false);
  assert.equal(checkClaim(example, { field: 'r_rows', kind: 'unknown', value: null }), true);
  assert.equal(checkClaim(example, { field: 'key', kind: 'supplied-plan', value: null }), true);
});

test('claim records reject accessors, inherited fields, symbols and hidden extras without reading them', () => {
  let reads = 0;
  for (const field of ['field', 'kind', 'value']) {
    const claim = { field: 'rows', kind: 'estimate', value: 10000 };
    Object.defineProperty(claim, field, { get() { reads++; return field === 'value' ? 10000 : field === 'field' ? 'rows' : 'estimate'; } });
    assert.throws(() => checkClaim(example, claim));
  }
  const inherited = Object.create({ value: 10000 });
  Object.assign(inherited, { field: 'rows', kind: 'estimate' });
  assert.throws(() => checkClaim(example, inherited));
  for (const key of ['hidden', Symbol('extra')]) {
    const claim = { field: 'rows', kind: 'estimate', value: 10000 };
    Object.defineProperty(claim, key, { value: true });
    assert.throws(() => checkClaim(example, claim));
  }
  assert.equal(reads, 0);
});

test('string arrays require exact data elements without getters or serialization hooks', () => {
  const claim = value => ({ field: 'possible_keys', kind: 'supplied-plan', value });
  assert.equal(checkClaim(example, claim(['idx_warehouse'])), true);
  assert.equal(checkClaim(example, claim(['other'])), false);
  assert.equal(checkClaim(example, claim(['idx_warehouse', 'other'])), false);
  assert.equal(checkClaim(example, claim([null])), false);
  assert.equal(checkClaim(example, claim(new Array(1))), false);
  let calls = 0;
  const accessor = [];
  Object.defineProperty(accessor, '0', { get() { calls++; return 'idx_warehouse'; }, enumerable: true });
  const hook = ['wrong'];
  hook.toJSON = () => { calls++; return ['idx_warehouse']; };
  const hidden = ['idx_warehouse'];
  Object.defineProperty(hidden, 'extra', { value: true });
  for (const value of [accessor, hook, hidden]) assert.equal(checkClaim(example, claim(value)), false);
  assert.equal(calls, 0);
});
