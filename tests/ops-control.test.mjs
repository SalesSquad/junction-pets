import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,symlink,writeFile,rm,readFile,unlink,cp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {loadPackages,packageDigest} from '../lib/catalog.mjs';
import {
  REPOSITORY,expectedEnvironment,validateEnvironment,validateRegistry,
  validateReceipt,loadEnvironmentManifests,loadPetReceipts,buildStatus,writeStatus,
  leaseContent,acquireLease,releaseLease,reclaimStaleCriticalLock,enterCriticalLock,leaveCriticalLock,
  pluginSourceFingerprint,validatePluginRegistration
} from '../ops/registry.mjs';
import {canonicalJson,sha256} from '../lib/artifact.mjs';
import {planCloudDispatch} from '../ops/cloud-dispatch.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const fixedTime=new Date('2026-11-12T19:00:00.000Z');
const sourceA='a'.repeat(40),sourceB='b'.repeat(40);
const sourceC='c'.repeat(40);
const registrationFor=(pet,fingerprint)=>({
  schemaVersion:1,petSlug:pet.slug,pluginName:pet.slug,provider:'chatgpt-plugin-creator',
  pluginId:'plugins_verified_readback_example',pluginUrl:'https://chatgpt.com/plugins/plugins_verified_readback_example',
  releaseId:'release_1234',visibility:'USER_PRIVATE',observedAt:fixedTime.toISOString(),
  sourceFiles:fingerprint.sourceFiles,sourceBundleSha256:fingerprint.sourceBundleSha256,
  evidenceUrl:'https://chatgpt.com/plugins/plugins_verified_readback_example'
});
const receiptFor=(packageSha256,{head=sourceA,work='junction.aiven.analysis-v1',at='2026-11-12T19:00:00.000Z',result='pass',executed=6,passed=6}={})=>({
  schemaVersion:2,petSlug:'junction-aiven',workId:work,taskHeadSha:head,packageSha256,
  recordedAt:at,branch:'codex/junction-aiven-analysis-v1',
  prUrl:'https://github.com/SalesSquad/junction-pets/pull/100',prHeadSha:head,
  checks:[{name:'test',result,evidenceUrl:'https://github.com/SalesSquad/junction-pets/actions/runs/123',taskHeadSha:head}],
  evaluation:{executed,passed,model:'actual-model-labelled',taskHeadSha:head,evidenceUrl:'https://example.org/eval-run'}
});
const writeReceipt=async (tmp,receipt)=>{
  const folder=join(tmp,'ops/receipts/aiven');
  await mkdir(folder,{recursive:true});
  await writeFile(join(folder,receipt.workId+'.'+receipt.taskHeadSha.slice(0,12)+'.json'),JSON.stringify(receipt));
};

async function fixtureRoot(){
  const path=await mkdtemp(join(tmpdir(),'junction-ops-fixture-'));
  await mkdir(join(path,'ops'));
  await symlink(resolve(root,'pets'),join(path,'pets'),'dir');
  await symlink(resolve(root,'ops/environments'),join(path,'ops/environments'),'dir');
  await mkdir(join(path,'ops/receipts'));
  return path;
}

test('34 individually scoped Codex Cloud declarations cover exact package roster',async()=>{
  const packs=await loadPackages(root),envs=await loadEnvironmentManifests(root);
  assert.equal(packs.length,34);
  assert.equal(envs.length,34);
  assert.equal(validateRegistry(packs,envs),true);
  assert.equal(new Set(envs.map(p=>p.agentId)).size,34);
  assert.equal(new Set(envs.map(p=>p.desiredName)).size,34);
  assert.ok(envs.every(p=>p.provisioning.state==='unprovisioned'));
  assert.ok(envs.every(p=>p.provisioning.environmentId===null));
  assert.ok(envs.every(p=>p.provisioning.verifiedAt===null));
  assert.ok(envs.every(p=>p.repository===REPOSITORY));
  assert.ok(envs.every(p=>p.agentInstructions==='ops/AGENTS.md'&&p.runtimeInstructions.includes('/AGENTS.md')));
});

