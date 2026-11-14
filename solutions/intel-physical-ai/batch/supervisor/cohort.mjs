// Predeclared deterministic synthetic fault matrix. No population inference or GPU.
import {plan} from '../cell.mjs';
import {runSupervisedBatch} from './supervisor.mjs';

const families = [
  ['GRIP_LOSS',e=>{e.grip=false;}],
  ['CAMERA_DISAGREEMENT',e=>{e.cameraAgreement=false;}],
  ['CAMERA_MISSING',e=>{e.fixtureId='missing-camera-05';}],
  ['CAPTURE_STALE',e=>{e.at=30001;}],
  ['PERCEPTION_LOW_CONFIDENCE',e=>{e.fixtureId='low-confidence-04';}],
  ['GLOBAL_OPERATOR_STOP',()=>{}]
];
const positions=[1,3,5];
function clean(seed) {
  const p=plan(seed);
  p.episodes.forEach((e,index)=>{
    e.fixtureId=index%2?'scratch-02':'clear-01';
    e.grip=true;e.cameraAgreement=true;e.at=100;
    e.operator={decision:'continue',reason:'Operator requests conservative simulation'};
  });
  return p;
}
const cols=['scenario','case_id','trip_position','seed','evidence','trip_reason','latched',
  'blocked_after_trip','baseline_post_trip_software_bowls','supervised_post_trip_software_bowls',
  'baseline_total_sorted','supervised_total_sorted','receipt_root'];
console.log(cols.join(','));
let n=0;
for(const [family,applyFault] of families){
 for(const pos of positions) {
  const seed=330+n*19,p=clean(seed);
  const controls=family==='GLOBAL_OPERATOR_STOP'?{globalStopEpisodeId:p.episodes[pos].id}:{};
  applyFault(p.episodes[pos]);
  const receipt=await runSupervisedBatch(p,controls);
  const m=receipt.summary;
  if(receipt.trip?.reason!==family || m.supervisedPostTripSoftwareBowls!==0) {
    throw Error('Fault cohort failed invariant');
  }
  console.log([family,`case-${++n}`,pos,seed,'SYNTHETIC_CONTROLLED',receipt.trip.reason,
    m.globalLatchTrips,m.subsequentBlocked,m.baselinePostTripSoftwareBowls,
    m.supervisedPostTripSoftwareBowls,m.baselineTotalSorted,m.supervisedTotalSorted,receipt.root].join(','));
 }
}
for(const [label,localStop] of [['NO_FAULT',false],['LOCAL_ITEM_STOP',true]]){
 const p=clean(330+n*19);if(localStop)p.episodes[2].operator={decision:'stop',reason:'Local inspection only'};
 const receipt=await runSupervisedBatch(p);
 if(receipt.trip!==null || receipt.summary.subsequentBlocked!==0)throw Error('Unexpected global STOP');
 const m=receipt.summary;
 console.log([label,`case-${++n}`,-1,p.seed,'SYNTHETIC_CONTROLLED','NONE',
   m.globalLatchTrips,m.subsequentBlocked,m.baselinePostTripSoftwareBowls,
   m.supervisedPostTripSoftwareBowls,m.baselineTotalSorted,m.supervisedTotalSorted,receipt.root].join(','));
}
