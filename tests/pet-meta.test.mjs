import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateWearableHistory } from '../pets/meta/wearable-permission.mjs';

const scope = 'synthetic-reminder-preview';
const snapshot = (at=0, permission='granted', bystanders='clear') => ({decision:'snapshot',at,scope,available:true,permission,bystanders});
const consent = (at=1,id='consent-1',expiresAt=100) => ({decision:'consent',at,scope,id,expiresAt});
const evaluate = (events,now=10) => evaluateWearableHistory({scope,now,events});
const blocked = result => {
  assert.equal(result.simulationAllowed,false);
  assert.equal(result.realActionAuthorized,false);
  assert.equal(result.fallback.cameraRequired,false);
  assert.equal(result.fallback.mode,'text');
};

test('initial state is unavailable/unknown; explicit scoped consent permits only synthetic preview',()=>{
  const initial=evaluate([]); blocked(initial);
  assert.equal(initial.state,'unavailable');
  assert.equal(initial.permission,'unknown');
  blocked(evaluate([snapshot()]));
  const result=evaluate([snapshot(),consent()]);
  assert.equal(result.simulationAllowed,true);
  assert.equal(result.realActionAuthorized,false);
  assert.equal(result.state,'consented');
});

for(const decision of ['cancel','revoke']) test(`${decision} survives a fresh granted snapshot`,()=>{
  const events=[snapshot(),consent(),{decision,at:2,scope},snapshot(3,'granted')];
  const result=evaluate(events); blocked(result);
  assert.equal(result.state,decision==='cancel'?'canceled':'revoked');
  blocked(evaluate([...events,consent(4)]));
  assert.equal(evaluate([...events,consent(4,'fresh')]).simulationAllowed,true);
});

test('expiry is exclusive and snapshots cannot renew it',()=>{
  assert.equal(evaluate([snapshot(),consent()],99).simulationAllowed,true);
  blocked(evaluate([snapshot(),consent()],100));
  blocked(evaluate([snapshot(),consent(),snapshot(100,'granted')],101));
});

test('explicit consent cannot override unknown/denied platform permission or revocation',()=>{
  for (const permission of ['unknown','denied']) {
    blocked(evaluate([snapshot(0,permission),consent()]));
    blocked(evaluate([snapshot(),consent(),snapshot(2,permission),consent(3,'fresh')]));
  }
  const revoked=evaluate([snapshot(),consent(),{decision:'revoke',scope,at:2},snapshot(3,'granted')]);
  blocked(revoked);
  assert.equal(revoked.state,'revoked');
  const granted=evaluate([snapshot(),consent()]);
  assert.equal(granted.simulationAllowed,true);
  assert.equal(granted.realActionAuthorized,false);
});

test('bystander uncertainty, denied/unknown permission and unavailable device clear consent',()=>{
  for(const bystanders of ['unknown','present']) {
    blocked(evaluate([snapshot(0,'unknown',bystanders),consent()]));
    blocked(evaluate([snapshot(),consent(),snapshot(2,'granted',bystanders)]));
  }
  for(const permission of ['unknown','denied']) blocked(evaluate([snapshot(),consent(),snapshot(2,permission)]));
  blocked(evaluate([snapshot(),consent(),{...snapshot(2),available:false}]));
});

test('malformed/unknown fields, decisions and scope fail closed',()=>{
  for(const value of [null,{},0,[],{scope,now:10,events:null},{scope:'camera',now:10,events:[]},
    {scope,now:10,events:[{decision:'authorize-real-camera',at:1,scope}]},
    {scope,now:10,events:[{...snapshot(),tool:'camera'}]},
    {scope,now:10,events:[{...consent(),scope:'other'}]},
    {scope,now:10,events:[{...snapshot(),permission:null}]}]) blocked(evaluateWearableHistory(value));
});

test('timestamps distinguish zero from missing/null and reject malformed, stale, future or reversed history',()=>{
  assert.equal(evaluate([snapshot(0),consent(0)],0).simulationAllowed,true);
  for(const at of [undefined,null,-1,NaN,Infinity,0.5,'2026-11-13',Number.MAX_SAFE_INTEGER+1]) {
    blocked(evaluate([{...snapshot(),at},consent()]));
  }
  blocked(evaluate([snapshot(),consent()],60001));
  blocked(evaluate([snapshot(11)]));
  blocked(evaluate([snapshot(2),consent(1)]));
  for(const expiresAt of [undefined,null,0,1,'100',Infinity]) blocked(evaluate([snapshot(),{...consent(1,'x'),expiresAt}]));
});

test('replayed consent, unavailable consent and snapshots alone cannot grant authority',()=>{
  blocked(evaluate([snapshot(0,'granted')]));
  blocked(evaluate([consent()]));
  blocked(evaluate([snapshot(),consent(),consent(2)]));
  blocked(evaluate([snapshot(),consent(),{decision:'revoke',scope,at:2},consent(3)]));
});

test('deterministic immutable input/output and accessible fallback in every state',()=>{
  const input={scope,now:10,events:[snapshot(),consent()]};
  const before=structuredClone(input);
  const result=evaluateWearableHistory(input);
  assert.deepEqual(input,before);
  assert.deepEqual(result,evaluateWearableHistory(input));
  result.fallback.text='mutated';
  assert.notEqual(evaluateWearableHistory(input).fallback.text,'mutated');
  assert.match(result.fallback.controls.join(' '),/Cancel/);
});
