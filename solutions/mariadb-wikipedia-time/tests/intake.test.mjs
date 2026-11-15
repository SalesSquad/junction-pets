import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchSnapshot,admitSnapshot,parseResponse,snapshotDigest,requestUrl,LIMITS,LICENSE} from '../src/wikipedia.mjs';
import {loadDataset,at} from '../src/chronicle.mjs';
import {importSnapshot,readAsOf,INSERT,connectLocal} from '../src/mariadb.mjs';
import {makeCatalog,evaluate} from '../studio/server.mjs';
const payload=()=>({batchcomplete:true,query:{pages:[{pageid:155,ns:0,title:'Test title',revisions:[
  {revid:103,parentid:102,timestamp:'2026-01-03T00:00:00Z',slots:{main:{contentmodel:'wikitext',contentformat:'text/x-wiki',content:"New '); DROP TABLE users; -- <script>"}}},
  {revid:102,parentid:101,timestamp:'2026-01-02T00:00:00Z',slots:{main:{contentmodel:'wikitext',contentformat:'text/x-wiki',content:'Before'}}}
]}]}});
const response=x=>new Response(JSON.stringify(x),{headers:{'content-type':'application/json'}});
const snapshot=async data=>fetchSnapshot({pageId:'155',limit:2,now:()=> '2026-02-01T00:00:00.000Z',fetchImpl:async()=>response(data||payload())});
const mutate=(s,fn)=>{const x=structuredClone(s);fn(x);return x;};
test('deterministic intake → core → studio, exact boundary and citation, never verified sponsor evidence',async()=>{
  const s=await snapshot();assert.equal(s.snapshot_sha256,(await snapshot()).snapshot_sha256);
  const d=loadDataset(s),result=at(d,'155','2026-01-02T00:00:00Z');
  assert.equal(result.revision_id,'102');assert.match(result.source_url,/oldid=102$/);
  assert.equal(at(d,'155','2026-01-01T00:00:00Z').status,'NO_EVIDENCE');
  assert.equal(result.provenance,'WIKIPEDIA_API_SNAPSHOT');assert.match(result.source_integrity,/UNVERIFIED/);
  assert.equal(makeCatalog(d).mode,'REAL_LOCAL_SNAPSHOT_NO_MARIADB');
  assert.equal(evaluate(d,{page_id:'155',as_of:'2026-01-03T00:00:00Z',compare_at:'2026-01-02T00:00:00Z'}).verified_live_source,false);
});
test('licence, attribution, source URL, page, hash, timestamp, duplicate, tie and order manipulations refused',async()=>{
  const s=await snapshot();
  const cases=[x=>x.dataset_license='public domain',x=>x.attribution='Sponsor verified',x=>x.source_uri='https://evil.test',
    x=>x.revisions[0].source_url='https://fi.wikipedia.org@evil.test/?oldid=103',x=>x.revisions[0].page_id='156',
    x=>x.revisions[0].body='changed',x=>x.revisions[0].revised_at='2026-02-30T00:00:00Z',
    x=>x.revisions[1].revision_id='103',x=>x.revisions[1].revised_at=x.revisions[0].revised_at,
    x=>x.revisions.reverse(),x=>x.revisions[0].verified=true,x=>x.provenance='SYNTHETIC'];
  for(const fn of cases)assert.throws(()=>admitSnapshot(mutate(s,fn)));
  const x=mutate(s,x=>x.revisions[0].body='self supplied');x.revisions[0].content_sha256=(await import('../src/chronicle.mjs')).sha256(x.revisions[0].body);x.snapshot_sha256=snapshotDigest(x);
  assert.match(admitSnapshot(x).source_integrity,/UNVERIFIED/); // a hash is not authentication
});
test('hidden, deleted, wrong identity, incomplete and ambiguous API records rejected',()=>{
  for(const change of [x=>x.query.pages[0].pageid=156,x=>x.query.pages.push(x.query.pages[0]),x=>x.query.pages[0].missing=true,
    x=>x.query.pages[0].revisions[0].texthidden=true,x=>delete x.query.pages[0].revisions[0].slots.main.content,
    x=>x.query.pages[0].revisions[0].slots.main.contenthidden=true,x=>x.query.pages[0].revisions[0].revid=1.5,
    x=>x.warnings={},x=>x.continue={continue:'||',rvcontinue:'https://evil.test'}]){
    const d=payload();change(d);assert.throws(()=>parseResponse(d,'155'));
  }
  assert.throws(()=>requestUrl('https://evil.test',1));assert.throws(()=>requestUrl('155',21));
});
test('bounded pagination pins endpoint, User-Agent, redirect policy and total timeout signal',async()=>{
  let calls=0;const s=await fetchSnapshot({pageId:'155',limit:2,now:()=> '2026-02-01T00:00:00Z',fetchImpl:async(url,opts)=>{
    calls++;assert.equal(new URL(url).origin,'https://fi.wikipedia.org');assert.equal(opts.redirect,'error');assert.match(opts.headers['User-Agent'],/ChronicleWitness/);assert.ok(opts.signal);
    const x=payload();x.query.pages[0].revisions=[x.query.pages[0].revisions[calls-1]];
    if(calls===1)x.continue={continue:'||',rvcontinue:'20260102000000|102'};return response(x);
  }});assert.equal(calls,2);assert.equal(s.has_more,false);
});
test('truncated JSON, response/content overlimit, overcount and incomplete windows fail closed',async()=>{
  for(const r of [new Response('{',{headers:{'content-type':'application/json'}}),
    new Response('x'.repeat(LIMITS.responseBytes+1),{headers:{'content-type':'application/json'}}),
    new Response('{}',{headers:{'content-type':'application/json','content-length':String(LIMITS.responseBytes+1)}})]) {
    await assert.rejects(fetchSnapshot({pageId:'155',limit:1,fetchImpl:async()=>r}));
  }
  await assert.rejects(fetchSnapshot({pageId:'155',limit:1,fetchImpl:async()=>response(payload())}));
  const huge=payload();huge.query.pages[0].revisions[0].slots.main.content='ä'.repeat(LIMITS.contentBytes);await assert.rejects(snapshot(huge));
  const empty=payload();empty.query.pages[0].revisions=[];await assert.rejects(snapshot(empty));
  const short=payload();short.query.pages[0].revisions.pop();await assert.rejects(snapshot(short),/INCOMPLETE/);
});
test('MariaDB import binds hostile content, deduplicates and rolls back conflicting IDs',async()=>{
  const s=await snapshot();let calls=[],existing=[],commits=0,rollbacks=0;
  const conn={beginTransaction:async()=>{},commit:async()=>commits++,rollback:async()=>rollbacks++,execute:async(sql,args)=>{
    calls.push({sql,args});return sql.startsWith('SELECT')?existing:[];
  }};
  const result=await importSnapshot(conn,s);assert.equal(result.inserted,2);assert.equal(commits,1);
  const inserts=calls.filter(c=>c.sql===INSERT);assert.equal(inserts.length,2);assert.equal(inserts[0].args[5],s.revisions[0].body);assert.ok(!inserts[0].sql.includes('DROP'));
  const columns='dataset_id,source_revision_id,page_id,article_title,revised_at_utc,content_body,content_sha256,source_url,dataset_license,provenance,retrieved_at_utc,source_uri,snapshot_sha256,attribution'.split(',');
  const saved=new Map(inserts.map(c=>[c.args[1],Object.fromEntries(columns.map((k,i)=>[k,c.args[i]]))]));
  conn.execute=async(sql,args)=>sql.startsWith('SELECT')?[saved.get(args[1])]:assert.fail('duplicate insert');
  assert.equal((await importSnapshot(conn,s)).deduplicated,2);
  saved.get('103').content_body='conflict';await assert.rejects(importSnapshot(conn,s),/ROLLED_BACK/);assert.equal(rollbacks,1);
});
test('DB readback binds both clocks and rejects hostile identity; timestamp tie is refused',async()=>{
  const s=await snapshot(),d=admitSnapshot(s);let seen;
  const rows=d.revisions.map(r=>({source_revision_id:r.revision_id,page_id:r.page_id,article_title:r.title,revised_at:r.revised_at,content_body:r.body,content_sha256:r.hash,source_url:r.source_url,dataset_license:LICENSE,provenance:d.provenance}));
  const conn={execute:async(sql,args)=>{seen={sql,args};return rows;}};
  assert.equal((await readAsOf(conn,d.dataset_id,'155','2026-01-04T00:00:00Z','2026-02-02T00:00:00Z')).revision_id,'103');
  assert.match(seen.sql,/FOR SYSTEM_TIME AS OF TIMESTAMP \?/);assert.deepEqual(seen.args,['2026-02-02 00:00:00.000',d.dataset_id,'155','2026-01-04 00:00:00.000']);
  rows[1].revised_at=rows[0].revised_at;assert.equal((await readAsOf(conn,d.dataset_id,'155','2026-01-04T00:00:00Z')).status,'AMBIGUOUS_TIMESTAMP');
  await assert.rejects(readAsOf(conn,"x' OR 1=1 --",'155','2026-01-04T00:00:00Z'),/IDENTITY/);
  rows[0].source_url='https://evil.test';await assert.rejects(readAsOf(conn,d.dataset_id,'155','2026-01-04T00:00:00Z'),/INTEGRITY/);
  await assert.rejects(connectLocal({host:'evil.test'}),/EXPLICIT_LOCAL/);
});
test('pagination request ceiling rejects incomplete window without issuing a fifth call',async()=>{
  let count=0;
  await assert.rejects(fetchSnapshot({pageId:'155',limit:5,fetchImpl:async()=>{
    count++;const p=payload();p.query.pages[0].revisions=[p.query.pages[0].revisions[0]];
    p.continue={continue:'||',rvcontinue:'20260102000000|'+(200-count)};return response(p);
  }}),/INCOMPLETE/);
  assert.equal(count,4);
});
test('legacy synthetic labels cannot promote caller-supplied integrity claims',()=>{
  const d=loadDataset({dataset_id:'demo',dataset_license:'fiction',provenance:'SYNTHETIC',source_integrity:'SPONSOR_VERIFIED',snapshot_sha256:'fabricated',revisions:[]});
  assert.equal(d.source_integrity,'LOCAL_HASH_ONLY_UNVERIFIED');assert.equal(d.snapshot_sha256,null);
});
