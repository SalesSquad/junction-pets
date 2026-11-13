import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {setImmediate} from 'node:timers/promises';
import {runNemotron,validateRequest,MODEL,ENDPOINT,LIMITS,SOURCE_CARDS} from './index.mjs';
import {syntheticFixture} from './fixture.mjs';

const KEY='nvapi-TEST_SECRET_CANARY_123456789';
const THOUGHT='PRIVATE_REASONING_CANARY_NEVER_SERIALIZE';
const facts=[{imageIndex:0,observation:'The worksheet labels the baseline 120 ms and candidate 60 ms as authored estimates.'}];
const comparison={comparable:true,reason:null,ratio:2,basis:'authored-estimate',provenance:'unverified',measuredPerformanceVerified:false};
const final=()=>({summary:'The visible worksheet contains authored estimates, with unverified provenance.',facts,sourceCardIds:['model'],comparison:{...comparison},
  limitations:['No GPU run was performed; this is an unverified estimate comparison.'],nextAction:'Measure the same scene and quality on verified hardware.'});
const call=(id,name,args)=>({id,type:'function',function:{name,arguments:JSON.stringify(args)}});
const tools=(id='1')=>[call('source_'+id,'nvidia_source_card',{card_id:'model'}),call('compare_'+id,'benchmark_compare',{baseline_id:'baseline',candidate_id:'candidate'})];
function payload(content,{calls,finish=calls?'tool_calls':'stop',model=MODEL,usage={prompt_tokens:100,completion_tokens:50,total_tokens:150},...extras}={}) {
  return {model,choices:[{index:0,finish_reason:finish,message:{role:'assistant',content:content==null?null:typeof content==='string'?content:JSON.stringify(content),
    reasoning_content:THOUGHT,...(calls?{tool_calls:calls}:{})}}],usage,...extras};
}
const standard=()=>[payload({facts,uncertainties:['The diagram is synthetic.']}),payload(null,{calls:tools()}),payload('Done selecting tools.'),payload(final()),payload({accepted:true,issues:[]})];
function scripted(steps) {
  const requests=[];
  return {requests,fetchImpl:async(url,options)=>{
    requests.push({url,options,body:JSON.parse(options.body)});
    if(!steps.length) throw new Error('unexpected fetch');
    const step=steps.shift();
    if(step instanceof Response) return step;
    if(step instanceof Error) throw step;
    return new Response(JSON.stringify(step),{status:200,headers:{'content-type':'application/json'}});
  }};
}
async function execute(steps=standard(),input=syntheticFixture()) {
  const host=scripted(steps);
  return {result:await runNemotron(input,{apiKey:KEY,fetchImpl:host.fetchImpl}),requests:host.requests};
}
test('injected finite workflow sends image, model-selected tools and results, synthesis and verification',async()=>{
  const {result,requests}=await execute();
  assert.equal(result.status,'completed');assert.equal(requests.length,5);
  assert.equal(result.result.comparison.ratio,2);assert.equal(result.result.comparison.measuredPerformanceVerified,false);
  assert.equal(result.companion.id,'junction.nvidia');assert.match(result.companion.manifestSha256,/^[a-f0-9]{64}$/);
  assert.equal(result.hostVerification,'unverified');assert.equal(result.usage.totalTokens,750);
  assert.equal(result.usageAccountingComplete,true);assert.equal(result.costs,'unknown');
  assert.deepEqual(result.providerCalls.map(x=>x.stage),['visual_observation','tool_selection','tool_selection','evidence_synthesis','evidence_verification']);
  assert.equal(result.tools.length,2);assert.match(result.inputDigest,/^[a-f0-9]{64}$/);
  assert.ok(requests[0].body.messages[1].content.some(x=>x.type==='image_url'&&x.image_url.url.startsWith('data:image/png;base64,')));
  assert.ok(requests[2].body.messages.some(x=>x.role==='tool'&&JSON.parse(x.content).ratio===2));
  for(const request of requests) {
    assert.equal(request.url,ENDPOINT);assert.equal(request.body.model,MODEL);assert.equal(request.options.redirect,'error');
    assert.equal(request.body.chat_template_kwargs.enable_thinking,true);assert.equal(request.body.extra_body,undefined);
    assert.equal(request.body.max_tokens,LIMITS.outputTokens);assert.ok(request.options.signal.aborted);
  }
  const serialized=JSON.stringify(result);
  assert.ok(!serialized.includes(KEY));assert.ok(!serialized.includes(THOUGHT));assert.ok(!serialized.includes('data:image/png'));
});
test('pinned exported source facts cannot be mutated',()=>{
  assert.throws(()=>SOURCE_CARDS.model.facts.push('injected'));assert.throws(()=>SOURCE_CARDS.model.facts[0]='changed');
});
test('missing key and invalid inputs make zero requests',async()=>{
  let calls=0;const fetchImpl=()=>{calls++;throw new Error('network forbidden');};
  const missing=await runNemotron(syntheticFixture(),{fetchImpl});
  assert.equal(missing.error.code,'missing-or-invalid-key');
  const invalid=syntheticFixture();invalid.question='x'.repeat(LIMITS.questionChars+1);
  assert.equal((await runNemotron(invalid,{apiKey:KEY,fetchImpl})).error.code,'invalid-input');
  invalid.question='valid';invalid.images=['https://attacker.example/image.png'];
  assert.equal((await runNemotron(invalid,{apiKey:KEY,fetchImpl})).error.code,'invalid-image');
  assert.equal(calls,0);
});
test('caller accessors and sparse arrays are rejected without evaluating code',()=>{
  let touched=false;const request=syntheticFixture();Object.defineProperty(request,'question',{get(){touched=true;throw new Error('getter');}});
  assert.throws(()=>validateRequest(request));assert.equal(touched,false);
  const sparse=syntheticFixture();sparse.images=Array(1);assert.throws(()=>validateRequest(sparse));
});
test('image and benchmark bounds reject before network',async()=>{
  const invalid=syntheticFixture();invalid.benchmarkRows[0].record.timings=[0];
  assert.throws(()=>validateRequest(invalid));
  const huge=syntheticFixture();const image=Buffer.from(huge.images[0].split(',')[1],'base64');image.writeUInt32BE(8193,16);
  huge.images=['data:image/png;base64,'+image.toString('base64')];assert.throws(()=>validateRequest(huge));
  const oversize=syntheticFixture();oversize.images=['data:image/png;base64,'+Buffer.alloc(LIMITS.imageBytes+1).toString('base64')];assert.throws(()=>validateRequest(oversize));
});
for(const [name,step,code] of [
  ['different returned model',payload({facts,uncertainties:[]},{model:'nvidia/older-model'}),'unexpected-model'],
  ['truncation',payload('{}',{finish:'length'}),'unsupported-provider-result'],
  ['malformed usage',payload({facts,uncertainties:[]},{usage:{prompt_tokens:1,completion_tokens:2,total_tokens:9}}),'invalid-provider-usage'],
  ['output token violation',payload({facts,uncertainties:[]},{usage:{prompt_tokens:1,completion_tokens:4097,total_tokens:4098}}),'invalid-provider-usage'],
  ['invalid JSON',new Response('not json',{headers:{'content-type':'application/json'}}),'invalid-provider-json'],
  ['non JSON response',new Response('oops',{headers:{'content-type':'text/plain'}}),'invalid-response-type'],
  ['provider auth rejection',new Response(KEY,{status:401}),'provider-auth-rejected'],
  ['rate limit',new Response(KEY,{status:429}),'provider-rate-limited'],
  ['transport secret',new Error(KEY),'provider-transport-error'],
  ['oversized declared response',new Response('{}',{headers:{'content-type':'application/json','content-length':String(LIMITS.responseBytes+1)}}),'response-too-large'],
  ['oversized streamed response',new Response('x'.repeat(LIMITS.responseBytes+1),{headers:{'content-type':'application/json'}}),'response-too-large'],
  ['invalid observation',payload({facts:[],uncertainties:[]}),'invalid-observation']
]) test('rejects '+name,async()=>{
  const {result,requests}=await execute([step]);assert.equal(result.error.code,code);assert.equal(requests.length,1);
  assert.equal(result.status,'failed');assert.ok(!JSON.stringify(result).includes(KEY));assert.ok(!JSON.stringify(result).includes(THOUGHT));
});
for(const [name,tc,code] of [
  ['unknown tool',call('unknown','shell_exec',{command:'whoami'}),'unknown-tool'],
  ['extra argument',call('extra','nvidia_source_card',{card_id:'model',url:'https://attacker.example'}),'invalid-tool-arguments'],
  ['non-string card',call('nonstring','nvidia_source_card',{card_id:{toString:'model'}}),'invalid-tool-arguments'],
  ['unknown benchmark',call('unknownrow','benchmark_compare',{baseline_id:'baseline',candidate_id:'missing'}),'invalid-tool-arguments'],
  ['same benchmark',call('same','benchmark_compare',{baseline_id:'baseline',candidate_id:'baseline'}),'invalid-tool-arguments'],
  ['invalid ID',call('spaces are forbidden','nvidia_source_card',{card_id:'model'}),'invalid-tool-call']
]) test('rejects '+name,async()=>{
  const {result}=await execute([standard()[0],payload(null,{calls:[tc]})]);assert.equal(result.error.code,code);assert.equal(result.tools.length,0);
});
test('rejects reused tool IDs even across separate rounds',async()=>{
  const {result}=await execute([standard()[0],payload(null,{calls:tools()}),payload(null,{calls:[call('source_1','nvidia_source_card',{card_id:'model'})]})]);
  assert.equal(result.error.code,'invalid-tool-call');assert.equal(result.tools.length,2);
});
test('does not synthesize without both real tools',async()=>{
  const {result}=await execute([standard()[0],payload('I will claim the tools ran without calling them.')]);
  assert.equal(result.error.code,'required-tools-not-used');assert.equal(result.providerCalls.length,2);
});
test('tool round and request budgets terminate persistent tool selection',async()=>{
  const steps=[standard()[0],...['1','2','3','4'].map(i=>payload(null,{calls:tools(i)})),payload(final()),payload({accepted:true,issues:[]})];
  const {result,requests}=await execute(steps);assert.equal(result.status,'completed');
  assert.equal(requests.length,LIMITS.providerCalls);assert.equal(result.tools.length,LIMITS.toolCalls);
});
test('reported total token budget stops the run and further calls',async()=>{
  const steps=standard();steps[0].usage={prompt_tokens:32000,completion_tokens:50,total_tokens:32050};steps[1].usage={prompt_tokens:32000,completion_tokens:50,total_tokens:32050};
  const {result,requests}=await execute(steps);assert.equal(result.error.code,'token-budget-exhausted');assert.equal(requests.length,2);
});
test('usage accounting remains explicitly incomplete on a failed request',async()=>{
  const {result}=await execute([new Error('provider unavailable')]);
  assert.equal(result.usageAccountingComplete,false);assert.equal(result.costs,'unknown');assert.equal(result.usage.totalTokens,0);
});
for(const [name,mutate] of [
  ['fabricated comparison',x=>{x.comparison.ratio=900;}],
  ['invented observation',x=>{x.facts=[{imageIndex:0,observation:'A GPU was measured.'}];}],
  ['unused source',x=>{x.sourceCardIds=['api'];}],
  ['extra output property',x=>{x.isOfficial=true;}]
]) test('rejects '+name,async()=>{
  const steps=standard();const answer=final();mutate(answer);steps[3]=payload(answer);
  assert.equal((await execute(steps)).result.error.code,'unverified-synthesis');
});
test('rejects model verifier refusal and contradictory acceptance',async()=>{
  for(const verification of [{accepted:false,issues:['Unsupported claim.']},{accepted:true,issues:['Unsupported claim.']}]) {
    const steps=standard();steps[4]=payload(verification);assert.equal((await execute(steps)).result.error.code,'model-verification-rejected');
  }
});
test('malicious credential echoes are redacted while private reasoning is excluded',async()=>{
  const steps=standard();const answer=final();answer.summary=KEY+' Bearer arbitrary_secret_123 sk-abcdEFGHijkl123456';steps[3]=payload(answer);
  const {result}=await execute(steps);assert.equal(result.status,'completed');
  assert.equal(result.result.summary,'[REDACTED] Bearer [REDACTED] [REDACTED]');
  assert.ok(!JSON.stringify(result).includes(THOUGHT));assert.ok(!JSON.stringify(result).includes(KEY));
});
test('timeout returns even when injected transport ignores abort',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  let observedSignal;
  const promise=runNemotron(syntheticFixture(),{apiKey:KEY,fetchImpl:(_url,options)=>{observedSignal=options.signal;return new Promise(()=>{});}});
  await setImmediate();t.mock.timers.tick(LIMITS.requestTimeoutMs+1);
  const result=await promise;assert.equal(result.error.code,'provider-timeout');assert.ok(observedSignal.aborted);assert.equal(result.usageAccountingComplete,false);
});
test('CLI default is plan-only even with a secret configured; execute fails closed outside pinned clean repository',()=>{
  const cli=new URL('./cli.mjs',import.meta.url);
  const options={encoding:'utf8',env:{...process.env,NVIDIA_API_KEY:KEY},timeout:10000};
  const plan=spawnSync(process.execPath,[cli.pathname],options);assert.equal(plan.status,0);
  const parsed=JSON.parse(plan.stdout);assert.equal(parsed.mode,'plan-only');assert.equal(parsed.networkRequests,0);assert.equal(parsed.secretReads,0);assert.ok(!plan.stdout.includes(KEY));
  const execute=spawnSync(process.execPath,[cli.pathname,'--execute','--source-commit','a'.repeat(40)],options);
  assert.equal(execute.status,1);assert.equal(JSON.parse(execute.stderr).error.code,'source-verification-failed');assert.ok(!execute.stderr.includes(KEY));
});

 test('accepts omitted assistant content only for valid tool calls',async()=>{
  const steps=standard();delete steps[1].choices[0].message.content;
  assert.equal((await execute(steps)).result.status,'completed');
  const invalid=standard();delete invalid[0].choices[0].message.content;
  assert.equal((await execute(invalid)).result.error.code,'invalid-provider-content');
 });
