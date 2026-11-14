import test from 'node:test';
import assert from 'node:assert/strict';
import { runTaskObservation,validateTaskObservationRequest } from './task-observation.mjs';
import { demoObservation,syntheticObservationTransport } from '../meta-spatial/observation-demo.mjs';
import { createObservationGate } from '../meta-spatial/observation-contract.mjs';
import { createObservationServer } from '../meta-spatial/observation-server.mjs';
import { FIXTURE } from '../../apps/meta-resume-web/fixture.mjs';

function request(frameIndex=0) {return {schemaVersion:1,task:{taskId:FIXTURE.taskId,revision:4,status:'active',
  nextStep:{stepId:FIXTURE.steps[2].stepId,label:FIXTURE.steps[2].label}},...demoObservation({frameIndex})};}
const context=()=>({taskId:FIXTURE.taskId,revision:4,sessionId:FIXTURE.sessionId,captureGeneration:1,captureEnabled:true,nowMs:Date.now()});
const options=extra=>({apiKey:'test-provider-key',fetchImpl:syntheticObservationTransport,context,...extra});

test('one bounded interpretation stays advisory and binds the actual image',async()=>{
  const r=await runTaskObservation(request(),options());
  assert.equal(r.status,'proposed');assert.equal(r.binding.expectedRevision,4);
  assert.equal(r.proposal.physicalIdentityVerified,false);assert.equal(r.proposal.taskCompletionAuthorized,false);
  assert.equal(r.receipt.providerCalls.length,1);assert.equal(r.receipt.execution,'injected-transport');
  assert.deepEqual(r.proposal.nextStepProposal,request().task.nextStep);
  const invalid=request();invalid.image.sha256='0'.repeat(64);
  const rejected=await runTaskObservation(invalid,options());
  assert.equal(rejected.error.code,'image-digest-mismatch');assert.equal(rejected.receipt.providerCalls.length,0);
});

test('causal source and RFC3339 timestamps match the Python worker contract',()=>{
  const r=request();r.observation.frame.capturedAt='2026-11-14T12:00:00.123456789+02:00';
  assert.doesNotThrow(()=>validateTaskObservationRequest(r));
  r.observation.sourceThroughFrameIndex=1;
  assert.throws(()=>validateTaskObservationRequest(r),/noncausal/);
});

test('local profile pins loopback alias without leaking hosted credentials or attesting weights',async()=>{
  let sent;
  const r=await runTaskObservation(request(),options({profile:'nemotron-local-nvfp4',fetchImpl:async(url,init)=>{
    sent={url,headers:init.headers,body:JSON.parse(init.body)};
    return syntheticObservationTransport(url,init);
  }}));
  assert.equal(r.status,'proposed');assert.equal(sent.url,'http://127.0.0.1:18765/v1/chat/completions');
  assert.equal(sent.headers.Authorization,undefined);assert.equal(sent.body.model,'nemotron-3.5-super-vl');
  assert.equal(sent.body.max_tokens,256);assert.equal(sent.body.chat_template_kwargs.enable_thinking,false);
  assert.equal(r.receipt.weightsAttestation,'unverified');assert.equal(r.receipt.weightsRevision,undefined);
  assert.equal(r.receipt.requestedWeightsRevision,'3acb09951cff50cda7be0200ebbad2c15a3e63ba');
});

test('invented track and wrong provider model are rejected without a task proposal',async()=>{
  for(const mutation of ['track','model']) {
    const r=await runTaskObservation(request(),options({fetchImpl:async(url,init)=>{
      const response=await syntheticObservationTransport(url,init),data=await response.json();
      if(mutation==='model')data.model='different-model';
      else {const answer=JSON.parse(data.choices[0].message.content);answer.observations[0].trackId='invented';data.choices[0].message.content=JSON.stringify(answer);}
      return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
    }}));
    assert.equal(r.status,'failed');assert.equal(r.proposal,null);
    assert.equal(r.error.code,mutation==='model'?'unexpected-model':'ungrounded-task-interpretation');
  }
});

test('a capture revoked during the model call cannot return a proposal',async()=>{
  let revoked=false;
  const r=await runTaskObservation(request(),options({context:()=>({...context(),captureEnabled:!revoked}),
    fetchImpl:async(url,init)=>{revoked=true;return syntheticObservationTransport(url,init);}}));
  assert.equal(r.error.code,'stale-or-unadmitted-context');assert.equal(r.proposal,null);
});

test('unchanged frame costs no second provider call',async()=>{
  const gate=createObservationGate();const first=request();
  assert.equal((await runTaskObservation(first,options({gate}))).status,'proposed');
  const r=await runTaskObservation(first,options({gate}));
  assert.equal(r.status,'skipped');assert.equal(r.receipt.reason,'same-frame');assert.equal(r.receipt.providerCalls.length,0);
});

test('out-of-order provider completion cannot regress the gate watermark',async()=>{
  const gate=createObservationGate(),pending=new Map();
  const fetchImpl=(url,init)=>new Promise(resolve=>pending.set(JSON.parse(JSON.parse(init.body).messages[1].content[0].text).frame.frameIndex,
    async()=>resolve(await syntheticObservationTransport(url,init))));
  const older=runTaskObservation(request(10),options({gate,fetchImpl,force:true}));
  const newer=runTaskObservation(request(11),options({gate,fetchImpl,force:true}));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(pending.size,2);await pending.get(11)();assert.equal((await newer).status,'proposed');
  await pending.get(10)();const late=await older;assert.equal(late.status,'failed');
  assert.equal(late.error.code,'superseded-observation');assert.equal(late.proposal,null);
  assert.equal(gate.inspect(request(10),{force:true}).analyze,false);
});

test('actual local HTTP journey requires same-origin CSRF and returns only synthetic advice',async()=>{
  const server=createObservationServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  try {
    const config=await(await fetch(origin+'/api/config')).json();assert.equal(config.mode,'synthetic');
    const bundle=await(await fetch(origin+'/api/demo-observation')).json();
    const input={...request(),...bundle},send=(headers={})=>fetch(origin+'/api/observe',{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(input)});
    assert.equal((await send()).status,403);
    assert.equal((await send({'X-Meta-CSRF':config.csrfToken,Origin:'https://unrelated.example'})).status,403);
    const response=await send({'X-Meta-CSRF':config.csrfToken,Origin:origin});assert.equal(response.status,200);
    const result=await response.json();assert.equal(result.status,'proposed');assert.equal(result.receipt.execution,'synthetic-fixture');
    assert.equal(result.proposal.taskCompletionAuthorized,false);assert.equal(result.binding.taskId,FIXTURE.taskId);
    assert.equal((await fetch(origin+'/api/unknown')).status,404);
  } finally {server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
