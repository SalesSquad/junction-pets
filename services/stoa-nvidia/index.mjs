import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {runDrawingObservation,validateDrawingRequest,drawingRequestDigest,validateDrawingObservationResult,MODEL} from '../nemotron-vl/index.mjs';

const sha=value=>createHash('sha256').update(typeof value==='string'||Buffer.isBuffer(value)?value:JSON.stringify(value)).digest('hex');
const SHA=/^[a-f0-9]{40}$/;
const exact=(v,keys)=>v && Object.getPrototypeOf(v)===Object.prototype &&
 Reflect.ownKeys(v).length===keys.length && keys.every(k=>Object.hasOwn(v,k)&&'value' in Object.getOwnPropertyDescriptor(v,k));
function requireValue(ok){if(!ok)throw new TypeError('invalid-stoa-drawing-task');}
function binding() {
 const manifest=readFileSync(new URL('../../pets/stoa/pet.json',import.meta.url));
 const guidance=readFileSync(new URL('../../pets/stoa/AGENTS.md',import.meta.url));
 requireValue(manifest.length<=65536&&guidance.length<=65536);
 const p=JSON.parse(manifest);requireValue(p.id==='junction.stoa'&&/^\d+\.\d+\.\d+$/.test(p.version));
 return {id:p.id,version:p.version,manifestSha256:sha(manifest),guidanceSha256:sha(guidance)};
}

