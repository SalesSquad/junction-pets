import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {WatchStore} from './store.mjs';
import {WatchService} from './service.mjs';
import {ContextClient} from './context.mjs';
import {nextOccurrence,onceInstant} from './schedule.mjs';
import {validateDefinition,productURL,problem} from './model.mjs';
import {offerFromResponse,detectChanges,executeWatch} from './engine.mjs';
import {createServer} from '../server.mjs';
const NOW=Date.parse('2026-11-15T06:00:00Z');
const URLS={gigantti:'https://www.gigantti.fi/product/computers/mouse/976944',proshop:'https://www.proshop.fi/Hiiret/Logitech-MX-Master-3S/3400336',verkkokauppa:'https://www.verkkokauppa.com/fi/product/999999/Logitech-MX-Master-3S'};
const definition=(patch={})=>validateDefinition({name:'Studio mouse',query:'Logitech MX Master 3S',gtin:'5099206129382',merchantIds:['gigantti','proshop'],schedule:{kind:'manual',timeZone:'Europe/Helsinki'},maxPriceCents:11000,...patch});
function response(url=URLS.gigantti,price='109.00'){
  return {operation:'scrape',requestId:'test-source-request',creditsConsumed:3,receivedAt:new Date(NOW).toISOString(),data:{url,request_id:'test-source-request',cache_metadata:{age_ms:0,status:'miss'},markdown:{success:true,data:'Logitech MX Master 3S. Price 109.00 EUR. Member price 99.99 EUR. In stock. New.'},product:{success:true,data:{isProductPage:true,product:{name:'Logitech MX Master 3S'}}},json:{success:true,data:{title:'Logitech MX Master 3S',gtin:'5099206129382',ordinaryPrice:price,memberPrice:null,currency:'EUR',stockStatus:'in_stock',condition:'new',shippingFrom:null,evidence:[],requirementsAssessment:''}},metadata:{jsonLd:[{'@type':'Product',name:'Logitech MX Master 3S',gtin13:'5099206129382',offers:{'@type':'Offer',url,price,priceCurrency:'EUR',availability:'https://schema.org/InStock',itemCondition:'https://schema.org/NewCondition'}}]}}};
}
class FakeClient {
  connected=true;calls=[];gate=null;fail=null;
  async result(operation,data,options){options.beforeCall();this.calls.push(operation);if(this.gate)await this.gate;if(options.signal?.aborted)throw problem('RUN_CANCELLED');if(this.fail)throw problem(this.fail);return {operation,data,requestId:'test-'+operation,creditsConsumed:1,receivedAt:new Date(NOW).toISOString()};}
  search(def,options){return this.result('search',{results:[{url:URLS.gigantti},{url:URLS.proshop},{url:'https://evil.invalid/x'}]},options);}
  map(domain,query,options){return this.result('map',{urls:[{url:URLS.gigantti}]},options);}
  scrape(url,requirements,options){return this.result('scrape',response(url).data,options);}
  research(def,options){return this.result('research',{json_content:{summary:'Review the cited product.'},sources:[URLS.gigantti,'https://evil.invalid/private']},options);}
}
test('selected local schedule, ISO weekdays and interval stay in the requested timezone',()=>{
  assert.equal(nextOccurrence({kind:'daily',time:'09:00',timeZone:'Europe/Helsinki'},NOW),'2026-11-15T07:00:00.000Z');
  assert.equal(nextOccurrence({kind:'weekly',time:'09:00',weekdays:[1],timeZone:'Europe/Helsinki'},NOW),'2026-11-16T07:00:00.000Z');
  assert.equal(nextOccurrence({kind:'interval',minutes:120,timeZone:'UTC'},NOW),'2026-11-15T08:00:00.000Z');
  assert.equal(nextOccurrence({kind:'daily',time:'09:00',timeZone:'Asia/Kathmandu'},Date.parse('2026-11-15T00:00:00Z')),'2026-11-15T03:15:00.000Z');
});
test('DST gap is skipped, ambiguous daily slot runs once, invalid once time refuses',()=>{
  assert.equal(nextOccurrence({kind:'daily',time:'03:30',timeZone:'Europe/Helsinki'},Date.parse('2026-03-29T00:00:00Z')),'2026-03-30T00:30:00.000Z');
  assert.throws(()=>onceInstant({kind:'once',at:'2026-03-29T03:30',timeZone:'Europe/Helsinki'}),{code:'INVALID_DATE_TIME'});
  assert.equal(nextOccurrence({kind:'daily',time:'03:30',timeZone:'Europe/Helsinki'},Date.parse('2026-10-25T00:31:00Z')),'2026-10-26T01:30:00.000Z');
  assert.equal(nextOccurrence({kind:'weekly',time:'03:30',weekdays:[7],timeZone:'Europe/Helsinki'},Date.parse('2026-03-23T00:00:00Z')),'2026-04-05T00:30:00.000Z');
});
test('definition rejects hidden capabilities, invalid zone, fractional cents and secret-like input',()=>{
  for(const patch of [{apiKey:'anything'},{schedule:{kind:'daily',time:'09:00',timeZone:'Not/AZone'}},{maxPriceCents:10.2},{query:'Bearer NEVER_REAL_SECRET'},{merchantIds:['unknown']},{schedule:{kind:'interval',minutes:1,timeZone:'UTC'}}])assert.throws(()=>definition(patch));
});
test('discovery URL validation fences private hosts, credentials, retailer auth paths and encoded traversal',()=>{
  for(const url of ['http://127.0.0.1/x','https://www.gigantti.fi@127.0.0.1/x','https://www.gigantti.fi:444/product/a/123','https://www.gigantti.fi/login','https://www.gigantti.fi/product/%2fprivate/123','https://evil.www.proshop.fi/Hiiret/a/123'])assert.equal(productURL(url,['gigantti','proshop']),null);
  assert.equal(productURL(URLS.gigantti+'?tracking=value#x',['gigantti']).url,URLS.gigantti);
});
test('actual-shape JSON-LD ordinary price drives filter; unknown shipping never becomes a delivered total',()=>{
  const offer=offerFromResponse(response(),URLS.gigantti,definition());assert.equal(offer.selectedPriceCents,10900);assert.equal(offer.meetsTarget,true);assert.equal(offer.shippingFromCents,null);
  assert.equal(offerFromResponse(response(),URLS.gigantti,definition({quantity:10})).meetsTarget,false);
  assert.equal(offerFromResponse(response(),URLS.gigantti,definition({requirements:'Must include a USB receiver'})).needsReview,true);
});
test('member price substring cannot turn 99.99 into a confirmed 9.99 offer',()=>{
  const raw=response();raw.data.json.data.memberPrice='9.99';raw.data.json.data.evidence=[{field:'memberPrice',quote:'Member price 99.99 EUR'}];
  const result=offerFromResponse(raw,URLS.gigantti,definition({includeMemberPrices:true,maxPriceCents:1000}));assert.equal(result.memberPriceCents,null);assert.equal(result.meetsTarget,false);
  raw.data.json.data.memberPrice='99.99';const verifiedQuote=offerFromResponse(raw,URLS.gigantti,definition({includeMemberPrices:true}));assert.equal(verifiedQuote.memberPriceCents,9999);assert.equal(verifiedQuote.needsReview,true);assert.equal(verifiedQuote.meetsTarget,false);
});
test('text-only new condition cannot qualify a like-new used product',()=>{
  const r=response();delete r.data.metadata.jsonLd[0].offers.itemCondition;r.data.markdown.data+=' Used item, like new';r.data.json.data.condition='new';r.data.json.data.evidence=[{field:'condition',quote:'Used item, like new'}];
  const offer=offerFromResponse(r,URLS.gigantti,definition());assert.equal(offer.needsReview,true);assert.equal(offer.meetsTarget,false);
});
test('wrong exact identity, conflicting prices, failed formats, stale cache and nonproduct pages refuse qualification',()=>{
  for(const mutate of [r=>r.data.metadata.jsonLd[0].gtin13='5099206103726',r=>r.data.markdown.success=false,r=>r.data.cache_metadata.age_ms=1,r=>r.data.product.data.isProductPage=false]){const raw=response();mutate(raw);assert.throws(()=>offerFromResponse(raw,URLS.gigantti,definition()));}
  const raw=response();raw.data.metadata.jsonLd[0].offers=[raw.data.metadata.jsonLd[0].offers,{...raw.data.metadata.jsonLd[0].offers,price:'5.00'}];assert.equal(offerFromResponse(raw,URLS.gigantti,definition()).meetsTarget,false);
});
test('durable create is idempotent, edits use CAS, pause/resume preserve evidence and archive is recoverable',()=>{
  const store=new WatchStore(':memory:');try{
    const def=definition(),token=randomUUID(),watch=store.create(def,token,NOW);assert.equal(store.create(def,token,NOW).id,watch.id);
    assert.throws(()=>store.create({...def,name:'Changed'},token,NOW),{code:'IDEMPOTENCY_CONFLICT'});
    const run=store.claim(watch.id,'manual','search',NOW);store.beforeRequest(run.id,NOW);store.finish(run.id,{summary:{offers:[{id:'offer'}],changes:[],headline:'one'}},NOW+1);
    const paused=store.action(watch.id,watch.revision,'pause',NOW+2);assert.equal(paused.lastSummary.offers.length,1);
    assert.throws(()=>store.update(watch.id,watch.revision,def,NOW+3),{code:'REVISION_CONFLICT'});
    const resumed=store.action(watch.id,paused.revision,'resume',NOW+4);const archived=store.action(watch.id,resumed.revision,'archive',NOW+5);assert.equal(store.detail(watch.id).runs.length,1);
    assert.equal(store.action(watch.id,archived.revision,'resume',NOW+6).status,'active');
  }finally{store.close();}
});
test('SQLite history and due schedules survive reopening without rerunning a completed once slot',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'supplypulse-watch-test-')),file=join(dir,'watches.sqlite');let store;
  try{store=new WatchStore(file);const w=store.create(definition({schedule:{kind:'once',at:'2026-11-15T09:00',timeZone:'Europe/Helsinki'}}),randomUUID(),NOW);store.close();store=new WatchStore(file);assert.deepEqual(store.due(NOW+3_600_000),[w.id]);const r=store.claim(w.id,'scheduled','search',NOW+3_600_000);store.finish(r.id,{summary:{offers:[],changes:[]}},NOW+3_600_001);store.close();store=new WatchStore(file);assert.deepEqual(store.due(NOW+10_000_000),[]);assert.equal(store.detail(w.id).runs.length,1);}
  finally{store?.close();await rm(dir,{recursive:true,force:true});}
});
test('two store connections cannot duplicate a running job or reset persisted request budget',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'supplypulse-watch-test-')),file=join(dir,'watches.sqlite');const first=new WatchStore(file,{dailyLimit:6}),second=new WatchStore(file,{dailyLimit:6});
  try{const w=first.create(definition(),randomUUID(),NOW),run=first.claim(w.id,'manual','search',NOW);assert.throws(()=>second.claim(w.id,'manual','search',NOW),{code:'RUN_BUSY'});first.beforeRequest(run.id,NOW);const w2=second.create(definition({name:'second'}),randomUUID(),NOW);assert.throws(()=>second.claim(w2.id,'manual','search',NOW),{code:'DAILY_REQUEST_LIMIT'});first.finish(run.id,{summary:{offers:[],changes:[]}},NOW+1);assert.equal(second.budget(NOW).dailyRequestsUsed,1);assert.equal(second.budget(NOW).dailyRequestsReserved,0);}
  finally{first.close();second.close();await rm(dir,{recursive:true,force:true});}
});
test('cancellation fences later requests and late results while retaining accounted submitted calls',()=>{
  const store=new WatchStore(':memory:');try{const w=store.create(definition(),randomUUID(),NOW),r=store.claim(w.id,'manual','search',NOW);store.beforeRequest(r.id,NOW);store.action(w.id,w.revision,'pause',NOW+1);assert.throws(()=>store.beforeRequest(r.id,NOW),{code:'RUN_CANCELLED'});assert.equal(store.finish(r.id,{summary:{offers:[{id:'stale'}],changes:[]}},NOW+2),false);assert.equal(store.get(w.id).lastSummary,null);assert.equal(store.budget(NOW).dailyRequestsUsed,1);assert.equal(store.budget(NOW).dailyRequestsReserved,0);}finally{store.close();}
});
test('a run crossing UTC midnight cannot submit unreserved requests against yesterday',()=>{
  const store=new WatchStore(':memory:',{dailyLimit:6});try{const before=Date.parse('2026-11-15T23:59:59Z'),after=Date.parse('2026-11-16T00:00:01Z');const w=store.create(definition(),randomUUID(),before),r=store.claim(w.id,'manual','search',before);store.beforeRequest(r.id,before);assert.throws(()=>store.beforeRequest(r.id,after),{code:'RUN_DAY_CHANGED'});store.finish(r.id,{errorCode:'RUN_DAY_CHANGED'},after);assert.equal(store.budget(before).dailyRequestsUsed,1);assert.equal(store.budget(before).dailyRequestsReserved,0);assert.equal(store.budget(after).dailyRequestsUsed,0);}finally{store.close();}
});
test('a stale running row cannot starve a later watch and lowering run limit pauses scheduling',async()=>{
  let clock=NOW;const store=new WatchStore(':memory:'),client=new FakeClient(),service=new WatchService({store,client,now:()=>clock});
  try{const first=service.create(definition({schedule:{kind:'daily',time:'09:00',timeZone:'Europe/Helsinki'}}),randomUUID());store.claim(first.id,'scheduled','search',NOW+3_600_000);clock=Date.parse('2026-11-16T07:30:00Z');const second=service.create(definition({name:'second',schedule:{kind:'daily',time:'10:00',timeZone:'Europe/Helsinki'}}),randomUUID());clock=Date.parse('2026-11-16T08:00:00Z');await service.tick();await service.settle();assert.equal(store.detail(second.id).runs.length,1);assert.equal(client.calls.filter(x=>x==='search').length,1);
    const revision=store.get(second.id).revision;const edited=service.update(second.id,revision,definition({name:'second',maxRuns:1,schedule:{kind:'daily',time:'10:00',timeZone:'Europe/Helsinki'}}));assert.equal(edited.status,'paused');assert.equal(edited.nextRunAt,null);
  }finally{await service.close();}
});
test('scheduled wake-up consumes one overdue slot then retains next chosen local time',async()=>{
  let clock=NOW;const store=new WatchStore(':memory:'),client=new FakeClient(),service=new WatchService({store,client,now:()=>clock});
  try{const w=service.create(definition({schedule:{kind:'daily',time:'09:00',timeZone:'Europe/Helsinki'}}),randomUUID());clock=Date.parse('2026-11-18T10:00:00Z');await service.tick();await service.settle();await service.tick();assert.equal(store.detail(w.id).runs.length,1);assert.equal(store.get(w.id).nextRunAt,'2026-11-19T07:00:00.000Z');assert.equal(client.calls.filter(v=>v==='search').length,1);}
  finally{await service.close();}
});
test('search + mapping + structured product extraction produces real changes, not layout changes',async()=>{
  const client=new FakeClient(),claim={definition:definition({expandCatalog:true}),kind:'search',previous:null};let calls=0;
  const first=await executeWatch(claim,{client,beforeCall:()=>calls++,signal:new AbortController().signal});assert.equal(first.summary.offers.length,2);assert.deepEqual(client.calls,['search','map','scrape','scrape']);assert.equal(calls,4);
  assert.equal(detectChanges(first.summary.offers,first.summary).length,0);
  const changed=structuredClone(first.summary.offers);changed[0].selectedPriceCents=9000;assert(detectChanges(changed,first.summary).some(c=>c.type==='price_drop'));
});
test('search auth/credits failure pauses all schedules without automatic retry',async()=>{
  const store=new WatchStore(':memory:'),client=new FakeClient(),service=new WatchService({store,client,now:()=>NOW});client.fail='PROVIDER_CREDITS_EXHAUSTED';
  try{const w=service.create(definition(),randomUUID());service.create(definition({name:'second'}),randomUUID());service.start(w.id);await service.settle();assert.equal(client.calls.length,1);assert(store.list().every(w=>w.status==='paused'));await service.tick();assert.equal(client.calls.length,1);assert.equal(store.detail(w.id).runs[0].errorCode,'PROVIDER_CREDITS_EXHAUSTED');
    for(const kind of ['search','research'])assert.throws(()=>service.start(w.id,{kind}),{code:'PROVIDER_CREDITS_EXHAUSTED'});
    assert.equal(store.get(w.id).runCount,1);assert.equal(store.budget(NOW).dailyRequestsUsed,1);
    client.fail=null;service.action(w.id,store.get(w.id).revision,'resume');service.start(w.id);await service.settle();assert.equal(store.get(w.id).runCount,2);assert.equal(store.detail(w.id).runs[0].status,'completed');}
  finally{await service.close();}
});
test('provider client uses only fixed endpoints and never persists credential/account metadata',async()=>{
  let called=0;const client=new ContextClient({apiKey:'synthetic-credential',fetchImpl:async(url,init)=>{called++;assert.equal(new URL(url).origin,'https://api.context.dev');assert.equal(init.redirect,'error');assert.equal(init.headers.Authorization,'Bearer synthetic-credential');return new Response(JSON.stringify({request_id:'test-request',results:[],key_metadata:{credits_consumed:1,credits_remaining:999}}));}});
  let reserved=0;const r=await client.search(definition(),{beforeCall:()=>reserved++});assert.equal(called,1);assert.equal(reserved,1);assert.equal(r.creditsConsumed,1);
  await assert.rejects(client.call('arbitrary',{url:'http://127.0.0.1/'},{}),{code:'INVALID_REQUEST'});assert.equal(called,1);
});
test('maximum-length saved preferences fit the documented Answers task limit without truncation',async()=>{
  let task;const client=new ContextClient({apiKey:'test',fetchImpl:async(_url,init)=>{task=JSON.parse(init.body).task;return new Response(JSON.stringify({request_id:'research-test',json_content:{summary:'test'},sources:[]}));}});
  const def=definition({query:'x'.repeat(300),requirements:'y'.repeat(1500),gtin:'12345678901234',quantity:100,merchantIds:['gigantti','proshop','verkkokauppa'],maxPriceCents:100_000_000});await client.research(def,{});assert(task.length<=2000);assert(task.includes(def.query));assert(task.includes(def.requirements));assert(task.includes(def.gtin));assert(task.includes('qty:100'));assert(task.includes('member:false'));
});
test('HTTP watch creation, explicit run, pause CAS, private routes and foreign-origin denial',async()=>{
  const store=new WatchStore(':memory:'),service=new WatchService({store,client:new FakeClient(),now:()=>NOW}),server=createServer({watchService:service});
  await new Promise((r,j)=>{server.once('error',j);server.listen(0,'127.0.0.1',r);});const base='http://127.0.0.1:'+server.address().port,headers={origin:base,'content-type':'application/json','x-supplypulse-refresh':'1'};
  try{const body=JSON.stringify({definition:definition(),idempotencyKey:randomUUID()});assert.equal((await fetch(base+'/api/watches',{method:'POST',headers:{...headers,origin:'https://other.invalid'},body})).status,403);
    const response=await fetch(base+'/api/watches',{method:'POST',headers,body});assert.equal(response.status,201);const {watch}=await response.json();assert.equal(store.detail(watch.id).runs.length,0);
    assert.equal((await fetch(base+'/api/watches/'+watch.id+'/run',{method:'POST',headers,body:'{}'})).status,202);await service.settle();assert.equal((await (await fetch(base+'/api/watches/'+watch.id)).json()).runs[0].status,'completed');
    assert.equal((await fetch(base+'/api/watches/'+watch.id+'/pause',{method:'POST',headers,body:JSON.stringify({revision:99})})).status,409);
    for(const path of ['/watch/store.mjs','/watches.sqlite','/watches/../README.md','/api/watches?export=all'])assert.equal((await fetch(base+path)).status,404);
    assert.match(await (await fetch(base+'/watches/')).text(),/YOUR WISH/);
  }finally{await service.settle();await new Promise(r=>server.close(r));await service.close();}
});
