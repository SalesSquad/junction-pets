/** Execute real local simulation through the lab's HTTP boundary. No provider calls. */
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { createSimulationServer } from './server.mjs';

const app=await createSimulationServer();
app.server.listen(0,'127.0.0.1');await once(app.server,'listening');
const base='http://127.0.0.1:'+app.server.address().port;
const send=(body,extra={})=>fetch(base+'/api/simulation/run',{method:'POST',headers:{'Content-Type':'application/json',Origin:base,...extra},body:typeof body==='string'?body:JSON.stringify(body)});
let report;
try {
  const index=await fetch(base+'/');assert.equal(index.status,200);assert.match(await index.text(),/Oikeita tilauksia tai maksuja ei lähetetä/);
  assert.equal((await fetch(base+'/api/simulation/status?unexpected=1')).status,400);
  assert.equal((await fetch(base+'/api/simulation/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"scenario":"all"}'})).status,403);
  assert.equal((await send({scenario:'all'},{Origin:'https://outside.invalid'})).status,403);
  assert.equal((await send({scenario:'unknown'})).status,400);
  assert.equal((await send({scenario:'purchase',url:'https://outside.invalid'})).status,400);
  assert.equal((await send({scenario:'all'},{'Content-Type':'text/plain'})).status,415);
  assert.equal((await send(' '.repeat(1025))).status,413);
  const pending=send({scenario:'all'});
  let busy=false;
  for(let i=0;i<50;i++){const state=await(await fetch(base+'/api/simulation/status')).json();if(state.busy){busy=true;break;}await new Promise(resolve=>setTimeout(resolve,10));}
  assert.equal(busy,true,'the HTTP run must be observable as active');
  assert.equal((await send({scenario:'all'})).status,409,'concurrent runs cannot share mutable lab state');
  const response=await pending;assert.equal(response.status,200);
  report=await response.json();
  assert.equal(report.mode,'LOCAL_SIMULATION');assert.equal(report.outcome,'PASS');assert.equal(report.busy,false);
  assert.equal(report.externalProviderCalls,0);assert.equal(report.results.length,7);
  assert.deepEqual(new Set(report.results.map(value=>value.scenarioId)),new Set(['purchase','reject','stale','revoked','retry','shortage','expired']));
  for(const result of report.results){assert.equal(result.outcome,'PASS',result.scenarioId);assert.equal(result.externalProviderCalls,0);assert.ok(result.steps.length>0);assert.ok(result.steps.every(step=>step.outcome==='PASS'));}
  const text=JSON.stringify(report);
  for(const forbidden of ['Bearer ','PRIVATE KEY','"privateKey"','"token"','"sub":','eyJhbGci'])assert.equal(text.includes(forbidden),false,'report must not expose host credentials or claims');
  const download=await fetch(base+'/api/simulation/report');assert.match(download.headers.get('content-disposition'),/attachment/);
  assert.deepEqual(await download.json(),report);
  if(process.env.VALIO_SIMULATION_REPORT){await mkdir(dirname(process.env.VALIO_SIMULATION_REPORT),{recursive:true});await writeFile(process.env.VALIO_SIMULATION_REPORT,JSON.stringify(report,null,2)+'\n');}
  console.log(JSON.stringify({check:'simulation-http-seven-scenarios',outcome:'PASS',source:report.source,runId:report.runId,
    scenarios:report.results.map(value=>({id:value.scenarioId,outcome:value.outcome,steps:value.steps.length})),
    originAndInputBounds:true,concurrentRunRefused:true,rawCredentialsExposed:false,externalProviderCalls:0}));
} finally {await app.close();}
