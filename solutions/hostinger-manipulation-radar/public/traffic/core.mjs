export const MAX_BYTES=1048576;
const limitations=['Real-world labels and error rates UNKNOWN. Authored examples are SYNTHETIC.','Per-import sequential aliases are NOT general anonymization of usage metadata.','Password mistakes, load tests, crawlers, rate limits and shared proxies can explain signals.','No attack, bot, account or reputation verdict; no automated bans.'];
function refuse(){throw Error('Import refused: malformed or unsupported combined log.');}
// Sort once, then maintain threshold counts with two pointers. Materialize each
// merged episode once: O(n log n) time and O(n) space, including evidence IDs.
function rollingReplay(events){
 const sorted=events.map((event,index)=>({event,index,t:Date.parse(event.time)})).sort((a,b)=>a.t-b.t||a.index-b.index);
 const auth=e=>[401,403].includes(e.status)&&['/login','/signin','/api/login','/wp-login.php','/admin','/account'].includes(e.route);
 const clients=new Map(),ranges=[];let left=0,authCount=0,rateCount=0;
 function adjust(e,delta){if(auth(e)){authCount+=delta;const count=(clients.get(e.client)||0)+delta;if(count)clients.set(e.client,count);else clients.delete(e.client);}if(e.status===429)rateCount+=delta;}
 for(let right=0;right<sorted.length;){
  const t=sorted[right].t;let last=right;
  // Evaluate equal timestamps together, independent of input order.
  while(last<sorted.length&&sorted[last].t===t)adjust(sorted[last++].event,1);
  while(left<last&&sorted[left].t<=t-300000)adjust(sorted[left++].event,-1);
  if(authCount>=10&&clients.size>=3&&rateCount>=5){
   const previous=ranges.at(-1);
   if(previous&&t-300000<previous.end){previous.end=t;previous.last=last;}
   else ranges.push({start:t-300000,end:t,first:left,last});
  }
  right=last;
 }
 return {mode:'OFFLINE_DETERMINISTIC',interval:'(end - 5 minutes, end]; evaluated at every distinct event timestamp',qualification:'Not tuned or qualified on real labels; real-world error rates UNKNOWN',episodes:ranges.map((range,i)=>{
  const evidence=sorted.slice(range.first,range.last).map(x=>x.event);
  return {id:'episode-'+(i+1),start:new Date(range.start).toISOString(),end:new Date(range.end).toISOString(),distinctClients:new Set(evidence.map(e=>e.client)).size,evidenceIds:evidence.map(e=>e.id),disposition:'UNREVIEWED',review:'Human review only; no actor or intent inference or automated enforcement',counterexplanations:['Authorized load testing can produce concurrent login failures and HTTP 429 responses.','A shared reverse proxy can distort client counts and combine unrelated visitors.']};
 })};
}
export function analyzeLog(bytes,{synthetic=false}={}){
 if(!(bytes instanceof Uint8Array)||bytes.length>MAX_BYTES)throw Error('Import refused: maximum 1 MiB.');
 let text;try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{throw Error('Import refused: invalid UTF-8.');}
 if(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u202a-\u202e\u2066-\u2069]/u.test(text))refuse();
 const lines=text?text.replace(/\n$/,'').split('\n'):[];if(lines.length>5000)throw Error('Import refused: maximum 5000 lines.');
 const aliases=new Map(),events=[];
 for(let line of lines){line=line.replace(/\r$/,'');if(line.length>4096)refuse();
 const m=/^([0-9a-fA-F:.]{2,64}) - (?:-|[\w.-]{1,64}) \[(\d{2})\/([A-Z][a-z]{2})\/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})\] "(GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS|TRACE|CONNECT) ([^"\s]{1,512}) HTTP\/1\.[01]" ([1-5]\d{2}) (\d{1,12}|-) "[^"\r\n]{0,1024}" "[^"\r\n]{0,1024}"$/.exec(line);if(!m)refuse();
 const [,ip,d,mon,y,h,min,s,sign,oh,om,method,target,status,size]=m;
 const ipv4=/^(?:\d{1,3}\.){3}\d{1,3}$/.test(ip)&&ip.split('.').every(x=>+x<=255);
 const groups=ip.split('::');const parts=ip.split(':').filter(Boolean);const ipv6=!ip.includes('.')&&groups.length<=2&&groups.every(side=>side===''||side.split(':').every(x=>/^[0-9a-fA-F]{1,4}$/.test(x)))&&parts.every(x=>/^[0-9a-fA-F]{1,4}$/.test(x))&&(groups.length===2?parts.length<8:parts.length===8);
 if(!ipv4&&!ipv6)refuse();
 const month=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].indexOf(mon);const local=Date.UTC(+y,month,+d,+h,+min,+s);
 if(month<0||+y<2000||+y>2100||+d<1||new Date(local).getUTCDate()!==+d||+h>23||+min>59||+s>59||+oh>14||+om>59||(+oh===14&&+om!==0))refuse();
 if(!target.startsWith('/')||target.startsWith('//')||/[\\#]/.test(target))refuse();const path=target.split('?')[0];if(path.length>160||!/^\/[A-Za-z0-9/_.%~-]*$/.test(path))refuse();
 const route=['/','/login','/signin','/api/login','/wp-login.php','/admin','/account','/robots.txt'].includes(path)?path:'[other path]';
 // Normalize numeric IP spellings BEFORE forming per-import aliases. In particular,
 // compressed/expanded IPv6 forms must never count as distinct clients.
 let clientAddress;try{clientAddress=ipv6?new URL('http://['+ip+']/').hostname.toLowerCase():ip.split('.').map(Number).join('.');}catch{refuse();}
 if(!aliases.has(clientAddress))aliases.set(clientAddress,'client-'+(aliases.size+1));
 events.push({id:'event-'+(events.length+1),client:aliases.get(clientAddress),time:new Date(local-(sign==='+'?1:-1)*(+oh*60 + +om)*60000).toISOString(),method,route,status:+status,bytes:size==='-'?null:+size});
 }
 const times=events.map(e=>Date.parse(e.time));if(times.length&&Math.max(...times)-Math.min(...times)>604800000)throw Error('Import refused: range exceeds seven days.');
 const windows=new Map();for(const e of events){const t=Math.floor(Date.parse(e.time)/300000)*300000;if(!windows.has(t))windows.set(t,[]);windows.get(t).push(e);}
 const clusters=[...windows].sort((a,b)=>a[0]-b[0]).map(([t,es],i)=>{const distinctClients=new Set(es.map(e=>e.client)).size;const auth=es.filter(e=>[401,403].includes(e.status)&&['/login','/signin','/api/login','/wp-login.php','/admin','/account'].includes(e.route));const rate=es.filter(e=>e.status===429),errors=es.filter(e=>e.status>=500);const signal=(rule,ev,active)=>({rule,count:ev.length,denominator:es.length,active,evidenceIds:ev.map(e=>e.id)});const a=auth.length>=10&&new Set(auth.map(e=>e.client)).size>=3,r=rate.length>=5;return {id:'window-'+(i+1),start:new Date(t).toISOString(),end:new Date(t+300000).toISOString(),count:es.length,distinctClients,candidate:a&&r,disposition:'UNREVIEWED',signals:[signal('auth-rejections',auth,a),signal('rate-limits',rate,r),signal('service-errors-operational-only',errors,errors.length>=5),signal('volume-context-only',es,es.length>=30&&distinctClients>=3)],counterexplanations:[limitations[2],'Repeated 5xx can be service failure. Seek support reports, authorized load-test schedules and proxy configuration.']};});
 return {ruleVersion:'traffic-review-1',provenance:synthetic?'SYNTHETIC':'USER_SUPPLIED_UNVERIFIED_LOG',realWorldLabels:'UNKNOWN',counts:{events:events.length,distinctClients:aliases.size,windows:clusters.length,candidates:clusters.filter(c=>c.candidate).length},range:times.length?{start:new Date(Math.min(...times)).toISOString(),end:new Date(Math.max(...times)).toISOString()}:null,limitations,events,clusters,rolling:rollingReplay(events)};
}
export const exportReport=report=>JSON.stringify(report,null,2)+'\n';
export const demoLog=()=>Array.from({length:40},(_,i)=>`192.0.2.${i%5+1} - - [14/Nov/2026:09:00:${String(i).padStart(2,'0')} +0200] "POST /login?secret=discard HTTP/1.1" ${i<30?401:429} 120 "https://private.example" "Private UA"`).join('\n');
