import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {MODEL,ENDPOINT,LIMITS,runDrawingObservation,validateDrawingRequest} from './index.mjs';
import {drawingFixture} from '../stoa-nvidia/fixture.mjs';
import {prepareStoaDrawingTask,validateStoaDrawingTask,runStoaNvidiaDrawing} from '../stoa-nvidia/index.mjs';

const KEY='nvapi-DRAWING_TEST_SECRET_CANARY_123';
const SHA='a'.repeat(40);
const clone=value=>JSON.parse(JSON.stringify(value));
const answer=(r=drawingFixture())=>({sourceSha256:r.source.sha256,page:r.source.page,
 answerCandidate:'The sheet labels the values as authored estimates.',
 observations:[{regionId:r.regions[0].id,imageSha256:r.regions[0].imageSha256,bounds:[...r.regions[0].bounds],
  text:'The worksheet visibly labels its numbers as estimates.'}],
 uncertainties:['This authored worksheet is not a real drawing or measured benchmark.']});
const payload=(v,model=MODEL)=>({model,choices:[{finish_reason:'stop',message:{role:'assistant',content:JSON.stringify(v),
 reasoning_content:'REASONING_CANARY'}}],usage:{prompt_tokens:100,completion_tokens:50,total_tokens:150}});
function scripted(values) {
 const requests=[];
 return {requests,fetchImpl:async(url,options)=>{
  const body=JSON.parse(options.body);requests.push({url,body,options});
  const value=values.shift();
  if(value instanceof Error)throw value;
  if(value instanceof Response)return value;
  if(value===undefined)throw Error('unexpected network call');
  return new Response(JSON.stringify(value),{headers:{'content-type':'application/json'}});
 }};
}
const standard=r=>[payload(answer(r)),payload({accepted:true,issues:[]})];
async function run(values=standard(),r=drawingFixture()) {
 const host=scripted(values);
 return {receipt:await runDrawingObservation(r,{apiKey:KEY,fetchImpl:host.fetchImpl}),requests:host.requests};
}
test('drawing mode uses actual bounded shared transport without any benchmark rows or tools',async()=>{
 const {receipt,requests}=await run();assert.equal(receipt.status,'completed');assert.equal(requests.length,2);
 assert.deepEqual(receipt.providerCalls.map(c=>c.stage),['drawing_observation','drawing_verification']);
 assert.equal(receipt.companion.id,'junction.nvidia');assert.equal(receipt.result.geometryVerified,false);
 assert.equal(receipt.result.factualVerification,'unverified-model-interpretation');
 assert.equal(receipt.evidenceType,'injected-transport-unqualified');assert.equal(receipt.hostVerification,'unverified');
 assert.equal(receipt.usage.totalTokens,300);assert.equal(receipt.usageAccountingComplete,true);
 for(const q of requests){
  assert.equal(q.url,ENDPOINT);assert.equal(q.body.model,MODEL);assert.equal(q.options.redirect,'error');
  assert.equal(q.body.tools,undefined);assert.equal(q.body.max_tokens,LIMITS.outputTokens);
  assert.ok(q.body.messages[1].content.some(c=>c.type==='image_url'));
 }
 const serialized=JSON.stringify(receipt);assert.ok(!serialized.includes(KEY));assert.ok(!serialized.includes('REASONING_CANARY'));
 assert.ok(!serialized.includes('data:image/'));
});
test('Stoa actually invokes NVIDIA and returns only source/region-bound candidate evidence',async()=>{
 const r=drawingFixture(),host=scripted(standard(r)),task=prepareStoaDrawingTask(r,{sourceCommit:SHA});
 const result=await runStoaNvidiaDrawing(task,{apiKey:KEY,fetchImpl:host.fetchImpl});
 assert.equal(result.status,'candidate');assert.equal(host.requests.length,2);
 assert.equal(result.actorBinding.id,'junction.stoa');assert.equal(result.recipientBinding.id,'junction.nvidia');
 assert.equal(result.sourceCommit,SHA);assert.equal(result.parentOutputDigest,task.parentOutputDigest);
 assert.equal(result.childReceipt.inputDigest,result.requestDigest);
 assert.equal(result.result.citations[0].sourceSha256,r.source.sha256);
 assert.deepEqual(result.result.citations[0].bounds,r.regions[0].bounds);assert.equal(result.productionAuthorized,false);
 assert.match(result.outputDigest,/^[a-f0-9]{64}$/);
});
test('a second page-region with independent byte hash remains explicitly cited',async()=>{
 const r=drawingFixture();const second=Buffer.from(r.regions[0].image.split(',')[1],'base64');
 second[second.length-1]^=1;const hash=createHash('sha256').update(second).digest('hex');
 r.regions.push({id:'detail',image:'data:image/png;base64,'+second.toString('base64'),imageSha256:hash,bounds:[.2,.2,.6,.6]});
 const a=answer(r);a.observations=[{regionId:'detail',imageSha256:hash,bounds:[.2,.2,.6,.6],text:'A supplied detail crop is visible.'}];
 const {receipt}=await run([payload(a),payload({accepted:true,issues:[]})],r);
 assert.equal(receipt.status,'completed');assert.equal(receipt.result.observations[0].imageSha256,hash);
});
for(const [name,change] of [
 ['private data class',r=>{r.source.dataClass='tenant-private';}],
 ['numeric source id',r=>{r.source.id=123;}],
 ['invalid source digest',r=>{r.source.sha256='bad';}],
 ['page zero',r=>{r.source.page=0;}],
 ['unknown source key',r=>{r.source.authorized=true;}],
 ['changed image hash',r=>{r.regions[0].imageSha256='b'.repeat(64);}],
 ['changed image bytes',r=>{const b=Buffer.from(r.regions[0].image.split(',')[1],'base64');b[b.length-1]^=1;r.regions[0].image='data:image/png;base64,'+b.toString('base64');}],
 ['out-of-bounds region',r=>{r.regions[0].bounds=[0,0,1.1,1];}],
 ['reversed region',r=>{r.regions[0].bounds=[.8,0,.1,1];}],
 ['empty region',r=>{r.regions[0].bounds=[0,0,0,1];}],
 ['unknown region key',r=>{r.regions[0].url='https://untrusted.invalid';}],
 ['duplicate region id',r=>{r.regions.push(clone(r.regions[0]));}],
 ['arbitrary image URL',r=>{r.regions[0].image='https://untrusted.invalid';}],
 ['too many regions',r=>{r.regions.push({...r.regions[0],id:'r2'},{...r.regions[0],id:'r3'});}]
]) test('rejects input before provider: '+name,async()=>{
 const r=drawingFixture();change(r);let calls=0;
 const result=await runDrawingObservation(r,{apiKey:KEY,fetchImpl:()=>{calls++;throw Error('forbidden');}});
 assert.equal(result.status,'failed');assert.equal(calls,0);
});
test('request accessors and sparse regions cannot execute caller code',()=>{
 let touched=false;const r=drawingFixture();Object.defineProperty(r.source,'id',{get(){touched=true;return 'injected';}});
 assert.throws(()=>validateDrawingRequest(r));assert.equal(touched,false);
 const sparse=drawingFixture();sparse.regions=Array(1);assert.throws(()=>validateDrawingRequest(sparse));
});
for(const [name,change] of [
 ['wrong source digest',a=>{a.sourceSha256='b'.repeat(64);}],
 ['wrong page',a=>{a.page=2;}],
 ['invented region',a=>{a.observations[0].regionId='missing';}],
 ['wrong image digest',a=>{a.observations[0].imageSha256='b'.repeat(64);}],
 ['changed region bounds',a=>{a.observations[0].bounds=[0,0,.5,.5];}],
 ['unsupported answer with no observations',a=>{a.observations=[];}],
 ['no uncertainty',a=>{a.uncertainties=[];}],
 ['fabricated authorization property',a=>{a.authorized=true;}]
]) test('refuses model evidence mismatch: '+name,async()=>{
 const a=answer();change(a);const {receipt,requests}=await run([payload(a)]);
 assert.equal(receipt.status,'failed');assert.equal(receipt.error.code,'drawing-evidence-mismatch');assert.equal(requests.length,1);
});
test('explicit abstention survives review and remains abstained through Stoa',async()=>{
 const r=drawingFixture(),a=answer(r);a.answerCandidate=null;a.observations=[];
 const host=scripted([payload(a),payload({accepted:true,issues:[]})]);
 const result=await runStoaNvidiaDrawing(prepareStoaDrawingTask(r,{sourceCommit:SHA}),{apiKey:KEY,fetchImpl:host.fetchImpl});
 assert.equal(result.status,'abstained');assert.equal(result.result.answerCandidate,null);assert.equal(result.result.citations.length,0);
});
for(const [name,step,code] of [
 ['provider authentication error',new Response(KEY,{status:401}),'provider-auth-rejected'],
 ['provider transport exception',new Error(KEY),'provider-transport-error'],
 ['wrong model',payload(answer(),'nvidia/other-model'),'unexpected-model'],
 ['oversized stream',new Response('x'.repeat(LIMITS.responseBytes+1),{headers:{'content-type':'application/json'}}),'response-too-large']
])test('shared drawing transport refuses '+name,async()=>{
 const {receipt}=await run([step]);assert.equal(receipt.status,'failed');assert.equal(receipt.error.code,code);
 assert.ok(!JSON.stringify(receipt).includes(KEY));assert.equal(receipt.usageAccountingComplete,false);
});
test('second-call revocation in an injected host wrapper fails without a candidate',async()=>{
 const host=scripted([payload(answer()),new Response('revoked',{status:403})]);
 const receipt=await runDrawingObservation(drawingFixture(),{apiKey:KEY,fetchImpl:host.fetchImpl});
 assert.equal(host.requests.length,2);assert.equal(receipt.error.code,'provider-auth-rejected');assert.equal(receipt.result,undefined);
});
test('same-model verification rejection is never candidate success',async()=>{
 for(const review of [{accepted:false,issues:['unsupported']},{accepted:true,issues:['unsupported']}]) {
  const {receipt}=await run([payload(answer()),payload(review)]);assert.equal(receipt.error.code,'model-verification-rejected');assert.equal(receipt.result,undefined);
 }
});
test('missing key fails at both entrypoints with zero provider requests',async()=>{
 let calls=0;const fetchImpl=()=>{calls++;throw Error('forbidden');};
 const n=await runDrawingObservation(drawingFixture(),{fetchImpl});assert.equal(n.error.code,'missing-or-invalid-key');
 const s=await runStoaNvidiaDrawing(prepareStoaDrawingTask(drawingFixture(),{sourceCommit:SHA}),{fetchImpl});
 assert.equal(s.status,'failed');assert.equal(s.error.childCode,'missing-or-invalid-key');assert.equal(calls,0);
});
test('changed parent source or image binding refuses before NVIDIA',async()=>{
 for(const change of [
  t=>{t.request.source.sha256='b'.repeat(64);},
  t=>{t.parentOutputDigest='b'.repeat(64);},
  t=>{t.sourceCommit='b'.repeat(40);},
  t=>{t.from='junction.exa';},
  t=>{t.request.regions[0].imageSha256='b'.repeat(64);}
 ]) {
  const t=prepareStoaDrawingTask(drawingFixture(),{sourceCommit:SHA});change(t);let called=false;
  const result=await runStoaNvidiaDrawing(t,{observe:()=>{called=true;throw Error('forbidden');}});
  assert.equal(result.status,'failed');assert.equal(called,false);assert.throws(()=>validateStoaDrawingTask(t));
 }
});
test('Stoa rejects mismatched child source, region, request, model and parent-output evidence',async()=>{
 const r=drawingFixture(),original=(await run()).receipt;
 for(const change of [
  c=>{c.source.sha256='b'.repeat(64);},
  c=>{c.result.source.sha256='b'.repeat(64);},
  c=>{c.inputDigest='b'.repeat(64);},
  c=>{c.requestedModel='unknown';},
  c=>{c.result.observations[0].bounds=[0,0,.2,.2];},
  c=>{c.regions[0].imageSha256='b'.repeat(64);},
  c=>{c.result.geometryVerified=true;},
  c=>{c.result.uncertainties=['x'.repeat(601)];},
  c=>{c.result.observations=Array(9).fill(c.result.observations[0]);}
 ]) {
  const c=clone(original);change(c);
  const result=await runStoaNvidiaDrawing(prepareStoaDrawingTask(r,{sourceCommit:SHA}),{observe:async()=>c});
  assert.equal(result.status,'failed');assert.equal(result.result,undefined);
 }
});
test('CLI default ignores keys and shows zero-network plan; source bypass refuses',()=>{
 const cli=new URL('../stoa-nvidia/cli.mjs',import.meta.url);
 const options={encoding:'utf8',env:{...process.env,NVIDIA_API_KEY:KEY},timeout:10000};
 const p=spawnSync(process.execPath,[cli.pathname],options);assert.equal(p.status,0);
 const plan=JSON.parse(p.stdout);assert.equal(plan.networkRequests,0);assert.equal(plan.secretReads,0);assert.equal(plan.actor,'junction.stoa');
 assert.ok(!p.stdout.includes(KEY));assert.ok(!p.stdout.includes('data:image/'));
 const e=spawnSync(process.execPath,[cli.pathname,'--execute','--source-commit','a'.repeat(40)],options);
 assert.equal(e.status,1);assert.equal(JSON.parse(e.stderr).error.code,'source-verification-failed');
});

test('Stoa projects child receipts and removes raw injected fields and known credential echoes',async()=>{
 const r=drawingFixture(),c=(await run()).receipt;
 c.rawProviderPayload='REASONING_PRIVATE_CANARY '+KEY;c.companion.rawSecret=KEY;
 c.providerCalls[0].rawReasoning='REASONING_PRIVATE_CANARY';
 c.result.answerCandidate=KEY;
 const result=await runStoaNvidiaDrawing(prepareStoaDrawingTask(r,{sourceCommit:SHA}),{apiKey:KEY,observe:async()=>c});
 assert.equal(result.status,'candidate');const text=JSON.stringify(result);
 assert.ok(!text.includes(KEY));assert.ok(!text.includes('REASONING_PRIVATE_CANARY'));
 assert.equal(result.result.answerCandidate,'[REDACTED]');
 assert.equal(result.outputDigest,createHash('sha256').update(JSON.stringify(result.result)).digest('hex'));
});
