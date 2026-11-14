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
    const cap = workload === 'meta-r-hardshift-2x' ? 24 : 12;
    if (workload === 'meta-r-hardshift-2x') assert.equal(plan.jobCount, 24);
    assert.ok(plan.jobCount >= 1 && plan.jobCount <= cap);
    assert.ok(plan.maxParallel >= 1 && plan.maxParallel <= 8);
    assert.equal(new Set(plan.matrix.include.map(row => row.cell)).size, plan.matrix.include.length);
    for (const row of plan.matrix.include) assert.match(row.source_sha, /^[a-f0-9]{40}$/);
  }
  assert.throws(() => resolvePlan({workload: 'meta-browser', browser: 'firefox'}, context), /Chromium/);
});
test('eight fresh real-image R/metadata lanes are unique and fail closed', () => {
  const all = resolvePlan({workload:'lens-r8-meta', lane_slice:'all'}, context);
  const pilot = resolvePlan({workload:'lens-r8-meta', lane_slice:'pilot'}, context);
  const remainder = resolvePlan({workload:'lens-r8-meta', lane_slice:'remaining'}, context);
  assert.equal(all.jobCount,8);
  assert.equal(all.maxParallel,8);
  assert.equal(pilot.jobCount,1);
  assert.equal(remainder.jobCount,7);
  assert.deepEqual([...pilot.matrix.include,...remainder.matrix.include].map(r=>r.cell),
                   all.matrix.include.map(r=>r.cell));
  assert.equal(new Set(all.matrix.include.map(r=>r.arm)).size,8);
  assert.ok(all.matrix.include.every(r=>r.source_sha === context.harnessSha));
  assert.throws(()=>resolvePlan({workload:'lens-r8-meta', source_sha:candidate},context),
    /pinned immutable harness/);
  assert.throws(()=>resolvePlan({workload:'lens-r8-meta', lane_slice:'unsupported'},context),
    /Unsupported R8 lane slice/);
});

test('R3 distinct risk, drift, and hard-negative pilots preserve source and green R8 cohorts', () => {
  const all = resolvePlan({workload:'lens-r3-methods',lane_slice:'all'},context);
  const pilot = resolvePlan({workload:'lens-r3-methods',lane_slice:'pilot'},context);
  const remaining = resolvePlan({workload:'lens-r3-methods',lane_slice:'remaining'},context);
  assert.equal(all.jobCount,3);
  assert.equal(all.maxParallel,3);
  assert.deepEqual(all.matrix.include.map(x=>x.method),
                   ['risk-upper','metadata-shield','hard-negative']);
  assert.deepEqual([...pilot.matrix.include,...remaining.matrix.include].map(x=>x.cell),
                   all.matrix.include.map(x=>x.cell));
  assert.equal(new Set(all.matrix.include.map(x=>x.cell)).size,3);
  assert.ok(all.matrix.include.every(x=>x.source_sha===context.harnessSha));
  assert.throws(()=>resolvePlan({workload:'lens-r3-methods',source_sha:candidate},context),
                /pinned immutable harness/);
  assert.throws(()=>resolvePlan({workload:'lens-r3-methods',lane_slice:'invalid'},context),
                /Unsupported R3 lane slice/);
  assert.throws(()=>resolvePlan({workload:'lens-r3-methods'}, {...context, now:'2026-11-15T16:29:00Z'}),
                /31-minute admission cutoff/);
  assert.equal(resolvePlan({workload:'lens-r3-methods'}, {...context, now:'2026-11-15T16:28:59Z'}).jobCount,3);
});
