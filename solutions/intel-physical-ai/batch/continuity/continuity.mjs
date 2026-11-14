// Source-bound synthetic continuity; no robot, hardware authorization, or secure host.
import {canonical,digest} from '../../core.mjs';
import {runSupervisedBatch} from '../supervisor/supervisor.mjs';

export const VERSION='synthetic-continuity/1';
export const MAX_EVENTS=64;
export const MAX_ITEMS=1024;
const fmt='intel-batch-epoch-ledger/v1';
const copy=x=>structuredClone(x);
// Trust-boundary data must be dense, acyclic, plain JSON. In particular,
// JSON.stringify/canonical must NEVER collapse [undefined] into [].
function checkedJsonClone(input) {
  // Materialize only data properties, exactly once, before any await. A getter
  // may return one value to validation and a different value to JSON.stringify,
  // so never serialize or reread caller-owned property values after checking.
  const visiting=new WeakSet();
  let nodesLeft=100000,charsLeft=8*1024*1024;
  const spend=n=>{
    charsLeft-=n;
    if(charsLeft<0)reject('NON_JSON_VALUE');
  };
  const normalize=(value,depth)=>{
    if(--nodesLeft<0||depth>64)reject('NON_JSON_VALUE');
    if(typeof value==='string'){spend(value.length);return value;}
    if(value===null||typeof value==='boolean')return value;
    if(typeof value==='number'&&Number.isFinite(value))return value;
    if(typeof value!=='object'||visiting.has(value))reject('NON_JSON_VALUE');
    visiting.add(value);
    let result;
    if(Array.isArray(value)){
      const keys=Reflect.ownKeys(value);
      if(value.length>100000||keys.length!==value.length+1)
        reject('NON_JSON_ARRAY');
      result=[];
      for(let i=0;i<value.length;i++){
        const d=Object.getOwnPropertyDescriptor(value,String(i));
        if(!d||!d.enumerable||!Object.hasOwn(d,'value'))
          reject('NON_JSON_ARRAY');
        result.push(normalize(d.value,depth+1));
      }
    }else{
      if(![Object.prototype,null].includes(Object.getPrototypeOf(value)))
        reject('NON_JSON_VALUE');
      result={};
      const keys=Reflect.ownKeys(value);
      if(keys.length>2048)reject('NON_JSON_VALUE');
      for(const key of keys){
        if(typeof key!=='string'||['__proto__','constructor','prototype'].includes(key))
          reject('NON_JSON_VALUE');
        const d=Object.getOwnPropertyDescriptor(value,key);
        if(!d||!d.enumerable||!Object.hasOwn(d,'value'))
          reject('NON_JSON_VALUE');
        spend(key.length);
        result[key]=normalize(d.value,depth+1);
      }
    }
    visiting.delete(value);
    return result;
  };
  return normalize(input,0);
}

const freeze=x=>{
  if(x&&typeof x==='object'){for(const v of Object.values(x))freeze(v);Object.freeze(x);}
  return x;
};
const record=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const hasKeys=(x,keys)=>record(x)&&Object.keys(x).sort().join('|')===keys.slice().sort().join('|');
const validId=x=>typeof x==='string'&&/^[a-z0-9][a-z0-9-]{2,63}$/.test(x);
const whole=x=>Number.isSafeInteger(x)&&x>=0;
const reject=reason=>{throw Error(reason);};

function validRequest(r) {
  if(!record(r)||!['RUN','PROPOSE_REARM','CONFIRM_REARM'].includes(r.kind)||
     !validId(r.eventId)||!whole(r.expectedRevision)||!whole(r.expectedEpoch))reject('INVALID_REQUEST');
  if(r.kind==='RUN'){
    if(!hasKeys(r,['kind','eventId','expectedRevision','expectedEpoch','batchId','itemIds','batchRequest','batchControl']) ||
       !validId(r.batchId)||!Array.isArray(r.itemIds) ||
       !r.itemIds.length||r.itemIds.length>64||Object.keys(r.itemIds).length!==r.itemIds.length||
       Array.from(r.itemIds).some(x=>!validId(x))||
       new Set(r.itemIds).size!==r.itemIds.length ||
       !record(r.batchRequest)||!hasKeys(r.batchControl,[])&&!hasKeys(r.batchControl,['globalStopEpisodeId'])||!Array.isArray(r.batchRequest.episodes)||
       r.batchRequest.episodes.length!==r.itemIds.length)reject('INVALID_RUN_INPUT');
  } else if (!hasKeys(r,['kind','eventId','expectedRevision','expectedEpoch','proposalId'])||
             !validId(r.proposalId))reject('INVALID_REARM_INPUT');
}

