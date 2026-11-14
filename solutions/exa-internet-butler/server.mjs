import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {makePacket} from './core.mjs';
import {retrieveExa} from './exa-adapter.mjs';
const root=new URL('./',import.meta.url);
const fixture=JSON.parse(await readFile(new URL('fixtures/official.json',root)));
const anchors=JSON.parse(await readFile(new URL('fixtures/anchors.json',root)));
const files={'/':['public/index.html','text/html'],'/app.mjs':['public/app.mjs','text/javascript'],'/style.css':['public/style.css','text/css']};
export function createServer({apiKey=process.env.EXA_API_KEY}={}) {
  let liveBusy=false; let recent=[];
  return http.createServer(async(req,res)=>{
    const host=req.headers.host||'';
    const headers={'cache-control':'no-store','x-content-type-options':'nosniff','referrer-policy':'no-referrer','content-security-policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"};
    function reply(status,data) {res.writeHead(status,{...headers,'content-type':'application/json'});res.end(JSON.stringify(data));}
    if (!/^127\.0\.0\.1:\d+$/.test(host) || (req.headers.origin && req.headers.origin!==`http://${host}`) || req.headers['sec-fetch-site']==='cross-site') return reply(403,{error:'Local same-origin requests only'});
    try {
      if (req.method==='GET' && files[req.url]) {const [path,type]=files[req.url];res.writeHead(200,{...headers,'content-type':type});res.end(await readFile(new URL(path,root)));return;}
      if (req.method==='GET' && req.url==='/api/status') return reply(200,{mode:'REPLAYED_OFFICIAL_FIXTURE',sponsorAPI:'NOT VERIFIED',liveConfigured:Boolean(apiKey),goal:fixture.goal,snapshot:fixture.snapshot});
      if (req.method!=='POST' || !['/api/packet','/api/live'].includes(req.url)) return reply(404,{error:'Not found'});
      if (req.headers['content-type']!=='application/json') return reply(415,{error:'JSON required'});
      let raw=''; for await (const chunk of req) {raw+=chunk;if(Buffer.byteLength(raw)>8192) return reply(413,{error:'Request too large'});}
      let body;try {body=JSON.parse(raw);}catch {return reply(400,{error:'Invalid JSON'});}
      if (!body || typeof body!=='object' || Array.isArray(body)) return reply(400,{error:'Expected request object'});
      if(req.url==='/api/packet') return reply(200,makePacket(body.goal,fixture,anchors));
      recent=recent.filter(t=>Date.now()-t<60000);
      if(liveBusy||recent.length>=5) return reply(429,{error:'Live lookup limit reached; try later'});
      liveBusy=true;recent.push(Date.now());
      try {return reply(200,await retrieveExa(body.goal,{consent:body.consent,apiKey}));}
      finally {liveBusy=false;}
    } catch(error) {
      const safe=/^(Explicit|CONNECTION_NEEDED|Invalid query|Enter a goal|Exa request failed|Exa response|Invalid Exa|Source |Contents |Duplicate |Unrecognized |Unsupported )/.test(error.message);
      reply(400,{state:'CONNECTION_NEEDED',mode:'LIVE_NOT_VERIFIED',error:safe?error.message:'Lookup failed safely; no result was invented or fixture substituted'});
    }
  });
}
if (process.argv[1]===fileURLToPath(import.meta.url)) {
  const port=Number(process.env.PORT||4318);
  if(!Number.isInteger(port)||port<1024||port>65535) throw new Error('PORT must be 1024–65535');
  const server=createServer();server.listen(port,'127.0.0.1',()=>console.log(`Event Opportunity Concierge · http://127.0.0.1:${port} · replay; LIVE not verified`));
  for(const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>server.close(()=>process.exit(0)));
}
