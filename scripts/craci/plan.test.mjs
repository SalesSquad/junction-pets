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

test('real MIT-licensed image feature trials use only pinned harness and four nonidentical feature sets', () => {
  const plan = resolvePlan({workload: 'lens-real-bop-train'}, context);
  assert.equal(plan.jobCount, 4);
  assert.equal(plan.maxParallel, 4);
  assert.deepEqual(plan.matrix.include.map(x => x.profile),
                   ['all', 'color', 'spatial', 'gradient']);
  assert.ok(plan.matrix.include.every(x => x.source_sha === context.harnessSha));
  assert.throws(() => resolvePlan({workload: 'lens-real-bop-train',source_sha:candidate},context),
                /pinned harness SHA/);
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
});

test('HB real AppleVision open-set source is pinned, four models and independently sliceable', () => {
  const all = resolvePlan({workload:'lens-hb-vision',lane_slice:'all'},context);
  const pilot = resolvePlan({workload:'lens-hb-vision',lane_slice:'pilot'},context);
  const remaining = resolvePlan({workload:'lens-hb-vision',lane_slice:'remaining'},context);
  assert.equal(all.jobCount,4);
  assert.equal(all.maxParallel,4);
  assert.deepEqual(all.matrix.include.map(x=>x.model),
    ['color','vision_prototype','vision_pca','vision_guard']);
  assert.equal(pilot.jobCount,1);
  assert.equal(remaining.jobCount,3);
  assert.deepEqual([...pilot.matrix.include,...remaining.matrix.include].map(x=>x.cell),
    all.matrix.include.map(x=>x.cell));
  assert.ok(all.matrix.include.every(x=>x.source_sha===context.harnessSha));
  assert.throws(()=>resolvePlan({workload:'lens-hb-vision',source_sha:candidate},context),
    /exact harness source SHA/);
  assert.throws(()=>resolvePlan({workload:'lens-hb-vision',lane_slice:'invalid'},context),
    /Unsupported HB lane slice/);
});

test('fresh public HB scene8 OOD has exactly one pinned source, no old-scene replay',()=>{
 const p=resolvePlan({workload:'lens-hb-scene8-ood'},context);
 assert.equal(p.jobCount,1);
 assert.equal(p.maxParallel,1);
 assert.deepEqual(p.matrix.include.map(x=>x.scene),[8]);
 assert.deepEqual(p.matrix.include.map(x=>x.cell),['hb-scene8-ood-public']);
 assert.equal(p.matrix.include[0].source_sha,context.harnessSha);
 assert.throws(()=>resolvePlan({workload:'lens-hb-scene8-ood',source_sha:candidate},context),
   /exact source\/harness SHA/);
});

test('HB source-defect repair admits only two changed Vision model selection paths', () => {
  const repair = resolvePlan({workload:'lens-hb-vision', lane_slice:'selection-repair'}, context);
  assert.equal(repair.jobCount,2);
  assert.deepEqual(repair.matrix.include.map(x=>x.model), ['vision_prototype','vision_guard']);
  assert.ok(repair.matrix.include.every(x=>x.source_sha===context.harnessSha));
  assert.equal(repair.maxParallel,2);
  assert.throws(()=>resolvePlan({
    workload:'lens-hb-vision',lane_slice:'selection-repair',source_sha:candidate
  },context),/exact harness source SHA/);
});
