import test from 'node:test';
import assert from 'node:assert/strict';
import { replay } from './replay.mjs';
test('material stock change switches review; cosmetic change preserves it',async()=>{assert.equal((await replay()).winner,'north');assert.equal((await replay('after')).winner,'coast');assert.equal((await replay('cosmetic')).winner,'north');assert.equal((await replay()).actionAuthorized,false);});
for(const [name,mutate] of Object.entries({redirect:r=>({...r,finalUrl:'https://evil.invalid/'}),partial:r=>({...r,partial:true}),stale:r=>({...r,cacheOriginAt:'2020-01-01T00:00:00.000Z'}),forged:r=>({...r,sourceId:'evil'}),overflow:r=>{r.json.data.priceCents=Number.MAX_SAFE_INTEGER;return r;},shipping:r=>{delete r.json.data.shippingCents;return r;},confidence:r=>{delete r.json.data.confidenceProvenance;return r;},unknown:r=>({...r,extra:true})}))test(name,async()=>assert.equal((await replay('before',mutate)).status,'REFUSE'));

test('untrusted host error cannot expose auth headers or private response', async () => {
  const result=await replay('before', () => {throw Error('Authorization: Bearer SECRET_PRIVATE_HEADER');});
  assert.equal(result.status,'REFUSE');
  assert.equal(result.reason,'CLIENT_FAILURE');
  assert(!JSON.stringify(result).includes('SECRET_PRIVATE_HEADER'));
});
