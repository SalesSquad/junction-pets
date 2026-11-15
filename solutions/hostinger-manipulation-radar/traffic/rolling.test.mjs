import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzeLog,exportReport,MAX_BYTES} from '../public/traffic/core.mjs';
const line=(second,status,i=0,ip=`2001:db8::${i%3+1}`)=>`${ip} - private-user [14/Nov/2026:09:${String(Math.floor(second/60)).padStart(2,'0')}:${String(second%60).padStart(2,'0')} +0000] "POST /login?email=alice@example.test HTTP/1.1" ${status} 120 "https://secret.example.test" "private-agent"`;
const burst=offset=>Array.from({length:15},(_,i)=>line(offset+i,i<10?i%2?403:401:429,i));
const run=lines=>analyzeLog(new TextEncoder().encode(lines.join('\n')));
test('exact fixed-bin crossing becomes one rolling episode with exact sanitized evidence',()=>{
 const lines=burst(294),r=run(lines);
 assert.equal(r.counts.candidates,0);assert.equal(r.clusters.length,2);
 assert.equal(r.rolling.episodes.length,1);
 const e=r.rolling.episodes[0];assert.equal(e.start,'2026-11-14T09:00:08.000Z');assert.equal(e.end,'2026-11-14T09:05:08.000Z');assert.equal(e.distinctClients,3);
 assert.deepEqual(e.evidenceIds,Array.from({length:15},(_,i)=>`event-${i+1}`));assert.equal(e.counterexplanations.length,2);assert.match(e.review,/Human review only/);
 assert.equal(r.provenance,'USER_SUPPLIED_UNVERIFIED_LOG');assert.equal(r.realWorldLabels,'UNKNOWN');assert.equal(exportReport(r),exportReport(run(lines)));
 for(const secret of ['2001:db8','private-user','alice@','secret.example','private-agent'])assert.ok(!exportReport(r).includes(secret));
});
test('overlapping windows merge; distant bursts stay separate; ledger IDs occur once',()=>{
 const r=run([...burst(294),...burst(320),...burst(1000)]),episodes=r.rolling.episodes;
 assert.equal(episodes.length,2);assert.equal(episodes[0].evidenceIds.length,30);assert.equal(episodes[1].evidenceIds.length,15);
 const ids=episodes.flatMap(e=>e.evidenceIds);assert.equal(new Set(ids).size,ids.length);
});
test('five-minute left boundary excluded, one second inside included',()=>{
 const lines=burst(0).map((l,i)=>i===0?line(0,401,i):line(300,i<10?401:429,i));
 assert.equal(run(lines).rolling.episodes.length,0);
 lines[0]=line(1,401,0);assert.equal(run(lines).rolling.episodes.length,1);
});
test('empty and benign traffic, insufficient aliases and missing rate limits stay negative',()=>{
 for(const lines of [[],burst(294).map(l=>l.replace(/ (401|403|429) /,' 200 ')),burst(294).map(l=>l.replace(/2001:db8::[123]/,'2001:db8::1')),burst(294).map(l=>l.replace(' 429 ',' 200 '))])assert.equal(run(lines).rolling.episodes.length,0);
});
test('unordered timestamps and tied IPv6 events replay deterministically',()=>{
 const lines=burst(294).map((l,i)=>line(300,i<10?401:429,i));const r=run(lines.reverse());assert.equal(r.rolling.episodes.length,1);assert.equal(r.rolling.episodes[0].evidenceIds.length,15);
 const shuffled=run(burst(294).reverse());assert.equal(shuffled.rolling.episodes[0].end,'2026-11-14T09:05:08.000Z');assert.deepEqual(shuffled.events.map(e=>e.id),Array.from({length:15},(_,i)=>`event-${i+1}`));
});
test('5000 event bound accepted and oversize refuses without exporting input',()=>{
 const lines=Array.from({length:5000},(_,i)=>line(300,200,i));assert.equal(run(lines).events.length,5000);assert.throws(()=>run([...lines,lines[0]]),/maximum 5000/);assert.throws(()=>analyzeLog(new Uint8Array(MAX_BYTES+1)),/maximum 1 MiB/);
});

test('equivalent IPv6 spellings cannot fabricate three distinct clients',()=>{
 const spellings=['2001:db8::1','2001:0DB8:0:0:0:0:0:1','2001:0db8::0001'];
 const lines=Array.from({length:15},(_,i)=>line(300+i,i<10?401:429,i,spellings[i%3]));
 const report=run(lines);
 assert.equal(report.counts.distinctClients,1);
 assert.equal(report.rolling.episodes.length,0);
 assert.equal(report.counts.candidates,0);
 for(const raw of spellings)assert.equal(exportReport(report).includes(raw),false);
});
