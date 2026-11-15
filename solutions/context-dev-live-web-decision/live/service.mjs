import {readFile} from 'node:fs/promises';
import {compare,safeCode} from './compare.mjs';
import {scrapeSource} from './context-client.mjs';
import {SOURCES} from './sources.mjs';
import {fetchRetailerNews,NEWS_TTL_MS,NEWS_CODES} from './news-client.mjs';

export function createLiveService({apiKey=process.env.CONTEXT_DEV_API_KEY,captureFile=process.env.SUPPLYPULSE_CAPTURE_FILE??new URL('./capture.json',import.meta.url),scrape=scrapeSource,news=fetchRetailerNews,newsTtlMs=NEWS_TTL_MS,now=Date.now,cooldownMs=10_000,maxRefreshes=10}={}) {
  let captures=[],errors=[],previous=null,busy=false,lastStart=-Infinity,refreshes=0,creditBlocked=false;
  let initialization;const newsById=new Map();
  function init() {
    return initialization??=(async()=>{
    try {
      const bytes=await readFile(captureFile);
      if(bytes.length>65_536) throw Error('CAPTURE_INVALID');
      const value=JSON.parse(bytes);
      if(value.schemaVersion!==1 || !Array.isArray(value.captures) || value.captures.length!==2) throw Error('CAPTURE_INVALID');
      captures=value.captures;
    }catch(e){if(e.code!=='ENOENT')errors=[{id:'capture',code:e.code?'CAPTURE_READ_FAILED':'CAPTURE_INVALID'}];}
    })();
  }
  const status=()=>({connected:!!apiKey,busy,creditBlocked,refreshesRemaining:Math.max(0,maxRefreshes-refreshes),refreshAfterMs:Math.max(0,cooldownMs-(now()-lastStart))});
  // Retailer news is advisory context from a second Context.dev endpoint. It is
  // shown beside each offer but never changes the ordinary-price ranking.
  const newsView=()=>SOURCES.map(s=>{
    const n=newsById.get(s.id);
    if(!n)return {sourceId:s.id,domain:s.domain,status:apiKey?'NOT_RETRIEVED':'CONNECTION_REQUIRED',articles:[],flaggedCount:0,flags:[],requestId:null,receivedAt:null};
    return {...n,ageMs:n.receivedAt?Math.max(0,now()-Date.parse(n.receivedAt)):null};
  });
  const signal=(data,newsList)=>{
    const flagged=newsList.filter(n=>n.status==='REVIEW_NEWS');
    if(!flagged.length)return null;
    const names=flagged.map(n=>SOURCES.find(s=>s.id===n.sourceId).name);
    const winner=data.winner&&flagged.some(n=>n.sourceId===data.winner);
    return {sourceIds:flagged.map(n=>n.sourceId),affectsShortlist:!!winner,
      text:`${winner?'Shortlisted retailer':'Retailer'} news to read before ordering: ${names.join(' and ')} (${[...new Set(flagged.flatMap(n=>n.flags))].join(', ')}). Ranking unchanged.`};
  };
  const result=()=>{const data=compare(captures,{now:now(),previous,errors});const newsList=newsView();return {...data,news:newsList,retailerSignal:signal(data,newsList),connection:status()};};
  return {
    async current(){await init();return result();},
    async refresh(){
      await init();
      if(!apiKey)throw Error('CONNECTION_REQUIRED');
      if(creditBlocked)throw Error('PROVIDER_CREDITS_EXHAUSTED');
      if(busy)throw Error('REFRESH_BUSY');
      if(now()-lastStart<cooldownMs)throw Error('REFRESH_COOLDOWN');
      if(refreshes>=maxRefreshes)throw Error('SESSION_REFRESH_LIMIT');
      busy=true;lastStart=now();refreshes++;
      previous=compare(captures,{now:now(),errors});
      try {
        // News has its own 15-minute TTL so price refreshes do not re-buy headlines.
        const newsDue=SOURCES.filter(s=>{const n=newsById.get(s.id);return !n||n.status==='ERROR'||!n.receivedAt||now()-Date.parse(n.receivedAt)>=newsTtlMs;});
        const [outcomes,newsOutcomes]=await Promise.all([Promise.allSettled(SOURCES.map(s=>scrape(s.id,{apiKey}))),Promise.allSettled(newsDue.map(s=>news(s.id,{apiKey})))]);
        newsOutcomes.forEach((o,i)=>{
          const s=newsDue[i];
          if(o.status==='fulfilled')newsById.set(s.id,o.value);
          else {const code=NEWS_CODES.has(o.reason?.message)?o.reason.message:'PROVIDER_FAILED';newsById.set(s.id,{sourceId:s.id,domain:s.domain,status:'ERROR',code,articles:[],flaggedCount:0,flags:[],requestId:null,receivedAt:null});if(code==='PROVIDER_CREDITS_EXHAUSTED')creditBlocked=true;}
        });
        captures=[];errors=[];
        outcomes.forEach((o,i)=>{
          if(o.status==='fulfilled')captures.push(o.value);
          else {const code=safeCode(o.reason);errors.push({id:SOURCES[i].id,code});if(code==='PROVIDER_CREDITS_EXHAUSTED')creditBlocked=true;}
        });
      } finally {busy=false;}
      return result();
    }
  };
}
