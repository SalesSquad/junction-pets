import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {loadPackages} from '../lib/catalog.mjs';
import {canonicalJson,sha256} from '../lib/artifact.mjs';
import {createSyntheticCouncil,runDemo,syntheticGrant,DEMO_TENANT,COLLABORATION_PROTOCOL} from '../lib/pet-collaboration.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const packages=await loadPackages(root);
function request(overrides={}) {
  return {
    id:'step.fixture',from:'junction.openai-codex',to:'junction.mariadb',
    capabilityId:'query-review',tenantId:DEMO_TENANT,mode:'synthetic',parents:[],
    context:{dataClass:'synthetic',fixtureId:'fixture.sample',summary:'Redacted and entirely invented example SQL.',evidence:{kind:'synthetic-fixture',reference:'fixture.sample'}},
    ...overrides,
  };
}
const pair=changes=>{const r=request(changes);return [r,syntheticGrant(r)];};

test('demo delegates three declared capabilities across four known companions',()=>{
  const trace=runDemo(packages);
  assert.equal(trace.protocol,COLLABORATION_PROTOCOL);
  assert.equal(trace.executionMode,'synthetic-no-model-no-tools');
  assert.equal(trace.messages.length,3);
  assert.equal(trace.participants.length,4);
  assert.deepEqual(trace.messages.map(m=>m.request.to),[
    'junction.mariadb','junction.nvidia','junction.meta',
  ]);
  assert.deepEqual(trace.messages[2].request.parents,['step.mariadb','step.nvidia']);
  for (const message of trace.messages) {
    const p=packages.find(p=>p.pet.id===message.request.to).pet;
    assert.ok(p.capabilities.find(c=>c.id===message.request.capabilityId));
    assert.equal(message.policy.externalEffects,false);
    assert.equal(message.policy.hostAuthorization,false);
    assert.equal(message.response.kind,'synthetic-example');
    assert.equal(message.provenance.petManifestSha256,sha256(canonicalJson(p)));
    assert.equal(message.provenance.sourceScope,'manifest-declared-only-not-fetched');
  }
  assert.equal(trace.reviewGate.state,'pending-human-review');
  assert.equal(trace.reviewGate.allowsExecution,false);
});

test('replay is deterministic and digest binds the complete trace',()=>{
  const a=runDemo(packages),b=runDemo(packages);
  assert.deepEqual(a,b);
  const {traceSha256,...content}=a;
  assert.equal(traceSha256,sha256(canonicalJson(content)));
});

test('live mode, unknown pet and undeclared capability fail closed',()=>{
  const council=createSyntheticCouncil(packages);
  let r,g;
  [r,g]=pair({mode:'live'});assert.throws(()=>council.delegate(r,g),/cannot perform live/);
  [r,g]=pair({to:'junction.no-such-company'});assert.throws(()=>council.delegate(r,g),/Unknown pet endpoint/);
  [r,g]=pair({capabilityId:'execute-payment'});assert.throws(()=>council.delegate(r,g),/Undeclared recipient capability/);
  assert.equal(council.snapshot().messages.length,0);
});

test('unknown user scope, cross tenant grant, private data and likely secret fail closed',()=>{
  const council=createSyntheticCouncil(packages);
  let r,g;
  [r,g]=pair({tenantId:'another-tenant'});assert.throws(()=>council.delegate(r,g),/Cross-tenant/);
  [r,g]=pair({context:{...request().context,dataClass:'private'}});assert.throws(()=>council.delegate(r,g),/Only synthetic context/);
  [r,g]=pair({context:{...request().context,summary:'Bearer abcdefghijklmnopqrstuvwxyz'}});assert.throws(()=>council.delegate(r,g),/Credential-looking/);
  [r,g]=pair();g={...g,tenantId:'other-user'};assert.throws(()=>council.delegate(r,g),/Cross-tenant/);
  [r,g]=pair();g={...g,allowsExternalEffects:true};assert.throws(()=>council.delegate(r,g),/cannot widen/);
  [r,g]=pair();g={...g,allowedCapability:'change-plan'};assert.throws(()=>council.delegate(r,g),/grant mismatch/);
  assert.equal(council.snapshot().messages.length,0);
});

