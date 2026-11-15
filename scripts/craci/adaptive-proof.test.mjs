import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {appendReceipt,digest,selectExperiments,tupleOf,verifyReceiptLog} from './adaptive-core.mjs';
import {fetchCraciEvidence} from './provider-proof.mjs';

const H='e338251e2f43d1115610d8dbed7f2fc66a801285';
const R='59479b42b177c1829a2e6678adfff1fb68aef09c';
const NOW=new Date('2026-11-14T16:30:00Z');
function candidate(id, seed, value={uncertainty:0.9,disagreement:0.7,safetyRisk:0.8,novelty:1}) {
  return {id,group:'rokoko',workload:'rokoko-rl-ablations',cell:'rokoko-ablation-'+seed,
    sourceSha:R,harnessSha:H,scenarioDigest:digest({id,seed,locked:true}),seed,
    jobs:1,worstCaseEur:1.5,value,
    hypothesis:'Distinct held-out failure classes require a nonconstant safety policy.'};
}
function manifest(candidates=[candidate('rokoko-17',17),candidate('rokoko-43',43)]) {
  return {schema:'craci-adaptive-v1',repository:'SalesSquad/junction-pets',harnessSha:H,
    creditWindowOpen:true,dispatchAuthorized:false,deadlineUtc:'2026-11-15T17:00:00Z',
    campaignHardStopUtc:'2026-11-14T18:00:00Z',maxJobs:8,maxParallel:4,
    creditRemainingEur:10,campaignRemainingEur:6,
    meterReference:'operator/known-existing-credit-snapshot',meterObservedAtUtc:'2026-11-14T16:25:00Z',
    candidates};
}
function event(c,status='passed',other={}) {
  return {tupleDigest:digest(tupleOf(c)),sourceSha:R,harnessSha:H,status,
    jobs:1,reservedEur:1.5,whenUtc:'2026-11-14T16:28:00Z',
    githubRunUrl:'https://github.com/SalesSquad/junction-pets/actions/runs/43605259084',...other};
}
const expectError=(fn,pattern)=>assert.throws(fn,pattern);

test('shadow planner ranks information, and never dispatches or claims inference',()=>{
  const plan=selectExperiments(manifest(),'',{now:NOW});
  assert.deepEqual(plan.selected.map(x=>x.id),['rokoko-17','rokoko-43']);
  assert.equal(plan.additionalReservedEur,3);
  assert.equal(plan.dispatchAuthorized,false);
  assert.match(plan.inferencePolicy,/exploration_only/);
});

test('all budget, matrix, deadline and meter caps fail closed',()=>{
  const m=manifest();m.campaignRemainingEur=1;
  assert.deepEqual(selectExperiments(m,'',{now:NOW}).selected,[]);
  m.campaignRemainingEur=6;m.creditWindowOpen=false;
  expectError(()=>selectExperiments(m,'',{now:NOW}),/ADVISORY_ONLY/);
  m.creditWindowOpen=true;
  expectError(()=>selectExperiments(m,'',{now:new Date('2026-11-14T18:00:00Z')}),/CRACI_WINDOW_CLOSED/);
  expectError(()=>selectExperiments(m,'',{now:new Date('2026-11-15T17:00:00Z')}),/CRACI_WINDOW_CLOSED/);
  expectError(()=>selectExperiments(m,'',{now:new Date('2026-11-14T17:05:00Z')}),/STALE_OR_MISSING/);
  m.deadlineUtc='2026-11-16T17:00:00Z';
  expectError(()=>selectExperiments(m,'',{now:NOW}),/CRACI_WINDOW_CLOSED/);
});

test('changed scenario SHA changes tuple; duplicate or unpinned source rejected',()=>{
  const c=candidate('rokoko-17',17);
  expectError(()=>selectExperiments(manifest([c,{...c,id:'different-id'}]),'',{now:NOW}),/DUPLICATE_EXPERIMENT/);
  expectError(()=>selectExperiments(manifest([{...c,sourceSha:'deadbeef'}]),'',{now:NOW}),/UNPINNED_EXPERIMENT/);
  const changed={...c,id:'other-world',scenarioDigest:digest({newWorld:1})};
  assert.notEqual(digest(tupleOf(c)),digest(tupleOf(changed)));
});