test('cloud declaration rejects invented ID for unprovisioned and missing evidence for ready',()=>{
  const manifest=expectedEnvironment('aiven');
  manifest.provisioning.environmentId='env-fake';
  assert.throws(()=>validateEnvironment(manifest,'aiven'),/Unprovisioned/);
  manifest.provisioning.state='ready';
  assert.throws(()=>validateEnvironment(manifest,'aiven'),/verifiedAt/);
});

test('cloud dispatch cannot run against an unprovisioned or invented environment',()=>{
  const manifest=expectedEnvironment('aiven');
  const request={petSlug:'junction-aiven',branch:'codex/junction-aiven-guidance',sourceCommit:sourceA,profile:'plus'};
  assert.throws(()=>planCloudDispatch(manifest,request),/not declared ready/);
  const declaration=structuredClone(manifest);
  declaration.provisioning={
    state:'ready',environmentId:'some_recorded_id',verifiedAt:'2026-11-12T18:00:00.000Z',
    evidenceUrl:'https://chatgpt.com/codex'
  };
  const plan=planCloudDispatch(declaration,request);
  assert.equal(plan.mode,'dry-run-only');
  assert.equal(plan.executable,false);
  assert.equal(plan.providerIndependentlyRechecked,false);
  assert.deepEqual(plan.argv.slice(0,6),['codex-plus','cloud','exec','--env','some_recorded_id','--branch']);
  assert.ok(plan.task.includes(sourceA));
  assert.ok(plan.task.includes('pets/aiven/'));
  assert.throws(()=>planCloudDispatch(declaration,{...request,branch:'codex/junction-mariadb-feature'}),/isolated to this pet/);
  assert.throws(()=>planCloudDispatch(declaration,{...request,profile:'automatic'}),/never rotate accounts/);
});

test('registry rejects duplicate agent, missing company and extra package drift',async()=>{
  const packs=await loadPackages(root),envs=await loadEnvironmentManifests(root);
  assert.throws(()=>validateRegistry(packs,envs.slice(1)),/Expected 34/);
  assert.throws(()=>validateRegistry([...packs,packs[0]],envs),/Expected 34/);
  const forged=structuredClone(envs);
  forged[1].agentId=forged[0].agentId;
  assert.throws(()=>validateRegistry(packs,forged),/Invalid agentId|Duplicate developer/);
  const duplicate=structuredClone(envs);
  duplicate[1].petSlug=duplicate[0].petSlug;
  assert.throws(()=>validateRegistry(packs,duplicate),/Manifest roster/);
});

test('status has 34 independently addressable pets and never calls authored cases executed',async()=>{
  const status=await buildStatus(root,{now:fixedTime,sourceCommit:sourceA});
  assert.equal(status.schemaVersion,1);
  assert.equal(status.generatedAt,fixedTime.toISOString());
  assert.equal(status.source.repository,REPOSITORY);
  assert.equal(status.source.commit,sourceA);
  assert.equal(status.source.hostedCiQualified,false);
  assert.deepEqual(status.summary,{
    total:34,cloudReady:0,cloudUnprovisioned:34,active:0,blocked:34,
    definedEvalCases:204,executedEvalCases:0,published:0
  });
  assert.equal(status.pets.filter(p=>p.evaluation.defined===6).length,34);
  assert.ok(status.pets.every(p=>p.evaluation.executed===0&&p.runtime.state==='unverified'));
  assert.ok(status.pets.every(p=>p.development.receiptBinding==='missing'));
  assert.ok(status.pets.every(p=>p.agent.id==='junction-dev-'+p.company.slug));
  assert.ok(status.pets.every(p=>p.plugin.desiredName===p.slug&&/^plugins_/.test(p.plugin.pluginId)));
  assert.ok(status.pets.every(p=>p.plugin.installationState==='registered-source-matched-reported'));
  assert.equal(new Set(status.pets.map(p=>p.plugin.pluginId)).size,34);
});

