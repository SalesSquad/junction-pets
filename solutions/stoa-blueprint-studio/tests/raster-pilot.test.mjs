import test from 'node:test';
import assert from 'node:assert/strict';
import {checkScale, readLines, roomAnnotation} from '../raster/pilot/reading.mjs';

const tag = {id:'a',text:'101',confidence:95,box:[10,10,30,20]};
const annotation = {id:'b',text:'12 m²',confidence:95,box:[10,24,37,36]};
const page = {page:1,width:100,height:100,sourceSha256:'source',rasterSha256:'raster'};

test('observations cite both labels on the exact page; duplicates and ambiguous units abstain', () => {
  const result = roomAnnotation({...page,lines:[tag,annotation]},'101');
  assert.equal(result.value,12);
  assert.deepEqual(result.citations.map(x=>[x.id,x.rasterSha256]),[['a','raster'],['b','raster']]);
  for (const lines of [[tag,tag,annotation],[tag,{...annotation,text:'12 m?'}],
    [tag,annotation,{...tag,id:'c',text:'102'}]]) {
    assert.equal(roomAnnotation({...page,lines},'101').status,'abstained');
  }
});

test('scale checks refuse contradictory, stale and nonorthogonal controls', () => {
  const horizontal = {rasterSha256:'raster',from:[10,10],to:[50,10],metres:4};
  const vertical = {rasterSha256:'raster',from:[10,10],to:[10,40],metres:3};
  assert.equal(checkScale(page,[horizontal,vertical]).pixelsPerMetre,10);
  assert.equal(checkScale(page,[horizontal,{...vertical,metres:2}]).reason,'Scale controls disagree.');
  assert.equal(checkScale(page,[horizontal,{...vertical,rasterSha256:'old'}]).status,'abstained');
  assert.equal(checkScale(page,[horizontal,horizontal]).status,'abstained');
});

test('OCR word coordinates outside the source raster reject', () => {
  const tsv = 'header\n5\t1\t1\t1\t1\t1\t90\t10\t20\t10\t90\t101';
  assert.throws(()=>readLines(tsv,100,100),/coordinates/);
});

test('retry boxes map to the original page and conflicting readings abstain', () => {
  const enlarged = [tag,annotation].map(line=>({...line,box:line.box.map(x=>2*x)}));
  const view = {id:'2x',inverse:[.5,0,0,0,.5,0],lines:enlarged};
  const input = {...page,lines:[tag],views:[view]};
  assert.deepEqual(roomAnnotation(input,'101').citations.map(c=>c.box),[tag.box,annotation.box]);
  const conflicting = {...view,id:'other',lines:[enlarged[0],{...enlarged[1],text:'13 m²'}]};
  assert.equal(roomAnnotation({...input,views:[view,conflicting]},'101').status,'abstained');
  assert.equal(roomAnnotation({...input,lines:[]},'101').status,'abstained');
});