test('append-only receipts are checked; unchanged green and failed tuples never reselected',async()=>{
  const root=await mkdtemp(join(tmpdir(),'craci-proof-')),path=join(root,'history.jsonl');
  try {
    const [a,b]=manifest().candidates;
    const first=await appendReceipt(path,event(a));
    await appendReceipt(path,event(b,'failed'),{expectedHead:first.hash});
    const raw=await readFile(path,'utf8');
    const checked=verifyReceiptLog(raw);
    assert.equal(checked.count,2);
    const plan=selectExperiments(manifest(),raw,{now:NOW});
    assert.deepEqual(plan.selected,[]);
    assert.deepEqual(plan.excluded.map(x=>x.reason),[
      'unchanged_green_tuple','unchanged_failed_tuple_requires_new_hypothesis']);
    expectError(()=>verifyReceiptLog(raw.replace('passed','failed')),/RECEIPT_CHAIN_BROKEN/);
    await assert.rejects(appendReceipt(path,event(a,'running'),{expectedHead:'0'.repeat(64)}),
      /RECEIPT_HEAD_CHANGED/);
  } finally {await rm(root,{recursive:true,force:true});}
});

test('currently reserved jobs are never admitted again and decrement future budget',async()=>{
  const root=await mkdtemp(join(tmpdir(),'craci-proof-')),path=join(root,'history.jsonl');
  try {
    const [a,b]=manifest().candidates;
    await appendReceipt(path,event(a,'queued'));
    const planned=selectExperiments(manifest(),await readFile(path,'utf8'),{now:NOW});
    assert.deepEqual(planned.selected.map(x=>x.id),[b.id]);
    assert.equal(planned.alreadyActiveReservedEur,1.5);
  } finally {await rm(root,{recursive:true,force:true});}
});

test('a later cancelled event cannot erase a historical green or failed tuple',async()=>{
  const root=await mkdtemp(join(tmpdir(),'craci-proof-')),path=join(root,'history.jsonl');
  try {
    const [a,b]=manifest().candidates;
    await appendReceipt(path,event(a,'passed'));
    await appendReceipt(path,event(a,'cancelled'));
    await appendReceipt(path,event(b,'failed'));
    await appendReceipt(path,event(b,'cancelled'));
    const plan=selectExperiments(manifest(),await readFile(path,'utf8'),{now:NOW});
    assert.deepEqual(plan.selected,[]);
    assert.deepEqual(plan.excluded.map(item=>item.reason),
      ['unchanged_green_tuple','unchanged_failed_tuple_requires_new_hypothesis']);
  } finally {await rm(root,{recursive:true,force:true});}
});

test('Immune and Chaos hard stop is immutable even if user manifest extends it',()=>{
  for (const workload of ['immune-tournament','chaos-lab']) {
    const c={...candidate('immune-17',17),workload};
    const m=manifest([c]);
    m.campaignHardStopUtc='2026-11-15T16:59:00Z';
    expectError(()=>selectExperiments(m,'',{now:NOW}),/IMMUNE_CHAOS_HARD_STOP_EXCEEDED/);
    m.campaignHardStopUtc='2026-11-14T18:00:00Z';
    assert.equal(selectExperiments(m,'',{now:NOW}).selected.length,1);
  }
});

test('one wave never exceeds maxParallel even with multiple multi-job candidates',()=>{
  const a={...candidate('batch-17',17),jobs:3};
  const b={...candidate('batch-43',43),jobs:3};
  const m=manifest([a,b]);m.maxParallel=4;
  const p=selectExperiments(m,'',{now:NOW});
  assert.equal(p.selected.length,1);
  assert.ok(p.selected.reduce((n,x)=>n+x.jobs,0)<=m.maxParallel);
  const impossible=manifest([{...a,jobs:8}]);impossible.maxParallel=4;
  assert.equal(selectExperiments(impossible,'',{now:NOW}).selected.length,0);
});

const mockData={
  job:{provider:'github',repository:'SalesSquad/junction-pets',jobId:'132303867708',
    runId:'43548053684',commitSha:H,status:'completed',runAttempt:1},
  observations:[{protocol:'http',http:{policyDenied:false}},
    {protocol:'tcp',tcp:{allowed:false}}],schemaVersion:'1'};
const query={repository:'SalesSquad/junction-pets',jobId:'132303867708',
  runId:'43548053684',expectedHarnessSha:H,runAttempt:1};
