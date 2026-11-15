import { test } from 'node:test';
import assert from 'node:assert/strict';
import { plan, csvDay, FEATURES, HEADER, sourceHashes, sha } from '../export.mjs';

test('day seeds are unique across all partitions/scenarios', () => {
  const days = plan(4, 42);
  assert.equal(days.length, 52);
  assert.equal(new Set(days.map(d => d.seed)).size, days.length);
  assert.equal(new Set(days.map(d => d.day_id)).size, days.length);
});
test('CSV is deterministic and represents 1440 minute decisions', () => {
  const d = plan()[0], a = csvDay(d);
  assert.equal(sha(a), sha(csvDay(d)));
  assert.equal(a.trim().split('\n').length, 1440);
  assert.equal(a.trim().split('\n').at(-1).split(',')[4], '86340');
});
test('exact hardware feature allowlist excludes target and occupancy', () => {
  assert.deepEqual(FEATURES, ['time_sin', 'time_cos', 'temperature_c', 'rh_percent', 'connected', 'age_seconds']);
  assert(!FEATURES.some(f => /target|occupancy|camera|truth/.test(f)));
  assert.equal(HEADER.at(-1), 'target_occupied');
});
test('schema and bounded seed/day admission', () => {
  for (const n of [3, 49, 4.5, NaN]) assert.throws(() => plan(n));
  for (const s of [-1, 2 ** 32, 1.5]) assert.throws(() => plan(4, s));
  assert.equal(plan(48, 0xffffffff - 1000).length, 624);
  assert.equal(csvDay(plan()[0]).trim().split('\n')[0].split(',').length, HEADER.length);
  assert.equal(Object.keys(sourceHashes()).length, 2);
});
test('fault is held out; disconnected and stale readings are retained', () => {
  const days = plan();
  assert(days.filter(d => d.scenario === 'fault').every(d => d.partition === 'test'));
  const rows = csvDay(days.find(d => d.scenario === 'fault')).trim().split('\n').map(r => r.split(','));
  assert(rows.some(r => r[HEADER.indexOf('connected')] === '0'));
  assert(rows.some(r => r[HEADER.indexOf('age_seconds')] === '40'));
});
test('no lux/camera/hidden truth columns exported; targets are binary', () => {
  assert(!HEADER.some(f => /lux|camera|truth/.test(f)));
  const rows = csvDay(plan()[0]).trim().split('\n').map(r => r.split(','));
  assert(rows.every(r => ['0', '1'].includes(r.at(-1))));
  assert(rows.every(r => r.slice(5).every(v => Number.isFinite(Number(v)))));
});
