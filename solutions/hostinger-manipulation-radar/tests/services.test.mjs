import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createServices,validateInterpretation} from '../services.mjs';
import {preflight} from '../deploy.mjs';
import {createServer} from '../server.mjs';
const material='Act now before it is too late. We have not published the supporting evidence.';
const env={HOSTINGER_AI_ROUTER_KEY:'DUMMY_HOSTINGER_KEY',HOSTINGER_AI_MODEL:'demo-model',SIGNAL_MAX_AI_REQUESTS:'1'};
const response=()=>new Response(JSON.stringify({choices:[{message:{content:JSON.stringify({techniques:[{name:'urgency pressure',excerpt:'Act now',explanation:'The opening asks for immediate action.'}],alternativeExplanation:'An actual urgent deadline may explain this.',missingContext:'The deadline and evidence are unavailable.'})}}]}),{headers:{'Content-Type':'application/json'}});
async function setup(t){const folder=await mkdtemp(join(tmpdir(),'signal-services-'));t.after(()=>rm(folder,{recursive:true,force:true}));return join(folder,'quota.json');}
test('exact-quote gate rejects hallucinated evidence and disallowed classifications',()=>{
 const r=validateInterpretation({techniques:[{name:'urgency pressure',excerpt:'Act now',explanation:'A call to action.'},{name:'urgency pressure',excerpt:'invented quotation',explanation:'Unsupported'},{name:'bot identity',excerpt:'Act now'}]},material);
 assert.equal(r.techniques.length,1);assert.equal(r.droppedUnsupported,2);assert.equal(r.intent,'UNKNOWN');assert.equal(r.truth,'NOT_ASSESSED');
});
test('explicit consent and configuration fail closed without making provider calls',async t=>{
 const path=await setup(t);let calls=0;const fetchImpl=async()=>{calls++;return response();};
 const s=createServices({env:{},quotaPath:path,fetchImpl});
 await assert.rejects(s.interpret({text:material,consent:false}),{code:'EXPLICIT_PROVIDER_CONSENT_REQUIRED'});
 await assert.rejects(s.interpret({text:material,consent:true}),{code:'HOSTINGER_AI_ROUTER_NOT_CONFIGURED'});
 assert.equal(calls,0);assert.equal(s.status().aiRouter,'NOT_CONFIGURED');
});
test('one reserved request survives service recreation and never persists submitted text or key',async t=>{
 const path=await setup(t);let calls=0;
 const fetchImpl=async(url,options)=>{calls++;assert.equal(url,'https://router.hostinger.com/v1/chat/completions');assert.equal(options.redirect,'error');assert.equal(JSON.parse(options.body).max_tokens,700);return response();};
 const options={env,quotaPath:path,fetchImpl};
 const r=await createServices(options).interpret({text:material,consent:true});assert.equal(r.mode,'LIVE_AI_ADVICE');assert.equal(r.techniques[0].excerpt,'Act now');
 await assert.rejects(createServices(options).interpret({text:material,consent:true}),{code:'DAILY_DEMO_LIMIT'});
 assert.equal(calls,1);const saved=await readFile(path,'utf8');assert.deepEqual(Object.keys(JSON.parse(saved)).sort(),['ai','day']);assert.ok(!saved.includes('Act now'));assert.ok(!saved.includes(env.HOSTINGER_AI_ROUTER_KEY));
});
test('failed or uncertain provider request is charged against the request allowance',async t=>{
 const path=await setup(t);let calls=0;
 const s=createServices({env,quotaPath:path,fetchImpl:async()=>{calls++;throw Error('secret-bearing provider failure');}});
 await assert.rejects(s.interpret({text:material,consent:true}),{code:'HOSTINGER_REQUEST_FAILED'});
 await assert.rejects(s.interpret({text:material,consent:true}),{code:'DAILY_DEMO_LIMIT'});assert.equal(calls,1);
});
test('simultaneous instances cannot both reserve the final request',async t=>{
 const path=await setup(t);let calls=0;const opts={env,quotaPath:path,fetchImpl:async()=>{calls++;return response();}};
 const results=await Promise.allSettled([createServices(opts).interpret({text:material,consent:true}),createServices(opts).interpret({text:material,consent:true})]);
 assert.equal(results.filter(r=>r.status==='fulfilled').length,1);assert.equal(calls,1);
 assert.ok(results.filter(r=>r.status==='rejected').every(r=>['QUOTA_STORE_BUSY','DAILY_DEMO_LIMIT'].includes(r.reason.code)));
});
test('invalid quota and backwards clock do not send requests',async t=>{
 const path=await setup(t);let calls=0;const opts={env,quotaPath:path,fetchImpl:async()=>{calls++;return response();}};
 await writeFile(path,'not JSON');await assert.rejects(createServices(opts).interpret({text:material,consent:true}),{code:'QUOTA_STORE_INVALID'});
 await writeFile(path,JSON.stringify({day:'2099-01-01',ai:0}));await assert.rejects(createServices(opts).interpret({text:material,consent:true}),{code:'CLOCK_MOVED_BACKWARDS'});assert.equal(calls,0);
});
test('HTTP API checks origin, content type, consent, size, private routes and returns no secrets',async t=>{
 const path=await setup(t),config={...env,SIGNAL_PUBLIC_ORIGIN:'https://signal.example.test'};
 const services=createServices({env:config,quotaPath:path,fetchImpl:async()=>response()});
 const server=createServer({env:config,services});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>{server.closeAllConnections();server.close(resolve);}));
 const base='http://127.0.0.1:'+server.address().port;
 const post=(body,headers={})=>fetch(base+'/api/interpret',{method:'POST',headers:{'Content-Type':'application/json',Origin:config.SIGNAL_PUBLIC_ORIGIN,...headers},body:JSON.stringify(body)});
 assert.equal((await post({text:material,consent:true},{Origin:'https://evil.example'})).status,403);
 assert.equal((await post({text:material,consent:true},{'Content-Type':'text/plain'})).status,415);
 assert.equal((await post({text:material,consent:false})).status,400);
 assert.equal((await post({text:'x'.repeat(9000),consent:true})).status,413);
 assert.equal((await fetch(base+'/.env')).status,404);
 assert.equal((await fetch(base+'/traffic/upload',{method:'POST'})).status,405);
 for(const route of ['/','/coordination/index.html','/coordination.mjs','/traffic/index.html','/text/index.html','/text/app.mjs','/text/style.css','/api/evaluation-v2'])assert.equal((await fetch(base+route)).status,200,route);
 const status=await(await fetch(base+'/api/status')).text();assert.ok(!status.includes(env.HOSTINGER_AI_ROUTER_KEY));
 const good=await post({text:material,consent:true});assert.equal(good.status,200);assert.equal((await good.json()).intent,'UNKNOWN');
});

