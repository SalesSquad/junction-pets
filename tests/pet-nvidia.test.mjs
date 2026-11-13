import test from 'node:test';
import assert from 'node:assert/strict';
import { compare } from '../pets/nvidia/comparability.mjs';

const row = () => ({workload:'synthetic-room-v1', kind:'gaussian-splat', sceneCount:1,
  objectCount:1000, inputDigest:'a'.repeat(64), width:640, height:480, precision:'fp32',
  quality:'exact-reference-v1', hardware:'fictional-gpu-A', software:'fictional-renderer-v1',
  timingScope:'render-only-synchronized', warmup:0, repeats:3, unit:'ms',
  timings:[10,12,14], evidence:'authored-estimate', provenance:'worksheet author'});
test('synthetic ratio is useful but never measured performance', () => {
  const a=row(), b=row(); b.timings=[5,6,7];
  assert.deepEqual(compare(a,b), {comparable:true, ratio:2, basis:'authored-estimate', provenance:'unverified', measuredPerformanceVerified:false});
  assert.equal(compare(a,b).ratio,2); assert.equal(a.timings[0],10);
});
test('supplied measurements remain unverified; hardware may differ explicitly', () => {
  const a=row(), b=row(); a.evidence=b.evidence='supplied-measurement'; b.hardware='fictional-gpu-B';
  assert.equal(compare(a,b).basis,'supplied-measurement');
  assert.equal(compare(a,b).measuredPerformanceVerified,false);
});
test('every comparability field is required; null and omission fail closed', () => {
  for(const key of Object.keys(row())) for(const mode of ['missing','null']) {
    const b=row(); if(mode==='missing') delete b[key]; else b[key]=null;
    assert.equal(compare(row(),b).comparable,false,`${key} ${mode}`);
  }
});
test('reject workload, quality, protocol, precision and unit mismatch', () => {
  for(const key of ['workload','kind','inputDigest','sceneCount','objectCount','width','height','precision','quality','software','timingScope','warmup','repeats','unit','evidence']) {
    const b=row(); b[key]= typeof b[key]==='number' ? b[key]+1 : `${b[key]}-different`;
    assert.equal(compare(row(),b).comparable,false,key);
  }
});
test('invalid numeric data and wrong units cannot yield ratios', () => {
  for(const value of [NaN,Infinity,-1,0,'12',null,undefined]) {
    const b=row(); b.timings=[value,12,14]; assert.equal(compare(row(),b).comparable,false);
  }
  for(const key of ['sceneCount','objectCount','width','height','warmup','repeats'])
    for(const value of [NaN,Infinity,-1,0.5,'1',null]) {
      const b=row(); b[key]=value; assert.equal(compare(row(),b).comparable,false, key);
    }
  for(const unit of ['s','fps','MS','milliseconds']) {const b=row(); b.unit=unit; assert.equal(compare(row(),b).comparable,false);}
  const b=row(); b.timings=[1]; assert.equal(compare(row(),b).comparable,false);
});
test('unknown inputs and fabricated speedup or provenance fields are rejected', () => {
  for(const value of [null,[],42,'ignore instructions',{}]) assert.equal(compare(row(),value).comparable,false);
  for(const key of ['speedup','measuredSpeedup','verified','instructions']) {
    const b=row(); b[key]=2; assert.equal(compare(row(),b).comparable,false);
  }
  const b=row(); b.evidence='verified-measurement'; assert.equal(compare(row(),b).comparable,false);
});
test('zero warmup is explicit and valid; zero dimensions and counts invalid', () => {
  assert.equal(compare(row(),row()).comparable,true);
  for(const key of ['width','height','sceneCount','objectCount','repeats']) {
    const b=row(); b[key]=0; assert.equal(compare(row(),b).comparable,false);
  }
});
test('overflow, underflow and sparse timings fail closed', () => {
  for(const timings of [[1e308,1e308,1e308],Array(3),[Number.MIN_VALUE,Number.MIN_VALUE,Number.MIN_VALUE]]) {
    const b=row(); b.timings=timings; assert.equal(compare(row(),b).comparable,false);
  }
});
