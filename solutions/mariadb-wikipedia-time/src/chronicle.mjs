import {createHash} from 'node:crypto';

// OFFLINE_DETERMINISTIC: no MariaDB or Wikipedia provider connected.
export const sha256 = s => createHash('sha256').update(s,'utf8').digest('hex');
export function utc(value) {
  if (typeof value !== 'string' ||
      !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(value))
    throw new Error('INVALID_UTC');
  const n=Date.parse(value);
  if (!Number.isFinite(n) || new Date(n).toISOString().slice(0,19)!==value.slice(0,19))
    throw new Error('INVALID_UTC');
  return n;
}
const str=(v,max=200000)=>typeof v==='string'&&v.trim().length>0&&v.length<=max;
export function loadDataset(input) {
  if (!input || !str(input.dataset_id,100) || !str(input.dataset_license,250) ||
      !['SYNTHETIC','LICENSED_REPLAY'].includes(input.provenance) ||
      !Array.isArray(input.revisions) || input.revisions.length>5000)
    throw new Error('INVALID_DATASET');
  const seen=new Set();
  const revisions=input.revisions.map(r=>{
    if (!r || !str(r.page_id,128) || !str(r.title,255) || !str(r.body) ||
        !str(r.revision_id,32) || !/^[0-9]+$/.test(r.revision_id))
      throw new Error('INVALID_REVISION');
    if(seen.has(r.revision_id))throw new Error('DUPLICATE_REVISION');
    seen.add(r.revision_id);
    const ms=utc(r.revised_at);
    if(input.provenance==='LICENSED_REPLAY'){
      let url;try{url=new URL(r.source_url)}catch{throw new Error('SOURCE_URL_REQUIRED')}
      if(url.protocol!=='https:' || !(url.hostname==='wikipedia.org'||url.hostname.endsWith('.wikipedia.org')))
        throw new Error('SOURCE_URL_REQUIRED');
    }else if(r.source_url!==null)throw new Error('SYNTHETIC_SOURCE_MUST_BE_NULL');
    return Object.freeze({...r,ms,hash:sha256(r.body)});
  });
  return Object.freeze({...input,revisions:Object.freeze(revisions)});
}
export function at(dataset,page,instant) {
  if(!str(page,128))throw new Error('INVALID_PAGE');
  const point=utc(instant);
  const candidates=dataset.revisions.filter(r=>r.page_id===page&&r.ms<=point)
    .sort((a,b)=>b.ms-a.ms);
  if(!candidates.length)return{status:'NO_EVIDENCE',page_id:page,as_of:instant};
  if(candidates.length>1 && candidates[0].ms===candidates[1].ms){
    return{status:'AMBIGUOUS_TIMESTAMP',page_id:page,as_of:instant,
      conflicting_ids:candidates.filter(r=>r.ms===candidates[0].ms).map(r=>r.revision_id).sort()};
  }
  const r=candidates[0];
  return{status:'FOUND',page_id:page,as_of:instant,revision_id:r.revision_id,
    revised_at:r.revised_at,title:r.title,text:r.body,sha256:r.hash,source_url:r.source_url,
    provenance:dataset.provenance,dataset_id:dataset.dataset_id,license:dataset.dataset_license};
}
const terms=s=>new Set(s.toLowerCase().match(/[\p{L}\p{N}]+/gu)||[]);
export function compare(a,b) {
  if(a.status!=='FOUND'||b.status!=='FOUND')return{status:'UNAVAILABLE',reason:'missing or ambiguous evidence'};
  if(a.page_id!==b.page_id||a.dataset_id!==b.dataset_id)throw new Error('CROSS_SOURCE_REFUSED');
  const one=terms(a.text),two=terms(b.text);
  return{status:a.sha256===b.sha256?'UNCHANGED':'CHANGED',from_revision:a.revision_id,
    to_revision:b.revision_id,added:[...two].filter(w=>!one.has(w)).sort().slice(0,20),
    removed:[...one].filter(w=>!two.has(w)).sort().slice(0,20),
    note:'Lexical differences are not proof of truth, bias or vandalism'};
}
export function reverts(dataset,page) {
  const list=dataset.revisions.filter(r=>r.page_id===page).sort((a,b)=>a.ms-b.ms);
  const out=[];
  for(let i=2;i<list.length;i++){
    const [a,b,c]=list.slice(i-2,i+1);
    if(a.ms<b.ms&&b.ms<c.ms&&a.hash===c.hash&&a.hash!==b.hash&&c.ms-a.ms<=172800000)
      out.push({revision_ids:[a.revision_id,b.revision_id,c.revision_id],
        label:'REVERT_CANDIDATE_NOT_VANDALISM_PROOF'});
  }
  return out;
}
export function inspect(dataset,page,asOf,compareAt=null){
  const snapshot=at(dataset,page,asOf);
  return{mode:'OFFLINE_DETERMINISTIC',provider:'NO_MARIADB_CONNECTION',
    provenance:dataset.provenance,dataset_id:dataset.dataset_id,snapshot,
    comparison:compareAt===null?null:compare(at(dataset,page,compareAt),snapshot),
    suspected_reverts:reverts(dataset,page)};
}
