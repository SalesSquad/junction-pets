import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchRetailerNews,newsPublic,riskFlags,NEWS_MAX_BYTES,NEWS_WINDOW_MS,NEWS_LIMIT} from './news-client.mjs';
import {capturePublic} from './compare.mjs';
import {SOURCES,PRODUCT} from './sources.mjs';
import {createLiveService} from './service.mjs';
import {createServer} from '../server.mjs';

// Synthetic transport only: shapes follow https://docs.context.dev/api-reference/news/search.md
const stamp='2026-11-15T02:00:00.000Z',now=Date.parse(stamp);
const article=(title,extra={})=>({id:'a-'+title.length,story_id:'s1',url:'https://news.example.fi/'+encodeURIComponent(title),title,description:null,language:'fi',authors:['PRIVATE_AUTHOR'],image_url:'https://img.example/x.jpg',published_at:'2026-11-10T08:00:00Z',type:'editorial',source:{name:'Example News',domain:'news.example.fi',direct:true},match:{level:'primary',confidence:0.9},...extra});
const envelope=(data,id='synthetic-news')=>({data,has_more:false,next_cursor:null,meta:{count:data.length},key_metadata:{credits_consumed:1,credits_remaining:42,secret:'MUST_NOT_LEAK'},request_id:id});
function scrapeBody(id,price){
  const source=SOURCES.find(s=>s.id===id);
  return {url:source.url,request_id:'synthetic-test-'+id,markdown:{requested:true,success:true},cache_metadata:{status:'miss',age_ms:0},
    metadata:{jsonLd:[{'@type':'Product',name:PRODUCT.name,gtin13:PRODUCT.gtin,mpn:PRODUCT.mpn,offers:{'@type':'Offer',url:source.url,price,priceCurrency:'EUR',availability:'https://schema.org/InStock'}}]}};
}
const capture=(id,price)=>capturePublic(scrapeBody(id,price),{sourceId:id,startedAt:stamp,receivedAt:stamp,transport:'CONTEXT_REST'});

