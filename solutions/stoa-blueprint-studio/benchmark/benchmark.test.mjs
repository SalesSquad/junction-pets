import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, unlink, stat } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { deflateRawSync } from 'node:zlib';
import { evaluate, sha256, run, immutableJson } from './run.mjs';
import { validateEntry, unpack, crc32, inspect, parseDirectory, MAX_RANGE } from './fetch-holdout.mjs';
import { answerDrawing } from '../src/grounding.mjs';
const bytes = Buffer.from('0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n6\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nTEXT\n8\nROOM_TEXT\n1\nOffice\n10\n1\n20\n2\n0\nTEXT\n8\nROOM_TEXT\n1\nOffice\n10\n4\n20\n5\n0\nTEXT\n8\nROOM_TEXT\n1\nLobby\n10\n8\n20\n9\n0\nENDSEC\n0\nEOF\n');
// Independently authored group positions; do not build references from engine output.
const offices = [
  { id:'e1', type:'TEXT', layer:'ROOM_TEXT', x:1, y:2, text:'Office' },
  { id:'e2', type:'TEXT', layer:'ROOM_TEXT', x:4, y:5, text:'Office' }
];
function suite() { return {
  evidenceType:'SYNTHETIC_MECHANICS_ONLY', source:{sha256:sha256(bytes),filename:'controlled.dxf',archivePath:'synthetic authored inline fixture',license:'CC0-1.0',attribution:'Task-authored synthetic geometry'},
  questions:[
    {id:'count',question:'How many rooms labelled Office?',reference:{method:'Manual ASCII TEXT group enumeration',sourceLocator:'ENTITIES TEXT #1 and #2, group10/20'},expected:{status:'supported',answer:'2',regions:structuredClone(offices)}},
    {id:'negative',question:'How many doors are there?',reference:{method:'Manual source inspection: no semantic door instances',sourceLocator:'ENTITIES: only three room label TEXT entities'},expected:{status:'abstained',answer:null,regions:[]}}
  ]}; }
