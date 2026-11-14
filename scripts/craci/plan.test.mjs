import test from 'node:test';
import assert from 'node:assert/strict';
import {resolvePlan, WORKLOADS} from './plan.mjs';

const harnessSha = '1283d38c0352055fb487f0c2d7af06f86a915f9b';
const candidate = '83c45015f475471a861d663677d060e26b2692c3';
const context = {harnessSha, now: '2026-11-14T08:00:00Z', creditOpen: 'true'};
test('corrected MariaDB and native sources are the source that each cell will check out', () => {
  for (const workload of ['mariadb-runtime', 'native-probe']) {
    const plan = resolvePlan({workload, source_sha: candidate}, context);
    assert.ok(plan.matrix.include.every(cell => cell.source_sha === candidate));
    assert.notEqual(plan.matrix.include[0].source_sha, 'd0be3abf66c86d6817f82ca5ae5598ae003b5360');
  }
});
test('an invalid portfolio default is rejected before fan-out instead of selecting every product', () => {
  for (const workload of ['portfolio-browser', 'new-products-browser']) {
    assert.throws(() => resolvePlan({workload, product: 'stoa'}, context), /product/);
    assert.throws(() => resolvePlan({workload, product: 'all', source_sha: candidate}, context), /one explicit product/);
  }
  const all = resolvePlan({workload: 'portfolio-browser', product: 'all'}, context);
  assert.equal(all.jobCount, 12); assert.equal(all.maxParallel, 8);
  assert.equal(new Set(all.matrix.include.map(row => row.source_sha)).size, 4);
  const one = resolvePlan({workload: 'portfolio-browser', product: 'sbank', browser: 'chromium', source_sha: candidate}, context);
  assert.equal(one.jobCount, 1); assert.equal(one.matrix.include[0].source_sha, candidate);
});
test('closed deadline, malformed source and unsupported sponsor override stop admission', () => {
  assert.throws(() => resolvePlan({}, {...context, creditOpen: 'false'}), /closed/);
  assert.throws(() => resolvePlan({}, {...context, now: '2026-11-15T17:00:00Z'}), /deadline/);
  for (const source_sha of ['main', '83c45015', `${candidate}\n`, `$(echo ${candidate})`]) {
    assert.throws(() => resolvePlan({source_sha}, context), /full lowercase/);
  }
  assert.throws(() => resolvePlan({}, {...context, repository: 'other/repo'}), /Junction-only/);
  assert.throws(() => resolvePlan({workload: 'tieto-sponsor', source_sha: candidate}, context), /unsupported/);
});
test('every fixed workload has bounded cells, full immutable sources and unique receipt keys', () => {
  for (const workload of WORKLOADS) {
    const input = {workload};
    if (['product-browser', 'sbank-sponsor'].includes(workload)) input.source_sha = candidate;
    if (['portfolio-browser', 'new-products-browser'].includes(workload)) input.product = 'all';
    const plan = resolvePlan(input, context);
    assert.ok(plan.jobCount >= 1 && plan.jobCount <= 12);
    assert.ok(plan.maxParallel >= 1 && plan.maxParallel <= 8);
    assert.equal(new Set(plan.matrix.include.map(row => row.cell)).size, plan.matrix.include.length);
    for (const row of plan.matrix.include) assert.match(row.source_sha, /^[a-f0-9]{40}$/);
  }
  assert.throws(() => resolvePlan({workload: 'meta-browser', browser: 'firefox'}, context), /Chromium/);
});

test('R training cohort maps to the exact physics source, never an implicit branch', () => {
  const expected = '59479b42b177c1829a2e6678adfff1fb68aef09c';
  const plan = resolvePlan({workload: 'rokoko-r-tournament', source_sha: expected}, context);
  assert.equal(plan.jobCount, 4);
  assert.equal(plan.maxParallel, 4);
  assert.deepEqual(plan.matrix.include.map(row => row.cohort), [0, 1, 2, 3]);
  assert.ok(plan.matrix.include.every(row => row.source_sha === expected));
  assert.throws(
    () => resolvePlan({workload: 'rokoko-r-tournament', source_sha: candidate}, context),
    /pinned simulator SHA/
  );
});

test('Meta trained model tournament gets eight distinct immutable cohorts', () => {
  const meta = '634f1e0e6cb2de46bcf0a783532d46c23f513d11';
  const matrix = resolvePlan({workload: 'meta-r-tournament', source_sha: meta}, context);
  assert.equal(matrix.jobCount, 8);
  assert.equal(matrix.maxParallel, 8);
  assert.deepEqual(matrix.matrix.include.map(row => row.cohort), [0,1,2,3,4,5,6,7]);
  assert.ok(matrix.matrix.include.every(row => row.source_sha === meta));
  assert.throws(() => resolvePlan({workload: 'meta-r-tournament', source_sha: candidate}, context), /pinned Meta/);
});

test('shift-calibrated Meta R robustness study has twelve independent CPU cohorts', () => {
  const meta = '634f1e0e6cb2de46bcf0a783532d46c23f513d11';
  const robust = resolvePlan({workload: 'meta-r-robust', source_sha: meta}, context);
  assert.equal(robust.jobCount, 12);
  assert.equal(robust.maxParallel, 8);
  assert.deepEqual(robust.matrix.include.map(row => row.cohort),
                   Array.from({length:12},(_,i)=>i));
  assert.equal(new Set(robust.matrix.include.map(row=>row.cell)).size,12);
  assert.ok(robust.matrix.include.every(row=>row.source_sha===meta));
  assert.throws(()=>resolvePlan({workload:'meta-r-robust',source_sha:candidate},context),
                /pinned Meta/);
});
