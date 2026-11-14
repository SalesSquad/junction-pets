import { POLICY, digest } from '../engine.mjs';
export const LIMITS=Object.freeze({bytes:32768,timeoutMs:1000});
const exact=(v,keys)=>v&&Object.getPrototypeOf(v)===Object.prototype&&Object.keys(v).sort().join('|')===[...keys].sort().join('|');
const num=(v,min=0,max=Number.MAX_SAFE_INTEGER)=>Number.isSafeInteger(v)&&v>=min&&v<=max;
const stamp=v=>typeof v==='string'&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString()===v;
function publicURL(s,replay){const u=new URL(s);if(u.href!==s||u.protocol!=='https:'||u.username||u.password||u.port||u.search||u.hash||!/^([a-z][a-z0-9-]*\.)+[a-z]{2,}$/.test(u.hostname)||/\.(local|localhost|internal|test|example)$/.test(u.hostname)||(!replay&&u.hostname.endsWith('.invalid')))throw Error('unsafe-target');}
// Host client is the transport trust boundary, including DNS, redirect denial and pre-parse byte caps.
export async function review({sources,consent,client,asOf,responseFormat,context,replay=false}){
 const reject=(status,reason)=>({status,reason,winner:null,actionAuthorized:false});
 if(consent!==true||responseFormat!=='CONTEXT_REST_JSON_V1'||context!=='40-ivory-desk-lamps')return reject('UNQUALIFIED','explicit-host-contract-required');
 try{
 if(!stamp(asOf)||!exact(sources,['north','coast'])||sources.north===sources.coast||typeof client!=='function')throw Error('invalid-host-config');
 for(const url of Object.values(sources))publicURL(url,replay);
 const candidates=[];const evidence=[];
 for(const [id,url] of Object.entries(sources)){
 let timer;let raw;
 try{raw=await Promise.race([client(Object.freeze({endpoint:'https://api.context.dev/v1/web/scrape',method:'POST',url,formats:['json'],maxAgeMs:0,redirects:'error',maxBytes:LIMITS.bytes,timeoutMs:LIMITS.timeoutMs})),new Promise((_,r)=>{timer=setTimeout(()=>r(Error('timeout')),LIMITS.timeoutMs);})]);}finally{clearTimeout(timer);}
 if(typeof raw!=='string'||Buffer.byteLength(raw)>LIMITS.bytes)throw Error('bounded-response-required');
 // Canonical serialized records only: rejects duplicate JSON keys and ambiguous serialization.
 const r=JSON.parse(raw);if(JSON.stringify(r)!==raw)throw Error('noncanonical-record');
 if(!exact(r,['sourceId','requestedUrl','finalUrl','requestId','observedAt','cacheOriginAt','httpStatus','partial','redirected','json'])||r.sourceId!==id||r.requestedUrl!==url||r.finalUrl!==url||r.redirected!==false||typeof r.requestId!=='string'||!/^[-a-zA-Z0-9_]{1,128}$/.test(r.requestId))throw Error('source-metadata');
 if(r.httpStatus!==200||r.partial!==false||!exact(r.json,['success','data'])||r.json.success!==true)throw Error('failed-or-partial');
 if(!stamp(r.observedAt)||!stamp(r.cacheOriginAt)||Date.parse(r.cacheOriginAt)>Date.parse(r.observedAt)||Date.parse(r.observedAt)>Date.parse(asOf)||Date.parse(asOf)-Date.parse(r.cacheOriginAt)>POLICY.ttlMs)throw Error('stale-time');
 const d=r.json.data;
 if(!exact(d,['currency','priceCents','shippingCents','taxCents','moq','inventory','leadDays','confidence','confidenceProvenance','text'])||d.currency!=='EUR'||!num(d.priceCents,1)||!num(d.shippingCents)||!num(d.taxCents)||!num(d.moq,1)||!num(d.inventory,0,1000000)||!num(d.leadDays,0,365)||!num(d.confidence,0,100)||d.confidenceProvenance!=='operator-verified-extraction'||typeof d.text!=='string'||d.text.length>4096)throw Error('unknown-data-or-provenance');
 const totalCents=d.priceCents*POLICY.quantity+d.shippingCents+d.taxCents;if(!num(totalCents))throw Error('unsafe-total');
 evidence.push({id,url,hash:await digest(r)});
 candidates.push({id,url,totalCents,eligible:d.inventory>=POLICY.quantity&&d.moq<=POLICY.quantity&&d.leadDays<=POLICY.maxLeadDays&&d.confidence>=POLICY.minConfidence&&totalCents<=POLICY.budgetCents});
 }
 const winner=candidates.filter(c=>c.eligible).sort((a,b)=>a.totalCents-b.totalCents||a.id.localeCompare(b.id))[0]?.id??null;
 const memo={mode:replay?'SYNTHETIC_PROVIDER_REPLAY':'HOST_INJECTED_UNVERIFIED',asOf,context,policy:POLICY,candidates,evidence,winner,authenticity:'Host assertions only; hashes do not authenticate provider execution.'};
 return {status:winner?'HUMAN_REVIEW':'REFUSE',winner,actionAuthorized:false,memo,memoHash:await digest(memo)};
 }catch(e){return reject('REFUSE',e.message);}
}
