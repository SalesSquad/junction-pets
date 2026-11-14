import {plan} from '../cell.mjs';
import {genesis,dispatch,verifyLedger,VERSION} from './continuity.mjs';

const hostStub=async input=>({...input,permit:true,reference:'test-only-local-host'});
const healthy=(seed)=>{
  const p=plan(seed);
  p.episodes.forEach((episode,index)=>{
    episode.fixtureId=index%2?'scratch-02':'clear-01';
    episode.grip=true;episode.cameraAgreement=true;episode.at=100;
    episode.operator={decision:'continue',reason:'Synthetic fixture run'};
  });
  return p;
};
const run=(state,name,batchRequest)=>({
  kind:'RUN',eventId:`ev-${name}`,expectedRevision:state.state.revision,
  expectedEpoch:state.state.epoch,batchId:`batch-${name}`,
  itemIds:Array.from({length:8},(_,i)=>`${name}-item-${i+1}`),batchRequest
});
const rearm=(state,kind)=>({
  kind,eventId:kind==='PROPOSE_REARM'?'ev-propose-demonstration':'ev-confirm-demonstration',
  expectedRevision:state.state.revision,expectedEpoch:state.state.epoch,proposalId:'demonstration-proposal'
});
let state=await genesis();
const original=await dispatch(state,run(state,'fault',plan(330)),{authorize:hostStub});
if(original.status!=='ADMITTED'||original.state.state.phase!=='LATCHED')
  throw Error('Expected synthetic grip loss latch');
state=original.state;
const bypass=await dispatch(state,run(state,'bypass',healthy(331)),{authorize:hostStub});
if(bypass.status!=='DENIED'||bypass.reason!=='GLOBAL_STOP_LATCHED')
  throw Error('Fresh batch bypass must be denied');
const proposal=await dispatch(state,rearm(state,'PROPOSE_REARM'));
if(proposal.status!=='ADMITTED')throw Error('Expected proposal');
state=proposal.state;
const noHost=await dispatch(state,rearm(state,'CONFIRM_REARM'));
if(noHost.status!=='DENIED')throw Error('Unverified rearm must be denied');
const confirmed=await dispatch(state,rearm(state,'CONFIRM_REARM'),{authorize:hostStub});
if(confirmed.status!=='ADMITTED')throw Error('Host-stub rearm refusal');
state=confirmed.state;
const after=await dispatch(state,run(state,'fresh',healthy(332)),{authorize:hostStub});
if(after.status!=='ADMITTED')throw Error('New distinct batch should work after authorized rearm');
state=await verifyLedger(after.state);
const retry=await dispatch(state,run(state,'attempted',healthy(333)),{authorize:hostStub});
if(retry.status!=='ADMITTED')throw Error('Expected independent run');
const repeat=await dispatch(retry.state,run(state,'attempted',healthy(333)));
if(repeat.status!=='CACHED')throw Error('Retry did not dedupe');
console.log(JSON.stringify({
  label:'SYNTHETIC_HOST_STUB_NOT_ROBOT_SAFETY',
  version:VERSION,initialTrip:original.result.trip,
  bypass:{status:bypass.status,reason:bypass.reason,operationalRootUnchanged:bypass.state.root===original.state.root},
  proposal:proposal.status,unverifiedRearm:noHost.status,hostStubRearm:confirmed.status,
  nextEpoch:confirmed.state.state.epoch,freshBatch:after.status,
  replayDeduplication:repeat.status,finalLedgerRoot:retry.state.root,
  physicalActuation:false,physicalEstop:false,operatorProofVerified:false,
  persistentHostCAS:false,providerModelInference:false
},null,2));