function validateGate(gate,scope,requestHash,snapshot) {
  if(!hasKeys(gate,['permit','scope','requestHash','previousRoot','revision','epoch','reference'])||
     gate.permit!==true||gate.scope!==scope||gate.requestHash!==requestHash||
     gate.previousRoot!==snapshot.root||gate.revision!==snapshot.state.revision||
     gate.epoch!==snapshot.state.epoch||!validId(gate.reference))reject('HOST_AUTHORIZATION_MISSING');
  // This is a host-injected decision envelope, NOT a signature/proof of identity.
  // A caller capable of injecting a forged callback can forge approvals.
}

export async function genesis() {
  const state={revision:0,epoch:0,phase:'READY',latch:null,proposalId:null,
    usedBatchIds:[],usedItemIds:[]};
  const snapshot={format:fmt,version:VERSION,state,events:[]};
  return freeze({...snapshot,root:await digest(snapshot)});
}

async function advance(snapshot,request,gate) {
  validRequest(request);
  const s=snapshot.state;
  if(request.expectedRevision!==s.revision)reject('STALE_REVISION');
  if(request.expectedEpoch!==s.epoch)reject('STALE_EPOCH');
  if(snapshot.events.length>=MAX_EVENTS)reject('LEDGER_CAPACITY_EXHAUSTED');
  const requestHash=await digest(request);
  let next=copy(s),outcome;
  if(request.kind==='RUN'){
    if(s.phase!=='READY')reject('GLOBAL_STOP_LATCHED');
    if(s.usedBatchIds.includes(request.batchId))reject('DUPLICATE_BATCH');
    if(request.itemIds.some(id=>s.usedItemIds.includes(id)))reject('DUPLICATE_ITEM');
    if(s.usedItemIds.length+request.itemIds.length>MAX_ITEMS)reject('ITEM_CAPACITY_EXHAUSTED');
    validateGate(gate,'RUN',requestHash,snapshot);
    let result;
    try{result=await runSupervisedBatch(request.batchRequest,request.batchControl);}
    catch{reject('SOURCE_BATCH_REFUSED');}
    if(result.trip&&result.summary.supervisedPostTripSoftwareBowls!==0)
      reject('UNSAFE_SOURCE_TRIP');
    outcome={batchId:request.batchId,trip:copy(result.trip),
      root:result.root,baselineRoot:result.baselineRoot,
      supervisedRoot:result.supervisedBatch.root,
      softwareSorted:result.summary.supervisedTotalSorted,
      postTripSoftwareBowls:result.summary.supervisedPostTripSoftwareBowls};
    next.usedBatchIds.push(request.batchId);
    next.usedItemIds.push(...request.itemIds);
    if(result.trip){
      next.phase='LATCHED';
      next.latch={batchId:request.batchId,episodeId:result.trip.episodeId,
                  cause:result.trip.reason,atRevision:s.revision+1};
    }
  }else if(request.kind==='PROPOSE_REARM'){
    if(s.phase!=='LATCHED')reject('NOT_LATCHED');
    if(gate!==null)reject('PROPOSAL_CANNOT_AUTHORIZE');
    next.phase='REARM_PENDING';next.proposalId=request.proposalId;
    outcome={proposalId:request.proposalId,cleared:false};
  }else{
    if(s.phase!=='REARM_PENDING'||request.proposalId!==s.proposalId)
      reject('REARM_PROPOSAL_MISSING');
    if(s.epoch===Number.MAX_SAFE_INTEGER)reject('EPOCH_EXHAUSTED');
    validateGate(gate,'REARM',requestHash,snapshot);
    next.phase='READY';next.epoch++;
    next.latch=null;next.proposalId=null;
    outcome={cleared:true,nextEpoch:next.epoch,hostApprovalReference:gate.reference};
  }
  next.revision++;
  const previous=snapshot.root;
  const entryCore={seq:next.revision,request:copy(request),gate:copy(gate),outcome:copy(outcome),
    previous};
  const entry={...entryCore,hash:await digest(entryCore)};
  const events=[...snapshot.events,entry];
  const beforeRoot={format:fmt,version:VERSION,state:next,events};
  return freeze({...beforeRoot,root:await digest(beforeRoot)});
}

