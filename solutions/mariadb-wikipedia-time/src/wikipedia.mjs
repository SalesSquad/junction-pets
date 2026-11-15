import {sha256, utc} from './chronicle.mjs';
import {writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

export const ENDPOINT = 'https://fi.wikipedia.org/w/api.php';
export const LICENSE = 'CC BY-SA 4.0; Wikipedia contributors; additional terms may apply';
export const ATTRIBUTION = 'Finnish Wikipedia contributors. Revision URLs provide article history and attribution. Wikitext may include separately licensed material; review before redistribution.';
export const LIMITS = Object.freeze({revisions:20, pages:4, responseBytes:1048576, contentBytes:131072, totalBytes:2097152, timeoutMs:10000});
const fail = () => {throw new Error('INVALID_WIKIPEDIA_SNAPSHOT');};
const id = x => typeof x === 'string' && /^[1-9][0-9]{0,14}$/.test(x) && Number.isSafeInteger(Number(x));
export const revisionUrl = revision => `https://fi.wikipedia.org/w/index.php?oldid=${revision}`;
export function requestUrl(page, limit, continuation) {
  if (!id(page) || !Number.isInteger(limit) || limit < 1 || limit > LIMITS.revisions) fail();
  const u = new URL(ENDPOINT);
  for (const [k,v] of Object.entries({action:'query',format:'json',formatversion:'2',prop:'revisions',pageids:page,rvprop:'ids|timestamp|content',rvslots:'main',rvdir:'older',rvlimit:String(limit)})) u.searchParams.set(k,v);
  if (continuation !== undefined) {
    if (typeof continuation !== 'string' || !/^[0-9]{14}\|[1-9][0-9]{0,14}$/.test(continuation)) fail();
    u.searchParams.set('rvcontinue',continuation);u.searchParams.set('continue','||');
  }
  return u.href;
}
// Fixed field order is the canonical digest format. No authentication claim is made.
export function snapshotDigest(s) {
  return sha256(JSON.stringify([s.format,s.provenance,s.page_id,s.retrieved_at,s.source_uri,s.dataset_license,s.attribution,s.window,s.has_more,
    s.revisions.map(r=>[r.page_id,r.title,r.revision_id,r.revised_at,r.body,r.source_url,r.content_sha256])]));
}
export function admitSnapshot(s) {
  if (!s || s.format !== 'chronicle-wikipedia-v1' || s.provenance !== 'WIKIPEDIA_API_SNAPSHOT' || !id(s.page_id) ||
      s.dataset_license !== LICENSE || s.attribution !== ATTRIBUTION || s.window !== 'LATEST_N_NOT_FULL_HISTORY' ||
      typeof s.has_more !== 'boolean' || !Array.isArray(s.revisions) || !s.revisions.length || s.revisions.length > LIMITS.revisions) fail();
  if(Object.keys(s).sort().join() !== ['format','provenance','page_id','retrieved_at','source_uri','dataset_license','attribution','window','has_more','revisions','snapshot_sha256'].sort().join())fail();
  const retrieved=utc(s.retrieved_at);
  if (s.source_uri !== requestUrl(s.page_id,s.revisions.length)) fail();
  let previous=Infinity, previousId=Infinity, total=0, title;
  const seen=new Set();
  const revisions=s.revisions.map(r=>{
    if(!r || Object.keys(r).sort().join() !== ['page_id','title','revision_id','revised_at','body','source_url','content_sha256'].sort().join())fail();
    const ms=utc(r.revised_at);
    if(r.page_id!==s.page_id || !id(r.revision_id) || seen.has(r.revision_id) || ms>=previous || Number(r.revision_id)>=previousId || ms>retrieved ||
        typeof r.title!=='string' || !r.title.trim() || r.title.length>255 || (title!==undefined && title!==r.title) ||
        typeof r.body!=='string' || !r.body.trim() || Buffer.byteLength(r.body)>LIMITS.contentBytes ||
        r.source_url!==revisionUrl(r.revision_id) || r.content_sha256!==sha256(r.body)) fail();
    total+=Buffer.byteLength(r.body);if(total>LIMITS.totalBytes)fail();
    title=r.title;seen.add(r.revision_id);previous=ms;previousId=Number(r.revision_id);
    return Object.freeze({page_id:r.page_id,title:r.title,revision_id:r.revision_id,revised_at:r.revised_at,body:r.body,source_url:r.source_url,hash:r.content_sha256,ms});
  });
  if(snapshotDigest(s)!==s.snapshot_sha256)fail();
  return Object.freeze({dataset_id:'fiwiki-'+s.snapshot_sha256,provenance:s.provenance,dataset_license:LICENSE,
    attribution:ATTRIBUTION,retrieved_at:s.retrieved_at,source_uri:s.source_uri,snapshot_sha256:s.snapshot_sha256,
    window:s.window,has_more:s.has_more,source_integrity:'LOCAL_SNAPSHOT_HASH_ONLY_UNVERIFIED',revisions:Object.freeze(revisions)});
}
export function parseResponse(data,page) {
  if(!data || data.error || data.warnings || !data.query || Object.keys(data.query).some(k=>k!=='pages') ||
      !Array.isArray(data.query.pages) || data.query.pages.length!==1) fail();
  const p=data.query.pages[0];
  if(Object.keys(p).some(k=>!['pageid','ns','title','revisions'].includes(k)) || String(p.pageid)!==page || !Number.isSafeInteger(p.pageid) || p.ns!==0 || p.missing!==undefined || p.invalid!==undefined ||
      typeof p.title!=='string' || !Array.isArray(p.revisions) || !p.revisions.length) fail();
  const rows=p.revisions.map(r=>{
    if(!Number.isSafeInteger(r.revid) || r.revid<=0 || !Number.isSafeInteger(r.parentid) || r.parentid<0 ||
        Object.keys(r).some(k=>!['revid','parentid','timestamp','slots'].includes(k)) || !r.slots || Object.keys(r.slots).join()!=='main') fail();
    const slot=r.slots.main;
    if(!slot || slot.contentmodel!=='wikitext' || slot.contentformat!=='text/x-wiki' || typeof slot.content!=='string' ||
        Object.keys(slot).some(k=>!['contentmodel','contentformat','content'].includes(k))) fail();
    return {page_id:page,title:p.title,revision_id:String(r.revid),revised_at:r.timestamp,body:slot.content,
      source_url:revisionUrl(String(r.revid)),content_sha256:sha256(slot.content)};
  });
  let next;
  if(data.continue!==undefined) {
    if(!data.continue || Object.keys(data.continue).sort().join()!=='continue,rvcontinue' || data.continue.continue!=='||')fail();
    next=data.continue.rvcontinue;requestUrl(page,1,next);
  }
  return {rows,next};
}
async function boundedJson(response) {
  if(!response.ok || response.redirected || !/^application\/json\b/i.test(response.headers.get('content-type')||'') ||
      Number(response.headers.get('content-length')||0)>LIMITS.responseBytes)fail();
  let size=0;const parts=[];
  for await (const chunk of response.body) {
    size+=chunk.length;if(size>LIMITS.responseBytes)throw new Error('RESPONSE_LIMIT');parts.push(chunk);
  }
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(parts)));
}
export async function fetchSnapshot({pageId,limit=3,fetchImpl=fetch,now=()=>new Date().toISOString()}) {
  const source_uri=requestUrl(pageId,limit);const rows=[];const tokens=new Set();let next;
  const signal=AbortSignal.timeout(LIMITS.timeoutMs);
  for(let page=0;page<LIMITS.pages;page++) {
    const response=await fetchImpl(requestUrl(pageId,limit-rows.length,next),{redirect:'error',signal,
      headers:{'User-Agent':'ChronicleWitness/1.0 (Junction M307; bounded educational revision intake)','Accept':'application/json'}});
    const parsed=parseResponse(await boundedJson(response),pageId);
    if(parsed.rows.length>limit-rows.length)fail();rows.push(...parsed.rows);next=parsed.next;
    if(rows.length===limit || next===undefined)break;
    if(tokens.has(next))fail();tokens.add(next);
  }
  if(rows.length!==limit)throw new Error('INCOMPLETE_REQUESTED_WINDOW');
  const s={format:'chronicle-wikipedia-v1',provenance:'WIKIPEDIA_API_SNAPSHOT',page_id:pageId,retrieved_at:now(),source_uri,
    dataset_license:LICENSE,attribution:ATTRIBUTION,window:'LATEST_N_NOT_FULL_HISTORY',has_more:next!==undefined,revisions:rows};
  s.snapshot_sha256=snapshotDigest(s);admitSnapshot(s);return s;
}
if(process.argv[1] && pathToFileURL(resolve(process.argv[1])).href===import.meta.url) {
  try {
    const a=process.argv.slice(2);
    if(a.length!==6 || a[0]!=='--page' || a[2]!=='--limit' || a[4]!=='--out' || !a[5])throw new Error('USAGE: --page ID --limit 1..20 --out FILE');
    const snapshot=await fetchSnapshot({pageId:a[1],limit:Number(a[3])});
    await writeFile(a[5],JSON.stringify(snapshot,null,2)+'\n',{flag:'wx',mode:0o600});
    process.stdout.write(JSON.stringify({status:'SAVED',snapshot_sha256:snapshot.snapshot_sha256,revisions:snapshot.revisions.length})+'\n');
  } catch {process.stderr.write('WIKIPEDIA_INTAKE_REFUSED (no snapshot written; check endpoint, bounds and output path)\n');process.exitCode=2;}
}