test('news client: exact documented endpoint, pinned domain entity search, reduced public output',async()=>{
  const result=await fetchRetailerNews('gigantti',{apiKey:'synthetic-only',clock:()=>stamp,now:()=>now,fetchImpl:async(url,init)=>{
    assert.equal(url,'https://api.context.dev/v1/news/search');assert.equal(init.method,'POST');assert.equal(init.redirect,'error');assert.equal(init.headers.Authorization,'Bearer synthetic-only');
    assert.deepEqual(JSON.parse(init.body),{searchBy:{type:'entity',entity:{type:'domain',domain:'gigantti.fi'}},filterBy:{date:{from:now-NEWS_WINDOW_MS}},sortBy:{type:'newest'},limit:NEWS_LIMIT});
    return new Response(JSON.stringify(envelope([article('Gigantti aloittaa muutosneuvottelut'),article('Uusi myymälä avataan'),article('Konkurssi naapurissa',{match:{level:'secondary',confidence:0.3}}),{title:'no url'},article('Insecure',{url:'http://x.invalid/'})])));
  }});
  assert.equal(result.status,'REVIEW_NEWS');assert.equal(result.flaggedCount,1);assert.deepEqual(result.flags,['layoffs']);
  assert.equal(result.articles.length,3);assert.equal(result.requestId,'synthetic-news');assert.equal(result.receivedAt,stamp);
  const text=JSON.stringify(result);for(const secret of ['MUST_NOT_LEAK','synthetic-only','PRIVATE_AUTHOR','img.example'])assert(!text.includes(secret));
});
test('news client: no key never calls the provider',async()=>{
  let calls=0;await assert.rejects(fetchRetailerNews('proshop',{apiKey:'',fetchImpl:async()=>{calls++;}}),{message:'CONNECTION_REQUIRED'});
  await assert.rejects(fetchRetailerNews('proshop',{fetchImpl:async()=>{calls++;}}),{message:'CONNECTION_REQUIRED'});
  await assert.rejects(fetchRetailerNews('evil.invalid',{apiKey:'x',fetchImpl:async()=>{calls++;}}),{message:'SOURCE_NOT_ALLOWED'});
  assert.equal(calls,0);
});
test('news client: provider errors, unknown company, oversize, bad schema and timeout map to safe codes',async()=>{
  for(const [status,code] of [[401,'PROVIDER_AUTH'],[402,'PROVIDER_CREDITS_EXHAUSTED'],[429,'PROVIDER_RATE_LIMIT'],[400,'PROVIDER_FAILED'],[500,'PROVIDER_FAILED']])
    await assert.rejects(fetchRetailerNews('gigantti',{apiKey:'t',fetchImpl:async()=>new Response('private provider detail',{status})}),{message:code});
  const unknown=await fetchRetailerNews('proshop',{apiKey:'t',clock:()=>stamp,fetchImpl:async()=>new Response('{"error":"not found"}',{status:404})});
  assert.equal(unknown.status,'NO_COVERAGE');assert.deepEqual(unknown.articles,[]);
  await assert.rejects(fetchRetailerNews('gigantti',{apiKey:'t',fetchImpl:async()=>new Response('x'.repeat(NEWS_MAX_BYTES+1))}),{message:'RESPONSE_TOO_LARGE'});
  await assert.rejects(fetchRetailerNews('gigantti',{apiKey:'t',fetchImpl:async()=>new Response('nope')}),{message:'INVALID_PROVIDER_JSON'});
  await assert.rejects(fetchRetailerNews('gigantti',{apiKey:'t',fetchImpl:async()=>new Response('{"data":[],"request_id":"x"}')}),{message:'NEWS_SCHEMA'});
  await assert.rejects(fetchRetailerNews('gigantti',{apiKey:'t',timeoutMs:10,fetchImpl:async(_u,{signal})=>new Promise((_r,reject)=>signal.addEventListener('abort',()=>reject(Error('private'))))}),{message:'PROVIDER_TIMEOUT'});
});
test('risk vocabulary and empty news',()=>{
  assert.deepEqual(riskFlags('Retailer files for bankruptcy after data breach'),['insolvency','data breach']);
  assert.deepEqual(riskFlags('Black Friday deals on mice'),[]);
  assert.equal(newsPublic(envelope([]),{sourceId:'proshop',receivedAt:stamp}).status,'NO_RECENT_NEWS');
});
test('service: news flags the shortlist without changing ranking, honours TTL, and no key degrades to replay',async()=>{
  let clock=now,newsCalls=0;
  const news=async id=>{newsCalls++;return newsPublic(envelope(id==='gigantti'?[article('Gigantti: tietomurto asiakasrekisteriin')]:[article('Proshop laajentaa')]),{sourceId:id,receivedAt:new Date(clock).toISOString()});};
  const service=createLiveService({apiKey:'test',captureFile:'/nonexistent-supplypulse-test',now:()=>clock,news,scrape:async id=>capture(id,id==='gigantti'?'109':'110')});
  const before=await service.current();assert.deepEqual(before.news.map(n=>n.status),['NOT_RETRIEVED','NOT_RETRIEVED']);
  const r=await service.refresh();
  assert.equal(r.winner,'gigantti');assert.equal(r.news[0].status,'REVIEW_NEWS');assert.equal(r.news[1].status,'NO_RISK_TERMS');
  assert.equal(r.retailerSignal.affectsShortlist,true);assert.match(r.retailerSignal.text,/Gigantti.*data breach.*Ranking unchanged/);assert.equal(newsCalls,2);
  clock+=10_000;await service.refresh();assert.equal(newsCalls,2,'news within TTL is not re-bought');
  clock+=15*60_000;await service.refresh();assert.equal(newsCalls,4);
  const failing=createLiveService({apiKey:'test',captureFile:'/nonexistent-supplypulse-test',now:()=>now,news:async()=>{throw Error('PROVIDER_CREDITS_EXHAUSTED');},scrape:async id=>capture(id,'109')});
  const f=await failing.refresh();assert.equal(f.status,'TIE');assert.equal(f.news[0].status,'ERROR');assert.equal(f.news[0].code,'PROVIDER_CREDITS_EXHAUSTED');assert.equal(f.connection.creditBlocked,true);
  const offline=createLiveService({apiKey:undefined,captureFile:new URL('./capture.json',import.meta.url),news:async()=>assert.fail('no call without key'),scrape:async()=>assert.fail('no call without key')});
  const replay=await offline.current();assert.equal(replay.offers.length,2);assert.deepEqual(replay.news.map(n=>n.status),['CONNECTION_REQUIRED','CONNECTION_REQUIRED']);assert.equal(replay.retailerSignal,null);
  await assert.rejects(offline.refresh(),{message:'CONNECTION_REQUIRED'});
});
test('HTTP: news reaches the browser JSON without the key',async()=>{
  const service=createLiveService({apiKey:'synthetic-secret',captureFile:'/nonexistent-supplypulse-test',now:()=>now,
    news:async id=>newsPublic(envelope([article('Kuluttajavirasto sakko '+id)]),{sourceId:id,receivedAt:stamp}),scrape:async id=>capture(id,id==='gigantti'?'109':'110')});
  const server=createServer({liveService:service});await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const base='http://127.0.0.1:'+server.address().port;
  try{
    const r=await fetch(base+'/api/refresh',{method:'POST',headers:{origin:base,'content-type':'application/json','x-supplypulse-refresh':'1'},body:'{}'});
    const body=await r.json();assert.equal(r.status,200);assert.equal(body.news.length,2);assert.deepEqual(body.news[0].flags,['regulator action']);
    assert(!JSON.stringify(body).includes('synthetic-secret'));assert.equal((await fetch(base+'/live/news-client.mjs')).status,404);
  }finally{await new Promise(r=>server.close(r));}
});
