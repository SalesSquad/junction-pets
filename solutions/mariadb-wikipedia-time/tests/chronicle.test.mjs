import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {loadDataset,at,compare,reverts,inspect,utc} from '../src/chronicle.mjs';
const raw=JSON.parse(readFileSync(fileURLToPath(new URL('../fixtures/synthetic.json',import.meta.url)),'utf8'));
const data=loadDataset(raw),p='demo:harbor-energy';
test('visible synthetic provenance and SHA256',()=>{
  const s=at(data,p,'2025-01-10T00:00:00Z');
  assert.equal(s.status,'FOUND');assert.equal(s.provenance,'SYNTHETIC');
  assert.match(s.sha256,/^[a-f0-9]{64}$/);assert.equal(s.source_url,null);
});
test('does not invent earlier revisions',()=>assert.equal(at(data,p,'2025-01-09T23:59:59Z').status,'NO_EVIDENCE'));
test('inclusive timestamp chooses proper revisions',()=>{
  assert.equal(at(data,p,'2025-01-11T00:00:00Z').revision_id,'102');
  assert.equal(at(data,p,'2025-01-11T03:00:00Z').revision_id,'103');
});
test('comparison returns source-bound lexical change',()=>{
  const c=compare(at(data,p,'2025-01-10T00:00:00Z'),at(data,p,'2025-01-11T01:00:00Z'));
  assert.equal(c.status,'CHANGED');assert.ok(c.added.includes('cancelled'));assert.ok(c.removed.includes('consultation'));
});
test('three-edit revert candidate is not a vandalism assertion',()=>{
  const r=reverts(data,p);assert.equal(r.length,1);assert.deepEqual(r[0].revision_ids,['101','102','103']);
  assert.match(r[0].label,/NOT_VANDALISM_PROOF/);
});
test('out-of-order input does not change the answer',()=>{
  const shuffled=loadDataset({...raw,revisions:raw.revisions.toReversed()});
  assert.deepEqual(inspect(shuffled,p,'2025-01-11T01:00:00Z'),inspect(data,p,'2025-01-11T01:00:00Z'));
});
test('same-time conflict is refused rather than chosen',()=>{
  const x=loadDataset({...raw,revisions:[...raw.revisions,{...raw.revisions[0],revision_id:'999'}]});
  const s=at(x,p,'2025-01-10T01:00:00Z');
  assert.equal(s.status,'AMBIGUOUS_TIMESTAMP');assert.deepEqual(s.conflicting_ids,['101','999']);
});
test('duplicate source revision is rejected',()=>assert.throws(()=>loadDataset({...raw,
  revisions:[...raw.revisions,{...raw.revisions[0],page_id:'other'}]}),/DUPLICATE_REVISION/));
test('malformed dates and time zones rejected',()=>{
  assert.throws(()=>utc('2025-02-30T01:00:00Z'),/INVALID_UTC/);
  assert.throws(()=>utc('2025-02-01T01:00:00+02:00'),/INVALID_UTC/);
});
test('live replay requires Wikipedia HTTPS provenance',()=>{
  assert.throws(()=>loadDataset({...raw,provenance:'LICENSED_REPLAY',revisions:[
    {...raw.revisions[0],source_url:'https://evil.test/data'}]}),/SOURCE_URL_REQUIRED/);
});
test('self-declared licensed source must bind URL to exact revision, not a page',()=>{
  const x={...raw,provenance:'LICENSED_REPLAY',revisions:[
    {...raw.revisions[0],source_url:'https://fi.wikipedia.org/w/index.php?oldid=999'}]};
  assert.throws(()=>loadDataset(x),/SOURCE_REVISION_MISMATCH/);
  const exact=loadDataset({...x,revisions:[{...x.revisions[0],
    source_url:'https://fi.wikipedia.org/w/index.php?oldid=101'}]});
  const s=at(exact,p,'2025-01-10T00:00:00Z');
  assert.equal(s.source_integrity,'LOCAL_HASH_ONLY_UNVERIFIED');
  assert.equal(inspect(exact,p,'2025-01-10T00:00:00Z').verified_live_source,false);
});
test('unavailable comparisons refuse an answer',()=>{
  const r=inspect(data,'missing','2025-01-01T00:00:00Z','2024-01-01T00:00:00Z');
  assert.equal(r.snapshot.status,'NO_EVIDENCE');assert.equal(r.comparison.status,'UNAVAILABLE');
});
