import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewWorkflow} from '../pets/tieto/workflow-review.mjs';

const raw=readFileSync(new URL('../pets/tieto/examples/workflow.json',import.meta.url),'utf8');
const fixture=()=>JSON.parse(raw);
const check=value=>reviewWorkflow(JSON.stringify(value));
const has=(result,code)=>result.issues.some(issue=>issue.code===code);

test('Tieto: declared workflow yields an explicit RACI map, never execution or permission',()=>{
  const result=reviewWorkflow(raw);
  assert.equal(result.status,'declared-consistent');
  assert.deepEqual(result.issues,[]);
  assert.equal(result.responsibilityMap.length,2);
  assert.deepEqual(result.responsibilityMap[0],{
    stepId:'fictional-intake-step',system:'fictional-intake',
    responsible:['fictional-operator'],accountable:'fictional-owner',
    consulted:[],informed:['fictional-reviewer'],failureOwner:'fictional-owner',
  });
  assert.deepEqual(result.boundary,{fictionalOnly:true,executionAuthorized:false,transferAuthorized:false,executed:false});
});

test('Tieto: a cross-system handoff cannot hide its missing transfer declaration',()=>{
  const value=fixture(); value.steps[0].handoffs[0].transferId=null; value.transfers=[];
  const result=check(value);
  assert.equal(result.status,'blocked'); assert.ok(has(result,'undeclared-cross-system-transfer'));
  value.steps[1].system=value.steps[0].system;
  assert.equal(check(value).status,'declared-consistent');
});

test('Tieto: denied and unknown approval remain distinct and never confer authority',()=>{
  for(const [approval,status,code] of [['denied','blocked','transfer-denied'],['unknown','needs-clarification','transfer-approval-unknown']]){
    const value=fixture(); value.transfers[0].approval=approval;
    const result=check(value);
    assert.equal(result.status,status); assert.ok(has(result,code));
    assert.equal(result.boundary.transferAuthorized,false);
  }
  const value=fixture(); value.transfers[0].approver=null;
  assert.ok(has(check(value),'transfer-approver-unknown'));
});

test('Tieto: missing owners, unknown actors and an empty responsibility role stay visible',()=>{
  const value=fixture(); value.steps[0].accountable=null; value.steps[0].failureOwner=null;
  assert.equal(check(value).status,'needs-clarification');
  assert.ok(has(check(value),'accountable-unknown')); assert.ok(has(check(value),'failure-owner-unknown'));
  value.steps[0].responsible=[];
  assert.equal(check(value).status,'blocked'); assert.ok(has(check(value),'responsible-missing'));
  value.steps[0].responsible=['fictional-stranger']; value.transfers[0].approver='fictional-stranger';
  assert.ok(has(check(value),'unregistered-actor')); assert.ok(has(check(value),'unregistered-approver'));
});

test('Tieto: zero retries is known; null and omitted retry fields are not silently defaulted',()=>{
  const value=fixture(); value.steps[0].retry={maxRetries:0,timeoutSeconds:1,idempotent:null};
  assert.equal(check(value).status,'declared-consistent');
  value.steps[0].retry.maxRetries=null;
  assert.equal(check(value).status,'needs-clarification'); assert.ok(has(check(value),'retry-limit-unknown'));
  value.steps[0].retry.timeoutSeconds=null;
  assert.ok(has(check(value),'timeout-unknown'));
  delete value.steps[0].retry.maxRetries;
  assert.throws(()=>check(value),TypeError);
  delete value.steps[0].retry;
  assert.throws(()=>check(value),TypeError);
});

test('Tieto: repeated non-idempotent work is blocked; unknown idempotency is unresolved',()=>{
  const value=fixture(); value.steps[0].retry.idempotent=false;
  assert.equal(check(value).status,'blocked'); assert.ok(has(check(value),'retry-not-idempotent'));
  value.steps[0].retry.idempotent=null;
  assert.equal(check(value).status,'needs-clarification'); assert.ok(has(check(value),'retry-idempotency-unknown'));
  value.steps[0].retry={maxRetries:3,timeoutSeconds:3600,idempotent:true};
  assert.equal(check(value).status,'declared-consistent');
  for(const retry of [{maxRetries:4,timeoutSeconds:10,idempotent:true},{maxRetries:-1,timeoutSeconds:10,idempotent:true},{maxRetries:1,timeoutSeconds:0,idempotent:true},{maxRetries:1,timeoutSeconds:3601,idempotent:true}]){
    value.steps[0].retry=retry; assert.throws(()=>check(value),TypeError);
  }
});

