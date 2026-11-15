// Second Context.dev endpoint: company News Search for each pinned retailer.
// Contract confirmed from the official docs on 2026-11-15:
//   https://docs.context.dev/api-reference/news/search.md  (POST /news/search, server https://api.context.dev/v1)
//   https://docs.context.dev/news/overview.md              (searchBy entity/domain, article fields, 404 for unknown company)
//   https://docs.context.dev/news/filter-and-sort.md       (filterBy.date epoch ms, sortBy newest)
//   https://docs.context.dev/account/credits.md            (1 credit per 10 returned results; unknown-company 404 costs 1)
// The retailer domain is pinned in sources.mjs; callers cannot supply a query, domain or URL.
import {sourceById} from './sources.mjs';

const ENDPOINT='https://api.context.dev/v1/news/search';
export const NEWS_MAX_BYTES=262_144;
export const NEWS_WINDOW_MS=30*24*60*60_000;
export const NEWS_LIMIT=5;
export const NEWS_TTL_MS=15*60_000;

// Advisory retailer-risk vocabulary (English + Finnish). A match never changes
// the price ranking; it flags a headline the buyer should read before ordering.
const RISK_TERMS=Object.freeze([
  ['insolvency',/\b(bankrupt\w*|insolven\w*|konkurssi\w*|yrityssaneeraus\w*|restructuring)\b/i],
  ['layoffs',/\b(layoffs?|redundanc\w*|yt-neuvottelu\w*|muutosneuvottelu\w*|lomautu\w*|irtisano\w*)\b/i],
  ['recall',/\b(recalls?|takaisinve\w*)\b/i],
  ['data breach',/\b(data breach|tietomurto\w*|tietovuoto\w*)\b/i],
  ['strike',/\b(strikes?|lakko\w*)\b/i],
  ['store closure',/\b(closures?|shut(s|ting)? down|sulke\w*|lopetta\w*)\b/i],
  ['delivery problems',/\b(deliver(y|ies) (delays?|problems?)|toimitusongelm\w*|viivästy\w*)\b/i],
  ['regulator action',/\b(fined?|penalt(y|ies)|lawsuit|kuluttajavirasto|kilpailu- ja kuluttajavirasto|sakko\w*|seuraamusmaksu\w*)\b/i],
]);
export function riskFlags(text) {return RISK_TERMS.filter(([,re])=>re.test(text)).map(([label])=>label);}

const STATUS_CODE={401:'PROVIDER_AUTH',403:'PROVIDER_AUTH',402:'PROVIDER_CREDITS_EXHAUSTED',429:'PROVIDER_RATE_LIMIT'};
const ARTICLE_TYPES=new Set(['editorial','press_release','regulatory_filing','advisory']);
const str=(v,max)=>typeof v==='string'?v.slice(0,max):null;
const httpsUrl=v=>{try{const u=new URL(v);return u.protocol==='https:'&&!u.username&&!u.password?u.href:null;}catch{return null;}};
const isoOrNull=v=>typeof v==='string'&&Number.isFinite(Date.parse(v))?new Date(v).toISOString():null;

// Keep only public headline metadata; drop key_metadata, authors, images and long text.
export function newsPublic(body,{sourceId,receivedAt}) {
  const source=sourceById(sourceId);
  if(!body||typeof body!=='object'||!Array.isArray(body.data)||typeof body.has_more!=='boolean'||typeof body.meta?.count!=='number') throw Error('NEWS_SCHEMA');
  if(typeof body.request_id!=='string'||!/^[-a-zA-Z0-9_]{1,128}$/.test(body.request_id)) throw Error('NEWS_SCHEMA');
  const articles=body.data.slice(0,NEWS_LIMIT).flatMap(a=>{
    const url=httpsUrl(a?.url),title=str(a?.title,300);
    if(!url||!title) return [];
    const description=str(a.description,600)??'';
    return [{id:str(a.id,128),title,url,publishedAt:isoOrNull(a.published_at),type:ARTICLE_TYPES.has(a.type)?a.type:'editorial',
      source:{name:str(a.source?.name,120)??'Unknown',domain:str(a.source?.domain,253)??''},
      match:a.match&&['primary','secondary'].includes(a.match.level)?{level:a.match.level,confidence:typeof a.match.confidence==='number'?a.match.confidence:null}:null,
      flags:riskFlags(`${title} ${description}`)}];
  });
  const flagged=articles.filter(a=>a.flags.length&&a.match?.level!=='secondary');
  return {sourceId,domain:source.domain,status:articles.length?(flagged.length?'REVIEW_NEWS':'NO_RISK_TERMS'):'NO_RECENT_NEWS',requestId:body.request_id,receivedAt,
    articles,flaggedCount:flagged.length,flags:[...new Set(flagged.flatMap(a=>a.flags))]};
}

export async function fetchRetailerNews(id,{apiKey,fetchImpl=fetch,clock=()=>new Date().toISOString(),now=Date.now,timeoutMs=20_000}={}) {
  const source=sourceById(id);
  if(typeof apiKey!=='string'||!apiKey.trim()) throw Error('CONNECTION_REQUIRED');
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try {
    const response=await fetchImpl(ENDPOINT,{method:'POST',redirect:'error',signal:controller.signal,headers:{Authorization:`Bearer ${apiKey}`,'Content-Type':'application/json'},
      body:JSON.stringify({searchBy:{type:'entity',entity:{type:'domain',domain:source.domain}},filterBy:{date:{from:now()-NEWS_WINDOW_MS}},sortBy:{type:'newest'},limit:NEWS_LIMIT})});
    if(response.status===404){await response.body?.cancel();return {sourceId:id,domain:source.domain,status:'NO_COVERAGE',requestId:null,receivedAt:clock(),articles:[],flaggedCount:0,flags:[]};}
    if(!response.ok){await response.body?.cancel();throw Error(STATUS_CODE[response.status]??'PROVIDER_FAILED');}
    if(Number(response.headers.get('content-length'))>NEWS_MAX_BYTES){await response.body?.cancel();throw Error('RESPONSE_TOO_LARGE');}
    if(!response.body) throw Error('INVALID_PROVIDER_JSON');
    const chunks=[];let size=0;
    for await(const chunk of response.body){size+=chunk.length;if(size>NEWS_MAX_BYTES){controller.abort();throw Error('RESPONSE_TOO_LARGE');}chunks.push(chunk);}
    let body;try{body=JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{throw Error('INVALID_PROVIDER_JSON');}
    return newsPublic(body,{sourceId:id,receivedAt:clock()});
  } catch(error) {
    if(controller.signal.aborted&&error.message!=='RESPONSE_TOO_LARGE') throw Error('PROVIDER_TIMEOUT');
    throw Error(NEWS_CODES.has(error?.message)?error.message:'PROVIDER_FAILED');
  } finally {clearTimeout(timer);}
}
export const NEWS_CODES=new Set(['CONNECTION_REQUIRED','PROVIDER_AUTH','PROVIDER_CREDITS_EXHAUSTED','PROVIDER_RATE_LIMIT','PROVIDER_FAILED','PROVIDER_TIMEOUT','RESPONSE_TOO_LARGE','INVALID_PROVIDER_JSON','NEWS_SCHEMA','SOURCE_NOT_ALLOWED']);
