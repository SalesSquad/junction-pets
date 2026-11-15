import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from '../fixture.mjs';
import { rank,DEFAULT_GOAL,validateGoal,makeArtifact,escapeHTML,safeJSON,safeURL } from '../core.mjs';
import { requestCala,CALA_CONTRACT } from '../cala-contract.mjs';
import { readFile } from 'node:fs/promises';
const clone=()=>structuredClone(fixture);
const row=(d,id='inv-larch')=>rank(d).find(r=>r.entity.id===id);
test('primary lead examples rank deterministically with stable ID tie-break',()=>{const a=rank(fixture);assert.equal(a[0].entity.id,'inv-larch');assert.equal(a[0].score,10);assert.deepEqual(rank(fixture),a);assert.equal(a.filter(r=>r.eligible).length,2);});
test('filing and round count once by issuer and economic round identity',()=>{const d=clone();d.events.push({...d.events[0],id:'second-copy'});assert.equal(row(d).roundCount,1);assert.equal(row(d).accepted[0].citations.length,3);});
test('issuer cannot be treated as investor',()=>{const d=clone();d.events.filter(e=>e.investorId==='inv-larch').forEach(e=>e.role='ISSUER');assert.equal(row(d).eligible,false);});
test('missing lead is UNKNOWN rather than false/zero evidence',()=>{const r=row(fixture,'inv-blank');assert.equal(r.score,null);assert.equal(r.roundCount,null);assert.equal(r.amount,'UNKNOWN');assert.equal(r.eligible,false);});
test('stale evidence is inactive even if historical search includes it',()=>{const r=rank(fixture,{...DEFAULT_GOAL,from:'2020-01-01'}).find(r=>r.entity.id==='inv-archive');assert.equal(r.eligible,true);assert.equal(r.active,false);});
test('ambiguous same-name exact identity abstains',()=>{const r=row(fixture,'inv-echo');assert.equal(r.eligible,false);assert.deepEqual(r.accepted,[]);});
test('duplicate stable IDs and conflicting exact URLs abstain',()=>{for(const extra of [{...fixture.entities[0]},{...fixture.entities[1],url:fixture.entities[0].url}]){const d=clone();d.entities.push(extra);assert.equal(row(d).eligible,false);}});
test('fake circular lead claim is not primary proof',()=>assert.equal(row(fixture,'inv-loop').eligible,false));
test('contradictory lead claims withhold only that economic round',()=>{const r=row(fixture,'inv-tide');assert.equal(r.roundCount,1);assert.equal(r.rejected.length,1);assert.equal(r.accepted[0].event.roundId,'round-kite-seed-2026');});
test('source date missing, invalid, future or preceding event cannot support lead',()=>{for(const date of [null,'2026-02-30','2027-01-01','2026-08-01']){const d=clone();d.events[0].source.publishedAt=date;assert.equal(row(d).eligible,false,date);}});
test('event date must be valid and within the window',()=>{for(const date of [null,'2026-02-30','2027-01-01','2020-01-01']){const d=clone();d.events[0].eventDate=date;assert.equal(row(d).eligible,false,date);}});
test('missing economic round or unknown issuer is not guessed',()=>{for(const patch of [{roundId:null},{issuerId:'unknown'}]){const d=clone();Object.assign(d.events[0],patch);assert.equal(row(d).eligible,false);}});
test('source URL and entity URL cannot inject javascript or embedded credentials',()=>{assert.equal(safeURL('javascript:alert(1)'),null);assert.equal(safeURL('https://user:pass@example.invalid'),null);const d=clone();d.events[0].source.url='javascript:alert(1)';assert.equal(row(d).eligible,false);});
test('goal filters are functional and invalid date windows fail closed',()=>{assert.equal(rank(fixture,{...DEFAULT_GOAL,sector:'Health software'}).filter(r=>r.eligible).length,0);assert.throws(()=>validateGoal({...DEFAULT_GOAL,from:'2026-12-01'},fixture.asOf));assert.throws(()=>validateGoal({...DEFAULT_GOAL,to:'2028-01-01'},fixture.asOf));});
test('prototype pollution and extra goal fields rejected without mutation',()=>{assert.throws(()=>validateGoal(JSON.parse('{"__proto__":{"polluted":true}}'),fixture.asOf));assert.throws(()=>validateGoal({...DEFAULT_GOAL,apiKey:'fake'},fixture.asOf));assert.equal({}.polluted,undefined);});
test('XSS text escaped and downloaded JSON safe if embedded elsewhere',()=>{const payload='<img src=x onerror="alert(1)">&';assert.ok(!escapeHTML(payload).includes('<'));const json=safeJSON({note:payload});assert.ok(!json.includes('<'));assert.equal(JSON.parse(json).note,payload);});
test('export requires human approval; no unresolved, duplicate or oversized entries',()=>{for(const reviews of [[],[{id:'inv-larch',note:'',approved:false}],[{id:'inv-echo',note:'',approved:true}],[{id:'inv-larch',note:'x'.repeat(2001),approved:true}],[{id:'inv-larch',note:'',approved:true},{id:'inv-larch',note:'',approved:true}]])assert.throws(()=>makeArtifact(fixture,DEFAULT_GOAL,reviews));});
test('approved export preserves exact citations, IDs, goal and review state',()=>{const a=makeArtifact(fixture,DEFAULT_GOAL,[{id:'inv-larch',note:'Reviewed both records',approved:true}]);assert.equal(a.shortlist[0].rounds[0].citations[0].url,fixture.events[0].source.url);assert.equal(a.shortlist[0].humanReview.state,'APPROVED_BY_LOCAL_USER');assert.equal(a.mode,'FICTIONAL_FIXTURE');assert.equal(a.autoSend,false);});
test('provider refuses even caller-asserted authority; no network or secret lookup',async()=>{const old=globalThis.fetch;globalThis.fetch=()=>{throw Error('network forbidden');};try{assert.equal((await requestCala({hostVerified:true,apiKey:'fake'})).status,'REFUSED');assert.deepEqual(CALA_CONTRACT.sequence,['entity_search/entity_lookup','entity_introspection','entity_retrieval']);assert.equal(CALA_CONTRACT.limits.timeoutMs,5000);}finally{globalThis.fetch=old;}});
test('application contains no outbound API, secret access, auto-send or storage',async()=>{for(const path of ['../public/app.mjs','../core.mjs','../fixture.mjs','../cala-contract.mjs']){const s=await readFile(new URL(path,import.meta.url),'utf8');assert.doesNotMatch(s,/\bfetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|localStorage|process\.env|readFile|https\.request/);}const server=await readFile(new URL('../server.mjs',import.meta.url),'utf8');assert.match(server,/listen\(port,'127\.0\.0\.1'/);});

test('issuer records remain visible as context without adding investor rounds',()=>{const r=row(fixture);assert.equal(r.issuerRecords[0].role,'ISSUER');assert.equal(r.roundCount,1);assert.ok(r.reasons.some(s=>s.includes('ISSUER')));});

test('export provenance matches current canonical product bytes, not a product Git SHA',async()=>{
 const { computeSourceDigest } = await import('../build.mjs');
 const a=makeArtifact(fixture,DEFAULT_GOAL,[{id:'inv-larch',note:'',approved:true}]);
 assert.equal(a.baseSourceSha,'a33f525171b6424d39dfc4c889b63e0fc5cb459e');
 assert.equal(Object.hasOwn(a,'sourceSha'),false);
 assert.equal(a.productSourceDigest,await computeSourceDigest());
});
test('canonical manifest is independently reproducible and any covered source edit fails build verification',async()=>{
 const { mkdtemp, mkdir, writeFile, rm }=await import('node:fs/promises');
 const { tmpdir }=await import('node:os');
 const { pathToFileURL }=await import('node:url');
 const { createHash }=await import('node:crypto');
 const { PRODUCT_SOURCE_FILES, verifySourceDigest }=await import('../build.mjs');
 const expected=['cala-contract.d.ts','cala-contract.mjs','core.mjs','fixture.mjs','public/app.mjs','public/index.html','public/style.css','server.mjs','workspace/restore.mjs'];
 assert.deepEqual(PRODUCT_SOURCE_FILES,expected);
 const dir=await mkdtemp(`${tmpdir()}/cala-provenance-`), root=pathToFileURL(`${dir}/`);
 try {
  await mkdir(new URL('public/',root));
  await mkdir(new URL('workspace/',root));
  let manifest='';
  for(const path of expected){const bytes=await readFile(new URL(`../${path}`,import.meta.url));await writeFile(new URL(path,root),bytes);manifest+=path+'\0'+createHash('sha256').update(bytes).digest('hex')+'\n';}
  assert.equal(await verifySourceDigest(root),createHash('sha256').update(manifest,'utf8').digest('hex'));
  for(const path of expected){const target=new URL(path,root),bytes=await readFile(target);await writeFile(target,Buffer.concat([bytes,Buffer.from('\n')]));await assert.rejects(verifySourceDigest(root),/Stale productSourceDigest/);await writeFile(target,bytes);}
 } finally {await rm(dir,{recursive:true,force:true});}
});
