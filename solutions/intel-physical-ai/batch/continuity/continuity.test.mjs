import test from 'node:test';
import assert from 'node:assert/strict';
import {plan} from '../cell.mjs';
import {genesis,verifyLedger,dispatch,VERSION} from './continuity.mjs';

const permit=async args=>({...args,permit:true,reference:'local-synthetic-host'});
const healthy=seed=>{
  const p=plan(seed);
  for(const [i,e] of p.episodes.entries()){
    e.fixtureId=i%2?'scratch-02':'clear-01';
    e.grip=true;e.cameraAgreement=true;e.at=100;
    e.operator={decision:'continue',reason:'Synthetic operator proceed'};
  }
  return p;
};
const ids=name=>Array.from({length:8},(_,i)=>`${name}-unit-${i+1}`);
const run=(state,name,req=healthy(330))=>({
  kind:'RUN',eventId:`ev-${name}`,expectedRevision:state.state.revision,
  expectedEpoch:state.state.epoch,batchId:`batch-${name}`,
  itemIds:ids(name),batchRequest:req,batchControl:{}
});
const propose=(state,name='rearm-one')=>({
  kind:'PROPOSE_REARM',eventId:`ev-propose-${name}`,
  expectedRevision:state.state.revision,expectedEpoch:state.state.epoch,
  proposalId:name
});
const confirm=(state,name='rearm-one')=>({
  kind:'CONFIRM_REARM',eventId:`ev-confirm-${name}`,
  expectedRevision:state.state.revision,expectedEpoch:state.state.epoch,
  proposalId:name
});
async function admit(state,request,authorize=permit){
  const r=await dispatch(state,request,{authorize});
  assert.equal(r.status,'ADMITTED',r.reason);
  return r.state;
}

test('healthy batches make distinct deterministic software receipts, no physical actuation',async()=>{
  let state=await genesis();
  assert.equal(state.state.phase,'READY');
  state=await admit(state,run(state,'clean-a'));
  assert.equal(state.state.phase,'READY');
  assert.equal(state.state.revision,1);
  assert.equal(state.events[0].outcome.softwareSorted,8);
  state=await admit(state,run(state,'clean-b',healthy(111)));
  assert.equal(state.state.revision,2);
  assert.equal(state.state.usedItemIds.length,16);
  assert.equal((await verifyLedger(state)).root,state.root);
  assert.equal(state.events[1].gate.scope,'RUN');
});

test('M4 grip loss latches across batches until a distinct host-approved rearm',async()=>{
  let state=await genesis();
  state=await admit(state,run(state,'fault',plan(330)));
  assert.equal(state.state.phase,'LATCHED');
  assert.equal(state.state.latch.cause,'GRIP_LOSS');
  const staleBatch=run(state,'attempt');
  const rejected=await dispatch(state,staleBatch,{authorize:permit});
  assert.equal(rejected.status,'DENIED');
  assert.equal(rejected.reason,'GLOBAL_STOP_LATCHED');
  assert.equal(rejected.state.root,state.root);
  state=await admit(state,propose(state));
  assert.equal(state.state.phase,'REARM_PENDING');
  assert.equal((await dispatch(state,run(state,'attempt2'),{authorize:permit})).status,'DENIED');
  const noProof=await dispatch(state,confirm(state));
  assert.equal(noProof.status,'DENIED');
  assert.equal(noProof.reason,'HOST_AUTHORIZATION_MISSING');
  state=await admit(state,confirm(state));
  assert.equal(state.state.phase,'READY');
  assert.equal(state.state.epoch,1);
  state=await admit(state,run(state,'resumed',healthy(442)));
  assert.equal(state.state.revision,4);
  assert.equal(state.events.at(-1).outcome.softwareSorted,8);
  assert.equal((await verifyLedger(state)).root,state.root);
});

test('local item STOP remains per-item; does not trigger GLOBAL latch',async()=>{
  let state=await genesis(),p=healthy(52);
  p.episodes[2].operator={decision:'stop',reason:'Local manual review'};
  state=await admit(state,run(state,'local',p));
  assert.equal(state.state.phase,'READY');
  assert.equal(state.events[0].outcome.softwareSorted,7);
  state=await admit(state,run(state,'next',healthy(51)));
  assert.equal(state.state.phase,'READY');
});

