import {capturePublic,safeCode} from './compare.mjs';
import {sourceById} from './sources.mjs';
const ENDPOINT='https://api.context.dev/v1/web/scrape';
export const MAX_BYTES=1_048_576;
export async function scrapeSource(id,{apiKey,fetchImpl=fetch,clock=()=>new Date().toISOString(),timeoutMs=55_000}={}) {
  const source=sourceById(id);
  if(typeof apiKey!=='string'||!apiKey.trim()) throw Error('CONNECTION_REQUIRED');
  const startedAt=clock();const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try {
    const response=await fetchImpl(ENDPOINT,{method:'POST',redirect:'error',signal:controller.signal,headers:{Authorization:`Bearer ${apiKey}`,'Content-Type':'application/json'},
      body:JSON.stringify({url:source.url,formats:{markdown:true},maxAgeMs:0,sharedParams:{mainContentOnly:true},timeoutOpts:{milliseconds:45_000,behavior:'fail'}})});
    if(!response.ok) {await response.body?.cancel();throw Error(response.status===401||response.status===403?'PROVIDER_AUTH':response.status===402?'PROVIDER_CREDITS_EXHAUSTED':response.status===429?'PROVIDER_RATE_LIMIT':'PROVIDER_FAILED');}
    if(Number(response.headers.get('content-length'))>MAX_BYTES) {await response.body?.cancel();throw Error('RESPONSE_TOO_LARGE');}
    const chunks=[];let size=0;
    if(!response.body) throw Error('INVALID_PROVIDER_JSON');
    for await(const chunk of response.body) {size+=chunk.length;if(size>MAX_BYTES){controller.abort();throw Error('RESPONSE_TOO_LARGE');}chunks.push(chunk);}
    let body;try {body=JSON.parse(Buffer.concat(chunks).toString('utf8'));} catch {throw Error('INVALID_PROVIDER_JSON');}
    return capturePublic(body,{sourceId:id,startedAt,receivedAt:clock(),transport:'CONTEXT_REST'});
  } catch(error) {if(controller.signal.aborted && error.message!=='RESPONSE_TOO_LARGE') throw Error('PROVIDER_TIMEOUT');throw Error(safeCode(error));}
  finally {clearTimeout(timer);}
}
