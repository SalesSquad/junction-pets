import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import QRCode from 'qrcode';
import {PNG} from 'pngjs';
import jsQR from 'jsqr';
import Ajv2020 from 'ajv/dist/2020.js';
import {loadPackages,validatePet,validateCollection,EXPECTED_COMPANIES,packageDigest,collectionDigest} from '../lib/catalog.mjs';
import {canonicalJson,sha256} from '../lib/artifact.mjs';
import {companyContext} from '../lib/company-context.mjs';
import {makerCandidate,verifyCandidate,createMakerDraft} from '../lib/export.mjs';
import {canonicalOrigin,publicPetUrl,signInUrl,recipientAvailable} from '../lib/links.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const packs=await loadPackages(root),pets=packs.map(p=>p.pet);
const host=JSON.parse(await readFile(new URL('../config/host-config.json',import.meta.url),'utf8'));
const syntheticBindings={provider:'synthetic-only',model:'fixture-model',allowedModelProviders:['synthetic-only'],privacyPolicyUrl:'https://example.invalid/privacy',region:'eu',retentionDays:0};
const hostSchema=JSON.parse(await readFile(new URL('../schemas/chibi-manifest.upstream.schema.json',import.meta.url),'utf8'));
const hostValidate=new Ajv2020({allErrors:true,strict:true,formats:{uri:value=>{try{new URL(value);return true;}catch{return false;}}}}).compile(hostSchema);

test('exact evidenced roster has34 distinct packages and all204 authored evaluation cases',()=>{
  assert.equal(packs.length,34);
  assert.deepEqual(new Set(pets.map(p=>p.company.slug)),new Set(EXPECTED_COMPANIES));
  assert.deepEqual(pets.map(p=>p.artIndex),Array.from({length:34},(_,i)=>i));
  assert.equal(packs.reduce((n,p)=>n+p.evals.cases.length,0),204);
  for(const pack of packs){assert.match(pack.instructions,/Chibi/);assert.ok(pack.story.includes('Suomeksi'));assert.equal(pack.pet.availability.runtime,'chibi-host-required');}
});

test('wrong company identity, duplicate art and undeclared connection are rejected',()=>{
  const wrong=structuredClone(pets[0]);wrong.slug=pets[1].slug;assert.throws(()=>validatePet(wrong),/identity/);
  const duplicate=structuredClone(pets);duplicate[1].artIndex=duplicate[0].artIndex;assert.throws(()=>validateCollection(duplicate),/Duplicate artIndex/);
  const connection=structuredClone(pets[0]);connection.capabilities[0].kind='connection-required';connection.capabilities[0].requiresConnection=false;assert.throws(()=>validatePet(connection),/connection/i);
  const injection=structuredClone(pets[0]);injection.sources[0].url='https://company.example@evil.invalid/';assert.throws(()=>validatePet(injection),/source/);
});

test('immutable content hashes include instructions, story, evals and exact source notes',()=>{
  assert.equal(collectionDigest(packs),collectionDigest(structuredClone(packs)));
  for(const field of ['instructions','story']){const changed=structuredClone(packs[0]);changed[field]+='Changed.';assert.notEqual(packageDigest(changed),packageDigest(packs[0]));}
  const changed=structuredClone(packs[0]);changed.pet.sources[0].summary+=' Changed evidence.';assert.notEqual(packageDigest(changed),packageDigest(packs[0]));
  assert.equal(canonicalJson({b:1,a:2}),canonicalJson({a:2,b:1}));
});

test('each release context receives only its selected company evidence',()=>{
  const a=structuredClone(packs[0]),b=structuredClone(packs[1]);
  a.pet.sources[0].summary='Unique scoped source note alpha-fixture.';
  b.pet.sources[0].summary='Unique scoped source note beta-fixture.';
  assert.match(companyContext(a),/alpha-fixture/);assert.doesNotMatch(companyContext(a),/beta-fixture/);
  assert.match(companyContext(b),/beta-fixture/);assert.doesNotMatch(companyContext(b),/alpha-fixture/);
  for(const pack of packs)assert.ok([...companyContext(pack)].length<=20000);
});