test('an accidentally pasted combined access log is refused before any provider transfer',async t=>{const quotaPath=await setup(t);let calls=0;const s=createServices({env,quotaPath,fetchImpl:async()=>{calls++;return response();}});await assert.rejects(s.interpret({text:'192.0.2.1 - - [14/Nov/2026:09:00:00 +0000] "POST /login HTTP/1.1" 401 120 "-" "-"',consent:true}),{code:'ACCESS_LOG_TEXT_NOT_ALLOWED'});assert.equal(calls,0);});
test('Hostinger mode refuses an absent public HTTPS origin at startup',()=>{assert.throws(()=>createServer({env:{SIGNAL_DEPLOYMENT_PROVIDER:'hostinger'}}),/HTTPS/);});
test('deployment preflight rejects readable env files and mismatched origins without exposing keys',async t=>{const quota=await setup(t),folder=quota.slice(0,quota.lastIndexOf('/')),path=join(folder,'.env');const content='SIGNAL_DOMAIN=demo.example.test\nSIGNAL_PUBLIC_ORIGIN=https://demo.example.test\nSIGNAL_DEPLOYMENT_PROVIDER=hostinger\nSIGNAL_SOURCE_REVISION='+('a'.repeat(40))+'\nHOSTINGER_AI_ROUTER_KEY=\nHOSTINGER_AI_MODEL=\n';await writeFile(path,content,{mode:0o644});await assert.rejects(preflight(folder),/owner-only/);const {chmod}=await import('node:fs/promises');await chmod(path,0o600);assert.equal((await preflight(folder)).aiConfigured,false);await writeFile(path,content.replace('https://demo.example.test','https://other.example.test'));await assert.rejects(preflight(folder),/match SIGNAL_DOMAIN/);});
