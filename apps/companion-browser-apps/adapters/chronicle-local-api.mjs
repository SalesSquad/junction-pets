// Browser-local execution of the original synthetic Chronicle Studio engine.
import {loadDataset, inspect, reverts, utc} from '../src/chronicle.mjs';
import fixture from './fixture.mjs';

const LABEL='SYNTHETIC_REPLAY_NO_MARIADB';
const mode=d=>d.provenance==='WIKIPEDIA_API_SNAPSHOT'?'REAL_LOCAL_SNAPSHOT_NO_MARIADB':LABEL;
/* STUDIO_FUNCTIONS */

export function createChronicleLocalApi() {
  const dataset=loadDataset(fixture);
  const json=(status,body)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json; charset=utf-8'}});
  return async (path,options={})=>{
    let url;
    try { url=new URL(path,'https://chronicle.local'); }
    catch { return json(404,{status:'NOT_FOUND'}); }
    if(url.origin!=='https://chronicle.local')return json(404,{status:'NOT_FOUND'});
    const source=url.searchParams.get('source')||'synthetic';
    if(source==='real')return json(422,{status:'REFUSED',reason:'NO_ADMITTED_REAL_SNAPSHOT'});
    if(source!=='synthetic')return json(422,{status:'REFUSED',reason:'UNKNOWN_SOURCE'});
    const method=(options.method||'GET').toUpperCase();
    if(method==='GET'&&url.pathname==='/api/catalog')return json(200,makeCatalog(dataset));
    if(method==='POST'&&url.pathname==='/api/compare') {
      if((new Headers(options.headers).get('content-type')||'').split(';')[0].trim()!=='application/json')
        return json(415,{status:'REFUSED',reason:'JSON_REQUIRED'});
      if(typeof options.body!=='string')return json(422,{status:'REFUSED',reason:'INVALID_JSON'});
      if(new TextEncoder().encode(options.body).byteLength>2048)return json(413,{status:'REFUSED',reason:'REQUEST_TOO_LARGE'});
      try {return json(200,evaluate(dataset,JSON.parse(options.body)));}
      catch(error) {return json(422,{status:'REFUSED',reason:error instanceof SyntaxError?'INVALID_JSON':error.message||'INVALID_REQUEST'});}
    }
    return json(404,{status:'NOT_FOUND'});
  };
}
