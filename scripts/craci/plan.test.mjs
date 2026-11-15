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
    // Main's frozen Meta R / Lens workloads pin their own harness and reject overrides.
    const harnessPinned = workload.startsWith('meta-r-') || workload.startsWith('lens-');
    if (!harnessPinned && !['tieto-sponsor', 'immune-tournament', 'chaos-lab',
         'portfolio-browser', 'new-products-browser'].includes(workload)) {
      input.source_sha = candidate;
    }
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

test('six HB feedback folds keep train-only source pins and distinct groups',()=>{
 const all=resolvePlan({workload:'lens-hb-six-feedback'},context);
 assert.equal(all.jobCount,6);
 assert.equal(all.maxParallel,4);
 assert.deepEqual(all.matrix.include.map(x=>x.fold),[0,1,2,3,4,5]);
 assert.equal(new Set(all.matrix.include.map(x=>x.cell)).size,6);
 assert.ok(all.matrix.include.every(x=>x.source_sha===context.harnessSha));
 const only=resolvePlan({workload:'lens-hb-six-feedback',learning_fold:'3'},context);
 assert.equal(only.jobCount,1);
 assert.deepEqual(only.matrix.include.map(x=>x.fold),[3]);
 assert.throws(()=>resolvePlan({workload:'lens-hb-six-feedback',source_sha:candidate},context),/exact source\/harness SHA/);
 assert.throws(()=>resolvePlan({workload:'lens-hb-six-feedback',learning_fold:'6'},context),/Unsupported HB six-feedback fold/);
 assert.throws(()=>resolvePlan({workload:'lens-hb-six-feedback'}, {...context,creditOpen:'false'}),/closed/);
 assert.throws(()=>resolvePlan({workload:'lens-hb-six-feedback'}, {...context,now:'2026-11-15T17:00:00Z'}),/deadline/);
});

test('new six-fold unknown risk ML has exact source, pilot and nonrepeating remainder',()=>{
 const all=resolvePlan({workload:'lens-six-unknown-ml'},context);
 assert.equal(all.jobCount,6); assert.equal(all.maxParallel,4);
 assert.deepEqual(all.matrix.include.map(x=>x.fold),[0,1,2,3,4,5]);
 const pilot=resolvePlan({workload:'lens-six-unknown-ml',learning_fold:'0'},context);
 const rest=resolvePlan({workload:'lens-six-unknown-ml',learning_fold:'remaining'},context);
 assert.deepEqual(pilot.matrix.include.map(x=>x.fold),[0]);
 assert.deepEqual(rest.matrix.include.map(x=>x.fold),[1,2,3,4,5]);
 assert.equal(new Set([...pilot.matrix.include,...rest.matrix.include].map(x=>x.cell)).size,6);
 assert.ok(all.matrix.include.every(x=>x.source_sha===context.harnessSha));
 assert.throws(()=>resolvePlan({workload:'lens-six-unknown-ml',source_sha:candidate},context),
                /exact source\/harness SHA/);
 assert.throws(()=>resolvePlan({workload:'lens-six-unknown-ml',learning_fold:'7'},context),
                /Unsupported HB unknown-ML fold/);
 assert.throws(()=>resolvePlan({workload:'lens-six-unknown-ml'},{...context,creditOpen:'false'}),/closed/);
 assert.throws(()=>resolvePlan({workload:'lens-six-unknown-ml'},{...context,now:'2026-11-15T17:00:00Z'}),/deadline/);
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
  const source = '78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f';
  const admitted = resolvePlan({workload, source_sha: source}, context);
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
