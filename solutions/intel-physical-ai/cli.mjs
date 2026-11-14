import {readFile,writeFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {createSession,apply,receipt,replayReceipt,FIXTURE_IDS} from './core.mjs';
const [mode,arg]=process.argv.slice(2);
try {
  if(mode==='serve') {
    const allowed={'/':'index.html','/index.html':'index.html','/core.mjs':'core.mjs','/app.mjs':'app.mjs','/style.css':'style.css'};
    createServer(async(req,res)=>{
      const name=allowed[req.url];
      if(!name || req.method!=='GET'){res.writeHead(404);res.end('Not found');return;}
      try { const data=await readFile(new URL(name,import.meta.url)); res.writeHead(200,{'Content-Type':name.endsWith('.mjs')?'text/javascript':name.endsWith('.css')?'text/css':'text/html','Content-Security-Policy':"default-src 'self'; connect-src 'none'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",'Cache-Control':'no-store'});res.end(data); } catch {res.writeHead(500);res.end('Local file unavailable');}
    }).listen(4310,'127.0.0.1',()=>console.log('Offline cell: http://127.0.0.1:4310 — Ctrl+C to stop'));
  } else if(mode==='demo') {
    const results=[];
    for(const id of FIXTURE_IDS.slice(0,3)) {
      let s=createSession(id), n=0;
      const step=type=>{s=apply(s,{id:`step-${++n}`,type,at:n*100});};
      step('gate'); if(s.state.phase==='uncertain'){step('reinspect');step('review');} step('route'); results.push(await receipt(s));
    }
    if(arg) {await writeFile(arg,JSON.stringify(results,null,2)+'\n',{flag:'wx'});console.log(`Saved 3 synthetic receipts to ${arg}`);} else console.log(JSON.stringify(results,null,2));
  } else if(mode==='verify' && arg) {
    const data=JSON.parse(await readFile(arg,'utf8'));
    for(const r of Array.isArray(data)?data:[data]) await replayReceipt(r);
    console.log('Verified deterministic synthetic replay; no hardware or authenticated attestation');
  } else {console.log('Usage: node cli.mjs demo [NEW_RECEIPT_FILE] | verify FILE | serve');process.exitCode=1;}
} catch(error) {console.error(error.message);process.exitCode=1;}
