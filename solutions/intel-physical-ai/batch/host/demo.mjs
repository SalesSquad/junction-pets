// Local synthetic-only example with disposable 0700 private storage.
// This program does not connect to network, real robot, camera or model.
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {plan} from '../cell.mjs';
import {localHost} from './host.mjs';

const allowedOnlyForTest=input=>({...input,permit:true,reference:'synthetic-host-test-only'});
const batch=(s,name,request)=>{
  return {kind:'RUN',eventId:'event-'+name,
    expectedEpoch:s.state.epoch,expectedRevision:s.state.revision,
    batchId:'batch-'+name,itemIds:request.episodes.map((_,i)=>name+'-item-'+i),
    batchRequest:request,batchControl:{}};
};
const dir=await mkdtemp(join(tmpdir(),'j26-intel-host-demo-'));
try{
  let h=localHost(dir,{authorize:allowedOnlyForTest});
  let state=await h.initialize();
  const first=await h.submit(batch(state,'fault',plan()),{expectedRoot:state.root});
  if(first.status!=='ADMITTED'||first.state.state.phase!=='LATCHED')
    throw Error('Unexpected synthetic host baseline');
  // New host object reads the journal. No in-memory latch is needed.
  h=localHost(dir,{authorize:allowedOnlyForTest});
  state=await h.read();
  const again=await h.submit(batch(state,'new-batch',plan(777)),{expectedRoot:state.root});
  if(again.status!=='DENIED'||again.reason!=='GLOBAL_STOP_LATCHED')
    throw Error('CROSS_BATCH_BYPASS');
  const ret=await h.submit(batch(await h.read(),'new-batch',plan(777)),{expectedRoot:state.root});
  if(ret.status!=='DENIED')throw Error('CROSS_BATCH_RETRY_UNEXPECTED');
  const current=await h.read();
  console.log(JSON.stringify({
    evidence:'OFFLINE_SYNTHETIC',physicalRobot:false,identityVerified:false,
    hostAuthorization:'TEST_STUB_NOT_PRODUCTION',persistentCAS:'SINGLE_LOCAL_DISK',
    first: first.status,trip:first.result.trip,phaseAfterRestart:current.state.phase,
    newBatch:{status:again.status,reason:again.reason,unchangedRoot:again.state.root===first.state.root},
    deniedAuditCount:(await h.inspectDenied()).length,
    finalRevision:current.state.revision,finalRoot:current.root
  },null,2));
}finally{
  // Task-created ephemeral fixture store only, no user files.
  await rm(dir,{recursive:true,force:true});
}
