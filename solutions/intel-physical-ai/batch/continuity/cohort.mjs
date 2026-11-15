// Synthetic controlled comparison: M4 fresh-batch reset vs M5 cross-batch latch.
// Not an i.i.d. benchmark, physical experiment, safety claim, or GPU run.
import {plan} from '../cell.mjs';
import {runSupervisedBatch} from '../supervisor/supervisor.mjs';
import {genesis,dispatch,verifyLedger} from './continuity.mjs';
import {digest} from '../../core.mjs';

const fail=(msg)=>{throw Error(msg);};
const permit=async a=>({...a,permit:true,reference:'synthetic-cohort-host'});
const clean=(seed)=>{
  const p=plan(seed);
  p.episodes.forEach((e,i)=>{
    e.fixtureId=i%2?'scratch-02':'clear-01';e.grip=true;
    e.cameraAgreement=true;e.at=100;
    e.operator={decision:'continue',reason:'Synthetic continue'};
  });
  return p;
};
const families=[
  ['GRIP_LOSS',e=>{e.grip=false;}],
  ['CAMERA_DISAGREEMENT',e=>{e.cameraAgreement=false;}],
  ['CAMERA_MISSING',e=>{e.fixtureId='missing-camera-05';}],
  ['CAPTURE_STALE',e=>{e.at=30001;}],
  ['PERCEPTION_LOW_CONFIDENCE',e=>{e.fixtureId='low-confidence-04';}],
  ['GLOBAL_OPERATOR_STOP',()=>{}]
];
const request=(snapshot,id,batch,control={})=>({
  kind:'RUN',eventId:'run-'+id,
  expectedRevision:snapshot.state.revision,
  expectedEpoch:snapshot.state.epoch,
  batchId:'batch-'+id,
  itemIds:Array.from({length:batch.episodes.length},(_,i)=>id+'-physical-'+i),
  batchRequest:batch,batchControl:control
});
const results=[];
let n=0,naiveSoftwarePlacements=0;
for(const [family,applyFault] of families){
 for(const position of [1,3,5]){
  const id=String(++n).padStart(2,'0'),fault=clean(330+n*19),next=clean(600+n);
  applyFault(fault.episodes[position]);
  const control=family==='GLOBAL_OPERATOR_STOP'?
    {globalStopEpisodeId:fault.episodes[position].id}:{};
  const baselineTrip=await runSupervisedBatch(fault,control);
  if(baselineTrip.trip?.reason!==family)fail('Wrong fault '+family);
  const naiveFresh=await runSupervisedBatch(next);
  const naive=naiveFresh.summary.supervisedTotalSorted;
  naiveSoftwarePlacements+=naive;
  let snapshot=await genesis();
  const trip=await dispatch(snapshot,request(snapshot,id+'-trip',fault,control),
    {authorize:permit});
  if(trip.status!=='ADMITTED')fail('M5 trip not admitted '+trip.reason);
  snapshot=trip.state;
  if(snapshot.state.phase!=='LATCHED')fail('M5 latch missing');
  const newBatch=await dispatch(snapshot,request(snapshot,id+'-fresh',next),
    {authorize:permit});
  if(newBatch.status!=='DENIED'||newBatch.reason!=='GLOBAL_STOP_LATCHED'||
     newBatch.state.root!==snapshot.root)
    fail('M5 fresh batch bypassed');
  await verifyLedger(snapshot);
  results.push({family,position,caseId:id,
    expectedM4FreshBatchSoftwarePlacements:naive,
    m5NewBatchSoftwarePlacements:0,
    m5Denial:newBatch.reason,
    m4TripRoot:baselineTrip.root,m5Root:snapshot.root});
 }
}
if(results.length!==18||results.some(x=>x.expectedM4FreshBatchSoftwarePlacements!==8||
    x.m5NewBatchSoftwarePlacements!==0))fail('Cohort result invariant');
const summary={
  evidence:'SYNTHETIC_CONTROLLED',mode:'OFFLINE_NONACTUATING',
  validComparisons:18,source:'M4 @ a31e2b314037f4a345ad4dbe3cd74a9e8df5712a',
  semanticUnit:'six fault families x three positions, same 8-brick fixture',
  priorM4FreshBatchSoftwarePlacements:naiveSoftwarePlacements,
  M5PostLatchNewBatchSoftwarePlacements:0,
  note:'Avoiding additional software bowl placements is not measured physical safety, accuracy or throughput',
  results
};
console.log(JSON.stringify({...summary,sha256:await digest(summary)},null,2));
