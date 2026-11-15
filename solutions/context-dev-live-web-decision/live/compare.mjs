import {createHash} from 'node:crypto';
import {PRODUCT,SOURCES,TTL_MS,sourceById} from './sources.mjs';

const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const list = v => v == null ? [] : Array.isArray(v) ? v : [v];
const time = s => typeof s==='string' && Number.isFinite(Date.parse(s)) && new Date(s).toISOString()===s ? Date.parse(s) : NaN;
const isType = (v,type) => list(v?.['@type']).includes(type);
const schemaType = v => typeof v==='string' ? v.replace(/^https?:\/\/schema\.org\//,'') : null;
export function cents(value,{allowZero=false}={}) {
  if(typeof value!=='string' || !/^(0|[1-9]\d{0,6})(\.\d{1,2})?$/.test(value)) return null;
  const [whole,fraction='']=value.split('.');
  const result=Number(whole)*100+Number(fraction.padEnd(2,'0'));
  return Number.isSafeInteger(result) && (result>0||allowZero&&result===0) ? result : null;
}
function nodes(items,path='metadata.jsonLd') {
  return list(items).flatMap((v,i)=>v && typeof v==='object' ? [{v,path:`${path}[${i}]`},...nodes(v['@graph'],`${path}[${i}].@graph`)] : []);
}
function onlyValue(values) { const unique=[...new Set(values)]; return unique.length===1 ? unique[0] : null; }
function fail(code) {throw Error(code);}

// Reduce public provider output before retaining it: no reviews, account/credit
// metadata, cookies, HTML, arbitrary links or page instructions are persisted.
export function capturePublic(body,{sourceId,receivedAt,startedAt,transport}) {
  const source=sourceById(sourceId);
  if(!['CONTEXT_REST','CONTEXT_MCP_CAPTURE'].includes(transport)) fail('TRANSPORT_UNKNOWN');
  if(!Number.isFinite(time(receivedAt)) || !Number.isFinite(time(startedAt)) || time(startedAt)>time(receivedAt)) fail('CLOCK_INVALID');
  if(!body || body.url!==source.url || body.partial===true || body._context_mcp?.truncated || body.markdown?.requested!==true || body.markdown.success!==true) fail('OUTPUT_FAILED_OR_PARTIAL');
  for(const u of [body.metadata?.finalUrl,body.metadata?.canonicalUrl]) if(u && u!==source.url) fail('SOURCE_MISMATCH');
  if(typeof body.request_id!=='string'||!/^[-a-zA-Z0-9_]{1,128}$/.test(body.request_id)) fail('REQUEST_ID_MISSING');
  const cache=body.cache_metadata;
  if(!cache || !['miss','hit'].includes(cache.status) || !Number.isSafeInteger(cache.age_ms) || cache.age_ms<0 || cache.age_ms!==0) fail('CACHE_NOT_FRESH');
  const products=nodes(body.metadata?.jsonLd).filter(({v})=>isType(v,'Product') && list(v.gtin13??v.gtin).includes(PRODUCT.gtin));
  if(products.length!==1) fail('PRODUCT_IDENTITY_UNCONFIRMED');
  const {v:p,path}=products[0];
  if(!list(p.mpn).includes(PRODUCT.mpn)) fail('PRODUCT_IDENTITY_UNCONFIRMED');
  const offerData=list(p.offers).filter(o=>isType(o,'Offer')).map((o,index)=>({
    path:`${path}.offers[${index}]`,currency:o.priceCurrency,price:typeof o.price==='number'?String(o.price):o.price,
    availability:schemaType(o.availability),url:o.url??source.url,
    conditional:!!(o.validForMemberTier||o.eligibleCustomerType?.['@id'] && o.eligibleCustomerType['@id']!=='https://schema.org/Public'),
    specifications:list(o.priceSpecification).map(s=>({price:typeof s.price==='number'?String(s.price):s.price,currency:s.priceCurrency,vat:s.valueAddedTaxIncluded,member:!!s.validForMemberTier})),
    shipping:list(o.shippingDetails).map(s=>({country:s.shippingDestination?.addressCountry,currency:s.shippingRate?.currency,value:typeof s.shippingRate?.value==='number'?String(s.shippingRate.value):s.shippingRate?.value})),
  }));
  if(!offerData.length) fail('OFFER_MISSING');
  return {schemaVersion:1,sourceId,url:source.url,transport,startedAt,receivedAt,requestId:body.request_id,cacheAgeMs:cache.age_ms,
    latencyMs:time(receivedAt)-time(startedAt),identity:{name:String(p.name??PRODUCT.name).slice(0,300),gtin:PRODUCT.gtin,mpn:PRODUCT.mpn},offers:offerData};
}

export function normalize(capture,now=Date.now()) {
  const source=sourceById(capture?.sourceId);
  if(capture.schemaVersion!==1 || capture.url!==source.url || !['CONTEXT_REST','CONTEXT_MCP_CAPTURE'].includes(capture.transport) || capture.identity?.gtin!==PRODUCT.gtin || capture.identity?.mpn!==PRODUCT.mpn || !Array.isArray(capture.offers) || capture.offers.length<1 || capture.offers.length>8) fail('CAPTURE_INVALID');
  if(!Number.isFinite(time(capture.receivedAt)) || !Number.isSafeInteger(capture.cacheAgeMs) || capture.cacheAgeMs!==0 || !/^[-a-zA-Z0-9_]{1,128}$/.test(capture.requestId??'')) fail('CAPTURE_INVALID');
  const ageMs=now-time(capture.receivedAt)+capture.cacheAgeMs;
  if(ageMs<0) fail('CLOCK_INVALID');
  const ordinary=capture.offers.filter(o=>o.currency==='EUR' && !o.conditional && o.url===source.url && cents(o.price)!==null);
  const price=onlyValue(ordinary.map(o=>cents(o.price)));
  const availability=onlyValue(ordinary.map(o=>o.availability));
  if(price===null) fail('PRICE_UNKNOWN_OR_CONFLICTING');
  const memberPrices=ordinary.flatMap(o=>o.specifications??[]).filter(s=>s.member && s.vat===true && s.currency==='EUR').map(s=>cents(s.price)).filter(v=>v!==null);
  // Conditional rates, destination-specific fees and absent shipping are never zero.
  const shipping=onlyValue(ordinary.flatMap(o=>o.shipping??[]).filter(s=>s.country==='FI'&&s.currency==='EUR').map(s=>cents(s.value,{allowZero:true})).filter(v=>v!==null));
  return {id:source.id,name:source.name,url:source.url,product:capture.identity,priceCents:price,memberPriceCents:onlyValue(memberPrices),shippingFromCents:shipping,
    availability:availability??'Unknown',receivedAt:capture.receivedAt,ageMs,fresh:ageMs<=TTL_MS,transport:capture.transport,requestId:capture.requestId,
    evidenceHash:hash(capture),latencyMs:capture.latencyMs,priceEvidence:ordinary.map(o=>({path:o.path,value:o.price,currency:o.currency})),
    eligible:availability==='InStock' && ageMs<=TTL_MS};
}

export function compare(captures,{now=Date.now(),previous=null,errors=[]}={}) {
  const offers=[];const failures=[...errors];
  for(const source of SOURCES) {
    const matches=captures.filter(c=>c.sourceId===source.id);
    if(matches.length!==1) {failures.push({id:source.id,code:'SOURCE_MISSING_OR_DUPLICATE'});continue;}
    try {offers.push(normalize(matches[0],now));} catch(e) {failures.push({id:source.id,code:safeCode(e)});}
  }
  const complete=offers.length===2 && !failures.length && offers.every(o=>o.fresh);
  const eligible=complete ? offers.filter(o=>o.eligible).sort((a,b)=>a.priceCents-b.priceCents||a.id.localeCompare(b.id)) : [];
  const best=eligible[0]??null;
  const tied=eligible.length===2 && eligible[0].priceCents===eligible[1].priceCents;
  const winner=tied?null:best?.id??null;
  const changes=offers.map(o=>{
    const old=previous?.offers?.find(p=>p.id===o.id);
    const changed=old ? ['priceCents','memberPriceCents','availability','shippingFromCents'].filter(k=>old[k]!==o[k]) : [];
    return {id:o.id,status:old?(changed.length?'material':'unchanged'):'first-observation',fields:changed,previousPriceCents:old?.priceCents??null};
  });
  return {mode:'REAL_PUBLIC_WEB',asOf:new Date(now).toISOString(),product:PRODUCT,status:!complete?'REFUSE':best?'REVIEW_LISTED_PRICE':'NO_AVAILABLE_OFFER',winner,tied,
    actionAuthorized:false,rankingBasis:'Ordinary listed item price, one unit, EUR. Delivery fees excluded; total delivered cost and arrival date unknown.',
    reason:!complete?'Refresh both successful sources before comparing.':tied?'Listed item prices are equal.':best?`Review ${best.name}: lowest eligible ordinary item price.`:'Neither source confirms an available offer.',
    offers,errors:failures,changes,previousWinner:previous?.winner??null,winnerChanged:!!previous && previous.status==='REVIEW_LISTED_PRICE' && complete && previous.winner!==winner,
    limitations:['Retailer claims, not independently verified stock or price.','Member prices require membership and are excluded from ranking.','Shipping is destination-dependent; displayed shipping is a starting rate only.','No purchase, reservation, background monitoring or outbound supplier message.']};
}
const CODES=new Set(['TRANSPORT_UNKNOWN','CLOCK_INVALID','OUTPUT_FAILED_OR_PARTIAL','SOURCE_MISMATCH','REQUEST_ID_MISSING','CACHE_NOT_FRESH','PRODUCT_IDENTITY_UNCONFIRMED','OFFER_MISSING','CAPTURE_INVALID','PRICE_UNKNOWN_OR_CONFLICTING','CONNECTION_REQUIRED','PROVIDER_AUTH','PROVIDER_CREDITS_EXHAUSTED','PROVIDER_RATE_LIMIT','PROVIDER_FAILED','PROVIDER_TIMEOUT','RESPONSE_TOO_LARGE','INVALID_PROVIDER_JSON','REFRESH_BUSY','REFRESH_COOLDOWN','SESSION_REFRESH_LIMIT']);
export function safeCode(error) {return CODES.has(error?.message)?error.message:'PROVIDER_FAILED';}