test('generated plugin presence is distinct from host installation and publication',async()=>{
  const status=await buildStatus(root,{now:fixedTime,sourceCommit:sourceA});
  assert.equal(status.pets.filter(p=>p.plugin.presence==='source-present').length,34);
  assert.ok(status.pets.every(p=>p.plugin.verification==='provider-readback-recorded-not-rechecked'));
  assert.ok(status.pets.every(p=>p.plugin.installationState==='registered-source-matched-reported'));
  assert.ok(status.pets.every(p=>p.runtime.state==='unverified'));
  assert.equal(status.summary.published,0);
  const tmp=await fixtureRoot();
  try{
    const absent=await buildStatus(tmp,{now:fixedTime,sourceCommit:null});
    assert.equal(absent.pets.filter(p=>p.plugin.presence==='missing').length,34);
    assert.match(absent.pets[0].blocker,/No generated plugin source/);
  }finally{await rm(tmp,{recursive:true,force:true});}
});

test('private plugin registration binds exact three generated source files, but remains reported',async()=>{
  const pet=(await loadPackages(root)).find(p=>p.pet.company.slug==='aiven').pet;
  const fingerprint=await pluginSourceFingerprint(root,pet);
  assert.equal(Object.keys(fingerprint.sourceFiles).length,3);
  assert.equal(fingerprint.sourceBundleSha256,sha256(canonicalJson(fingerprint.sourceFiles)));
  const receipt=registrationFor(pet,fingerprint);
  const recorded=validatePluginRegistration(receipt,pet,fingerprint);
  assert.equal(recorded.binding,'source-matched-reported');
  assert.equal(recorded.verification,'provider-readback-recorded-not-rechecked');
  const tmp=await fixtureRoot();
  try{
    await symlink(resolve(root,'plugins'),join(tmp,'plugins'),'dir');
    await mkdir(join(tmp,'ops/plugin-registrations'));
    await writeFile(join(tmp,'ops/plugin-registrations/aiven.json'),JSON.stringify(receipt));
    const status=await buildStatus(tmp,{now:fixedTime,sourceCommit:sourceA});
    const p=status.pets.find(x=>x.company.slug==='aiven');
    assert.equal(p.plugin.presence,'source-present');
    assert.equal(p.plugin.installationState,'registered-source-matched-reported');
    assert.equal(p.plugin.pluginId,receipt.pluginId);
    assert.equal(p.plugin.releaseId,receipt.releaseId);
    assert.equal(p.plugin.visibility,'USER_PRIVATE');
    assert.equal(p.plugin.verification,'provider-readback-recorded-not-rechecked');
    assert.equal(p.cloud.state,'unprovisioned');
    assert.equal(status.summary.published,0);
    assert.equal(status.pets.filter(x=>x.plugin.installationState==='not-registered').length,33);
  }finally{await rm(tmp,{recursive:true,force:true});}
});

test('plugin source fingerprint ties all four canonical pet input files to deterministic generated bytes',async()=>{
  const pet=(await loadPackages(root)).find(p=>p.pet.company.slug==='aiven').pet;
  const canonicalPaths={
    PET:'pet.json',AGENTS:'AGENTS.md',STORY:'STORY.md',EVALS:'evals.json'
  };
  const provenance=JSON.parse(await readFile(join(root,'plugins/junction-aiven/assets/source-manifest.json'),'utf8'));
  for(const [name,filename] of Object.entries(canonicalPaths)){
    const content=await readFile(join(root,'pets/aiven',filename),'utf8');
    assert.equal(provenance.source.paths[name].sha256,sha256(content));
  }
  const tmp=await fixtureRoot();
  try{
    // Copy, never modify shared canonical pet sources. Keep generated plugin bytes unchanged.
    await unlink(join(tmp,'pets'));
    await cp(join(root,'pets'),join(tmp,'pets'),{recursive:true});
    await symlink(resolve(root,'plugins'),join(tmp,'plugins'),'dir');
    await writeFile(join(tmp,'pets/aiven/AGENTS.md'),
      (await readFile(join(tmp,'pets/aiven/AGENTS.md'),'utf8'))+'\nEdited without version bump.\n');
    await assert.rejects(pluginSourceFingerprint(tmp,pet),/Generated plugin bytes stale/);
    const status=await buildStatus(tmp,{now:fixedTime,sourceCommit:sourceA});
    const changed=status.pets.find(p=>p.company.slug==='aiven');
    assert.equal(changed.plugin.presence,'source-drift');
    assert.equal(changed.plugin.pluginId,null);
    assert.match(changed.blocker,/Plugin source manifest does not match/);
  }finally{await rm(tmp,{recursive:true,force:true});}
});