const response=(obj,type='application/json',status=200)=>new Response(JSON.stringify(obj),
  {status,headers:{'content-type':type}});

test('no CRACI API token yields explicit unknown evidence and unknown actual bill',async()=>{
  const x=await fetchCraciEvidence(query);
  assert.equal(x.network.status,'unknown');
  assert.equal(x.sbom.status,'unknown');
  assert.equal(x.perJobBilledEur,null);
  assert.equal(x.providerAttestationVerified,false);
});

test('authenticated mock network and SBOM are source-bound but never signed or billed',async()=>{
  const seen=[];
  const x=await fetchCraciEvidence(query,{token:'test-token-private',fetchImpl:async(url,opts)=>{
    seen.push({url,auth:opts.headers.Authorization});
    return url.includes('/network-trace')? response(mockData) :
      url.includes('/sbom')? response({bomFormat:'CycloneDX',specVersion:'1.7',components:[{name:'npm'}]},'application/vnd.cyclonedx+json; version=1.7') :
      response({start:'2026-11-14T00:00:00Z',end:'2026-11-15T00:00:00Z',total:{vcpuSeconds:12456}});
  },usagePeriod:{start:'2026-11-14T00:00:00Z',end:'2026-11-15T00:00:00Z'}});
  assert.equal(x.network.status,'provider_api_observed');
  assert.equal(x.network.observations,2);
  assert.equal(x.network.denied,1);
  assert.equal(x.sbom.components,1);
  assert.equal(x.sbom.coverage,'unverified');
  assert.equal(x.usage.aggregatedVcpuSeconds,'12456');
  assert.equal(x.usage.billedEur,null);
  assert.equal(x.perJobBilledEur,null);
  assert.equal(x.providerAttestationVerified,false);
  assert.ok(seen.every(entry=>entry.url.startsWith('https://api.craci.com/v1preview1/')));
  assert.ok(seen.every(entry=>entry.auth==='Bearer test-token-private'));
  assert.ok(!JSON.stringify(x).includes('test-token-private'));
});

test('official ssh_git discriminator and allowed:false are counted as denied',async()=>{
  const trace={...mockData,observations:[
    {protocol:'dns',dns:{record:'example.com A',response:'203.0.113.1'}},
    {protocol:'ssh_git',sshGit:{allowed:false,denyReason:'policy'}},
    {protocol:'ssh_git',sshGit:{allowed:true}},
  ]};
  const x=await fetchCraciEvidence(query,{token:'test-token-private',fetchImpl:async url=>
    url.includes('network-trace')?response(trace):response({bomFormat:'CycloneDX',specVersion:'1.7',components:[]})});
  assert.equal(x.network.status,'provider_api_observed');
  assert.equal(x.network.denied,1);
  assert.equal(x.network.protocolCounts.ssh_git,2);
});

test('wrong source, wrong run and API 403 never produce provider verified status',async()=>{
  for (const body of [{...mockData,job:{...mockData.job,commitSha:R}},
    {...mockData,job:{...mockData.job,runId:'1'}}]) {
    const x=await fetchCraciEvidence(query,{token:'test-token-private',fetchImpl:async url=>
      url.includes('network-trace')?response(body):response({},'application/json',403)});
    assert.equal(x.network.status,'unknown');
    assert.equal(x.sbom.status,'unknown');
    assert.equal(x.perJobBilledEur,null);
  }
});

test('apparently valid CycloneDX cannot qualify a mismatched GitHub source',async()=>{
  const bad={...mockData,job:{...mockData.job,commitSha:R}};
  const x=await fetchCraciEvidence(query,{token:'test-token-private',fetchImpl:async url=>
    url.includes('network-trace')?response(bad):
      response({bomFormat:'CycloneDX',specVersion:'1.7',components:[{name:'npm'}]})});
  assert.equal(x.network.reason,'PROVIDER_JOB_BINDING_MISMATCH');
  assert.equal(x.sbom.status,'unknown');
  assert.equal(x.sbom.reason,'JOB_BINDING_UNVERIFIED');
});

test('invalid query selectors never issue HTTP and fail closed',async()=>{
  let calls=0;
  await assert.rejects(fetchCraciEvidence({...query,jobId:'1&token=leak'},
    {token:'private-token',fetchImpl:async()=>{calls++;return response(mockData);}}),/INVALID_PROOF_SELECTOR/);
  assert.equal(calls,0);
});
