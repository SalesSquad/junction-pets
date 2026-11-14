import test from 'node:test';
import assert from 'node:assert/strict';
import {loadFixture, makeCatalog, evaluate, createStudioServer, LABEL, MAX_REQUEST_BYTES} from './server.mjs';
import {loadDataset} from '../src/chronicle.mjs';
const d = await loadFixture();
test('catalog remains source-bound and sorted chronologically', () => {
  const catalog=makeCatalog(d);
  assert.equal(catalog.mode, LABEL);
  assert.equal(catalog.live,false);
  assert.equal(catalog.pages.length,2);
  assert.equal(catalog.pages.find(p=>p.page_id==='demo:harbor-energy').revisions[0].revision_id,'101');
  assert.match(catalog.dataset_license,/synthetic/);
});
test('exact as-of boundaries do not leak a future revert into historical findings', () => {
  const base={page_id:'demo:harbor-energy',compare_at:'2025-01-10T00:00:00Z'};
  const before=evaluate(d,{...base,as_of:'2025-01-11T01:00:00Z'});
  assert.equal(before.snapshot.revision_id,'102');
  assert.equal(before.comparison.status,'CHANGED');
  assert.equal(before.suspected_reverts.length,0);
  assert.equal(before.verified_live_source,false);
  assert.equal(before.mode,LABEL);
  const after=evaluate(d,{...base,as_of:'2025-01-11T03:00:00Z'});
  assert.equal(after.snapshot.revision_id,'103');
  assert.equal(after.suspected_reverts.length,1);
  assert.equal(after.suspected_reverts[0].label,'REVERT_CANDIDATE_NOT_VANDALISM_PROOF');
});
test('no invented earlier history and honest comparison refusal', () => {
  const result=evaluate(d,{page_id:'demo:civic-debate',as_of:'2025-01-01T00:00:00Z',compare_at:'2024-01-01T00:00:00Z'});
  assert.equal(result.snapshot.status,'NO_EVIDENCE');
  assert.equal(result.comparison.status,'UNAVAILABLE');
});
test('invalid ordering, shape, injection keys and impossible pages fail closed', () => {
  const good={page_id:'demo:harbor-energy',as_of:'2025-01-11T03:00:00Z',compare_at:'2025-01-10T00:00:00Z'};
  for(const value of [
    {...good,as_of:'2025-01-01T00:00:00Z'}, {...good,page_id:'DEMO:harbor-energy'},
    {...good,admin:true}, {...good,compare_at:null},
    {...good,as_of:'2025-02-30T00:00:00Z'}, {...good,page_id:'../../etc/passwd'}])
    assert.throws(()=>evaluate(d,value));
});
test('ambiguous same-time events return explicit refusal, no chosen truth', () => {
  const original={
    dataset_id:d.dataset_id,dataset_license:d.dataset_license,provenance:d.provenance,
    revisions:d.revisions.map(({ms,hash,...r})=>r)
  };
  original.revisions.push({...original.revisions[1],revision_id:'990'});
  const x=loadDataset(original);
  const r=evaluate(x,{page_id:'demo:harbor-energy',as_of:'2025-01-11T01:00:00Z',compare_at:'2025-01-10T00:00:00Z'});
  assert.equal(r.snapshot.status,'AMBIGUOUS_TIMESTAMP');
  assert.deepEqual(r.snapshot.conflicting_ids,['102','990']);
  assert.equal(r.comparison.status,'UNAVAILABLE');
});
test('loopback server labels truth, blocks cross-origin and refuses malformed requests', async t => {
  const server=createStudioServer(d);
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  t.after(()=>new Promise(resolve=>server.close(resolve)));
  const base='http://127.0.0.1:'+server.address().port;
  const c=await fetch(base+'/api/catalog');
  assert.equal(c.status,200);
  assert.equal(c.headers.get('cache-control'),'no-store');
  assert.match(c.headers.get('content-security-policy'),/default-src 'none'/);
  assert.equal((await c.json()).live,false);
  const data=JSON.stringify({page_id:'demo:harbor-energy',as_of:'2025-01-11T03:00:00Z',compare_at:'2025-01-10T00:00:00Z'});
  const good=await fetch(base+'/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:data});
  assert.equal(good.status,200);assert.equal((await good.json()).snapshot.revision_id,'103');
  const bad=await fetch(base+'/api/compare',{method:'POST',headers:{'Content-Type':'application/json',Origin:'https://attacker.invalid'},body:data});
  assert.equal(bad.status,403);assert.equal((await bad.json()).reason,'ORIGIN_REFUSED');
  const large=await fetch(base+'/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:'x'.repeat(MAX_REQUEST_BYTES+1)});
  assert.equal(large.status,413);
  const notFound=await fetch(base+'/etc/passwd');
  assert.equal(notFound.status,404);
  const html=await (await fetch(base+'/')).text();
  assert.match(html,/SYNTHETIC REPLAY/);
  assert.doesNotMatch(html,/script[^>]+https:/);
});