test('tampered generated SKILL bytes invalidate fingerprint even when source-manifest claims original hashes',async()=>{
  const pet=(await loadPackages(root)).find(p=>p.pet.company.slug==='aiven').pet;
  const tmp=await fixtureRoot();
  try{
    await mkdir(join(tmp,'plugins'));
    await cp(join(root,'plugins/junction-aiven'),join(tmp,'plugins/junction-aiven'),{recursive:true});
    const file=join(tmp,'plugins/junction-aiven/skills/junction-aiven-companion/SKILL.md');
    await writeFile(file,(await readFile(file,'utf8'))+'\nTampered execution guidance.\n');
    await assert.rejects(pluginSourceFingerprint(tmp,pet),/Generated plugin bytes stale/);
  }finally{await rm(tmp,{recursive:true,force:true});}
});

test('stale plugin source file hashes suppress plugin ID and require re-registration',async()=>{
  const pet=(await loadPackages(root)).find(p=>p.pet.company.slug==='aiven').pet;
  const fingerprint=await pluginSourceFingerprint(root,pet);
  const receipt=registrationFor(pet,fingerprint);
  const differentMap={...receipt.sourceFiles,[Object.keys(receipt.sourceFiles)[1]]:'f'.repeat(64)};
  const stale={...receipt,sourceFiles:differentMap,sourceBundleSha256:sha256(canonicalJson(differentMap))};
  assert.equal(validatePluginRegistration(stale,pet,fingerprint).binding,'stale-source');
  const tmp=await fixtureRoot();
  try{
    await symlink(resolve(root,'plugins'),join(tmp,'plugins'),'dir');
    await mkdir(join(tmp,'ops/plugin-registrations'));
    await writeFile(join(tmp,'ops/plugin-registrations/aiven.json'),JSON.stringify(stale));
    const status=await buildStatus(tmp,{now:fixedTime,sourceCommit:sourceA});
    const p=status.pets.find(x=>x.company.slug==='aiven');
    assert.equal(p.plugin.installationState,'stale-registration');
    assert.equal(p.plugin.pluginId,null);
    assert.match(p.blocker,/stale source bytes/);
  }finally{await rm(tmp,{recursive:true,force:true});}
});