test('controlled bytes stay pinned; count, coordinates, negative and denominators',()=>{
  assert.equal(sha256(bytes),"e394d4a506a3ae6654ca9a86bd746246ed6b92ba88d58702b4995f5a76abf440");
  const report=evaluate(bytes,suite()); const m=report.metrics;
  assert.equal(m.totalQuestions,2); assert.equal(m.expectedSupported,1); assert.equal(m.expectedAbstentions,1);
  assert.equal(m.correct,2); assert.equal(m.groundedCorrect,2); assert.equal(m.accuracy,1);
  assert.equal(m.coverage,.5); assert.equal(m.abstentionRate,.5); assert.equal(m.regionPrecision,1); assert.equal(m.regionRecall,1);
  assert.equal(m.predictedRegions,2); assert.equal(m.expectedRegions,2);
  assert.deepEqual(report.rows[0].resolved.map(x=>x.verifiedSourceEntity),offices);
  assert.equal(report.officialSponsorScore,null); assert.equal(report.baseline.comparable,false);
  assert.ok(m.meanResponseLatencyMs>=0);
});
test('SHA mismatch and prior preview cannot be admitted',()=>{
  const s=suite();s.source.sha256='0'.repeat(64);assert.throws(()=>evaluate(bytes,s),/SHA mismatch/);
  const old=suite();old.source.filename='site1102_bldg2242_floor10281.dxf';assert.throws(()=>evaluate(bytes,old),/excluded/);
});
test('fabricated reference IDs, altered source coordinates and missing labels fail closed',()=>{
  for(const alter of [s=>s.questions[0].expected.regions[0].id='e99',s=>s.questions[0].expected.regions[0].x=99,s=>delete s.questions[0].expected.answer]){
    const s=suite();alter(s);assert.throws(()=>evaluate(bytes,s),/reference region|Missing expected/);
  }
});
test('incorrect citation substitution lowers region precision/recall without inventing geometry',()=>{
  const r=evaluate(bytes,suite(),(d,q)=>{const a=answerDrawing(d,q);if(a.status==='supported')a.evidence[0]={entityId:'e3',kind:'TEXT',layer:'ROOM_TEXT'};return a;});
  assert.equal(r.metrics.accuracy,1);assert.equal(r.metrics.groundedAccuracy,.5);
  assert.equal(r.metrics.regionPrecision,.5);assert.equal(r.metrics.regionRecall,.5);
});
test('unknown, duplicate and source-mismatched citations never gain credit',()=>{
  for(const change of [a=>a.evidence[0].entityId='fake',a=>a.evidence[0]=a.evidence[1],a=>a.source.sha256='0'.repeat(64)]){
    const r=evaluate(bytes,suite(),(d,q)=>{const a=answerDrawing(d,q);if(a.status==='supported')change(a);return a;});
    assert.ok(r.metrics.regionPrecision<1);assert.ok(r.metrics.groundedAccuracy<1);
  }
});
test('missing response stays in denominator; unsupported abstention is not correct',()=>{
  const r=evaluate(bytes,suite(),(d,q)=>q.includes('Office')?undefined:answerDrawing(d,q));
  assert.equal(r.metrics.totalQuestions,2);assert.equal(r.metrics.accuracy,.5);assert.equal(r.metrics.missingResponses,1);
  assert.equal(r.metrics.regionPrecision,null);assert.equal(r.metrics.regionRecall,0);
  const a=evaluate(bytes,suite(),(d)=>answerDrawing(d,'What color is the roof?'));
  assert.equal(a.metrics.accuracy,.5);assert.equal(a.metrics.coverage,0);assert.equal(a.metrics.abstentionRate,1);
});
test('missing answer is incorrect; unsupported answer to negative is incorrect',()=>{
  const r=evaluate(bytes,suite(),(d,q)=>{const a=answerDrawing(d,q);delete a.answer;return a;});assert.equal(r.metrics.accuracy,0);
  const f=evaluate(bytes,suite(),d=>answerDrawing(d,'How many rooms labelled Office?'));assert.equal(f.metrics.accuracy,.5);
});
test('no real source means no real score',async()=>{
  const s=JSON.parse(await readFile(new URL('./holdout-source-v1.json',import.meta.url)));
  assert.throws(()=>evaluate(bytes,s),/NO_REAL_HELDOUT_SOURCE/);
  await assert.rejects(run(['--drawing','/private/tmp/absent.dxf','--suite',new URL('./holdout-source-v1.json',import.meta.url).pathname,'--output','/private/tmp/no-score.json']),/NO_REAL_HELDOUT_SOURCE/);
});
test('CLI runs pinned application and creates private immutable report',async t=>{
  const stem='/private/tmp/stoa-m3-test-'+randomUUID(); const input=stem+'.dxf', manifest=stem+'.suite.json', output=stem+'.result.json';
  const {writeFile}=await import('node:fs/promises');
  t.after(async()=>{for(const p of [input,manifest,output])await unlink(p).catch(()=>{});});
  await writeFile(input,bytes,{flag:'wx',mode:0o600});await immutableJson(manifest,suite());
  await run(['--drawing',input,'--suite',manifest,'--output',output]);
  const report=JSON.parse(await readFile(output));assert.equal(report.metrics.correct,2);assert.equal(report.app.baseCommit,'79d998af372c26cb05907ad9a4aa8e0662caeaf8');
  assert.equal((await stat(output)).mode & 0o777,0o600);
  await assert.rejects(immutableJson(output,{}),/EEXIST/);
  await assert.rejects(immutableJson('/private/tmp/../bad.json',{}),/private\/tmp/);
});
const entry=()=>({path:'junction-dataset-preview/data/swiss_dwellings/site2_bldg3_floor4.dxf',flags:0,method:8,compressed:10,raw:20,disk:0});
test('archive paths, bombs, encryption and ranges reject unsafe entries',()=>{
  for(const change of [e=>e.path='../evil.dxf',e=>e.raw=7*1024*1024,e=>e.compressed=MAX_RANGE+1,e=>e.flags=1,e=>e.method=99,e=>{e.compressed=1;e.raw=201;}]){const e=entry();change(e);assert.throws(()=>validateEntry(e),/Unsafe/);}
  assert.throws(()=>parseDirectory(Buffer.from('bad')),/Malformed/);
});
test('ZIP bounded decompression validates original length and CRC',()=>{
  const raw=Buffer.from('0\nSECTION\n2\nENTITIES\n'),packed=deflateRawSync(raw),e={...entry(),compressed:packed.length,raw:raw.length,crc:crc32(raw)};
  assert.deepEqual(unpack(e,packed),raw);assert.throws(()=>unpack({...e,crc:0},packed),/CRC/);
  assert.throws(()=>unpack({...e,raw:1},packed));
});
test('archive failure is a single attempt without retry',()=>{
  let calls=0;assert.throws(()=>inspect(()=>{calls++;throw new Error('DNS unavailable');}),/DNS/);assert.equal(calls,1);
});
test('small ZIP entry uses exactly two bounded requests and verifies local name',async()=>{
  const {readEntry}=await import('./fetch-holdout.mjs');
  const raw=Buffer.from('CC BY 4.0 synthetic license transport fixture');
  const path='junction-dataset-preview/data/swiss_dwellings/LICENSE.md';
  const e={...entry(),path,method:0,raw:raw.length,compressed:raw.length,crc:crc32(raw),localOffset:123};
  const h=Buffer.alloc(30);h.writeUInt32LE(0x04034b50);h.writeUInt16LE(Buffer.byteLength(path),26);
  const body=Buffer.concat([Buffer.from(path),raw]);let requests=0;
  const request=(a,b)=>{requests++;assert.ok(b-a+1<1024*1024);return {bytes:requests===1?h:body};};
  assert.deepEqual(readEntry(e,request),raw);assert.equal(requests,2);
  requests=0;assert.throws(()=>readEntry({...e,path:'junction-dataset-preview/data/swiss_dwellings/site9_bldg9_floor9.dxf'},request),/name mismatch/);
});
