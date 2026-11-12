import {readFile, readdir, mkdir, writeFile, rename, stat, unlink, rmdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {hostname} from 'node:os';
import {randomUUID} from 'node:crypto';
import {loadPackages,packageDigest,EXPECTED_COMPANIES} from '../lib/catalog.mjs';

export const REPOSITORY = 'SalesSquad/junction-pets';
export const CLOUD_PROVIDER = 'codex-cloud';
export const CLOUD_STATES = Object.freeze(['unprovisioned','provisioning','ready','running','blocked','failed','stale']);
const shaPattern=/^[a-f0-9]{40}$/;
const digestPattern=/^[a-f0-9]{64}$/;
const slugPattern=/^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const validInstant=value=>typeof value==='string'&&Number.isFinite(Date.parse(value))&&value.endsWith('Z');
const required=(condition,message)=>{if(!condition)throw new Error(message);};
const jsonFile=async path=>JSON.parse(await readFile(path,'utf8'));

export function expectedEnvironment(companySlug) {
  required(slugPattern.test(companySlug),'Invalid company slug');
  return {
    schemaVersion:1,
    petSlug:'junction-'+companySlug,
    agentId:'junction-dev-'+companySlug,
    provider:CLOUD_PROVIDER,
    desiredName:'junction-'+companySlug,
    repository:REPOSITORY,
    branchPattern:'codex/junction-'+companySlug+'-*',
    ownedPath:'pets/'+companySlug+'/',
    agentInstructions:'ops/AGENTS.md',
    runtimeInstructions:'pets/'+companySlug+'/AGENTS.md',
    setupCommand:'npm ci --ignore-scripts',
    checkCommands:['npm run validate','npm test','npm run build'],
    provisioning:{state:'unprovisioned',environmentId:null,verifiedAt:null,evidenceUrl:null}
  };
}

export function validateEnvironment(manifest,companySlug) {
  const desired=expectedEnvironment(companySlug);
  for(const key of ['schemaVersion','petSlug','agentId','provider','desiredName','repository','branchPattern','ownedPath','agentInstructions','runtimeInstructions','setupCommand']) {
    required(manifest[key]===desired[key], 'Invalid '+key+' in '+companySlug+' environment');
  }
  required(JSON.stringify(manifest.checkCommands)===JSON.stringify(desired.checkCommands),'Invalid check commands for '+companySlug);
  const p=manifest.provisioning;
  required(p&&typeof p==='object'&&CLOUD_STATES.includes(p.state),'Invalid cloud state for '+companySlug);
  if(p.state==='unprovisioned') {
    required(p.environmentId===null&&p.verifiedAt===null&&p.evidenceUrl===null,'Unprovisioned environment cannot claim an ID or evidence');
  } else {
    // A failed/provisioning attempt need not have an ID. Ready/running must have a provider ID.
    if(['ready','running','stale'].includes(p.state))required(typeof p.environmentId==='string'&&p.environmentId.length>=5,'Cloud ID requires evidence for '+companySlug);
    else required(p.environmentId===null||(typeof p.environmentId==='string'&&p.environmentId.length>=5),'Invalid cloud ID');
    // A manifest is a DECLARATION. The dashboard labels recorded provenance; it does not query OpenAI.
    required(validInstant(p.verifiedAt),'Cloud verifiedAt requires UTC instant for '+companySlug);
    required(typeof p.evidenceUrl==='string'&&p.evidenceUrl.startsWith('https://'),'Cloud evidence URL required for '+companySlug);
  }
  return manifest;
}

export function validateReceipt(receipt,slug,expectedPackageDigest,mainCommit) {
  required(receipt&&receipt.schemaVersion===2&&receipt.petSlug===slug,'Invalid version-2 receipt identity for '+slug);
  required(typeof receipt.workId==='string'&&receipt.workId.startsWith('junction.'+slug.slice('junction-'.length)+'.'),'Receipt requires pet-scoped work ID');
  required(shaPattern.test(receipt.taskHeadSha),'Receipt requires exact 40-character task/PR HEAD SHA for '+slug);
  required(digestPattern.test(receipt.packageSha256),'Receipt requires exact 64-character package content digest for '+slug);
  required(digestPattern.test(expectedPackageDigest),'Expected pet package content digest required');
  required(validInstant(receipt.recordedAt),'Receipt requires recordedAt UTC for '+slug);
  required(Array.isArray(receipt.checks)&&receipt.checks.every(c=>
    typeof c.name==='string'&&c.name.length>0&&
    ['pass','fail','blocked'].includes(c.result)&&
    typeof c.evidenceUrl==='string'&&c.evidenceUrl.startsWith('https://')&&c.taskHeadSha===receipt.taskHeadSha
  ),'Receipt checks require result, exact task HEAD and external evidence URLs for '+slug);
  required(new Set(receipt.checks.map(c=>c.name)).size===receipt.checks.length,'Duplicate receipt checks for '+slug);
  required(
    typeof receipt.branch==='string'&&receipt.branch.startsWith('codex/'+slug+'-')&&
    /^[a-z0-9/_-]+$/.test(receipt.branch),'Invalid task branch for '+slug
  );
  if(receipt.prUrl!==undefined&&receipt.prUrl!==null)required(
    typeof receipt.prUrl==='string'&&/^https:\/\/github\.com\/SalesSquad\/junction-pets\/pull\/[1-9][0-9]*$/.test(receipt.prUrl),
    'Invalid canonical PR URL for '+slug
  );
  if(receipt.prUrl)required(receipt.prHeadSha===receipt.taskHeadSha,'Recorded PR HEAD must exactly match task HEAD');
  if(receipt.integration!==undefined){
    required(receipt.integration&&shaPattern.test(receipt.integration.mainHeadSha)&&
      receipt.integration.prUrl===receipt.prUrl&&validInstant(receipt.integration.recordedAt)&&
      typeof receipt.integration.evidenceUrl==='string'&&receipt.integration.evidenceUrl.startsWith('https://'),
    'Main integration requires distinct main SHA and external merge evidence');
  }
  if(receipt.evaluation){
    const e=receipt.evaluation;
    required(Number.isInteger(e.executed)&&e.executed>=0&&Number.isInteger(e.passed)&&e.passed>=0&&e.passed<=e.executed,'Invalid evaluation counts '+slug);
    required(typeof e.model==='string'&&e.model.length>0&&typeof e.evidenceUrl==='string'&&e.evidenceUrl.startsWith('https://')&&
      e.taskHeadSha===receipt.taskHeadSha,'Evaluation requires model, exact task HEAD and evidence link');
  }
  const contentCurrent=receipt.packageSha256===expectedPackageDigest;
  const binding=!contentCurrent?'stale-package':
    (mainCommit&&receipt.integration?.mainHeadSha===mainCommit?'main-integration-recorded':
    (mainCommit&&receipt.taskHeadSha===mainCommit?'source-matched-recorded':'task-branch-package-recorded'));
  return {
    ...receipt,
    binding,
    // There is no authenticated provider query here; evidence remains reported, never hosted-certified.
    verification:'reported-not-independently-verified'
  };
}

export function validateRegistry(packs,manifests) {
  required(packs.length===34,'Expected 34 pet packages');
  required(manifests.length===34,'Expected 34 cloud environment manifests');
  const sorted=[...EXPECTED_COMPANIES].sort();
  const found=manifests.map(m=>m.petSlug.slice('junction-'.length)).sort();
  required(JSON.stringify(found)===JSON.stringify(sorted),'Manifest roster mismatch or duplicate');
  for(const pack of packs) {
    const slug=pack.pet.company.slug;
    const manifest=manifests.find(m=>m.petSlug===pack.pet.slug);
    required(!!manifest,'Missing manifest '+slug);
    validateEnvironment(manifest,slug);
  }
  const agentIds=manifests.map(m=>m.agentId);
  required(new Set(agentIds).size===agentIds.length,'Duplicate developer agent IDs');
  const names=manifests.map(m=>m.desiredName);
  required(new Set(names).size===names.length,'Duplicate Codex Cloud desired names');
  return true;
}

export async function loadEnvironmentManifests(root){
  const dir=resolve(root,'ops/environments');
  const filenames=(await readdir(dir)).filter(name=>name.endsWith('.json')).sort();
  const manifests=await Promise.all(filenames.map(name=>jsonFile(resolve(dir,name))));
  for(let i=0;i<filenames.length;i++)required(filenames[i]===manifests[i].petSlug.slice('junction-'.length)+'.json','Manifest filename/identity mismatch: '+filenames[i]);
  return manifests;
}

export function localSourceCommit(root){
  const result=spawnSync('git',['rev-parse','--verify','HEAD'],{cwd:root,encoding:'utf8',timeout:2000});
  const sha=result.status===0?result.stdout.trim():null;
  if(!shaPattern.test(sha??''))return null;
  const dirty=spawnSync('git',['status','--porcelain','--untracked-files=normal'],{cwd:root,encoding:'utf8',timeout:5000});
  // A local SHA cannot identify the current bytes if any files are modified or untracked.
  return dirty.status===0&&dirty.stdout.trim().length===0?sha:null;
}

export async function loadPetReceipts(root,companySlug,expectedPackageDigest,mainCommit){
  const folder=resolve(root,'ops/receipts/'+companySlug);
  let names;
  try{names=(await readdir(folder)).filter(name=>name.endsWith('.json')).sort();}
  catch(error){if(error?.code==='ENOENT')return [];throw error;}
  const receipts=await Promise.all(names.map(async name=>{
    const record=validateReceipt(await jsonFile(resolve(folder,name)),'junction-'+companySlug,expectedPackageDigest,mainCommit);
    required(name===record.workId+'.'+record.taskHeadSha.slice(0,12)+'.json','Receipt filename must bind work ID and task HEAD');
    return record;
  }));
  const keys=receipts.map(r=>r.workId+'@'+r.taskHeadSha);
  required(new Set(keys).size===keys.length,'Duplicate task/HEAD receipts for '+companySlug);
  return receipts.sort((a,b)=>b.recordedAt.localeCompare(a.recordedAt)||a.workId.localeCompare(b.workId));
}

async function pluginSourceState(root,pet){
  const sourcePath='plugins/'+pet.slug+'/plugin.json';
  let manifest;
  try{manifest=await jsonFile(resolve(root,sourcePath));}
  catch(error){if(error?.code==='ENOENT')return {
    desiredName:pet.slug,sourcePath,presence:'missing',installationState:'not-registered',pluginId:null,sourceVersion:null,verification:'not-checked-at-host'
  };throw error;}
  const matches=manifest.name===pet.slug&&manifest.version===pet.version&&
    manifest.repository==='https://github.com/SalesSquad/junction-pets';
  return {
    desiredName:pet.slug,sourcePath,presence:matches?'source-present':'source-drift',
    installationState:'not-registered',pluginId:null,
    sourceVersion:typeof manifest.version==='string'?manifest.version:null,
    verification:'source-file-only-no-install-proof'
  };
}

async function optionalClaim(claimRoot,slug,now,sourceCommit){
  try{
    const claim=await jsonFile(resolve(claimRoot,slug+'.json'));
    required(claim.petSlug==='junction-'+slug&&validInstant(claim.expiresAt),'Invalid local claim for '+slug);
    // A lease for an older source cannot silently occupy the new source work item.
    return Date.parse(claim.expiresAt)>now&&sourceCommit!==null&&claim.sourceCommit===sourceCommit
      ?{agentId:claim.agentId,workId:claim.workId,expiresAt:claim.expiresAt,scope:'single-workspace-only'}:null;
  }catch(error){if(error?.code==='ENOENT')return null;throw error;}
}

export async function buildStatus(root,{now=new Date(),sourceCommit=localSourceCommit(root),claimRoot=resolve(root,'dist/ops-claims')}={}){
  required(now instanceof Date&&Number.isFinite(now.valueOf()),'Invalid snapshot time');
  required(sourceCommit===null||shaPattern.test(sourceCommit),'Invalid source commit');
  const packs=await loadPackages(root);
  const manifests=await loadEnvironmentManifests(root);
  validateRegistry(packs,manifests);
  const pets=await Promise.all(packs.map(async pack=>{
    const pet=pack.pet, company=pet.company;
    const manifest=manifests.find(m=>m.petSlug===pet.slug);
    const digest=packageDigest(pack);
    const plugin=await pluginSourceState(root,pet);
    const receipts=await loadPetReceipts(root,company.slug,digest,sourceCommit);
    const claim=await optionalClaim(claimRoot,company.slug,now.valueOf(),sourceCommit);
    const applicableReceipts=receipts.filter(receipt=>receipt.binding!=='stale-package');
    const receipt=applicableReceipts[0]??null;
    const reported=!!receipt;
    for(const item of applicableReceipts)required(
      !item.evaluation||item.evaluation.executed<=pack.evals.cases.length,
      'Evaluation exceeds authored case count for '+pet.slug
    );
    const recordedEval=reported&&receipt.evaluation?receipt.evaluation:null;
    const failedChecks=receipt?.checks.filter(check=>check.result!=='pass')??[];
    const failedEval=!!recordedEval&&recordedEval.passed<recordedEval.executed;
    const noModelRun=!recordedEval||recordedEval.executed===0;
    const declarationState=manifest.provisioning.state;
    // A manifest is not the cloud provider. Never show provider-ready based on editable JSON.
    const reportedState=['ready','running'].includes(declarationState)?'reported-'+declarationState:declarationState;
    const cloud={
      provider:manifest.provider,desiredName:manifest.desiredName,
      environmentId:manifest.provisioning.environmentId,
      state:reportedState,declaredState:declarationState,verifiedAt:manifest.provisioning.verifiedAt,
      evidenceUrl:manifest.provisioning.evidenceUrl,
      repository:manifest.repository,
      verification:declarationState==='unprovisioned'?'not-provisioned':'declaration-not-live-rechecked'
    };
    const blockers=[];
    if(plugin.presence==='missing')blockers.push('No generated plugin source is present for this pet.');
    if(plugin.presence==='source-drift')blockers.push('Plugin source manifest does not match this pet version or identity.');
    if(cloud.state==='unprovisioned')blockers.push('A Codex Cloud environment ID has not been verified or provisioned for this pet.');
    if(!reported)blockers.push('No receipt matches the current pet content digest; branch work is unqualified.');
    else {
      if(!receipt.checks.length)blockers.push('Current task receipt has no executable check evidence.');
      if(failedChecks.length)blockers.push('Task checks failed or were blocked: '+failedChecks.map(c=>c.name+'='+c.result).join(', ')+'.');
      if(noModelRun)blockers.push('No actual model evaluation run has been recorded.');
      if(failedEval)blockers.push('Model evaluation reported '+(recordedEval.executed-recordedEval.passed)+' failed cases.');
    }
    if(cloud.state!=='unprovisioned')blockers.push('Cloud/provider and Chibi recipient journey are not independently verified.');
    const blocker=blockers.join(' ');
    const nextAction=failedChecks.length||failedEval
      ?'Repair the latest source-matched failures, rerun checks, then record a new immutable task receipt.'
      :cloud.state==='unprovisioned'
      ?'Create and publish this pet Codex Cloud environment, then record its actual ID and evidence URL.'
      :!reported?'Run branch-specific CI and behavior evaluations; attach pet digest and exact PR HEAD.':'Recheck provider evidence and the complete Chibi recipient journey.';
    return {
      slug:pet.slug,company:{slug:company.slug,name:company.name,role:company.role},role:company.role,
      packageVersion:pet.version,
      agent:{id:manifest.agentId,instructions:manifest.agentInstructions,petInstructions:manifest.runtimeInstructions,workItem:'junction.'+company.slug+'.cloud-bootstrap'},
      cloud,plugin,
      development:{
        state:failedChecks.length||failedEval?'reported-failures':claim?'local-lease-active':(reported?'task-branch-receipts-recorded':'content-ready'),
        sourceCommit:reported?receipt.taskHeadSha:null,
        branch:reported?(receipt.branch??null):null,
        prUrl:reported?(receipt.prUrl??null):null,
        claim,
        checks:reported?receipt.checks:[],
        recordedAt:reported?receipt.recordedAt:null,
        receiptBinding:receipt?.binding??(receipts.length?'stale-package':'missing'),
        evidenceVerification:reported?receipt.verification:'none',
        packageDigest:digest,
        receipts:receipts.map(r=>({
          workId:r.workId,branch:r.branch,prUrl:r.prUrl??null,taskHeadSha:r.taskHeadSha,
          packageSha256:r.packageSha256,recordedAt:r.recordedAt,binding:r.binding,
          checks:r.checks,evaluation:r.evaluation??null,
          integration:r.integration??null,verification:r.verification
        }))
      },
      evaluation:{
        defined:pack.evals.cases.length,
        executed:recordedEval?.executed??0,
        passed:recordedEval?.passed??0,
        failed:recordedEval?recordedEval.executed-recordedEval.passed:0,
        lastRun:recordedEval?{model:recordedEval.model,evidenceUrl:recordedEval.evidenceUrl,verification:'reported-not-independently-verified'}:null
      },
      runtime:{state:'unverified',publicationState:'not-published',verifiedAt:null},
      blocker,nextAction
    };
  }));
  const summary={
    total:pets.length,
    cloudReady:pets.filter(p=>p.cloud.state==='ready'||p.cloud.state==='running').length,
    cloudUnprovisioned:pets.filter(p=>p.cloud.state==='unprovisioned').length,
    active:pets.filter(p=>p.development.claim).length,
    blocked:pets.filter(p=>typeof p.blocker==='string'&&p.blocker.length>0).length,
    definedEvalCases:pets.reduce((sum,p)=>sum+p.evaluation.defined,0),
    executedEvalCases:pets.reduce((sum,p)=>sum+p.evaluation.executed,0),
    published:0
  };
  return {
    schemaVersion:1,generatedAt:now.toISOString(),
    source:{repository:REPOSITORY,commit:sourceCommit,verification:sourceCommit?'local-git-only':'unverified',hostedCiQualified:false},
    summary,pets
  };
}

export async function writeStatus(root,options={}){
  const status=await buildStatus(root,options);
  const target=resolve(root,'dist/mission-control/status.json');
  await mkdir(resolve(root,'dist/mission-control'),{recursive:true});
  await writeFile(target,JSON.stringify(status,null,2)+'\n','utf8');
  return {target,status};
}

export function leaseContent({petSlug,agentId,workId,sourceCommit,minutes=30,now=new Date()}){
  required(/^junction-[a-z0-9-]+$/.test(petSlug),'Invalid pet slug');
  required(/^junction-dev-[a-z0-9-]+$/.test(agentId),'Invalid developer agent ID');
  required(typeof workId==='string'&&workId.startsWith('junction.'),'Invalid work ID');
  required(shaPattern.test(sourceCommit),'Lease requires exact source commit');
  required(Number.isInteger(minutes)&&minutes>=1&&minutes<=120,'Lease must be 1–120 minutes');
  const leaseId=randomUUID();
  return {schemaVersion:1,leaseId,petSlug,agentId,workId,sourceCommit,createdAt:now.toISOString(),expiresAt:new Date(now.valueOf()+minutes*60000).toISOString(),scope:'single-workspace-only'};
}

const CRITICAL_LOCK_MS=120000;
export async function enterCriticalLock(claimRoot,company,{now=new Date()}={}){
  required(EXPECTED_COMPANIES.includes(company),'Unknown lock owner company');
  await mkdir(claimRoot,{recursive:true});
  const owner={
    schemaVersion:1,ownerId:randomUUID(),company,pid:process.pid,hostname:hostname(),
    createdAt:now.toISOString(),expiresAt:new Date(now.valueOf()+CRITICAL_LOCK_MS).toISOString()
  };
  const stage=resolve(claimRoot,company+'.pending-'+owner.ownerId);
  const lock=resolve(claimRoot,company+'.lock');
  await mkdir(stage);
  try{
    await writeFile(resolve(stage,'owner.json'),JSON.stringify(owner,null,2)+'\n','utf8');
    await rename(stage,lock); // Atomic directory publication; a live lock is non-empty.
  }catch(error){
    await unlink(resolve(stage,'owner.json')).catch(e=>{if(e.code!=='ENOENT')throw e;});
    await rmdir(stage).catch(e=>{if(e.code!=='ENOENT')throw e;});
    if(error.code==='EEXIST'||error.code==='ENOTEMPTY')throw new Error('Pet critical lock busy; inspect owner metadata before explicit stale recovery');
    throw error;
  }
  return owner;
}

export async function leaveCriticalLock(claimRoot,company,owner){
  const lock=resolve(claimRoot,company+'.lock');
  const current=await jsonFile(resolve(lock,'owner.json'));
  required(current.ownerId===owner.ownerId,'Critical lock owner changed: refuse release');
  await unlink(resolve(lock,'owner.json'));
  await rmdir(lock);
}

const processStillAlive=pid=>{
  if(!Number.isInteger(pid)||pid<=0)return true;
  try{process.kill(pid,0);return true;}
  catch(error){return error.code!=='ESRCH';}
};

export async function reclaimStaleCriticalLock({claimRoot,petSlug,expectedOwnerId,now=new Date(),graceMs=120000}){
  const company=petSlug?.startsWith('junction-')?petSlug.slice('junction-'.length):null;
  required(EXPECTED_COMPANIES.includes(company),'Unknown pet critical lock');
  required(typeof expectedOwnerId==='string'&&expectedOwnerId.length>=16,'Exact lock owner ID required');
  required(Number.isInteger(graceMs)&&graceMs>=60000,'Lock recovery grace cannot be less than 60 seconds');
  const lock=resolve(claimRoot,company+'.lock');
  const owner=await jsonFile(resolve(lock,'owner.json'));
  required(owner.ownerId===expectedOwnerId,'Critical lock owner mismatch');
  required(owner.hostname===hostname(),'Remote-host lock cannot be reclaimed by this process');
  required(validInstant(owner.expiresAt)&&Date.parse(owner.expiresAt)+graceMs<now.valueOf(),'Critical lock not beyond expiry and safety grace');
  required(!processStillAlive(owner.pid),'Critical lock owner PID is still alive; refusing recovery');
  const quarantined=resolve(claimRoot,company+'.reclaim-'+randomUUID());
  await rename(lock,quarantined);
  const after=await jsonFile(resolve(quarantined,'owner.json'));
  if(after.ownerId!==expectedOwnerId){
    await rename(quarantined,lock);
    throw new Error('Critical lock changed during recovery; no deletion performed');
  }
  await unlink(resolve(quarantined,'owner.json'));
  await rmdir(quarantined);
  return {result:'dead-owner-stale-lock-recovered',petSlug,ownerId:expectedOwnerId};
}

export async function acquireLease(root,lease,{claimRoot=resolve(root,'dist/ops-claims'),now=new Date()}={}){
  const company=lease.petSlug.slice('junction-'.length);
  required(EXPECTED_COMPANIES.includes(company),'Pet not in company roster');
  const manifest=await jsonFile(resolve(root,'ops/environments/'+company+'.json'));
  validateEnvironment(manifest,company);
  required(lease.agentId===manifest.agentId,'Cannot claim with a different pet agent');
  const owner=await enterCriticalLock(claimRoot,company,{now});
  try {
    const path=resolve(claimRoot,company+'.json');
    let previous=null;
    try{previous=await jsonFile(path);}catch(error){if(error.code!=='ENOENT')throw error;}
    if(previous && Date.parse(previous.expiresAt)>now.valueOf())throw new Error('Active lease belongs to '+previous.agentId);
    const tmp=resolve(claimRoot,company+'.'+randomUUID()+'.tmp');
    await writeFile(tmp,JSON.stringify(lease,null,2)+'\n','utf8');
    await rename(tmp,path);
    return lease;
  }finally{
    await leaveCriticalLock(claimRoot,company,owner);
  }
}

export async function releaseLease(root,{petSlug,leaseId,claimRoot=resolve(root,'dist/ops-claims')}){
  const company=petSlug.slice('junction-'.length);
  required(EXPECTED_COMPANIES.includes(company),'Invalid pet for release');
  const owner=await enterCriticalLock(claimRoot,company);
  try{
    const path=resolve(claimRoot,company+'.json');
    const claim=await jsonFile(path);
    required(claim.leaseId===leaseId,'Lease ownership mismatch');
    await unlink(path);
    return true;
  }finally{
    await leaveCriticalLock(claimRoot,company,owner);
  }
}
