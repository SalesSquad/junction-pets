import {canonicalJson,sha256} from './artifact.mjs';

/**
 * Chibi-independent, SYNTHETIC-ONLY collaboration contract.
 * A Chibi host must replace its grant checks with authenticated Cedar decisions
 * before any external tool, model, user data or provider connection is involved.
 */
export const COLLABORATION_PROTOCOL = 'junction.pet-collaboration/v1';
export const DEMO_TENANT = 'synthetic-junction-demo';
export const DEMO_CLOCK = '2026-11-12T18:00:00.000Z';
const MAX_MESSAGES = 12;
const MAX_DEPTH = 4;

function invariant(condition,message) {
  if (!condition) throw new Error(message);
}
function safeId(value) {return typeof value==='string' && /^[a-z0-9][a-z0-9._:-]{1,100}$/.test(value);}
function exactKeys(value,allowed,label) {
  invariant(value && typeof value==='object' && !Array.isArray(value),`Invalid ${label}`);
  for (const key of Object.keys(value)) invariant(allowed.includes(key),`Unexpected ${label} field: ${key}`);
}
function packageMap(packages) {
  const map=new Map();
  for (const candidate of packages) {
    const pet=candidate.pet??candidate;
    invariant(safeId(pet.id), 'Invalid pet identity');
    invariant(!map.has(pet.id),'Duplicate pet identity');
    invariant(Array.isArray(pet.capabilities),'Missing pet capability catalog');
    map.set(pet.id,pet);
  }
  return map;
}

/** A grant is a NON-AUTHORITATIVE synthetic fixture, never a Chibi entitlement. */
export function syntheticGrant({id,from,to,capabilityId,tenantId=DEMO_TENANT}) {
  invariant([id,from,to,capabilityId,tenantId].every(safeId),'Invalid synthetic grant input');
  return Object.freeze({
    kind:'synthetic-fixture',
    id:`grant.${id}`,
    requestId:id,
    tenantId,
    actor:from,
    recipient:to,
    allowedCapability:capabilityId,
    allowedDataClass:'synthetic',
    allowsExternalEffects:false,
    expiresAt:'2026-11-13T18:00:00.000Z',
  });
}

/**
 * Pure in-memory trace engine. Requests cannot execute tools or reach networks.
 * All outputs are deterministic demonstration copy, NOT a language model's answer.
 */
