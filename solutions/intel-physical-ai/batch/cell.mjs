import {createSession, apply, receipt, replayReceipt, digest, canonical, POLICY} from '../core.mjs';
export const VERSION = 'synthetic-batch/1';
export const SOURCE = 'ee2ce767ed779cafa0f048c6b087ce5c84831a7f';
const freeze = value => { if(value && typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value; };
// Truth belongs only to the simulator/evaluator, never the routing policy.
const truth = ['good','defect','good','defect','good','defect','good','defect'];
const fixtures = ['clear-01','scratch-02','ambiguous-03','clear-01','scratch-02','clear-01','clear-01','scratch-02'];
export function plan(seed=330) {
  if(!Number.isSafeInteger(seed) || seed<0 || seed>0xffffffff) throw Error('Seed must be uint32');
  let state=seed;
  const episodes=fixtures.map((fixtureId,i)=>{
    state=(Math.imul(state,1664525)+1013904223)>>>0;
    return {id:`brick-${i+1}`,fixtureId,feedSlot:state%1000,grip:i!==3,cameraAgreement:i!==4,at:i===5?30001:100,
      operator:{decision:i===6?'stop':'continue',reason:i===6?'Operator ends this episode for inspection':'Operator requests conservative simulation'}};
  });
  return {seed,episodes};
}
function validate(input) {
  if(!input || !Number.isSafeInteger(input.seed) || input.seed<0 || input.seed>0xffffffff || !Array.isArray(input.episodes) || input.episodes.length<1 || input.episodes.length>64) throw Error('Invalid batch');
  const ids=new Set();
  for(const e of input.episodes){
    if(!/^[a-z0-9-]{1,64}$/.test(e.id) || ids.has(e.id)) throw Error('Duplicate or invalid episode id');ids.add(e.id);
    if(typeof e.grip!=='boolean' || typeof e.cameraAgreement!=='boolean' || !Number.isSafeInteger(e.at) || e.at<0 || !Number.isSafeInteger(e.feedSlot) || e.feedSlot<0 || e.feedSlot>999 || !['continue','stop'].includes(e.operator?.decision) || typeof e.operator.reason!=='string' || !e.operator.reason.trim() || e.operator.reason.length>240) throw Error('Invalid episode or operator reason');
    createSession(e.fixtureId);
  }
}
export function metrics(rows, key) {
  const counts={total:rows.length,sorted:0,held:0,stopped:0,correctSorted:0,wrongSorted:0,unsafeSorted:0};
  for(const row of rows){
    const outcome=row[key];
    if(['good','defect'].includes(outcome)){
      counts.sorted++; counts[outcome===row.groundTruth?'correctSorted':'wrongSorted']++;
      if(row.hazard)counts.unsafeSorted++;
    } else if(outcome==='hold')counts.held++;
    else if(outcome==='stop')counts.stopped++;
    else throw Error('Invalid metric outcome');
  }
  return {...counts,coverage:counts.total?counts.sorted/counts.total:0,conditionalCorrectness:counts.sorted?counts.correctSorted/counts.sorted:null};
}
export async function runBatch(input=plan()) {
  validate(input);
  const request=structuredClone(input);
  const provenance={version:VERSION,sourceMain:SOURCE,evidence:'SYNTHETIC',generator:'seeded-feed/1',truthGenerator:'independent-labelled-scene/1',policy:'M1-conservative-plus-interlocks/1',actuation:false,realActionAuthorization:false,inference:false};
  let previous=await digest({provenance,request});const inputDigest=previous,steps=[],rows=[];
  const record=async (episodeId,stage,data)=>{
    const body={sequence:steps.length+1,version:VERSION,episodeId,stage,data,previous};
    previous=await digest(body);steps.push({...body,hash:previous});
  };
  for(const [index,e] of request.episodes.entries()){
    let session=createSession(e.fixtureId),n=0;
    const command=type=>{session=apply(session,{id:`batch-${++n}`,type,at:e.at});};
    await record(e.id,'feed',{slot:e.feedSlot,simulated:true});
    await record(e.id,'grip-verification',{retained:e.grip,simulated:true});
    const f=session.fixture;
    await record(e.id,'inspection',{fixtureId:f.id,score:f.score,uncertainty:f.uncertainty,confidence:f.confidence,cameras:f.cameras,cameraAgreement:e.cameraAgreement,captureAgeMs:e.at-f.capturedAt,generator:f.generator});
    let outcome,reason;
    if(e.operator.decision==='stop'){command('stop');outcome='stop';reason='Explicit operator stop';}
    else if(!e.grip || !e.cameraAgreement){command('stop');outcome='hold';reason=!e.grip?'Gripper loss: retained HOLD, no placement':'Camera disagreement: retained HOLD, no placement';}
    else {
      command('gate');
      if(session.state.phase==='stopped'){outcome='hold';reason=`${session.state.reason}: retained HOLD, no placement`;}
      else {
        if(session.state.phase==='uncertain')command('review');
        command('route');outcome=session.state.bowl;reason=session.state.reason;
      }
    }
    const coreReceipt=await receipt(session);
    await record(e.id,'operator-decision',{...e.operator,outcome,reason,coreReceipt});
    // Evaluator joins independent truth only AFTER the policy outcome exists.
    const groundTruth=truth[index%truth.length];
    const hazard=!e.grip || !e.cameraAgreement || e.at-f.capturedAt>POLICY.maxAgeMs || f.confidence<POLICY.minConfidence || !f.cameras.top || !f.cameras.inspection || (f.score-f.uncertainty<=POLICY.threshold && f.score+f.uncertainty>=POLICY.threshold) || e.operator.decision==='stop';
    rows.push({episodeId:e.id,groundTruth,conservative:outcome,baseline:f.score<POLICY.threshold?'good':'defect',hazard});
  }
  const evaluation={label:'SYNTHETIC fixture counts only; not robot accuracy',rows,conservative:metrics(rows,'conservative'),alwaysSortWithoutGate:metrics(rows,'baseline')};
  await record(null,'evaluation',evaluation);
  return freeze({schema:1,provenance,request,inputDigest,steps,evaluation,root:previous});
}
export async function replayBatch(input) {
  if(!input || !Array.isArray(input.steps) || input.steps.length>257)throw Error('Invalid batch receipt');
  for(const s of input.steps)if(s.stage==='operator-decision')await replayReceipt(s.data.coreReceipt);
  const rebuilt=await runBatch(input.request);
  if(canonical(rebuilt)!==canonical(input))throw Error('Batch receipt integrity failure');
  return rebuilt;
}