test('malformed, forged or public-scope plugin registration fails closed per pet',async()=>{
  const pet=(await loadPackages(root)).find(p=>p.pet.company.slug==='aiven').pet;
  const fingerprint=await pluginSourceFingerprint(root,pet);
  const good=registrationFor(pet,fingerprint);
  for(const bad of [
    {...good,visibility:'PUBLIC'},
    {...good,releaseId:''},
    {...good,pluginId:'x'},
    {...good,pluginUrl:'https://evil.example/plugins/x'},
    {...good,evidenceUrl:'https://chatgpt.com/plugins/plugins_verified_readback_example?token=secret'},
    {...good,pluginUrl:'https://chatgpt.com/space/page_123'},
    {...good,pluginUrl:'https://chatgpt.com/plugins/arbitrary-path'},
    {...good,evidenceUrl:'https://chatgpt.com/plugins/plugins_different_plugin'},
    {...good,pluginUrl:'https://chatgpt.com/plugins/plugins_different_plugin',
      evidenceUrl:'https://chatgpt.com/plugins/plugins_different_plugin'},
    {...good,pluginId:'Plugin_wrong_id_prefix'},
    {...good,sourceBundleSha256:'0'.repeat(64)},
    {...good,sourceFiles:{...good.sourceFiles,'plugins/junction-aiven/more.txt':'a'.repeat(64)}},
    {...good,secret:'synthetic-not-a-real-secret'},
    {...good,authorization:'Bearer synthetic-value'},
    {...good,ownerEmail:'synthetic@example.invalid'}
  ])assert.throws(()=>validatePluginRegistration(bad,pet,fingerprint));
  const tmp=await fixtureRoot();
  try{
    await symlink(resolve(root,'plugins'),join(tmp,'plugins'),'dir');
    await mkdir(join(tmp,'ops/plugin-registrations'));
    await writeFile(join(tmp,'ops/plugin-registrations/aiven.json'),JSON.stringify({...good,secret:'synthetic-not-a-real-secret'}));
    const status=await buildStatus(tmp,{now:fixedTime,sourceCommit:sourceA});
    const affected=status.pets.find(x=>x.company.slug==='aiven');
    assert.equal(affected.plugin.installationState,'malformed-registration');
    assert.equal(affected.plugin.pluginId,null);
    assert.match(affected.blocker,/Malformed private plugin registration/);
    assert.ok(!JSON.stringify(status).includes('synthetic-not-a-real-secret'));
    assert.equal(status.pets.length,34);
    assert.equal(status.pets.filter(x=>x.plugin.installationState==='not-registered').length,33);
  }finally{await rm(tmp,{recursive:true,force:true});}
});

test('missing Git metadata stays unverified and not manufactured',async()=>{
  const tmp=await fixtureRoot();
  try{
    const status=await buildStatus(tmp,{now:fixedTime,sourceCommit:null});
    assert.equal(status.source.commit,null);
    assert.equal(status.source.verification,'unverified');
    assert.ok(status.pets.every(p=>p.cloud.environmentId===null));
  } finally {await rm(tmp,{recursive:true,force:true});}
});

test('branch-specific receipts survive unrelated main SHA; package drift invalidates them',async()=>{
  const tmp=await fixtureRoot();
  try{
    const pack=(await loadPackages(root)).find(p=>p.pet.company.slug==='aiven');
    const digest=packageDigest(pack);
    const receipt=receiptFor(digest);
    await writeReceipt(tmp,receipt);
    const otherMain=await buildStatus(tmp,{now:fixedTime,sourceCommit:sourceB});
    const branch=otherMain.pets.find(p=>p.company.slug==='aiven');
    assert.equal(branch.development.receiptBinding,'task-branch-package-recorded');
    assert.equal(branch.development.prUrl,receipt.prUrl);
    assert.equal(branch.development.sourceCommit,sourceA);
    assert.equal(branch.development.receipts.length,1);
    assert.equal(otherMain.summary.published,0);
    const matched=await buildStatus(tmp,{now:fixedTime,sourceCommit:sourceA});
    const reported=matched.pets.find(p=>p.company.slug==='aiven');
    assert.equal(reported.development.receiptBinding,'source-matched-recorded');
    assert.equal(reported.development.evidenceVerification,'reported-not-independently-verified');
    assert.equal(reported.evaluation.executed,6);
    assert.equal(reported.evaluation.lastRun.verification,'reported-not-independently-verified');
    assert.equal(matched.summary.published,0);
    const staleReceipt={...receipt,packageSha256:sourceC+sourceC.slice(0,24)};
    await writeReceipt(tmp,staleReceipt);
    const stale=await buildStatus(tmp,{now:fixedTime,sourceCommit:sourceB});
    const aiven=stale.pets.find(p=>p.company.slug==='aiven');
    assert.equal(aiven.development.receiptBinding,'stale-package');
    assert.equal(aiven.development.prUrl,null);
    assert.deepEqual(aiven.development.checks,[]);
    assert.equal(aiven.evaluation.executed,0);
  } finally {await rm(tmp,{recursive:true,force:true});}
});

