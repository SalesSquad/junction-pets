import test from 'node:test';
import assert from 'node:assert/strict';
import {createSession,apply,receipt,replayReceipt,FIXTURE_IDS,loadFixture,canonical} from '../core.mjs';
const step=(s,type,at=100,id=`step-${s.commands.length+1}`)=>apply(s,{id,type,at});
test('labelled deterministic fixtures are isolated copies',()=>{
  assert.ok(FIXTURE_IDS.length>=3);const f=loadFixture('clear-01');f.score=1;
  assert.equal(loadFixture('clear-01').score,.12);assert.throws(()=>loadFixture('camera-live'));
});
for(const [id,bowl] of [['clear-01','good'],['scratch-02','defect']])test(`${id} requires gate then manual placement`,()=>{
  let s=createSession(id);assert.throws(()=>step(s,'route'));s=step(s,'gate');assert.equal(s.state.bowl,null);assert.equal(s.state.candidate,bowl);
  s=step(s,'route',200);assert.equal(s.state.bowl,bowl);assert.throws(()=>step(s,'gate',300));
});
for(const id of ['ambiguous-03','threshold-touch-06'])test(`${id} never passes uncertainty or equality`,()=>{
  let s=step(createSession(id),'gate');assert.equal(s.state.phase,'uncertain');assert.equal(s.state.candidate,null);assert.throws(()=>step(s,'route'));
  s=step(s,'reinspect',200);assert.equal(s.state.phase,'review');assert.equal(s.fixture.confidence,loadFixture(id).confidence);assert.throws(()=>step(s,'reinspect',250));
  s=step(s,'review',300);assert.equal(s.state.candidate,'hold');s=step(s,'route',400);assert.equal(s.state.bowl,'hold');
});
for(const [id,reason] of [['low-confidence-04','Low confidence'],['missing-camera-05','Missing camera evidence']])test(`${reason} stops before gate`,()=>{
  const s=step(createSession(id),'gate');assert.equal(s.state.phase,'stopped');assert.equal(s.state.reason,reason);assert.equal(s.state.bowl,null);assert.throws(()=>step(s,'review',200));
});
test('freshness rechecked at placement, including boundary and idle tick',()=>{
  let s=step(createSession('clear-01'),'gate',30000);assert.equal(s.state.phase,'gated');s=step(s,'route',30001);assert.equal(s.state.reason,'Stale capture');assert.equal(s.state.bowl,null);
  assert.equal(step(createSession('clear-01'),'tick',30001).state.phase,'stopped');
});
test('manual stop is terminal even after safe gate',()=>{
  let s=step(createSession('clear-01'),'gate');s=step(s,'stop',200);assert.equal(s.state.candidate,null);assert.equal(s.state.bowl,null);assert.throws(()=>step(s,'route',300));
});
test('idempotency returns same state and conflicting IDs are rejected',()=>{
  const a={id:'one',type:'gate',at:100};const s=apply(createSession('clear-01'),a);assert.deepEqual(apply(s,a),s);assert.equal(s.commands.length,1);assert.throws(()=>apply(s,{...a,type:'route'}));
});
test('invalid command, backward time and forged state/policy fail closed',()=>{
  const s=step(createSession('clear-01'),'gate');assert.throws(()=>step(s,'route',99));
  for(const at of [NaN,Infinity,-1,.1])assert.throws(()=>step(s,'route',at));
  assert.throws(()=>apply(s,{id:123,type:'route',at:200}));assert.throws(()=>apply(s,{id:'two',type:'route',at:200,extra:true}));
  const fake=structuredClone(s);fake.state.candidate='hold';assert.throws(()=>step(fake,'route',200));
  const policy=structuredClone(s);policy.policy.maxAgeMs=999999;assert.throws(()=>step(policy,'route',200));
});
test('receipt is deterministic, SHA-256 chained, replayable and non-actuating',async()=>{
  let s=step(createSession('scratch-02'),'gate');s=step(s,'route',200);const r=await receipt(s);
  assert.equal(r.evidence,'SYNTHETIC');assert.equal(r.actuation,false);assert.equal(r.inference,false);assert.match(r.inputDigest,/^[a-f0-9]{64}$/);assert.equal(r.steps[0].previous,r.inputDigest);assert.equal(r.root,r.steps[1].hash);
  assert.deepEqual(await replayReceipt(r),s);assert.equal(canonical(await receipt(s)),canonical(r));
});
test('all fixture outcomes replay, including stops and zero steps',async()=>{
  for(const id of FIXTURE_IDS){const empty=createSession(id);assert.deepEqual(await replayReceipt(await receipt(empty)),empty);const s=step(empty,'gate');assert.deepEqual(await replayReceipt(await receipt(s)),s);}
});
test('receipt detects altered digest, final, step, provenance, extra fields and order',async()=>{
  let s=step(createSession('clear-01'),'gate');s=step(s,'route',200);const r=await receipt(s);
  const mutations=[x=>x.inputDigest='bad',x=>x.final.bowl='defect',x=>x.steps[0].state.candidate='defect',x=>x.steps[0].producer='OpenVINO',x=>x.steps.reverse(),x=>x.extra=true,x=>x.fixtureId='scratch-02',x=>x.steps[1].command.at=30001];
  for(const mutate of mutations){const changed=structuredClone(r);mutate(changed);await assert.rejects(()=>replayReceipt(changed));}
  s.state.bowl='hold';await assert.rejects(()=>receipt(s));
});
test('checked-in CLI receipts reproduce good, defect and hold outcomes',async()=>{
  const {readFile}=await import('node:fs/promises');
  const examples=JSON.parse(await readFile(new URL('./demo-receipts.json',import.meta.url),'utf8'));
  assert.deepEqual(examples.map(x=>x.final.bowl),['good','defect','hold']);
  for(const example of examples)assert.deepEqual(await receipt(await replayReceipt(example)),example);
});
