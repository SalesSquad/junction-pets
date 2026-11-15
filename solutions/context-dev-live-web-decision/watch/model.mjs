import {createHash} from 'node:crypto';

export const MERCHANTS=Object.freeze([
  {id:'gigantti',name:'Gigantti',domain:'www.gigantti.fi',path:/^\/product\/.+\/\d+\/?$/},
  {id:'proshop',name:'Proshop',domain:'www.proshop.fi',path:/^\/[^/]+\/[^/]+\/\d+\/?$/},
  {id:'verkkokauppa',name:'Verkkokauppa.com',domain:'www.verkkokauppa.com',path:/^\/fi\/product\/\d+\/[^/]+\/?$/}
]);
export const LIMITS=Object.freeze({dailyRequests:40,requestsPerSearch:6,offersPerRun:4,maxWatches:30,maxRuns:30});
export function problem(code){return Object.assign(Error(code),{code});}
export function text(value,max,required=false){
  if(typeof value!=='string'||value.length>max||/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value)||required&&!value.trim())throw problem('INVALID_DEFINITION');
  if(/ctxt_secret_|Bearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----/i.test(value))throw problem('PRIVATE_VALUE_NOT_ALLOWED');
  return value.trim();
}
export function validZone(zone){try{if(typeof zone!=='string'||zone.length>100)throw Error();new Intl.DateTimeFormat('en-GB',{timeZone:zone}).format(0);return zone;}catch{throw problem('INVALID_TIME_ZONE');}}
export function validDate(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const time=Date.parse(value+'T00:00:00Z');return Number.isFinite(time)&&new Date(time).toISOString().slice(0,10)===value;
}
export function validateSchedule(raw){
  if(!raw||typeof raw!=='object'||Array.isArray(raw))throw problem('INVALID_SCHEDULE');
  const {kind}=raw;const timeZone=validZone(raw.timeZone??'Europe/Helsinki');
  const fields={manual:[],once:['at'],daily:['time'],weekly:['time','weekdays'],interval:['minutes']}[kind];
  if(!fields||Object.keys(raw).some(k=>!['kind','timeZone',...fields].includes(k)))throw problem('INVALID_SCHEDULE');
  if(kind==='manual')return {kind,timeZone};
  if(kind==='interval'){
    if(!Number.isInteger(raw.minutes)||raw.minutes<15||raw.minutes>10080)throw problem('INVALID_SCHEDULE');
    return {kind,timeZone,minutes:raw.minutes};
  }
  if(kind==='once'){
    if(typeof raw.at!=='string'||!/^\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d$/.test(raw.at)||!validDate(raw.at.slice(0,10)))throw problem('INVALID_SCHEDULE');
    return {kind,timeZone,at:raw.at};
  }
  if(typeof raw.time!=='string'||!/^([01]\d|2[0-3]):[0-5]\d$/.test(raw.time))throw problem('INVALID_SCHEDULE');
  if(kind==='weekly'){
    if(!Array.isArray(raw.weekdays)||!raw.weekdays.length||raw.weekdays.length>7||raw.weekdays.some(n=>!Number.isInteger(n)||n<1||n>7))throw problem('INVALID_SCHEDULE');
    return {kind,timeZone,time:raw.time,weekdays:[...new Set(raw.weekdays)].sort()};
  }
  return {kind,timeZone,time:raw.time};
}
export function validateDefinition(raw){
  const keys=['name','query','requirements','gtin','maxPriceCents','quantity','condition','inStockOnly','includeMemberPrices','merchantIds','schedule','maxRuns','expandCatalog'];
  if(!raw||typeof raw!=='object'||Array.isArray(raw)||Object.keys(raw).some(k=>!keys.includes(k)))throw problem('INVALID_DEFINITION');
  const def={name:text(raw.name,100,true),query:text(raw.query,300,true),requirements:text(raw.requirements??'',1500),gtin:text(raw.gtin??'',14),maxPriceCents:raw.maxPriceCents??null,
    quantity:raw.quantity??1,condition:raw.condition??'new',inStockOnly:raw.inStockOnly??true,includeMemberPrices:raw.includeMemberPrices??false,
    merchantIds:raw.merchantIds,schedule:validateSchedule(raw.schedule),maxRuns:raw.maxRuns??10,expandCatalog:raw.expandCatalog??false};
  if(def.gtin&&!/^(\d{8}|\d{12}|\d{13}|\d{14})$/.test(def.gtin))throw problem('INVALID_GTIN');
  if(def.maxPriceCents!==null&&(!Number.isSafeInteger(def.maxPriceCents)||def.maxPriceCents<1||def.maxPriceCents>100_000_000))throw problem('INVALID_TARGET_PRICE');
  if(!Number.isInteger(def.quantity)||def.quantity<1||def.quantity>100||!['new','any'].includes(def.condition)||!Number.isInteger(def.maxRuns)||def.maxRuns<1||def.maxRuns>LIMITS.maxRuns)throw problem('INVALID_DEFINITION');
  for(const field of ['inStockOnly','includeMemberPrices','expandCatalog'])if(typeof def[field]!=='boolean')throw problem('INVALID_DEFINITION');
  if(!Array.isArray(def.merchantIds)||!def.merchantIds.length||def.merchantIds.length>3||def.merchantIds.some(id=>!MERCHANTS.some(m=>m.id===id)))throw problem('INVALID_MERCHANTS');
  def.merchantIds=[...new Set(def.merchantIds)].sort();return def;
}
export function productURL(input,merchantIds){
  try{const u=new URL(input);const m=MERCHANTS.find(m=>m.domain===u.hostname&&merchantIds.includes(m.id));
    if(!m||u.protocol!=='https:'||u.username||u.password||u.port||!m.path.test(u.pathname)||/%(2f|5c|00|2e)/i.test(u.pathname))return null;
    u.search='';u.hash='';return {url:u.href,merchant:m};
  }catch{return null;}
}
export function fingerprint(value){return createHash('sha256').update(JSON.stringify(value)).digest('hex');}
export function criteriaKey(def){const {name,schedule,maxRuns,...criteria}=def;return fingerprint(criteria);}
export const SAFE_ERRORS=new Set(['INVALID_DEFINITION','PRIVATE_VALUE_NOT_ALLOWED','INVALID_TIME_ZONE','INVALID_DATE_TIME','INVALID_SCHEDULE','INVALID_GTIN','INVALID_TARGET_PRICE','INVALID_MERCHANTS','WATCH_NOT_FOUND','REVISION_CONFLICT','WATCH_ARCHIVED','RUN_BUSY','RUN_LIMIT_REACHED','DAILY_REQUEST_LIMIT','REQUEST_LIMIT','RUN_DAY_CHANGED','RUN_CANCELLED','CONNECTION_REQUIRED','PROVIDER_AUTH','PROVIDER_CREDITS_EXHAUSTED','PROVIDER_RATE_LIMIT','PROVIDER_TIMEOUT','PROVIDER_FAILED','PROVIDER_PARTIAL','PROVIDER_SCHEMA','RESPONSE_TOO_LARGE','INVALID_PROVIDER_JSON','SOURCE_REJECTED','IDEMPOTENCY_CONFLICT','INVALID_REQUEST','WATCH_LIMIT','STORE_UNAVAILABLE']);
export const safeError=e=>SAFE_ERRORS.has(e?.code??e?.message)?(e.code??e.message):'PROVIDER_FAILED';