const HEX=/^[a-f0-9]{64}$/;
function safeBinding(value) {
 requireValue(value&&value.id==='junction.nvidia'&&typeof value.version==='string'&&/^\d+\.\d+\.\d+$/.test(value.version)&&
  typeof value.manifestSha256==='string'&&HEX.test(value.manifestSha256)&&typeof value.guidanceSha256==='string'&&HEX.test(value.guidanceSha256));
 return {id:value.id,version:value.version,manifestSha256:value.manifestSha256,guidanceSha256:value.guidanceSha256};
}
function childSummary(child) {
 requireValue(Array.isArray(child.providerCalls)&&child.providerCalls.length<=7&&child.usage&&
  ['promptTokens','completionTokens','totalTokens'].every(k=>Number.isSafeInteger(child.usage[k])&&child.usage[k]>=0));
 const calls=child.providerCalls.map(c=>{
  requireValue(['drawing_observation','drawing_verification'].includes(c.stage)&&['pending','completed','failed'].includes(c.status)&&
   c.requestedModel===MODEL&&(c.returnedModel===null||c.returnedModel===MODEL)&&typeof c.requestDigest==='string'&&HEX.test(c.requestDigest)&&
   (c.responseDigest===null||typeof c.responseDigest==='string'&&HEX.test(c.responseDigest))&&Number.isFinite(c.elapsedMs)&&c.elapsedMs>=0);
  return {stage:c.stage,status:c.status,requestedModel:c.requestedModel,returnedModel:c.returnedModel,
   requestDigest:c.requestDigest,responseDigest:c.responseDigest,elapsedMs:c.elapsedMs};
 });
 return {workflow:'junction.nvidia.drawing-observation',status:child.status==='completed'?'completed':'failed',
  requestedModel:MODEL,inputDigest:child.inputDigest,providerCalls:calls,
  usage:{promptTokens:child.usage.promptTokens,completionTokens:child.usage.completionTokens,totalTokens:child.usage.totalTokens},
  usageAccountingComplete:child.usageAccountingComplete===true,costs:'unknown'};
}
function scrub(value,key) {
 if(typeof value==='string')return (key?value.split(key).join('[REDACTED]'):value)
  .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi,'Bearer [REDACTED]')
  .replace(/\b(?:nvapi-|sk-)[A-Za-z0-9_-]{8,}/g,'[REDACTED]');
 if(Array.isArray(value))return value.map(v=>scrub(v,key));
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,scrub(v,key)]));
 return value;
}
const parentDigest=(sourceCommit,requestDigest)=>sha({actor:'junction.stoa',recipient:'junction.nvidia',sourceCommit,requestDigest});
/** A finite developer task, not a signed grant or production collaboration envelope. */
export function prepareStoaDrawingTask(request,{sourceCommit}={}) {
 requireValue(typeof sourceCommit==='string'&&SHA.test(sourceCommit));
 const safe=validateDrawingRequest(request),requestDigest=drawingRequestDigest(safe);
 return {schemaVersion:1,from:'junction.stoa',to:'junction.nvidia',sourceCommit,
  parentOutputDigest:parentDigest(sourceCommit,requestDigest),request:safe};
}
export function validateStoaDrawingTask(task) {
 requireValue(exact(task,['schemaVersion','from','to','sourceCommit','parentOutputDigest','request']));
 requireValue(task.schemaVersion===1&&task.from==='junction.stoa'&&task.to==='junction.nvidia'&&
  typeof task.sourceCommit==='string'&&SHA.test(task.sourceCommit)&&typeof task.parentOutputDigest==='string');
 const safe=validateDrawingRequest(task.request),requestDigest=drawingRequestDigest(safe);
 requireValue(task.parentOutputDigest===parentDigest(task.sourceCommit,requestDigest));
 return {schemaVersion:1,from:task.from,to:task.to,sourceCommit:task.sourceCommit,parentOutputDigest:task.parentOutputDigest,request:safe};
}
/** Execute one fixed Stoa→NVIDIA delegation. Host owns source/rights/consent/provider authority. */
export async function runStoaNvidiaDrawing(task,{apiKey,fetchImpl=globalThis.fetch,observe=runDrawingObservation}={}) {
 const receipt={schemaVersion:1,workflow:'junction.stoa-to-nvidia.drawing',status:'failed',
  actor:'junction.stoa',recipient:'junction.nvidia',actorCapabilityId:'drawing-evidence-delegation',recipientCapabilityId:'drawing-observation',hostVerification:'unverified',
  productionAuthorized:false,evidenceType:observe!==runDrawingObservation||fetchImpl!==globalThis.fetch?
    'injected-synthetic-unqualified':'developer-provider-attempt-unverified',
  limitations:['Finite developer recipe, not authenticated Chibi collaboration.',
   'Source/rights declarations are not verified. A model answer candidate is not factual or geometric proof.'],
  childReceipt:null};
 try {
  const safe=validateStoaDrawingTask(task);
  receipt.actorBinding=binding();receipt.sourceCommit=safe.sourceCommit;
  receipt.parentOutputDigest=safe.parentOutputDigest;receipt.requestDigest=drawingRequestDigest(safe.request);
  if(typeof observe!=='function')throw new TypeError('invalid executor');
  const child=await observe(safe.request,{apiKey,fetchImpl});
  // Never accept arbitrary returned source/region claims as a successful delegation.
  if(!child || child.workflow!=='junction.nvidia.drawing-observation' ||
    child.requestedModel!==MODEL || child.companion?.id!=='junction.nvidia' ||
    child.inputDigest!==receipt.requestDigest)throw new TypeError('child binding');
  receipt.recipientBinding=safeBinding(child.companion);receipt.childReceipt=childSummary(child);
  if(child.status!=='completed'){receipt.error={code:'nvidia-drawing-failed',childCode:['missing-or-invalid-key','provider-auth-rejected','provider-rate-limited','provider-http-error','provider-transport-error','provider-timeout','deadline-exceeded','unexpected-model','model-verification-rejected'].includes(child.error?.code)?child.error.code:'nvidia-drawing-rejected'};return scrub(receipt,typeof apiKey==='string'?apiKey:'');}
  const drawing=validateDrawingObservationResult(child.result,safe.request);
  if(child.verification?.localEvidenceValidated!==true||child.verification?.modelReviewPassed!==true||
    !drawing||JSON.stringify(child.source)!==JSON.stringify(safe.request.source)||
    JSON.stringify(drawing.source)!==JSON.stringify(safe.request.source)||
    drawing.sourceSha256!==safe.request.source.sha256||drawing.page!==safe.request.source.page||
    !Array.isArray(drawing.observations)||
    drawing.geometryVerified!==false||drawing.factualVerification!=='unverified-model-interpretation')throw new TypeError('child evidence');
  const expectedRegions=safe.request.regions.map(r=>({id:r.id,imageSha256:r.imageSha256,bounds:r.bounds}));
  if(JSON.stringify(child.regions)!==JSON.stringify(expectedRegions))throw new TypeError('child regions');
  for(const observation of drawing.observations) {
   const region=expectedRegions.find(r=>r.id===observation.regionId);
   if(!region||observation.imageSha256!==region.imageSha256||JSON.stringify(observation.bounds)!==JSON.stringify(region.bounds))throw new TypeError('child citation');
  }
  if(!(drawing.answerCandidate===null||typeof drawing.answerCandidate==='string'&&
    drawing.answerCandidate.trim().length>0&&drawing.answerCandidate.length<=1200)||
    drawing.answerCandidate!==null&&drawing.observations.length===0)throw new TypeError('child answer');
  receipt.status=drawing.answerCandidate===null?'abstained':'candidate';
  receipt.result={answerCandidate:drawing.answerCandidate,citations:drawing.observations.map(o=>({
    sourceId:safe.request.source.id,sourceSha256:safe.request.source.sha256,page:safe.request.source.page,
    regionId:o.regionId,imageSha256:o.imageSha256,bounds:[...o.bounds],observation:o.text})),
    uncertainties:drawing.uncertainties,geometryVerified:false,factualVerification:'unverified-model-interpretation'};
  receipt.result=scrub(receipt.result,typeof apiKey==='string'?apiKey:'');
  receipt.outputDigest=sha(receipt.result);
 } catch {receipt.status='failed';receipt.error={code:'drawing-delegation-binding-failed'};delete receipt.result;}
 return scrub(receipt,typeof apiKey==='string'?apiKey:'');
}
