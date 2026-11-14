import test from 'node:test';
import assert from 'node:assert/strict';
import {plan,runBatch,replayBatch,metrics} from './cell.mjs';
test('eight sequential bricks: gates, retained faults, third bowl and explicit episode stop',async()=>{
  const r=await runBatch();
  assert.deepEqual(r.evaluation.rows.map(x=>x.conservative),['good','defect','hold','hold','hold','hold','stop','defect']);
  assert.equal(r.steps.length,33);
  for(const stage of ['feed','grip-verification','inspection','operator-decision'])assert.equal(r.steps.filter(s=>s.stage===stage).length,8);
  const decisions=r.steps.filter(s=>s.stage==='operator-decision');
  for(const i of [3,4,5,6])assert.equal(decisions[i].data.coreReceipt.final.bowl,null);
  assert.equal(decisions[2].data.coreReceipt.final.bowl,'hold');
  assert.equal(r.provenance.realActionAuthorization,false);assert.ok(Object.isFrozen(r.steps[0].data));
});
test('metrics conserve counts and use correct denominators, including zero sorted',async()=>{
  const r=await runBatch(),c=r.evaluation.conservative,b=r.evaluation.alwaysSortWithoutGate;
  assert.deepEqual(c,{total:8,sorted:3,held:4,stopped:1,correctSorted:3,wrongSorted:0,unsafeSorted:0,coverage:3/8,conditionalCorrectness:1});
  assert.deepEqual(b,{total:8,sorted:8,held:0,stopped:0,correctSorted:5,wrongSorted:3,unsafeSorted:5,coverage:1,conditionalCorrectness:5/8});
  assert.equal(c.total,c.sorted+c.held+c.stopped);assert.equal(b.sorted,b.correctSorted+b.wrongSorted);
  assert.equal(metrics([],'conservative').conditionalCorrectness,null);
  assert.throws(()=>metrics([{conservative:'unknown'}],'conservative'));
});
test('ground truth never shortcuts routing: confidently clear defect still routes good',async()=>{
  const p=plan();p.episodes[3].grip=true;
  const row=(await runBatch(p)).evaluation.rows[3];
  assert.equal(row.groundTruth,'defect');assert.equal(row.conservative,'good');
});
test('M1 missing camera, low confidence and equality remain fail closed',async()=>{
  for(const fixtureId of ['missing-camera-05','low-confidence-04','threshold-touch-06']){
    const p=plan();p.episodes=[{...p.episodes[0],fixtureId}];
    assert.equal((await runBatch(p)).evaluation.rows[0].conservative,'hold');
  }
  const p=plan();p.episodes[0].at=30000;assert.equal((await runBatch(p)).evaluation.rows[0].conservative,'good');
  p.episodes[0].at=30001;assert.equal((await runBatch(p)).evaluation.rows[0].conservative,'hold');
});
test('seeded replay is deterministic and duplicate episode ids fail instead of double counting',async()=>{
  assert.deepEqual(plan(9),plan(9));assert.notDeepEqual(plan(9),plan(10));
  const r=await runBatch(plan(9));assert.deepEqual(await replayBatch(r),r);assert.deepEqual(await replayBatch(r),r);
  const p=plan();p.episodes.push(structuredClone(p.episodes[0]));await assert.rejects(()=>runBatch(p),/Duplicate/);
  for(const seed of [-1,NaN,1.5,2**32])assert.throws(()=>plan(seed));
  const invalid=plan();invalid.episodes[0].operator.reason=' ';await assert.rejects(()=>runBatch(invalid));
});
test('tampered steps, nested M1 receipts, metrics, truth, reasons, provenance and order rejected',async()=>{
  const r=await runBatch();
  for(const mutate of [x=>x.root='0',x=>x.steps[0].data.slot++,x=>x.steps.reverse(),x=>x.steps[3].data.coreReceipt.final.bowl='defect',x=>x.evaluation.conservative.correctSorted++,x=>x.evaluation.rows[0].groundTruth='defect',x=>x.steps[3].data.reason='override',x=>x.provenance.actuation=true,x=>x.request.episodes[0].operator.reason='changed',x=>x.extra=true]){
    const changed=structuredClone(r);mutate(changed);await assert.rejects(()=>replayBatch(changed));
  }
});
