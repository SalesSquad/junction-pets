import test from 'node:test';
import assert from 'node:assert/strict';
import {plan} from '../cell.mjs';
import {VERSION,prepareSupervisedBatch,runSupervisedBatch,replaySupervisedBatch} from './supervisor.mjs';

const healthy = seed => {
  const r=plan(seed);
  r.episodes.forEach((e,i)=>{
    e.fixtureId = i%2 ? 'scratch-02' : 'clear-01';
    e.grip=true;e.cameraAgreement=true;e.at=100;
    e.operator={decision:'continue',reason:'Operator requests conservative simulation'};
  });
  return r;
};

test('default fault latches all subsequent episodes; unchanged M2 still routes later ones',async()=>{
  const r=await runSupervisedBatch(plan());
  assert.equal(r.provenance.version,VERSION);
  assert.deepEqual(r.trip,{episodeId:'brick-4',index:3,reason:'GRIP_LOSS'});
  assert.equal(r.summary.subsequentBlocked,4);
  assert.equal(r.summary.supervisedPostTripSoftwareBowls,0);
  assert.ok(r.summary.baselinePostTripSoftwareBowls>0);
  assert.deepEqual(r.audit.slice(4).map(x=>x.state),['LATCHED_BLOCK','LATCHED_BLOCK','LATCHED_BLOCK','LATCHED_BLOCK']);
  for (const step of r.supervisedBatch.steps.filter(x=>x.stage==='operator-decision').slice(4)) {
    assert.equal(step.data.coreReceipt.final.bowl,null);
    assert.equal(step.data.outcome,'stop');
  }
  assert.deepEqual(await replaySupervisedBatch(r),r);
});

test('global emergency STOP is persistent, unlike per-item STOP',async()=>{
  const p=healthy(19);
  p.episodes[1].operator={decision:'stop',reason:'Local inspection'};
  const local=await runSupervisedBatch(p);
  assert.equal(local.trip,null);
  assert.equal(local.audit[1].state,'LOCAL_STOP');
  assert.equal(local.supervisedBatch.evaluation.rows[2].conservative,'good');

  const global=await runSupervisedBatch(p,{globalStopEpisodeId:'brick-2'});
  assert.equal(global.trip.reason,'GLOBAL_OPERATOR_STOP');
  assert.equal(global.summary.subsequentBlocked,6);
  assert.equal(global.summary.supervisedPostTripSoftwareBowls,0);
  assert.equal(global.supervisedBatch.evaluation.rows[7].conservative,'stop');
  assert.deepEqual(await replaySupervisedBatch(global),global);
});

test('sensor interlock families trip without allowing software placement beyond fault',async()=>{
  const faults=[
    ['GRIP_LOSS', e=>e.grip=false],
    ['CAMERA_DISAGREEMENT',e=>e.cameraAgreement=false],
    ['CAMERA_MISSING',e=>e.fixtureId='missing-camera-05'],
    ['CAPTURE_STALE',e=>e.at=30001],
    ['PERCEPTION_LOW_CONFIDENCE',e=>e.fixtureId='low-confidence-04']
  ];
  for(const [reason,mutate] of faults){
    const p=healthy(121);mutate(p.episodes[2]);
    const r=await runSupervisedBatch(p);
    assert.equal(r.trip.reason,reason);
    assert.equal(r.supervisedBatch.evaluation.rows[2].conservative,'hold');
    assert.equal(r.summary.subsequentBlocked,5);
    assert.equal(r.summary.supervisedPostTripSoftwareBowls,0);
    await replaySupervisedBatch(r);
  }
});

test('ambiguous score holds locally but does not create an unsupported global E-stop',async()=>{
  const p=healthy(188);p.episodes[2].fixtureId='ambiguous-03';
  const r=await runSupervisedBatch(p);
  assert.equal(r.trip,null);
  assert.equal(r.supervisedBatch.evaluation.rows[2].conservative,'hold');
  assert.equal(r.supervisedBatch.evaluation.rows[3].conservative,'defect');
});

test('unknown controls, episode replay mismatches, and corrupted stop trace fail closed',async()=>{
  const p=healthy(72);
  assert.throws(()=>prepareSupervisedBatch(p,{globalStopEpisodeId:'brick-9'}),/reference/);
  assert.throws(()=>prepareSupervisedBatch(p,{clearLatch:true}),/Unknown/);
  const duplicate=structuredClone(p);duplicate.episodes[1].id=duplicate.episodes[0].id;
  assert.throws(()=>prepareSupervisedBatch(duplicate),/duplicate/);
  const r=await runSupervisedBatch(p,{globalStopEpisodeId:'brick-3'});
  const mutate=[
    x=>x.root='bad',
    x=>x.trip.index=5,
    x=>x.summary.supervisedPostTripSoftwareBowls=1,
    x=>x.supervisedRequest.episodes[6].operator.decision='continue',
    x=>x.supervisedBatch.steps[0].data.slot=999,
    x=>x.supervisedBatch.steps.filter(s=>s.stage==='operator-decision')[5].data.coreReceipt.final.bowl='good',
    x=>x.audit.pop(),
    x=>x.provenance.realActuation=true
  ];
  for(const change of mutate) {
    const x=structuredClone(r);change(x);
    await assert.rejects(()=>replaySupervisedBatch(x));
  }
});