export function createSyntheticCouncil(packages,{clock=DEMO_CLOCK,maxDepth=MAX_DEPTH}={}) {
  const pets=packageMap(packages);
  invariant(Number.isInteger(maxDepth)&&maxDepth>=1&&maxDepth<=MAX_DEPTH,'Invalid max depth');
  const messages=[];
  const byId=new Map();
  const seenGrants=new Set();

  function delegate(request,grant) {
    invariant(messages.length<MAX_MESSAGES,'Message budget exceeded');
    exactKeys(request,['id','from','to','capabilityId','tenantId','context','parents','mode'], 'request');
    invariant(request.mode==='synthetic','This engine cannot perform live agent or model execution');
    invariant(safeId(request.id)&&!byId.has(request.id),'Invalid or replayed request ID');
    invariant(safeId(request.from)&&safeId(request.to)&&request.from!==request.to,'Invalid delegation endpoints');
    invariant(pets.has(request.from)&&pets.has(request.to),'Unknown pet endpoint');
    invariant(safeId(request.capabilityId),'Invalid capability ID');
    const pet=pets.get(request.to);
    const capability=pet.capabilities.find(c=>c.id===request.capabilityId);
    invariant(capability,'Undeclared recipient capability');
    invariant(!capability.requiresConnection && capability.kind!=='connection-required','Provider connection is not available');

    exactKeys(request.context,['dataClass','fixtureId','summary','evidence'], 'context');
    invariant(request.context.dataClass==='synthetic','Only synthetic context may cross pet boundaries in this demo');
    invariant(safeId(request.context.fixtureId),'Invalid fixture identity');
    invariant(typeof request.context.summary==='string'&&request.context.summary.length>0&&request.context.summary.length<=1800,'Invalid bounded context');
    invariant(!/(?:sk-[a-z0-9]{12,}|bearer\s+[a-z0-9._-]{12,}|password\s*[:=]|api[_-]?key\s*[:=])/i.test(request.context.summary),'Credential-looking context rejected');
    exactKeys(request.context.evidence,['kind','reference'], 'evidence');
    invariant(request.context.evidence.kind==='synthetic-fixture' && safeId(request.context.evidence.reference),'Real or unscoped evidence cannot enter synthetic demo');

    exactKeys(grant,['kind','id','requestId','tenantId','actor','recipient','allowedCapability','allowedDataClass','allowsExternalEffects','expiresAt'], 'grant');
    invariant(grant.kind==='synthetic-fixture','Host authorization is not modeled here');
    invariant(safeId(grant.id)&&!seenGrants.has(grant.id),'Missing or replayed task grant');
    invariant(grant.requestId===request.id&&grant.actor===request.from&&grant.recipient===request.to&&grant.allowedCapability===request.capabilityId,'Task-scoped grant mismatch');
    invariant(request.tenantId===DEMO_TENANT&&grant.tenantId===DEMO_TENANT,'Cross-tenant delegation denied');
    invariant(grant.allowedDataClass==='synthetic'&&grant.allowsExternalEffects===false,'Grant cannot widen data or tool rights');
    invariant(Number.isFinite(Date.parse(clock)) && Number.isFinite(Date.parse(grant.expiresAt)) && Date.parse(grant.expiresAt)>Date.parse(clock),'Expired or invalid grant');

    invariant(Array.isArray(request.parents)&&request.parents.length<=5,'Invalid dependencies');
    invariant(new Set(request.parents).size===request.parents.length,'Duplicate dependencies');
    const ancestors=new Set();
    function addAncestors(id) {
      invariant(byId.has(id),'Missing or future dependency');
      if (ancestors.has(id)) return; // A valid DAG may join two branches from the same ancestor.
      ancestors.add(id);
      byId.get(id).request.parents.forEach(addAncestors);
    }
    request.parents.forEach(addAncestors);
    const depth=1+Math.max(0,...request.parents.map(id=>byId.get(id).depth));
    invariant(depth<=maxDepth,'Delegation depth exceeded');
    for (const dependency of ancestors) {
      const ancestor=byId.get(dependency).request;
      invariant(ancestor.to!==request.to && ancestor.from!==request.to,'Delegation cycle back to an ancestor');
    }

    const contextDigest=sha256(canonicalJson(request.context));
    const message={
      id:request.id,
      index:messages.length+1,
      kind:'synthetic-agent-message',
      protocol:COLLABORATION_PROTOCOL,
      request:{
        id:request.id,from:request.from,to:request.to,capabilityId:request.capabilityId,
        tenantId:request.tenantId,parents:[...request.parents],
        context:{fixtureId:request.context.fixtureId,dataClass:'synthetic',summary:request.context.summary,digest:contextDigest},
      },
      depth,
      policy:{result:'synthetic-contract-validated',grantId:grant.id,externalEffects:false,hostAuthorization:false},
      capability:{id:capability.id,title:capability.title,kind:capability.kind,description:capability.description},
      response:{kind:'synthetic-example',title:exampleTitle(pet.id,capability.id),bullets:exampleBullets(pet.id,capability.id)},
      provenance:{
        petManifestSha256:sha256(canonicalJson(pet)),
        sourceScope:'manifest-declared-only-not-fetched',
        referenceUrls:pet.sources.map(s=>s.url),
        fixtureId:request.context.fixtureId,
      },
    };
    messages.push(message);
    byId.set(message.id,message);
    seenGrants.add(grant.id);
    return structuredClone(message);
  }

  function snapshot() {
    const publicMessages=structuredClone(messages);
    const content={
      schemaVersion:1,protocol:COLLABORATION_PROTOCOL,
      executionMode:'synthetic-no-model-no-tools',
      generatedBy:'deterministic-local-simulator',
      source:{repository:'SalesSquad/junction-pets',verifiedCommit:null,reason:'portable fixture; compare deployed source to GitHub separately'},
      tenantId:DEMO_TENANT,
      demoDate:clock,
      participants:[...new Set(publicMessages.flatMap(m=>[m.request.from,m.request.to]))].map(id=>({
        id,displayName:pets.get(id).displayName,company:pets.get(id).company.name,accent:pets.get(id).accent,
        sourcePath:`pets/${pets.get(id).company.slug}/pet.json`,
      })),
      messages:publicMessages,
      reviewGate:{required:true,state:'pending-human-review',allowsExecution:false,
        acceptance:['Confirm scope and source citations','Review privacy and bystander consent','Attach verified host/model test receipts before calling this live']},
      limitations:['No real LLM invocation','No external provider connection','No Chibi authentication or private memory','No voice or device execution'],
    };
    return {...content,traceSha256:sha256(canonicalJson(content))};
  }
  return {delegate,snapshot};
}