test('Tieto: transfer identity must bind both ends and every declaration must be used',()=>{
  const value=fixture(); value.transfers[0].fromStep='fictional-review-step';
  assert.equal(check(value).status,'blocked'); assert.ok(has(check(value),'transfer-binding-mismatch'));
  value.transfers[0].fromStep='fictional-intake-step'; value.steps[0].handoffs=[];
  assert.ok(has(check(value),'unused-transfer'));
  value.steps[0].handoffs=[{toStep:'fictional-review-step',transferId:'fictional-absent'}];
  assert.ok(has(check(value),'transfer-not-declared'));
});

test('Tieto: unknown systems, absent steps and self-handoffs cannot pass the map',()=>{
  const value=fixture(); value.steps[0].system='fictional-absent';
  assert.ok(has(check(value),'unregistered-system'));
  value.steps[0].handoffs[0].toStep='fictional-absent';
  assert.ok(has(check(value),'step-not-declared'));
  value.steps[0].handoffs[0].toStep=value.steps[0].id;
  assert.ok(has(check(value),'self-handoff'));
});

test('Tieto: closed schemas reject undeclared effects and non-fictional or object input',()=>{
  for(const mutate of [v=>{v.sendTo='https://example.invalid';},v=>{v.steps[0].execute=true;},v=>{v.transfers[0].credential='invented';},v=>{v.fictional=false;},v=>{v.schemaVersion=2;},v=>{v.steps[0].accountable=['fictional-owner'];}]){
    const value=fixture(); mutate(value); assert.throws(()=>check(value),TypeError);
  }
  assert.throws(()=>reviewWorkflow(fixture()),TypeError);
  assert.throws(()=>reviewWorkflow('{bad json'),TypeError);
  assert.throws(()=>reviewWorkflow(raw.slice(0,-2)+',"__proto__":{}}'),TypeError);
});

test('Tieto: identifiers, unique references, array bounds and numeric types fail closed',()=>{
  for(const mutate of [v=>{v.workflowId='actual-customer';},v=>{v.actors.push(v.actors[0]);},v=>{v.steps.push(v.steps[0]);},v=>{v.steps[0].handoffs.push(v.steps[0].handoffs[0]);},v=>{v.transfers.push(v.transfers[0]);},v=>{v.transfers[0].dataCategories=[];},v=>{v.steps[0].retry.maxRetries='0';},v=>{v.steps[0].retry.idempotent='true';},v=>{v.actors=Array.from({length:17},(_,i)=>`fictional-actor-${i}`);}]){
    const value=fixture(); mutate(value); assert.throws(()=>check(value),TypeError);
  }
  assert.throws(()=>reviewWorkflow(' '.repeat(65537)),TypeError);
});

test('Tieto: blocked findings dominate without erasing unknowns; output is deterministic and isolated',()=>{
  const value=fixture(); value.steps[0].failureOwner=null; value.transfers[0].approval='denied';
  const snapshot=JSON.stringify(value), result=check(value);
  assert.equal(result.status,'blocked'); assert.ok(has(result,'failure-owner-unknown')); assert.ok(has(result,'transfer-denied'));
  assert.equal(JSON.stringify(value),snapshot); assert.deepEqual(result,check(value));
  result.responsibilityMap[0].responsible.push('fictional-output-edit');
  assert.deepEqual(check(value).responsibilityMap[0].responsible,['fictional-operator']);
});

test('Tieto: original six model eval definitions remain authored, not helper execution proof',()=>{
  const evals=JSON.parse(readFileSync(new URL('../pets/tieto/evals.json',import.meta.url),'utf8'));
  assert.equal(evals.petId,'junction.tieto'); assert.equal(evals.cases.length,6);
  assert.deepEqual(evals.cases.map(item=>item.id),['useful-domain-answer','no-provider-connection','company-source-isolation','unverified-event-brief','untrusted-source-instructions','domain-boundary']);
  assert.equal(reviewWorkflow(raw).boundary.executed,false);
});
