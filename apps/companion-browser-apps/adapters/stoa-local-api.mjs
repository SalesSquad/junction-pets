// Browser-local equivalent of the existing Stoa demo/import/ask routes.
// Drawings remain in this tab; no file bytes or questions are uploaded.
import {parseDxf,DXF_LIMITS} from '../src/dxf.mjs';
import {answerDrawing} from '../src/grounding.mjs';
import {makeDemo} from '../src/demo.mjs';

export function createStoaLocalApi() {
 const cache=new Map([['demo',{drawing:makeDemo(),created:Date.now()}]]);
 const json=(status,body)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json; charset=utf-8'}});
 const get=id=>{const item=cache.get(id);if(!item)return null;if(id!=='demo'&&Date.now()-item.created>30*60*1000){cache.delete(id);return null;}return item.drawing;};
 const remember=drawing=>{for(const [id,item] of cache)if(id!=='demo'&&Date.now()-item.created>30*60*1000)cache.delete(id);while(cache.size>=4)cache.delete([...cache.keys()].find(id=>id!=='demo'));cache.set(drawing.id,{drawing,created:Date.now()});};
 return async (path,options={})=>{
  try {
   const method=(options.method??'GET').toUpperCase();
   if(method==='GET'&&path==='/api/demo')return json(200,{drawing:get('demo')});
   if(method==='POST'&&path==='/api/import-dxf'){
    if(!/^application\/(?:dxf|octet-stream)/i.test(new Headers(options.headers).get('content-type')??''))return json(415,{error:'Use application/dxf or application/octet-stream.'});
    const bytes=new Uint8Array(options.body);
    if(bytes.byteLength>DXF_LIMITS.bytes)return json(413,{error:'Request is too large.'});
    const filename=new Headers(options.headers).get('x-filename')??'uploaded.dxf';
    const drawing=parseDxf(new TextDecoder().decode(bytes),filename);
    drawing.sha256=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
    drawing.id=crypto.randomUUID();
    drawing.sourceNotice='USER-IMPORTED LOCAL FILE · Geometry extracted; claims require human verification';
    remember(drawing);
    return json(201,{drawing});
   }
   if(method==='POST'&&path==='/api/ask'){
    if(!/^application\/json/i.test(new Headers(options.headers).get('content-type')??''))return json(415,{error:'Use application/json.'});
    if(typeof options.body!=='string'||new TextEncoder().encode(options.body).byteLength>2048)return json(413,{error:'Request is too large.'});
    const input=JSON.parse(options.body),drawing=get(input?.drawingId);
    if(!drawing)return json(404,{error:'The drawing expired. Reimport the DXF file.'});
    return json(200,{result:answerDrawing(drawing,input.question)});
   }
   return json(404,{error:'No route at this path.'});
  } catch(error) {return json(error instanceof SyntaxError?400:422,{error:String(error?.message??error).slice(0,240)});}
 };
}
