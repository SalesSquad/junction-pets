import assert from 'node:assert/strict';
import {once} from 'node:events';
import {createServer} from '../server.mjs';
const server=createServer({apiKey:null});
try {
 server.listen(0,'127.0.0.1');await once(server,'listening');const base=`http://127.0.0.1:${server.address().port}`;
 const page=await fetch(base);assert.equal(page.status,200);assert.match(await page.text(),/Approve locally/);assert.match(page.headers.get('content-security-policy'),/frame-ancestors 'none'/);
 const status=await (await fetch(base+'/api/status')).json();
 const post=async(path,body,extra={})=>fetch(base+path,{method:'POST',headers:{'content-type':'application/json',...extra},body:JSON.stringify(body)});
 const packet=await (await post('/api/packet',{goal:status.goal})).json();assert.equal(packet.state,'EVIDENCE_READY');assert.ok(packet.draft);assert.ok(packet.actions.length);assert.ok(packet.sources.length);
 const arbitrary=await (await post('/api/packet',{goal:'arbitrary judge query'})).json();assert.equal(arbitrary.state,'CONNECTION_NEEDED');
 const live=await (await post('/api/live',{goal:'q',consent:true})).json();assert.match(live.error,/EXA_API_KEY/);
 assert.equal((await post('/api/live',{goal:'q',consent:true},{origin:'https://attacker.test'})).status,403);
 assert.equal((await fetch(base+'/fixtures/official.json')).status,404);
 assert.equal((await post('/api/packet',{goal:'x'.repeat(9000)})).status,413);
 for(const path of ['/app.mjs','/style.css','/curation.mjs'])assert.equal((await fetch(base+path)).status,200);
 console.log('HTTP smoke PASS: static assets, packet, unknown query, missing key, origin, private path and body bounds. No browser/device claim.');
} finally {await new Promise(resolve=>server.close(resolve));}
