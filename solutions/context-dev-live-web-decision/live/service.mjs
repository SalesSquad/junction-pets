import {readFile} from 'node:fs/promises';
import {compare,safeCode} from './compare.mjs';
import {scrapeSource} from './context-client.mjs';
import {SOURCES} from './sources.mjs';

export function createLiveService({apiKey=process.env.CONTEXT_DEV_API_KEY,captureFile=process.env.SUPPLYPULSE_CAPTURE_FILE??new URL('./capture.json',import.meta.url),scrape=scrapeSource,now=Date.now,cooldownMs=10_000,maxRefreshes=10}={}) {
  let captures=[],errors=[],previous=null,busy=false,lastStart=-Infinity,refreshes=0,creditBlocked=false;
  let initialization;
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
  const result=()=>({...compare(captures,{now:now(),previous,errors}),connection:status()});
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
        const outcomes=await Promise.allSettled(SOURCES.map(s=>scrape(s.id,{apiKey})));
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