test('malformed receipt fails closed instead of being treated as green',async()=>{
  const digest='d'.repeat(64),receipt=receiptFor(digest);
  assert.throws(()=>validateReceipt({...receipt,checks:[{name:'test',result:'pass',taskHeadSha:sourceA}]},'junction-aiven',digest,sourceA),/evidence URLs/);
  assert.throws(()=>validateReceipt({...receipt,taskHeadSha:'short'},'junction-aiven',digest,sourceA),/HEAD SHA/);
  assert.throws(()=>validateReceipt({...receipt,prHeadSha:sourceB},'junction-aiven',digest,sourceA),/PR HEAD/);
  assert.throws(()=>validateReceipt({...receipt,evaluation:{...receipt.evaluation,taskHeadSha:sourceB}},'junction-aiven',digest,sourceA),/Evaluation requires/);
});

test('multiple task and PR receipts retained; newest failures are never cherry-picked away',async()=>{
  const tmp=await fixtureRoot();
  try{
    const pack=(await loadPackages(root)).find(p=>p.pet.company.slug==='aiven');
    const digest=packageDigest(pack);
    await writeReceipt(tmp,receiptFor(digest,{at:'2026-11-12T18:00:00.000Z',head:sourceA,work:'junction.aiven.original',result:'pass',executed:6,passed:6}));
    await writeReceipt(tmp,receiptFor(digest,{at:'2026-11-12T19:00:00.000Z',head:sourceB,work:'junction.aiven.retry',result:'fail',executed:6,passed:4}));
    const status=await buildStatus(tmp,{sourceCommit:sourceC,now:fixedTime});
    const pet=status.pets.find(p=>p.company.slug==='aiven');
    assert.equal(pet.development.receipts.length,2);
    assert.equal(pet.development.sourceCommit,sourceB);
    assert.equal(pet.development.state,'reported-failures');
    assert.match(pet.blocker,/Task checks failed/);
    assert.match(pet.blocker,/Model evaluation reported 2 failed/);
    assert.equal(pet.evaluation.passed,4);
    assert.equal(pet.evaluation.failed,2);
    assert.equal(status.summary.published,0);
    const records=await loadPetReceipts(tmp,'aiven',digest,sourceC);
    assert.equal(records[0].workId,'junction.aiven.retry');
  } finally {await rm(tmp,{recursive:true,force:true});}
});

test('reported main integration is separate from branch activity and never signed qualification',async()=>{
  const tmp=await fixtureRoot();
  try{
    const pack=(await loadPackages(root)).find(p=>p.pet.company.slug==='aiven');
    const receipt=receiptFor(packageDigest(pack));
    receipt.integration={
      mainHeadSha:sourceB,prUrl:receipt.prUrl,recordedAt:fixedTime.toISOString(),
      evidenceUrl:'https://github.com/SalesSquad/junction-pets/pull/100'
    };
    await writeReceipt(tmp,receipt);
    const status=await buildStatus(tmp,{now:fixedTime,sourceCommit:sourceB});
    const pet=status.pets.find(p=>p.company.slug==='aiven');
    assert.equal(pet.development.receiptBinding,'main-integration-recorded');
    assert.equal(pet.development.evidenceVerification,'reported-not-independently-verified');
    assert.equal(pet.runtime.state,'unverified');
    assert.equal(status.summary.published,0);
  }finally{await rm(tmp,{recursive:true,force:true});}
});