// Verifies recomputed source decisions, replay sequence, source receipts, and all
// changes in the local ledger. No cryptographic identity/host trust is provided.
export async function verifyLedger(snapshot){
  // Snapshot is detached synchronously, before replay's first await.
  snapshot=checkedJsonClone(snapshot);
  if(!record(snapshot)||snapshot.format!==fmt||snapshot.version!==VERSION||
     !record(snapshot.state)||!Array.isArray(snapshot.events)||
     snapshot.events.length>MAX_EVENTS||typeof snapshot.root!=='string')
    reject('INVALID_LEDGER');
  let rebuilt=await genesis();
  for(const stored of snapshot.events){
    if(!record(stored)||!record(stored.request))reject('INVALID_LEDGER_ENTRY');
    const next=await advance(rebuilt,stored.request,stored.gate);
    const last=next.events[next.events.length-1];
    if(canonical(last)!==canonical(stored))reject('LEDGER_TAMPERED');
    rebuilt=next;
  }
  if(canonical(rebuilt)!==canonical(snapshot))reject('LEDGER_TAMPERED');
  return rebuilt;
}

async function denied(snapshot,request,reason){
  // Host may persist this separately as a denied audit; operational revision,
  // epoch, and source ledger remain EXACTLY unchanged on refusal.
  const denial={status:'DENIED',reason,operationalRoot:snapshot.root,
    eventId:validId(request?.eventId)?request.eventId:null};
  return freeze({...denial,auditHash:await digest(denial),state:snapshot});
}

// The trusted host must validate the operator/device outside this module,
// and durably compare-and-swap the returned state against previousRoot BEFORE
// acknowledging. Without CAS/host admission, this is a synthetic algorithm.
export async function dispatch(snapshot,request,{authorize}={}){
  // Snapshot and request may be caller-owned mutable objects. Copy the request
  // before the first await; use the rebuilt immutable ledger, not the caller's
  // snapshot. Otherwise a concurrent mutation can clear a LATCHED state while
  // the asynchronous host admission callback is waiting.
  let immutableRequest;
  try{immutableRequest=checkedJsonClone(request);}
  catch{immutableRequest=null;}
  snapshot=await verifyLedger(snapshot);
  if(immutableRequest===null)return denied(snapshot,null,'INVALID_REQUEST');
  request=immutableRequest;
  try{validRequest(request);}catch(e){return denied(snapshot,request,e.message);}
  const earlier=snapshot.events.find(e=>e.request.eventId===request.eventId);
  if(earlier){
    if(canonical(earlier.request)!==canonical(request))
      return denied(snapshot,request,'IDEMPOTENCY_CONFLICT');
    return freeze({status:'CACHED',state:snapshot,receiptHash:earlier.hash,
      result:copy(earlier.outcome),operationalRoot:snapshot.root});
  }
  if(request.expectedRevision!==snapshot.state.revision)
    return denied(snapshot,request,'STALE_REVISION');
  if(request.expectedEpoch!==snapshot.state.epoch)
    return denied(snapshot,request,'STALE_EPOCH');
  let gate=null;
  if(request.kind==='RUN'||request.kind==='CONFIRM_REARM'){
    const scope=request.kind==='RUN'?'RUN':'REARM';
    const hostInput=freeze({scope,requestHash:await digest(request),
      previousRoot:snapshot.root,revision:snapshot.state.revision,
      epoch:snapshot.state.epoch});
    try{
      if(typeof authorize!=='function')reject('HOST_AUTHORIZATION_MISSING');
      gate=checkedJsonClone(await authorize(hostInput));
      validateGate(gate,scope,hostInput.requestHash,snapshot);
    }catch{return denied(snapshot,request,'HOST_AUTHORIZATION_MISSING');}
  }
  try{
    const next=await advance(snapshot,request,gate);
    const entry=next.events[next.events.length-1];
    return freeze({status:'ADMITTED',state:next,receiptHash:entry.hash,
      result:copy(entry.outcome),previousRoot:snapshot.root,
      operationalRoot:next.root});
  }catch(e){return denied(snapshot,request,e.message);}
}
