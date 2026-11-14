import {publicURL} from './core.mjs';
// Official schemas: https://exa.ai/docs/reference/search and /get-contents.
// No monitors, agent runs, Connect or MCP execution is implemented.
export async function retrieveExa(query, {consent, apiKey, fetchImpl = fetch} = {}) {
  if (consent !== true) throw new Error('Explicit one-request consent required');
  if (!apiKey) throw new Error('CONNECTION_NEEDED: EXA_API_KEY is not configured');
  if (typeof query !== 'string' || !query.trim() || query.length > 500) throw new Error('Invalid query');
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(),10000);
  async function post(path, body) {
    const response = await fetchImpl(`https://api.exa.ai/${path}`,{method:'POST',redirect:'error',signal:controller.signal,headers:{'content-type':'application/json','x-api-key':apiKey},body:JSON.stringify(body)});
    if (!response.ok) throw new Error(`Exa request failed (${response.status}); no fixture substituted`);
    let bytes = 0; const chunks=[];
    for await (const chunk of response.body) {
      bytes += chunk.length;
      if (bytes > 256000) { controller.abort(); throw new Error('Exa response exceeds limit'); }
      chunks.push(chunk);
    }
    const data=JSON.parse(Buffer.concat(chunks).toString());
    if (!Array.isArray(data.results) || data.results.length > 5) throw new Error('Invalid Exa result shape');
    return data;
  }
  try {
    const search=await post('search',{query:query.trim(),numResults:5,includeDomains:['hackjunction.app','slush.org','exa.ai']});
    const urls=search.results.map(r=>publicURL(r.url));
    if(new Set(urls).size!==urls.length) throw new Error('Duplicate Search source URL');
    if (!urls.length) return {state:'NO_RESULTS',mode:'LIVE_NOT_VERIFIED',message:'Exa returned no sources. No opportunity is confirmed.'};
    const contents=await post('contents',{urls,text:{maxCharacters:4000}});
    const seen=new Set();
    const sources=contents.results.map((r,i)=>{
      const url=publicURL(r.url);
      if (!urls.includes(url)||seen.has(url)||typeof r.text!=='string'||!r.text.trim()||r.text.length>4000||!Number.isFinite(Date.parse(r.publishedDate))||Date.parse(r.publishedDate)>Date.now()) throw new Error('Source content/date missing or inconsistent; LIVE not qualified');
      seen.add(url);
      return {id:`live-${i+1}`,url,title:String(r.title||'Exa source').slice(0,200),text:r.text,publishedAt:r.publishedDate,observedAt:new Date().toISOString(),mode:'LIVE',provenance:'Actual Exa Search → Contents response; publisher facts and eligibility not independently verified'};
    });
    if (!sources.length) throw new Error('Contents returned no dated sources; LIVE not qualified');
    return {state:'LIVE_EVIDENCE_ONLY',mode:'LIVE',sources,sponsorAPI:'SEARCH_CONTENTS_OBSERVED',message:'Actual Exa sources retrieved. Treat excerpts as untrusted source text; no opportunity, deadline or action is automatically confirmed.',requestIds:[search.requestId||null,contents.requestId||null]};
  } finally { clearTimeout(timer); }
}