test('local per-pet lease rejects simultaneous competitors, wrong owner and releases exactly once',async()=>{
  const tmp=await mkdtemp(join(tmpdir(),'junction-lease-'));
  const opts={claimRoot:tmp,now:fixedTime};
  const a=leaseContent({petSlug:'junction-aiven',agentId:'junction-dev-aiven',workId:'junction.aiven.cloud-bootstrap',sourceCommit:sourceA,now:fixedTime});
  const b=leaseContent({petSlug:'junction-aiven',agentId:'junction-dev-aiven',workId:'junction.aiven.cloud-bootstrap',sourceCommit:sourceA,now:fixedTime});
  try{
    const results=await Promise.allSettled([acquireLease(root,a,opts),acquireLease(root,b,opts)]);
    assert.equal(results.filter(r=>r.status==='fulfilled').length,1);
    assert.equal(results.filter(r=>r.status==='rejected').length,1);
    const winner=results[0].status==='fulfilled'?a:b;
    await assert.rejects(releaseLease(root,{petSlug:'junction-aiven',leaseId:'wrong',claimRoot:tmp}),/ownership mismatch/);
    await releaseLease(root,{petSlug:'junction-aiven',leaseId:winner.leaseId,claimRoot:tmp});
    await assert.rejects(releaseLease(root,{petSlug:'junction-aiven',leaseId:winner.leaseId,claimRoot:tmp}),/ENOENT/);
  } finally {await rm(tmp,{recursive:true,force:true});}
});

test('expired local lease may be re-acquired; cross-pet agent cannot claim another pet',async()=>{
  const tmp=await mkdtemp(join(tmpdir(),'junction-lease-'));
  const early=new Date('2026-11-12T18:00:00.000Z');
  const old=leaseContent({petSlug:'junction-aiven',agentId:'junction-dev-aiven',workId:'junction.aiven.cloud-bootstrap',sourceCommit:sourceA,now:early,minutes:1});
  const renewed=leaseContent({petSlug:'junction-aiven',agentId:'junction-dev-aiven',workId:'junction.aiven.cloud-bootstrap',sourceCommit:sourceA,now:fixedTime});
  try{
    await acquireLease(root,old,{claimRoot:tmp,now:early});
    await acquireLease(root,renewed,{claimRoot:tmp,now:fixedTime});
    await assert.rejects(acquireLease(root,{...renewed,agentId:'junction-dev-mariadb'},{claimRoot:tmp,now:fixedTime}),/different pet agent/);
    await releaseLease(root,{petSlug:'junction-aiven',leaseId:renewed.leaseId,claimRoot:tmp});
  } finally {await rm(tmp,{recursive:true,force:true});}
});

test('crashed critical lock requires exact owner, expiry grace and dead PID before explicit reclaim',async()=>{
  const tmp=await mkdtemp(join(tmpdir(),'junction-lock-recover-'));
  const early=new Date('2026-11-12T18:00:00.000Z');
  try{
    const owner=await enterCriticalLock(tmp,'aiven',{now:early});
    const args={claimRoot:tmp,petSlug:'junction-aiven',expectedOwnerId:owner.ownerId,now:fixedTime};
    await assert.rejects(reclaimStaleCriticalLock({...args,expectedOwnerId:'different-owner-uuid'}),/owner mismatch/);
    await assert.rejects(reclaimStaleCriticalLock(args),/owner PID is still alive/);
    const dead={...owner,pid:99999999};
    await writeFile(join(tmp,'aiven.lock/owner.json'),JSON.stringify(dead));
    await assert.rejects(reclaimStaleCriticalLock({...args,now:early}),/expiry and safety grace/);
    const result=await reclaimStaleCriticalLock(args);
    assert.equal(result.result,'dead-owner-stale-lock-recovered');
    const second=await enterCriticalLock(tmp,'aiven',{now:fixedTime});
    await leaveCriticalLock(tmp,'aiven',second);
    await assert.rejects(reclaimStaleCriticalLock(args),/ENOENT/);
  }finally{await rm(tmp,{recursive:true,force:true});}
});

test('status writer creates the dashboard data without contaminating public site build',async()=>{
  const tmp=await fixtureRoot();
  try {
    const {target,status}=await writeStatus(tmp,{sourceCommit:null,now:fixedTime});
    assert.equal(target,join(tmp,'dist/mission-control/status.json'));
    assert.equal(JSON.parse(await readFile(target,'utf8')).pets.length,34);
    assert.equal(status.summary.published,0);
  } finally {await rm(tmp,{recursive:true,force:true});}
});