test('exact idempotency cached, mutated same eventId refused and audited without operational mutation',async()=>{
  let state=await genesis(),req=run(state,'once');
  const first=await dispatch(state,req,{authorize:permit});
  assert.equal(first.status,'ADMITTED');
  state=first.state;
  const same=await dispatch(state,req);
  assert.equal(same.status,'CACHED');
  assert.equal(same.state.root,state.root);
  assert.equal(same.receiptHash,first.receiptHash);
  const changed=structuredClone(req);changed.itemIds[0]='new-unit-id';
  const denied=await dispatch(state,changed,{authorize:permit});
  assert.equal(denied.status,'DENIED');
  assert.equal(denied.reason,'IDEMPOTENCY_CONFLICT');
  assert.equal(denied.state.root,state.root);
  assert.equal(state.events.length,1);
  assert.match(denied.auditHash,/^[a-f0-9]{64}$/);
});

test('stale revision and epoch refused, including after rearm',async()=>{
  let state=await genesis();
  state=await admit(state,run(state,'fault',plan()));
  const old=run(await genesis(),'old');
  assert.equal((await dispatch(state,old,{authorize:permit})).reason,'STALE_REVISION');
  state=await admit(state,propose(state));
  state=await admit(state,confirm(state));
  const stale=run(state,'new');
  stale.expectedEpoch=0;
  assert.equal((await dispatch(state,stale,{authorize:permit})).reason,'STALE_EPOCH');
  assert.equal(state.state.epoch,1);
});

test('used physical-item identity is unique globally, even after latch and rearm',async()=>{
  let state=await genesis();
  state=await admit(state,run(state,'fault',plan()));
  state=await admit(state,propose(state));
  state=await admit(state,confirm(state));
  const replay=run(state,'different',healthy(331));
  replay.itemIds[0]='fault-unit-1';
  const rejected=await dispatch(state,replay,{authorize:permit});
  assert.equal(rejected.status,'DENIED');
  assert.equal(rejected.reason,'DUPLICATE_ITEM');
  const duplicateBatch=run(state,'duplicate',healthy(333));
  duplicateBatch.batchId='batch-fault';
  assert.equal((await dispatch(state,duplicateBatch,{authorize:permit})).reason,'DUPLICATE_BATCH');
});

test('no caller-supplied authorization booleans or incorrectly scoped host predicate are accepted',async()=>{
  const state=await genesis(),r=run(state,'noauth');
  assert.equal((await dispatch(state,r)).reason,'HOST_AUTHORIZATION_MISSING');
  assert.equal((await dispatch(state,{...r,authorized:true},{authorize:permit})).reason,'INVALID_RUN_INPUT');
  for(const invalid of [async()=>true,async a=>({...a,permit:true,scope:'REARM',reference:'bad'}),
      async a=>({...a,permit:true,previousRoot:'false',reference:'bad'})]){
    const x=await dispatch(state,r,{authorize:invalid});
    assert.equal(x.reason,'HOST_AUTHORIZATION_MISSING');
    assert.equal(x.state.root,state.root);
  }
});

test('rearm proposal cannot be confirmed early, wrong ID or no host proof leaves latch unchanged',async()=>{
  let state=await genesis();
  assert.equal((await dispatch(state,propose(state))).reason,'NOT_LATCHED');
  state=await admit(state,run(state,'fault',plan()));
  assert.equal((await dispatch(state,confirm(state),{authorize:permit})).reason,'REARM_PROPOSAL_MISSING');
  state=await admit(state,propose(state));
  assert.equal((await dispatch(state,confirm(state,'other'),{authorize:permit})).reason,'REARM_PROPOSAL_MISSING');
  assert.equal((await dispatch(state,confirm(state),{authorize:async()=>{throw Error('offline')}})).reason,'HOST_AUTHORIZATION_MISSING');
  assert.equal(state.state.phase,'REARM_PENDING');
});

test('source replay tamper, altered hash, forged host envelope and invalid structure rejected',async()=>{
  let state=await genesis();
  state=await admit(state,run(state,'good'));
  for(const change of [
    x=>x.root='0',
    x=>x.state.phase='LATCHED',
    x=>x.events[0].outcome.softwareSorted=0,
    x=>x.events[0].request.itemIds[0]='replaced-id',
    x=>x.events[0].gate.reference='forged-host',
    x=>x.events[0].hash='0'
  ]){
    const tampered=structuredClone(state);change(tampered);
    await assert.rejects(()=>verifyLedger(tampered));
    await assert.rejects(()=>dispatch(tampered,run(state,'other'),{authorize:permit}));
  }
});

test('sensor fault families latch while threshold ambiguity only holds without global latch',async()=>{
  for(const fault of ['missing-camera-05','low-confidence-04']){
    let state=await genesis(),request=healthy(18);
    request.episodes[1].fixtureId=fault;
    state=await admit(state,run(state,`fault-${fault}`,request));
    assert.equal(state.state.phase,'LATCHED');
    assert.equal(state.events[0].outcome.postTripSoftwareBowls,0);
  }
  let state=await genesis(),request=healthy(18);
  request.episodes[2].fixtureId='ambiguous-03';
  state=await admit(state,run(state,'ambiguous',request));
  assert.equal(state.state.phase,'READY');
  assert.equal(state.events[0].outcome.softwareSorted,7);
});

