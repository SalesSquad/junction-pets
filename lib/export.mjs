import {validatePet,packageDigest} from './catalog.mjs';
import {canonicalJson,sha256,safeHttps} from './artifact.mjs';
import {companyContext} from './company-context.mjs';

/** Server-owned, nonsecret deployment settings; never infer these from a user prompt. */
export function validateBindings(bindings) {
  if(!bindings||typeof bindings.provider!=='string'||!bindings.provider.trim()||typeof bindings.model!=='string'||!bindings.model.trim()||!Array.isArray(bindings.allowedModelProviders)||!bindings.allowedModelProviders.includes(bindings.provider)||!safeHttps(bindings.privacyPolicyUrl)||!['eu','us','apac'].includes(bindings.region)||!Number.isInteger(bindings.retentionDays)||bindings.retentionDays<0||bindings.retentionDays>3650)throw new TypeError('Verified host model, privacy and region bindings are required');
  return bindings;
}
export function makerCandidate(pack,bindings) {
  const b=validateBindings(bindings),pet=validatePet(pack.pet),prompt=companyContext(pack);
  if([...prompt].length>20000)throw new TypeError('Company instructions exceed Chibi manifest limit');
  const manifest={manifest_version:1,name:pet.agentName,languages:['en','fi'],model:{provider:b.provider,id:b.model,region_preference:[b.region]},tools:[],privacy:{policy_url:b.privacyPolicyUrl,trains_on_user_data:false,retention_days:b.retentionDays},job:{en:pet.tagline},intro:{en:pet.tagline},category:'research',persona:{system_prompt:prompt,temperament:{chatty:45,bold:25,playful:30}},playpen:{fixture_set:pet.id+'@'+pet.version,scenarios:pet.starterPrompts.map(prompt=>({prompt,expect_tools:[]}))}};
  const text=canonicalJson(manifest);
  const candidate={schemaVersion:1,status:'prepared-not-submitted',petId:pet.id,packageSha256:packageDigest(pack),artifactSha256:sha256(text),makerRequest:{slug:pet.slug,taxonomy:{product_type:'pet',use_tags:['junction-2026',pet.company.slug]},artifact_manifest_json:text},sidecar:{sources:pet.sources,company:pet.company,capabilities:pet.capabilities,availability:pet.availability}};
  return {...candidate,requestSha256:candidateDigest(candidate)};
}

export function candidateDigest(candidate) {
  return sha256(canonicalJson({petId:candidate.petId,packageSha256:candidate.packageSha256,artifactSha256:candidate.artifactSha256,makerRequest:candidate.makerRequest}));
}

/** Hashes establish byte integrity only; authenticated Chibi still owns authority. */
export function verifyCandidate(input) {
  const candidate=structuredClone(input);
  const company=candidate?.petId?.match(/^junction\.([a-z0-9]+(?:-[a-z0-9]+)*)$/)?.[1];
  const request=candidate?.makerRequest;
  if(!company||candidate.schemaVersion!==1||candidate.status!=='prepared-not-submitted'||!request||request.slug!=='junction-'+company||
    canonicalJson(request.taxonomy)!==canonicalJson({product_type:'pet',use_tags:['junction-2026',company]})||
    !/^[0-9a-f]{64}$/.test(candidate.packageSha256)||typeof request.artifact_manifest_json!=='string'||
    sha256(request.artifact_manifest_json)!==candidate.artifactSha256||candidateDigest(candidate)!==candidate.requestSha256||
    Object.keys(request).sort().join(',')!=='artifact_manifest_json,slug,taxonomy')throw new TypeError('Invalid immutable company candidate');
  return candidate;
}

/** One caller-directed create only. Unknown writes are never automatically retried. */
export async function createMakerDraft(input,{request}) {
  const candidate=verifyCandidate(input);
  let response;
  try {response=await request('/v1/maker/products',{method:'POST',body:candidate.makerRequest});}
  catch(error){return {state:'unknown',petId:candidate.petId,artifactSha256:candidate.artifactSha256,errorCode:Number.isInteger(error?.status)?error.status:null,retryAutomatically:false};}
  return {state:'draft-response-received',petId:candidate.petId,artifactSha256:candidate.artifactSha256,response,published:false};
}
