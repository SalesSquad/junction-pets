import test from 'node:test';
import assert from 'node:assert/strict';
import { resolvePlan, WORKLOADS } from './plan.mjs';

const base={harnessSha:'c1e926f624fda2d4063e71a48306d92940d097d3',
  creditOpen:'true',now:'2026-11-14T20:00:00Z',repository:'SalesSquad/junction-pets'};
const frozen='634f1e0e6cb2de46bcf0a783532d46c23f513d11';

test('source-bound experimental job matrix has no cross-model source substitution',()=>{
 for(const [name,count,max] of [
  ['meta-r-tournament',8,8],['meta-r-robust',12,8],['meta-r-hardshift-2x',24,6]]) {
  assert.ok(WORKLOADS.includes(name));
  const p=resolvePlan({workload:name,source_sha:frozen},base);
  assert.equal(p.jobCount,count);
  assert.equal(p.maxParallel,max);
  assert.equal(new Set(p.matrix.include.map(x=>x.cell)).size,count);
  assert.deepEqual(p.matrix.include.map(x=>x.cohort),Array.from({length:count},(_,i)=>i));
  assert.ok(p.matrix.include.every(x=>x.source_sha===frozen));
 }
 assert.throws(()=>resolvePlan({workload:'meta-r-hardshift-2x',source_sha:base.harnessSha},base),
               /frozen candidate SHA/);
});
test('licensed RGB numeric workload stays exact-source and limited to four profiles',()=>{
 const p=resolvePlan({workload:'lens-real-bop-train'},base);
 assert.equal(p.jobCount,4);
 assert.equal(p.maxParallel,4);
 assert.deepEqual(p.matrix.include.map(x=>x.profile),['all','color','spatial','gradient']);
 assert.ok(p.matrix.include.every(x=>x.source_sha===base.harnessSha));
 assert.throws(()=>resolvePlan({workload:'lens-real-bop-train',source_sha:frozen},base),
   /exact source\/harness SHA/);
});
test('closed window and wrong repository fail closed before scheduling model work',()=>{
 for(const name of ['meta-r-robust','meta-r-hardshift-2x','lens-real-bop-train']){
  assert.throws(()=>resolvePlan({workload:name},{...base,creditOpen:'false'}),/closed/);
  assert.throws(()=>resolvePlan({workload:name},{...base,now:'2026-11-15T17:00:00Z'}),/deadline/);
  assert.throws(()=>resolvePlan({workload:name},{...base,repository:'other/repo'}),/Junction-only/);
 }
});