test('connected-only capability is denied even if manifest declares it',()=>{
  const fake=structuredClone(packages);
  const mariadb=fake.find(p=>p.pet.id==='junction.mariadb').pet;
  mariadb.capabilities[0].requiresConnection=true;
  const council=createSyntheticCouncil(fake);
  const [r,g]=pair();assert.throws(()=>council.delegate(r,g),/Provider connection/);
});

test('replay protection, missing grant, expiry and future dependency deny',()=>{
  const council=createSyntheticCouncil(packages);
  let [r,g]=pair();
  assert.throws(()=>council.delegate(r,{...g,expiresAt:'2020-01-01T00:00:00Z'}),/Expired/);
  assert.throws(()=>council.delegate(r,{...g,kind:'cedar-approval'}),/Host authorization is not modeled/);
  assert.throws(()=>council.delegate({...r,parents:['not-yet-created']},g),/Missing or future dependency/);
  council.delegate(r,g);
  assert.throws(()=>council.delegate(r,g),/replayed request/);
  const another=request({id:'step.another',to:'junction.nvidia',capabilityId:'performance-plan'});
  assert.throws(()=>council.delegate(another,{...g,id:'grant.fresh-but-wrong-request'}),/grant mismatch/);
});

test('delegation graph cannot return to an ancestor recipient or exceed depth',()=>{
  const council=createSyntheticCouncil(packages,{maxDepth:2});
  let [r,g]=pair();council.delegate(r,g);
  [r,g]=pair({id:'step.two',from:'junction.mariadb',to:'junction.nvidia',capabilityId:'stack-map',parents:['step.fixture']});council.delegate(r,g);
  [r,g]=pair({id:'step.cycle',from:'junction.nvidia',to:'junction.mariadb',capabilityId:'query-review',parents:['step.two']});
  assert.throws(()=>council.delegate(r,g),/Delegation depth exceeded|cycle/);
  [r,g]=pair({id:'step.three',from:'junction.nvidia',to:'junction.meta',capabilityId:'interaction-review',parents:['step.two']});
  assert.throws(()=>council.delegate(r,g),/Delegation depth exceeded/);
});

test('dependency DAG can join shared ancestors but cannot loop back to the origin',()=>{
  const council=createSyntheticCouncil(packages);
  let [r,g]=pair();council.delegate(r,g);
  [r,g]=pair({id:'step.two',from:'junction.mariadb',to:'junction.nvidia',capabilityId:'performance-plan',parents:['step.fixture']});council.delegate(r,g);
  [r,g]=pair({id:'step.diamond',from:'junction.openai-codex',to:'junction.meta',capabilityId:'interaction-review',parents:['step.fixture','step.two']});
  const joined=council.delegate(r,g);
  assert.equal(joined.depth,3);
  [r,g]=pair({id:'step.cycle',from:'junction.nvidia',to:'junction.openai-codex',capabilityId:'handoff-evidence',parents:['step.two']});
  assert.throws(()=>council.delegate(r,g),/Delegation cycle back to an ancestor/);
});

test('arbitrary keys and effect requests are never silently accepted',()=>{
  const council=createSyntheticCouncil(packages);
  let [r,g]=pair();
  assert.throws(()=>council.delegate({...r,providerToken:'stolen'},g),/Unexpected request field/);
  assert.throws(()=>council.delegate({...r,context:{...r.context,customerMemory:'private'}},g),/Unexpected context field/);
  assert.throws(()=>council.delegate({...r,context:{...r.context,evidence:{kind:'external-tool',reference:'fixture.sample'}}},g),/Real or unscoped evidence/);
});