test('forked concurrent proposals need external CAS; module does not claim persistence',async()=>{
  let state=await genesis();
  const a=await dispatch(state,run(state,'fork-a'),{authorize:permit});
  const b=await dispatch(state,run(state,'fork-b'),{authorize:permit});
  assert.equal(a.status,'ADMITTED');
  assert.equal(b.status,'ADMITTED');
  assert.equal(a.state.state.revision,b.state.state.revision);
  assert.notEqual(a.state.root,b.state.root);
  // Real host MUST accept at most one via compare-and-swap of original state.root.
});

test('misformed batch, duplicate item IDs, invalid clocks fail without side effects',async()=>{
  const state=await genesis(),bad=run(state,'bad');
  bad.itemIds[2]=bad.itemIds[1];
  assert.equal((await dispatch(state,bad,{authorize:permit})).reason,'INVALID_RUN_INPUT');
  const badTime=run(state,'bad-time');badTime.batchRequest.episodes[0].at=-2;
  assert.equal((await dispatch(state,badTime,{authorize:permit})).reason,'SOURCE_BATCH_REFUSED');
  assert.equal(state.events.length,0);
});

test('explicit GLOBAL operator STOP is latched, host-approved new epoch unblocks only after rearm',async()=>{
  let state=await genesis(),batch=healthy(331);
  state=await admit(state,{...run(state,'global',batch),batchControl:{globalStopEpisodeId:batch.episodes[2].id}});
  assert.equal(state.state.phase,'LATCHED');
  assert.equal(state.state.latch.cause,'GLOBAL_OPERATOR_STOP');
  assert.equal(state.events[0].outcome.postTripSoftwareBowls,0);
  const denied=await dispatch(state,run(state,'newbatch'),{authorize:permit});
  assert.equal(denied.reason,'GLOBAL_STOP_LATCHED');
  state=await admit(state,propose(state));
  state=await admit(state,confirm(state));
  state=await admit(state,run(state,'newbatch'));
  assert.equal(state.state.phase,'READY');
});

test('regression: mutable caller snapshot cannot clear latch while host authorization awaits',async()=>{
  let state=await genesis();
  state=await admit(state,run(state,'race-trip',plan()));
  assert.equal(state.state.phase,'LATCHED');
  const mutable=structuredClone(state);
  let notifyStarted,release;
  const started=new Promise(resolve=>notifyStarted=resolve);
  const delayed=async args=>{
    notifyStarted();
    await new Promise(resolve=>{release=resolve;});
    return {...args,permit:true,reference:'test-host-proof'};
  };
  const pending=dispatch(mutable,run(mutable,'race-bypass',healthy(444)),{authorize:delayed});
  await started;
  mutable.state.phase='READY';
  mutable.state.latch=null;
  release();
  const result=await pending;
  assert.equal(result.status,'DENIED');
  assert.equal(result.reason,'GLOBAL_STOP_LATCHED');
  assert.equal(result.state.state.phase,'LATCHED');
  assert.equal(result.state.root,state.root);
  assert.equal(result.state.events.length,state.events.length);
});

test('regression: sparse and non-JSON item IDs are rejected; holes cannot forge a replayable ledger',async()=>{
  const state=await genesis();
  const sparse=run(state,'sparse',healthy(55));
  sparse.itemIds=new Array(8);
  const rejected=await dispatch(state,sparse,{authorize:permit});
  assert.equal(rejected.status,'DENIED');
  assert.equal(rejected.reason,'INVALID_REQUEST');
  assert.equal(rejected.state.root,state.root);
  const partial=run(state,'partial',healthy(55));
  delete partial.itemIds[0];
  assert.equal((await dispatch(state,partial,{authorize:permit})).status,'DENIED');
  const noReason=run(state,'nullref',healthy(55));
  noReason.batchRequest.episodes[0].operator.reason=undefined;
  assert.equal((await dispatch(state,noReason,{authorize:permit})).reason,'INVALID_REQUEST');
  const nan=run(state,'nan',healthy(55));
  nan.batchRequest.episodes[0].at=NaN;
  assert.equal((await dispatch(state,nan,{authorize:permit})).status,'DENIED');
  const admitted=await admit(state,run(state,'clean-a',healthy(55)));
  const badLedger=structuredClone(admitted);
  delete badLedger.state.usedItemIds[0];
  await assert.rejects(()=>verifyLedger(badLedger));
});
