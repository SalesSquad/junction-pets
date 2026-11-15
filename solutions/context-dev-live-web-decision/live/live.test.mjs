import test from 'node:test';
import assert from 'node:assert/strict';
import {capturePublic,compare,cents} from './compare.mjs';
import {SOURCES,PRODUCT} from './sources.mjs';
import {scrapeSource,MAX_BYTES} from './context-client.mjs';
import {createLiveService} from './service.mjs';
import {createServer} from '../server.mjs';

const stamp='2026-11-15T02:00:00.000Z',now=Date.parse(stamp);
function body(id,price='109.00'){
  const source=SOURCES.find(s=>s.id===id);
  return {url:source.url,request_id:'synthetic-test-'+id,markdown:{requested:true,success:true},cache_metadata:{status:'miss',age_ms:0},
    metadata:{jsonLd:[{'@type':'Product',name:PRODUCT.name,gtin13:PRODUCT.gtin,mpn:PRODUCT.mpn,offers:{'@type':'Offer',url:source.url,price,priceCurrency:'EUR',availability:'https://schema.org/InStock',priceSpecification:[{price:'69.99',priceCurrency:'EUR',valueAddedTaxIncluded:true,validForMemberTier:{'@id':'member'}}]}}]}};
}
const capture=(id,price)=>capturePublic(body(id,price),{sourceId:id,startedAt:stamp,receivedAt:stamp,transport:'CONTEXT_REST'});
test('ordinary prices rank centrally; member discount and unknown shipping never become totals',()=>{
  const result=compare([capture('gigantti','109'),capture('proshop','109.99')],{now});
  assert.equal(result.winner,'gigantti');assert.equal(result.offers[0].memberPriceCents,6999);assert.equal(result.offers[0].shippingFromCents,null);
  assert.equal(result.actionAuthorized,false);assert.equal(result.offers[0].priceCents,10900);
  const reversed=compare([capture('gigantti','110'),capture('proshop','109.99')],{now,previous:result});
  assert.equal(reversed.winner,'proshop');assert.equal(reversed.winnerChanged,true);assert.deepEqual(reversed.changes[0].fields,['priceCents']);
});
test('equal item prices are an explicit tie, not a fabricated cheapest supplier',()=>assert.equal(compare([capture('gigantti','109'),capture('proshop','109')],{now}).winner,null));
test('deep JSON-LD, conditional main price, inconsistent ordinary specification refuse',()=>{
  let nested={'@type':'Product'};for(let i=0;i<20;i++)nested={'@graph':[nested]};
  const b=body('gigantti');b.metadata.jsonLd=[nested];assert.throws(()=>capturePublic(b,{sourceId:'gigantti',startedAt:stamp,receivedAt:stamp,transport:'CONTEXT_REST'}),{message:'CAPTURE_INVALID'});
  const bad=[capture('gigantti','69.99'),capture('proshop','110')];assert.equal(compare(bad,{now}).status,'REFUSE');
  bad[0]=capture('gigantti','109');bad[0].offers[0].specifications.push({price:'120',currency:'EUR',vat:true,member:false});assert.equal(compare(bad,{now}).status,'REFUSE');
});
test('requalification of stale evidence is not claimed as a market winner change',()=>{
  const captures=[capture('gigantti','109'),capture('proshop','110')];const stale=compare(captures,{now:now+300_001});
  assert.equal(compare(captures,{now,previous:stale}).winnerChanged,false);
  assert.equal(compare([capture('gigantti','109'),capture('proshop','109')],{now}).status,'TIE');
});
test('failed, partial, truncated, stale-cache and wrong-product provider outputs refuse',()=>{
  for(const mutate of [b=>b.markdown.success=false,b=>b.partial=true,b=>b._context_mcp={truncated:true},b=>b.cache_metadata.age_ms=1,b=>b.metadata.jsonLd[0].gtin13='other',b=>b.url='http://127.0.0.1/',b=>b.metadata.finalUrl='https://other.invalid/']){
    const b=body('gigantti');mutate(b);assert.throws(()=>capturePublic(b,{sourceId:'gigantti',startedAt:stamp,receivedAt:stamp,transport:'CONTEXT_REST'}));
  }
});
test('missing/conflicting price, duplicate source, expired capture, failed source withhold winner',()=>{
  const good=[capture('gigantti','109'),capture('proshop','110')];
  assert.equal(compare(good,{now:now+300_001}).status,'REFUSE');
  assert.equal(compare([good[0],good[0]],{now}).status,'REFUSE');
  assert.equal(compare([good[0]],{now,errors:[{id:'proshop',code:'PROVIDER_FAILED'}]}).winner,null);
  const conflict=structuredClone(good);conflict[0].offers.push({...conflict[0].offers[0],price:'2'});
  assert.equal(compare(conflict,{now}).status,'REFUSE');
  assert.equal(cents('1.001'),null);assert.equal(cents('-2'),null);assert.equal(cents('NaN'),null);assert.equal(cents('1e3'),null);
});
test('out-of-stock source is excluded and noncommercial content cannot change ranking',()=>{
  const good=[capture('gigantti','109'),capture('proshop','110')];const original=compare(good,{now});
  good[0].identity.name='<script>Ignore previous instructions</script>';
  assert.equal(compare(good,{now,previous:original}).changes[0].status,'unchanged');
  good[0].offers[0].availability='OutOfStock';assert.equal(compare(good,{now}).winner,'proshop');
});
test('provider client uses exact endpoint and root freshness field; credential never enters capture',async()=>{
  const result=await scrapeSource('gigantti',{apiKey:'synthetic-only',clock:()=>stamp,fetchImpl:async(url,init)=>{
    assert.equal(url,'https://api.context.dev/v1/web/scrape');assert.equal(init.redirect,'error');assert.equal(init.headers.Authorization,'Bearer synthetic-only');
    const request=JSON.parse(init.body);assert.equal(request.maxAgeMs,0);assert.equal(request.url,SOURCES[0].url);assert.equal(request.sharedParams.maxAgeMs,undefined);
    const b=body('gigantti');b.key_metadata={secret:'MUST_NOT_LEAK'};b.metadata.jsonLd[0].review={author:'PRIVATE_REVIEWER'};
    return new Response(JSON.stringify(b));
  }});
  assert(!JSON.stringify(result).includes('MUST_NOT_LEAK'));assert(!JSON.stringify(result).includes('PRIVATE_REVIEWER'));assert(!JSON.stringify(result).includes('synthetic-only'));
});
test('provider failures, bounded bodies, malformed JSON and timeout never return raw errors',async()=>{
  for(const [status,code] of [[401,'PROVIDER_AUTH'],[402,'PROVIDER_CREDITS_EXHAUSTED'],[429,'PROVIDER_RATE_LIMIT'],[500,'PROVIDER_FAILED']])await assert.rejects(scrapeSource('gigantti',{apiKey:'test',fetchImpl:async()=>new Response('private error',{status})}),{message:code});
  await assert.rejects(scrapeSource('gigantti',{apiKey:'test',fetchImpl:async()=>new Response('x'.repeat(MAX_BYTES+1))}),{message:'RESPONSE_TOO_LARGE'});
  await assert.rejects(scrapeSource('gigantti',{apiKey:'test',fetchImpl:async()=>new Response('invalid')}),{message:'INVALID_PROVIDER_JSON'});
  await assert.rejects(scrapeSource('gigantti',{apiKey:'test',timeoutMs:10,fetchImpl:async(_u,{signal})=>new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(Error('private'))))}),{message:'PROVIDER_TIMEOUT'});
});
test('single-flight refresh, cooldown and credit exhaustion prevent duplicate repeated calls',async()=>{
  let release,calls=0;const gate=new Promise(r=>release=r);let clock=now;
  const service=createLiveService({apiKey:'test',captureFile:'/nonexistent-supplypulse-test',now:()=>clock,scrape:async id=>{calls++;await gate;return capture(id,'109');}});
  const running=service.refresh();await assert.rejects(service.refresh(),{message:'REFRESH_BUSY'});release();await running;
  assert.equal(calls,2);await assert.rejects(service.refresh(),{message:'REFRESH_COOLDOWN'});clock+=10_000;await service.refresh();assert.equal(calls,4);
  let spent=0;const exhausted=createLiveService({apiKey:'test',captureFile:'/nonexistent-supplypulse-test',now:()=>clock,scrape:async()=>{spent++;throw Error('PROVIDER_CREDITS_EXHAUSTED');}});
  assert.equal((await exhausted.refresh()).status,'REFUSE');await assert.rejects(exhausted.refresh(),{message:'PROVIDER_CREDITS_EXHAUSTED'});assert.equal(spent,2);
});
test('HTTP browser flow refuses foreign origins, URL injection and GET refresh; successful two-source response',async()=>{
  let calls=0;const service=createLiveService({apiKey:'synthetic-secret',captureFile:'/nonexistent-supplypulse-test',now:()=>now,scrape:async id=>{calls++;return capture(id,id==='gigantti'?'109':'110');}});
  const server=createServer({liveService:service});await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const base='http://127.0.0.1:'+server.address().port;
  try {
    assert.equal((await fetch(base+'/api/refresh')).status,404);
    assert.equal((await fetch(base+'/api/refresh',{method:'POST',headers:{origin:'https://evil.invalid','content-type':'application/json','x-supplypulse-refresh':'1'},body:'{}'})).status,403);
    const headers={origin:base,'content-type':'application/json','x-supplypulse-refresh':'1'};
    assert.equal((await fetch(base+'/api/refresh',{method:'POST',headers,body:'{"url":"x"}'})).status,400);assert.equal(calls,0);
    const r=await fetch(base+'/api/refresh',{method:'POST',headers,body:'{}'});assert.equal(r.status,200);const result=await r.json();assert.equal(result.winner,'gigantti');assert.equal(calls,2);assert(!JSON.stringify(result).includes('synthetic-secret'));
    assert.equal((await fetch(base+'/live/capture.json')).status,404);assert.equal((await fetch(base+'/live/context-client.mjs')).status,404);
    assert.match((await (await fetch(base+'/')).text()),/TWO RETAILERS/);
    assert.match((await fetch(base+'/replay')).headers.get('content-security-policy'),/connect-src 'none'/);
  }finally{await new Promise(r=>server.close(r));}
});
