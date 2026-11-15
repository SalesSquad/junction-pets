import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {projectEvidence} from './evidence.mjs';

test('companion keeps real observation dates, ordinary/member prices and unknown shipping',async()=>{
  const bytes=await readFile(new URL('../../solutions/context-dev-live-web-decision/live/capture.json',import.meta.url),'utf8');
  const view=projectEvidence(bytes),saved=JSON.parse(await readFile(new URL('./evidence.json',import.meta.url),'utf8'));
  assert.deepEqual(view,saved);assert.equal(view.mode,'HISTORICAL_CAPTURE');assert.equal(view.offers.length,2);
  const gigantti=view.offers.find(o=>o.name==='Gigantti');assert.equal(gigantti.priceCents,10900);assert.equal(gigantti.memberPriceCents,6999);assert.equal(gigantti.shippingFromCents,null);
  assert.deepEqual(view.offers.map(o=>o.receivedAt),JSON.parse(bytes).captures.map(c=>c.receivedAt));
  assert(!('winner' in view));assert(!('connection' in view));assert(!('apiKey' in view));assert.match(view.sourceCaptureSha256,/^[a-f0-9]{64}$/);
});
test('companion projection refuses conflicting identity rather than publishing another product',async()=>{
  const pack=JSON.parse(await readFile(new URL('../../solutions/context-dev-live-web-decision/live/capture.json',import.meta.url),'utf8'));
  pack.captures[0].identity.gtin='0000000000000';assert.throws(()=>projectEvidence(JSON.stringify(pack)));
});
