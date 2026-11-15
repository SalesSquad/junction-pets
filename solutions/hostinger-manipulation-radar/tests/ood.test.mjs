import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {corpus,SEEDS,FAMILIES,random32} from '../stress/ood.mjs';
import {report,aggregate,proportion,metrics,hash,baseline} from '../stress/report.mjs';
import {analyze,validate,POLICY} from '../public/detector.mjs';
import {createServer} from '../server.mjs';
const audit=report();
test('OOD uses deterministic uint32 PRNG, identical seeds repeat and separate seeds differ',()=>{
 assert.deepEqual(corpus([SEEDS[0]]),corpus([SEEDS[0]]));
 const sets=SEEDS.map(seed=>corpus([seed]));assert.equal(new Set(sets.map(s=>hash(JSON.stringify(s.cases)))).size,8);
 assert.equal(new Set(sets.flatMap(s=>s.cases.map(c=>c.id))).size,512);
 assert.equal(random32(12011)(),random32(12011)());assert.throws(()=>corpus([1,1]),/distinct/);assert.throws(()=>corpus([-1]),/uint32/);
});
test('five predeclared cohorts vary bounded observations without importing the M2 generator',async()=>{
 const {cases,labels}=corpus();assert.equal(cases.length,512);assert.equal(FAMILIES.length,5);
 for(const family of FAMILIES){const subset=cases.filter(c=>c.family===family.id);assert.equal(subset.length,family.count*8);assert.ok(subset.every(c=>labels[c.id].harmful===family.harmful&&labels[c.id].stipulation.length>20));}
 for(const path of ['ood.mjs','report.mjs']){const source=await readFile(new URL(`../stress/${path}`,import.meta.url),'utf8');const imports=[...source.matchAll(/from\s+['"]([^'"]+)/g)].map(m=>m[1]);assert.ok(imports.every(i=>i.startsWith('node:')||['./ood.mjs','../public/detector.mjs'].includes(i)),path);assert.ok(!/Math\.random\(|fetch\(|writeFile|exec\(/.test(source));}
 const fields=cases.flatMap(c=>c.events);assert.ok(new Set(fields.map(e=>e.accountAgeDays)).size>50);assert.ok(new Set(fields.map(e=>e.text)).size>50);assert.ok(new Set(fields.map(e=>e.url)).size>50);assert.ok(new Set(cases.map(c=>c.events.length)).size>5);
 assert.ok(cases.some(c=>Date.parse(c.events[1].time)-Date.parse(c.events[0].time)>60000));assert.ok(cases.some(c=>Date.parse(c.events[1].time)-Date.parse(c.events[0].time)<10000));
 for(const c of cases){assert.equal(validate(c.events).length,c.events.length);assert.ok(c.events.every(e=>Object.keys(e).sort().join(',')==='account,accountAgeDays,amplifies,attribution,id,text,time,url'));}
});
test('truth stays outside events and detector policy bytes/gates remain exactly M2',async()=>{
 assert.equal(hash(await readFile(new URL('../public/detector.mjs',import.meta.url))),'f3050adf27f4a588e81cb0ba75e020a05d91fae54af1c7f8b6479eec48dc7455');
 assert.equal(POLICY.threshold,65);assert.equal(POLICY.windowSeconds,60);assert.ok(Object.isFrozen(POLICY));
 const c=corpus([SEEDS[0]]).cases[1],before=analyze(c.events);
 assert.deepEqual(analyze(c.events.map(e=>({...e,truth:true,label:'harmful',stipulation:'poison'}))),before);
 assert.deepEqual(analyze(c.events.map(e=>({...e,truth:false,label:'benign'}))),before);
 assert.ok(!analyze(c.events,{omit:['timing']}).findings.some(f=>f.review));
 const source=await readFile(new URL('../stress/report.mjs',import.meta.url),'utf8');assert.ok(source.includes('analyze(c.events)'));
});
test('exact confusion denominators, null rates and independently known Wilson endpoints',async()=>{
 assert.deepEqual(metrics([]).falsePositiveRate,{numerator:0,denominator:0,value:null,wilson95:null});
 const known=proportion(1,2);assert.ok(Math.abs(known.wilson95.low-0.0945312057342307)<1e-12);assert.ok(Math.abs(known.wilson95.high-0.9054687942657693)<1e-12);
 assert.equal(proportion(0,10).wilson95.low,0);assert.equal(proportion(10,10).wilson95.high,1);assert.throws(()=>proportion(2,1));
 const r=await audit;assert.deepEqual([r.radar.tp,r.radar.fp,r.radar.tn,r.radar.fn],[45,70,250,147]);assert.deepEqual([r.baseline.tp,r.baseline.fp,r.baseline.tn,r.baseline.fn],[90,173,147,102]);
 assert.equal(r.radar.falsePositiveRate.numerator,70);assert.equal(r.radar.falsePositiveRate.denominator,320);assert.equal(r.radar.precision.denominator,115);assert.equal(r.radar.recall.denominator,192);
 for(const c of [r,...r.cohorts])for(const method of ['radar','baseline']){const m=c[method];assert.equal(m.tp+m.fp+m.tn+m.fn,c.cases);for(const key of ['precision','falsePositiveRate','recall']){const p=m[key];if(p.denominator)assert.ok(0<=p.wilson95.low&&p.wilson95.low<=p.value&&p.value<=p.wilson95.high&&p.wilson95.high<=1);else assert.equal(p.wilson95,null);}}
});
test('all errors retained with IDs, reasons, signal evidence and actionable counterevidence',async()=>{
 const r=await audit,{cases,labels}=corpus();assert.equal(r.errors.length,r.radar.fp+r.radar.fn);assert.equal(r.errors.length,217);
 const actualErrors=cases.filter(c=>analyze(c.events).findings.some(f=>f.review)!==labels[c.id].harmful).map(c=>c.id);assert.deepEqual(r.errors.map(e=>e.id),actualErrors);
 for(const e of r.errors){const c=cases.find(c=>c.id===e.id);assert.ok(e.reason.length>30&&e.counterevidence.length>30&&e.nextReviewerAction.length>30);assert.ok(e.signals.every(s=>s.eventIds.every(id=>c.events.some(event=>event.id===id))));}
 assert.equal(r.errorFamilies.find(f=>f.family==='evasive').falseNegatives,96);assert.equal(r.errorFamilies.find(f=>f.family==='volunteers').falsePositives,50);
 assert.equal(r.samples.length,40);for(const s of r.samples){const c=cases.find(c=>c.id===s.id);assert.equal(s.caseSHA256,hash(JSON.stringify(c)));assert.equal(s.labelSHA256,hash(JSON.stringify(labels[c.id])));}
 assert.equal(r.sources['public/detector.mjs'],hash(await readFile(new URL('../public/detector.mjs',import.meta.url))));assert.equal(r.sourceSHA256,hash(JSON.stringify(r.sources)));assert.equal(r.generatorSHA256,hash(await readFile(new URL('../stress/ood.mjs',import.meta.url))));
 assert.equal(baseline([{text:'URGENT community meeting'}]),true);assert.equal(baseline([{text:'one'},{text:'one'},{text:'one'}]),true);assert.equal(baseline([{text:'one'},{text:'two'}]),false);
});
test('cached aggregate and exact server allowlist expose no OOD cases or label maps, no socket',async()=>{
 const server=createServer();const request=(url,method='GET')=>new Promise(resolve=>server.emit('request',{url,method},{writeHead(status,headers){this.status=status;this.headers=headers;},end(body){resolve({status:this.status,headers:this.headers,body:body?.toString()||''});}}));
 for(const path of ['/stress/ood.mjs','/stress/report.mjs','/stress/labels.json','/fixtures/held-out.mjs','/fixtures/held-out-labels.json','/tests/ood.test.mjs','/%2e%2e/stress/ood.mjs','/api/benchmark?raw=true'])assert.equal((await request(path)).status,404,path);
 assert.equal((await request('/api/benchmark','POST')).status,405);assert.equal((await request('/api/benchmark','HEAD')).body,'');
 const response=await request('/api/benchmark');assert.equal(response.status,200);assert.ok(response.headers['Content-Security-Policy'].includes("connect-src 'self'"));
 const first=JSON.parse(response.body).robustness,second=JSON.parse((await request('/api/benchmark')).body).robustness;assert.deepEqual(first,second);assert.deepEqual(first,aggregate(await audit));
 assert.ok(!Object.hasOwn(first,'errors')&&!Object.hasOwn(first,'samples')&&!Object.hasOwn(first,'labels'));assert.ok(!response.body.includes('"events":')&&!response.body.includes('"stipulation":'));
});
