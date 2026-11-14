// Fixed policy v1. No fixture labels, keywords, political or identity features.
export const POLICY = Object.freeze({version:'radar-v1',threshold:65,windowSeconds:60,maxEvents:400,maxBytes:524288});
export const clean = (v,n=600) => String(v ?? '').replace(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g,' ').slice(0,n);
const norm = s => clean(s).toLowerCase().replace(/https?:\/\/\S+/g,'').replace(/[^\p{L}\p{N}\s]/gu,' ').replace(/\s+/g,' ').trim();
export function canonicalURL(value) {try {const u=new URL(clean(value,300));if(!['http:','https:'].includes(u.protocol))return '';return u.hostname.toLowerCase()+u.pathname.replace(/\/$/,'');}catch{return '';}}
const ratio = (a,b) => b ? a/b : 0;
function similarity(a,b) {const x=new Set(norm(a).split(' ').filter(Boolean)),y=new Set(norm(b).split(' ').filter(Boolean)); if(x.size<4||y.size<4)return 0;return [...x].filter(t=>y.has(t)).length/new Set([...x,...y]).size;}
function dominant(values) {const counts=new Map(); for(const v of values.filter(Boolean))counts.set(v,(counts.get(v)||0)+1);return [...counts].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0]||['',0];}
export function validate(input) {
 if(!Array.isArray(input))throw new Error('Events must be an array.');
 if(input.length>POLICY.maxEvents)throw new Error(`Limit: ${POLICY.maxEvents} events.`);
 if(new TextEncoder().encode(JSON.stringify(input)).length>POLICY.maxBytes)throw new Error('Limit: 512 KiB of event data.');
 const ids=new Set();return input.map((e,i)=>{if(!e||typeof e!=='object'||Array.isArray(e))throw new Error(`Invalid event ${i+1}.`);const id=clean(e.id,60),account=clean(e.account,60),time=Date.parse(e.time);if(!id||!account||!Number.isFinite(time)||ids.has(id))throw new Error(`Invalid or duplicate event ${i+1}.`); ids.add(id);
 const age=typeof e.accountAgeDays==='number'&&Number.isFinite(e.accountAgeDays)&&e.accountAgeDays>=0?Math.min(e.accountAgeDays,50000):null;
 return {id,account,time:new Date(time).toISOString(),ms:time,text:clean(e.text),url:canonicalURL(e.url),amplifies:clean(e.amplifies,60),accountAgeDays:age,attribution:clean(e.attribution,100)};
 }).sort((a,b)=>a.ms-b.ms||a.id.localeCompare(b.id));
}
export function analyze(input,{omit=[]}={}) {
 const events=validate(input),parent=events.map((_,i)=>i);const root=i=>{while(parent[i]!==i)i=parent[i];return i;};const links=[];
 for(let i=0;i<events.length;i++)for(let j=i+1;j<events.length;j++){
 const a=events[i],b=events[j];if(b.ms-a.ms>86400000)break;
 const sim=similarity(a.text,b.text),types=[];if(a.url&&a.url===b.url)types.push('url');if(sim>=.72)types.push('text');if(a.amplifies&&a.amplifies===b.amplifies)types.push('amplification');
 if(types.length){parent[root(j)]=root(i);links.push({a:a.id,b:b.id,types,similarity:Math.round(sim*100)});}}
 const groups=new Map();events.forEach((e,i)=>{const k=root(i);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(e);});
 const findings=[...groups.values()].map(es=>{
 const accounts=[...new Map(es.map(e=>[e.account,e])).values()];let peak=[];
 for(let i=0;i<es.length;i++){const slice=es.slice(i).filter(e=>e.ms-es[i].ms<=POLICY.windowSeconds*1000);if(new Set(slice.map(e=>e.account)).size>new Set(peak.map(e=>e.account)).size)peak=slice;}
 const ids=new Set(es.map(e=>e.id)),edges=links.filter(l=>ids.has(l.a)&&ids.has(l.b)),cross=edges.filter(l=>es.find(e=>e.id===l.a).account!==es.find(e=>e.id===l.b).account);
 const textIds=new Set(cross.filter(l=>l.types.includes('text')).flatMap(l=>[l.a,l.b]));
 const [url,urlN]=dominant(es.map(e=>e.url)),[target,targetN]=dominant(es.map(e=>e.amplifies));
 const [stem,stemN]=dominant(accounts.map(e=>e.account.toLowerCase().replace(/[\d_\-]+/g,'')));
 const known=accounts.filter(e=>e.accountAgeDays!==null),young=known.filter(e=>e.accountAgeDays<=14);
 const attributed=es.filter(e=>e.attribution).length;
 const organic=accounts.length>=4&&known.length===accounts.length&&known.every(e=>e.accountAgeDays>180)&&textIds.size/es.length<.5&&stemN/accounts.length<.5;
 const specs=[
 ['timing','Synchronized window',new Set(peak.map(e=>e.account)).size>=4?25:0,`${new Set(peak.map(e=>e.account)).size} distinct accounts within 60 seconds`,peak.map(e=>e.id)],
 ['text','Text reuse',accounts.length>=3&&textIds.size/es.length>=.6?20:0,`${textIds.size}/${es.length} events share ≥72% token overlap (4+ tokens)`,[...textIds]],
 ['url','Destination concentration',accounts.length>=3&&urlN/es.length>=.7?10:0,`${urlN}/${es.length} events share ${url||'no destination'}`,es.filter(e=>e.url===url&&url).map(e=>e.id)],
 ['names','Account naming pattern',accounts.length>=4&&stemN/accounts.length>=.7?15:0,`${stemN}/${accounts.length} account IDs share a digit-stripped stem; weak, spoofable evidence`,accounts.filter(e=>e.account.toLowerCase().replace(/[\d_\-]+/g,'')===stem).map(e=>e.id)],
 ['age','Recent account cohort',accounts.length>=4&&young.length/accounts.length>=.75?15:0,`${young.length}/${accounts.length} accounts ≤14 days old; ${accounts.length-known.length} unknown`,young.map(e=>e.id)],
 ['amplification','Shared amplification target',accounts.length>=4&&targetN/es.length>=.7?15:0,`${targetN}/${es.length} events amplify ${target||'no shared target'}`,es.filter(e=>e.amplifies===target&&target).map(e=>e.id)],
 ['syndication','Attributed syndication',attributed/es.length>=.8&&attributed>=3?-35:0,`${attributed}/${es.length} events declare attribution; supplied provenance is unverified and can be spoofed`,es.filter(e=>e.attribution).map(e=>e.id)],
 ['organic','Organic spread counterevidence',organic?-20:0,'Established, differently named accounts with varied text; does not prove authenticity',organic?es.map(e=>e.id):[]]
 ];
 const signals=specs.map(([key,label,points,detail,eventIds])=>({key,label,points:omit.includes(key)?0:points,originalPoints:points,detail,eventIds}));
 const score=Math.max(0,Math.min(100,signals.reduce((n,s)=>n+s.points,0)));const active=signals.filter(s=>s.points>0);
 const review=score>=POLICY.threshold&&active.some(s=>s.key==='timing')&&active.length>=3;
 return {id:es[0].id,score,review,status:review?'Analyst review':accounts.length<4?'Insufficient evidence':score>=POLICY.threshold?'Review gate not met':'Below review threshold',events:es,accountCount:accounts.length,peak:peak.map(e=>e.id),signals,links:edges.slice(0,100),start:es[0].time,end:es.at(-1).time,uncertainty:[accounts.length<4?'Too few distinct accounts for a coordination finding.':'Coordination does not establish deception, intent or automation.',known.length<accounts.length?'Missing account ages are unknown, never treated as new.':'Account metadata is supplied, not independently verified.','Disconnected or delayed campaigns can evade this 24-hour linkage model.']};
 }).sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
 return {mode:'SYNTHETIC / OFFLINE_DETERMINISTIC',policy:POLICY,eventCount:events.length,findings,limits:'Review aid only. Scores are rule points, not probabilities. No political, identity or protected-trait inference.'};
}
