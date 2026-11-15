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
    if (!['tieto-sponsor', 'immune-tournament', 'chaos-lab',
         'portfolio-browser', 'new-products-browser'].includes(workload)) {
      input.source_sha = candidate;
    }
    if (workload === 'rokoko-mujoco-v12-pilot') {
      // Generic matrix inventory must use the uniquely reviewed product source,
      // not the arbitrary override used to exercise other bounded workloads.
      input.source_sha = 'c77158f9ae80acc2b1eafaf9284c4397426799b2';
    }
    if (workload === 'rokoko-mujoco-v13-pilot') {
      input.source_sha = 'faec266d6d3a44af3a564f46e0778209c1dc3af1';
    }
    if (['portfolio-browser', 'new-products-browser'].includes(workload)) input.product = 'all';
    const plan = resolvePlan(input, context);
    assert.ok(plan.jobCount >= 1 && plan.jobCount <= 12);
    assert.ok(plan.maxParallel >= 1 && plan.maxParallel <= 8);
    assert.equal(new Set(plan.matrix.include.map(row => row.cell)).size, plan.matrix.include.length);
    for (const row of plan.matrix.include) assert.match(row.source_sha, /^[a-f0-9]{40}$/);
  }
  assert.throws(() => resolvePlan({workload: 'meta-browser', browser: 'firefox'}, context), /Chromium/);
});

test('V8 prospective workload admits exactly one reviewed source and stops at credit cutoff', () => {
  const workload = 'rokoko-mujoco-v8-prospective';
  assert.throws(() => resolvePlan({workload}, context), /requires an explicit source_sha/);
  const admitted = resolvePlan({workload, source_sha: candidate}, context);
  assert.equal(admitted.jobCount, 1);
  assert.deepEqual(admitted.matrix.include.map(x => x.source_sha), [candidate]);
  assert.deepEqual(admitted.matrix.include.map(x => x.qualification), ['product-source']);
  assert.throws(() => resolvePlan({workload, source_sha: candidate}, {
    ...context, now: '2026-11-15T17:00:00Z'}), /deadline/);
});

test('V11 fresh real MuJoCo 800-episode workload requires one exact reviewed source', () => {
  const workload = 'rokoko-mujoco-v11-prospective';
  assert.ok(WORKLOADS.includes(workload));
  assert.throws(() => resolvePlan({workload}, context), /requires an explicit source_sha/);
  const admitted = resolvePlan({workload, source_sha: candidate}, context);
  assert.equal(admitted.jobCount, 1);
  assert.equal(admitted.maxParallel, 1);
  assert.deepEqual(admitted.matrix.include.map(x => x.source_sha), [candidate]);
  assert.deepEqual(admitted.matrix.include.map(x => x.qualification), ['product-source']);
  assert.throws(() => resolvePlan({workload, source_sha: candidate}, {
    ...context, now: '2026-11-15T17:00:00Z'
  }), /deadline/);
});

test('V12 source-trained 144-episode fresh pilot source and deadline are exact inputs', () => {
  const workload = 'rokoko-mujoco-v12-pilot';
  assert.ok(WORKLOADS.includes(workload));
  assert.throws(() => resolvePlan({workload}, context), /requires an explicit source_sha/);
  const source = 'c77158f9ae80acc2b1eafaf9284c4397426799b2';
  const admitted = resolvePlan({workload, source_sha: source}, context);
  assert.throws(() => resolvePlan({workload, source_sha: candidate}, context),
    /V12 pilot requires exact reviewed source_sha/);
  assert.equal(admitted.jobCount, 1);
  assert.equal(admitted.maxParallel, 1);
  assert.deepEqual(admitted.matrix.include.map(x => x.source_sha), [source]);
  assert.deepEqual(admitted.matrix.include.map(x => x.cell), [workload]);
  assert.deepEqual(admitted.matrix.include.map(x => x.qualification), ['product-source']);
  assert.throws(() => resolvePlan({workload, source_sha: source}, {
    ...context, now: '2026-11-15T17:00:00Z'
  }), /deadline/);
});

test('V13 causal original TRAIN admission is a single pinned source and never automatic promotion', () => {
  const workload = 'rokoko-mujoco-v13-causal';
  const exactSource = '0751d78b93855bf70820b03b0a543e123d218baf';
  assert.ok(WORKLOADS.includes(workload));
  assert.throws(() => resolvePlan({workload}, context), /requires an explicit source_sha/);
  const plan = resolvePlan({workload, source_sha: exactSource}, context);
  assert.equal(plan.jobCount, 1);
  assert.equal(plan.maxParallel, 1);
  assert.deepEqual(plan.matrix.include.map(x => x.source_sha), [exactSource]);
  assert.deepEqual(plan.matrix.include.map(x => x.cell), [workload]);
  assert.deepEqual(plan.matrix.include.map(x => x.qualification), ['product-source']);
  assert.throws(() => resolvePlan({workload, source_sha: exactSource}, {
    ...context, creditOpen: 'false',
  }), /closed/);
  assert.throws(() => resolvePlan({workload, source_sha: exactSource}, {
    ...context, now: '2026-11-15T17:00:00Z',
  }), /deadline/);
});

test('V13 new 519024 physics 192-episode pilot requires exact prospective SHA and blocks old study', () => {
  const workload='rokoko-mujoco-v13-pilot';
  const source='faec266d6d3a44af3a564f46e0778209c1dc3af1';
  assert.ok(WORKLOADS.includes(workload));
  assert.throws(()=>resolvePlan({workload}, context), /requires an explicit source_sha/);
  assert.throws(()=>resolvePlan({workload,source_sha:candidate}, context),
    /V13 pilot requires exact prospective source_sha/);
  assert.throws(()=>resolvePlan({workload,source_sha:'c77158f9ae80acc2b1eafaf9284c4397426799b2'}, context),
    /V13 pilot requires exact prospective source_sha/);
  const planned=resolvePlan({workload,source_sha:source},context);
  assert.equal(planned.jobCount,1);
  assert.equal(planned.maxParallel,1);
  assert.deepEqual(planned.matrix.include.map(v=>v.source_sha),[source]);
  assert.deepEqual(planned.matrix.include.map(v=>v.cell),[workload]);
  assert.throws(()=>resolvePlan({workload,source_sha:source},
    {...context,creditOpen:'false'}), /closed/);
  assert.throws(()=>resolvePlan({workload,source_sha:source},
    {...context,now:'2026-11-15T17:00:00Z'}), /deadline/);
});
