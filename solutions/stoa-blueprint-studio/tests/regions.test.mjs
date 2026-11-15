import test from 'node:test';
import assert from 'node:assert/strict';
import { boxIoU, scoreRegions } from '../benchmark/regions.mjs';
const box = (coords=[0,0,10,10], page=1, sha='a'.repeat(64)) => ({sourceSha256:sha,page,box:coords});
test('region scoring requires same source/page, penalizes duplicates and missing predictions',()=>{
  assert.equal(boxIoU(box(),box([5,0,15,10])),1/3);
  assert.equal(boxIoU(box(),box(undefined,2)),0);
  assert.equal(boxIoU(box(),box(undefined,1,'b'.repeat(64))),0);
  const r=scoreRegions([{expected:[box()],predicted:[box(),box()]},{expected:[box()],predicted:[]}]);
  assert.equal(r.matched,1);assert.equal(r.precision,.5);assert.equal(r.recall,.5);assert.equal(r.meanMatchedIoU,1);
  assert.equal(scoreRegions([{expected:[],predicted:[]}]).precision,null);
  assert.throws(()=>boxIoU(box([0,0,0,0]),box()),/positive/);
});
test('maximum matching avoids greedy loss when one prediction can match two regions',()=>{
  const r=scoreRegions([{expected:[box([0,0,10,10]),box([5,0,15,10])],predicted:[box([2,0,13,10]),box([0,0,10,10])]}]);
  assert.equal(r.matched,2);
});
