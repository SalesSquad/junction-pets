// Pure deterministic policy. No network, clock, model, or action authority.
export const MODE = 'SYNTHETIC_REPLAY';
export const SOURCES = Object.freeze({north:'https://north.example.invalid/stock/desk-lamp', coast:'https://coast.example.invalid/stock/desk-lamp'});
export const POLICY = Object.freeze({quantity:40,budgetCents:60000,maxLeadDays:5,minConfidence:90,ttlMs:300000});
export function canonical(v) {
  if (v === null || typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return '['+v.map(canonical).join(',')+']';
  return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
}
// Portable SHA-256, supplied by the runtime; browser and Node use the same bytes.
export async function digest(v) {
  const bytes = new TextEncoder().encode(canonical(v));
  return [...new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
}
const time = s => typeof s==='string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(s) && Number.isFinite(Date.parse(s)) && new Date(s).toISOString()===s ? Date.parse(s) : NaN;
const shape=(v,keys)=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const integer = (n,min,max) => Number.isSafeInteger(n)&&n>=min&&n<=max;
export function semantic(s) {return {id:s.id,url:s.url,priceCents:s.priceCents,inventory:s.inventory,leadDays:s.leadDays,confidence:s.confidence,currency:s.currency};}
export function change(a,b) {return canonical(semantic(a))!==canonical(semantic(b))?'material':a.text!==b.text?'cosmetic':'unchanged';}
export async function decide(json) {
  const refuse = reason => ({mode:MODE,status:'REFUSE',reason,winner:null,actionAuthorized:false,candidates:[]});
  if(typeof json!=='string'||new TextEncoder().encode(json).length>32768) return refuse('bounded-json-required');
  let input;try{input=JSON.parse(json);}catch{return refuse('invalid-json');}
  if(!shape(input,['mode','asOf','snapshots'])||input?.mode!==MODE||!Number.isFinite(time(input.asOf))||!Array.isArray(input.snapshots)||input.snapshots.length<2||input.snapshots.length>8) return refuse('invalid-envelope');
  const seen=new Map();
  for(const s of input.snapshots){
    if(!shape(s,['mode','id','url','httpStatus','jsonSuccess','partial','observedAt','cacheOriginAt','currency','priceCents','inventory','leadDays','confidence','text'])||s.mode!==MODE||!Object.hasOwn(SOURCES,s.id)||SOURCES[s.id]!==s.url) return refuse('source-not-allowlisted');
    if(s.httpStatus!==200||s.jsonSuccess!==true||s.partial!==false) return refuse('failed-or-partial-output');
    const observed=time(s.observedAt),cached=time(s.cacheOriginAt),now=time(input.asOf);
    if(!Number.isFinite(observed)||!Number.isFinite(cached)||cached>observed||observed>now) return refuse('invalid-time');
    if(now-observed>POLICY.ttlMs||now-cached>POLICY.ttlMs) return refuse('stale-evidence');
    if(s.currency!=='EUR'||!integer(s.priceCents,1,Number.MAX_SAFE_INTEGER)||!integer(s.inventory,0,1000000)||!integer(s.leadDays,0,365)||!integer(s.confidence,0,100)||typeof s.text!=='string'||s.text.length>4096) return refuse('unknown-or-invalid-field');
    if(!Number.isSafeInteger(s.priceCents*POLICY.quantity)) return refuse('spend-overflow');
    if(seen.has(s.id)&&canonical(seen.get(s.id))!==canonical(s)) return refuse('conflicting-duplicate');
    seen.set(s.id,s);
  }
  if(seen.size!==2) return refuse('missing-source');
  const candidates=[];
  for(const s of [...seen.values()].sort((a,b)=>a.id.localeCompare(b.id))){
    const totalCents=s.priceCents*POLICY.quantity;
    const constraints=[];
    if(totalCents>POLICY.budgetCents)constraints.push('over-budget');
    if(s.inventory<POLICY.quantity)constraints.push('insufficient-stock');
    if(s.leadDays>POLICY.maxLeadDays)constraints.push('late-delivery');
    if(s.confidence<POLICY.minConfidence)constraints.push('low-confidence');
    candidates.push({...semantic(s),observedAt:s.observedAt,totalCents,constraints,evidenceHash:await digest(s)});
  }
  const eligible=candidates.filter(c=>!c.constraints.length).sort((a,b)=>a.totalCents-b.totalCents||a.leadDays-b.leadDays||a.id.localeCompare(b.id));
  return {mode:MODE,status:eligible.length?'REVIEW':'REFUSE',reason:eligible.length?'human-review-required':'no-eligible-source',winner:eligible[0]?.id??null,actionAuthorized:false,candidates,inputHash:await digest(input),policyHash:await digest(POLICY),asOf:input.asOf};
}
export function memo(result){return [MODE,'SUPPLYPULSE — HUMAN-ONLY SOURCING MEMO',`As of: ${result.asOf??'unknown'}`,`Disposition: ${result.status} / ${result.reason}`,`Candidate for review: ${result.winner??'none'}`,...result.candidates.map(c=>`${c.id}: EUR ${(c.totalCents/100).toFixed(2)} / ${c.constraints.join(', ')||'within constraints'} / evidence ${c.evidenceHash}`),`Input: ${result.inputHash??'rejected'}`,`Policy: ${result.policyHash??'not evaluated'}`,'What would change my decision: stock below 40, lead time above 5 days, confidence below 90, total above EUR 600, or cheaper eligible evidence. Refresh both sources after 5 minutes.','No purchase, monitoring, webhook or outbound action is authorized. Synthetic claims are not supplier facts.'].join('\n');}