const examples={
  'junction.mariadb#query-review': ['Ask for MariaDB version, cardinality and redacted EXPLAIN evidence before changing indexes.','Separate logical query review from benchmark claims; no query was run.'],
  'junction.nvidia#performance-plan': ['Draft a benchmark matrix: hardware, driver, input size, precision, warm-up, repetitions and memory.','Keep CUDA/Isaac capabilities and speedups unverified until a real run.'],
  'junction.meta#interaction-review': ['Offer explicit microphone/camera state, a pause action and a manual alternative.','Consider bystander privacy, consent and accessible error recovery before testing on a device.'],
  'junction.openai-codex#handoff-evidence': ['Bind each contributor to a versioned artifact and classify planned versus actually tested.','Require exact CI/model evidence and a human acceptance gate before claiming an integrated demo.'],
};
function exampleTitle(petId,capabilityId) {
  const title={
    'junction.mariadb#query-review':'Database evidence plan',
    'junction.nvidia#performance-plan':'Spatial workload benchmark plan',
    'junction.meta#interaction-review':'Voice and wearable consent review',
    'junction.openai-codex#handoff-evidence':'Source-bound integration handoff',
  };
  return title[`${petId}#${capabilityId}`]??'Synthetic guidance preview';
}
function exampleBullets(petId,capabilityId) {
  return examples[`${petId}#${capabilityId}`]??['This is a deterministic illustrative output, not a model response.','Collect real context and an authorized runtime receipt before presenting results as tested.'];
}

export function runDemo(packages) {
  const council=createSyntheticCouncil(packages);
  const steps=[
    {
      id:'step.mariadb',from:'junction.openai-codex',to:'junction.mariadb',capabilityId:'query-review',
      fixtureId:'fixture.redacted-sql',parents:[],
      summary:'Synthetic asset inventory SQL review. Query and EXPLAIN have not been executed; no customer tables or live credentials are present.',
    },
    {
      id:'step.nvidia',from:'junction.openai-codex',to:'junction.nvidia',capabilityId:'performance-plan',
      fixtureId:'fixture.spatial-workload',parents:[],
      summary:'Synthetic 3D scene and GPU benchmark planning; input is a fictitious set of equipment meshes with no real Valmet dataset.',
    },
    {
      id:'step.meta',from:'junction.openai-codex',to:'junction.meta',capabilityId:'interaction-review',
      fixtureId:'fixture.voice-storyboard',parents:['step.mariadb','step.nvidia'],
      summary:'Synthetic hands-free assistant storyboard: user asks about a fictional equipment item. Review bystander consent and fallback UX, not real hardware behavior.',
    },
  ];
  for (const step of steps) {
    const request={id:step.id,from:step.from,to:step.to,capabilityId:step.capabilityId,
      tenantId:DEMO_TENANT,mode:'synthetic',parents:step.parents,
      context:{dataClass:'synthetic',fixtureId:step.fixtureId,summary:step.summary,evidence:{kind:'synthetic-fixture',reference:step.fixtureId}},
    };
    council.delegate(request,syntheticGrant(request));
  }
  return council.snapshot();
}