test('public QR links contain no grant, preserve exact company and use same-origin sign-in returns',()=>{
  for(const pet of pets){const url=new URL(publicPetUrl(host.canonicalOrigin,pet.slug));assert.equal(url.pathname,'/en/chibi/'+pet.slug);assert.equal(url.search,'');assert.equal(url.hash,'');const login=new URL(signInUrl(host.canonicalOrigin,pet.slug));assert.equal(login.origin,url.origin);assert.equal(login.searchParams.get('next'),url.pathname);}
  for(const origin of ['http://example.com','https://user:pass@example.com','https://example.com/path','https://example.com?next=https://evil.invalid','https://example.com#token',' https://example.com','https://example.com\\evil'])assert.throws(()=>canonicalOrigin(origin));
  for(const slug of ['../admin','//evil.invalid','junction-foo?token=bar','not-junction'])assert.throws(()=>publicPetUrl(host.canonicalOrigin,slug));
});

test('actual PNG QR encode/decode roundtrip preserves all34 exact destinations',async()=>{
  for(const pet of pets){const url=publicPetUrl(host.canonicalOrigin,pet.slug),png=PNG.sync.read(await QRCode.toBuffer(url,{width:360,margin:4,errorCorrectionLevel:'M'}));const decoded=jsQR(new Uint8ClampedArray(png.data),png.width,png.height);assert.equal(decoded?.data,url,pet.id);}
});

test('unverified or malformed publication evidence cannot enable a recipient handoff',()=>{
  assert.equal(recipientAvailable(host,pets[0].slug),false);
  const config={...host,runtimeStatus:'verified',publishedSlugs:[pets[0].slug],verifiedAt:'2026-11-10T12:00:00Z'};
  const now=Date.parse('2026-11-11T12:00:00Z');assert.equal(recipientAvailable(config,pets[0].slug,now),true);assert.equal(recipientAvailable(config,pets[1].slug,now),false);
  for(const verifiedAt of [null,1,'garbage','2999-01-01T00:00:00Z'])assert.equal(recipientAvailable({...config,verifiedAt},pets[0].slug,now),false);
});

test('all34 Maker candidates obey structural manifest limits and grant no company tools',()=>{
  for(const pack of packs){const c=makerCandidate(pack,syntheticBindings),manifest=JSON.parse(c.makerRequest.artifact_manifest_json);assert.ok(hostValidate(manifest),JSON.stringify(hostValidate.errors));assert.equal(c.artifactSha256,sha256(c.makerRequest.artifact_manifest_json));assert.equal(verifyCandidate(c).petId,pack.pet.id);assert.equal(manifest.manifest_version,1);assert.ok([...manifest.name].length<=12);assert.deepEqual(manifest.tools,[]);assert.ok([...manifest.persona.system_prompt].length<=20000);assert.equal(c.status,'prepared-not-submitted');}
  assert.throws(()=>makerCandidate(packs[0],{}),/bindings/);
  assert.throws(()=>makerCandidate(packs[0],{...syntheticBindings,provider:'not-allowed'}),/bindings/);
});

test('tampered full candidate identity, taxonomy, manifest and package digest cause no POST',async()=>{
  for(const mutate of [c=>c.makerRequest.slug='junction-other',c=>c.makerRequest.taxonomy.product_type='agent',c=>c.makerRequest.taxonomy.use_tags.push('other'),c=>c.petId='junction.other',c=>c.packageSha256='0'.repeat(64),c=>c.makerRequest.artifact_manifest_json+=' ',c=>c.makerRequest.extra=true]){
    const c=makerCandidate(packs[0],syntheticBindings);mutate(c);let calls=0;
    await assert.rejects(createMakerDraft(c,{request:async()=>{calls++;}}));assert.equal(calls,0);
  }
});

test('create snapshots verified bytes, sends once and never calls submission or publication',async()=>{
  const candidate=makerCandidate(packs[0],syntheticBindings),expected=canonicalJson(candidate.makerRequest);let calls=0;
  const result=await createMakerDraft(candidate,{request:async(path,options)=>{calls++;candidate.makerRequest.slug='junction-tampered';assert.equal(path,'/v1/maker/products');assert.equal(options.method,'POST');assert.equal(canonicalJson(options.body),expected);return {synthetic:true};}});
  assert.equal(calls,1);assert.equal(result.published,false);
});

test('unknown create effects return reconciliation state without a retry',async()=>{
  let calls=0;const result=await createMakerDraft(makerCandidate(packs[0],syntheticBindings),{request:async()=>{calls++;throw new Error('Synthetic lost response after possible commit');}});
  assert.equal(calls,1);assert.equal(result.state,'unknown');assert.equal(result.retryAutomatically,false);
});
