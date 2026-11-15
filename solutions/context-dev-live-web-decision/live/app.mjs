const $=id=>document.getElementById(id);
const euro=n=>n===null||n===undefined?'Unknown':new Intl.NumberFormat('en-FI',{style:'currency',currency:'EUR'}).format(n/100);
const when=s=>new Date(s).toLocaleString('en-FI',{timeZoneName:'short'});
const el=(tag,text,cls)=>{const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node;};
let current=null,fetching=false,expiryTimer=null,cooldownTimer=null;
const messages={CONNECTION_REQUIRED:'The server needs its own Context.dev API key to refresh. The saved MCP capture remains available as historical evidence.',PROVIDER_AUTH:'Context.dev rejected the server credential. Update the server connection, then retry.',PROVIDER_CREDITS_EXHAUSTED:'Context.dev credits are exhausted. Automatic retries are stopped; check the account before restarting.',PROVIDER_RATE_LIMIT:'Context.dev rate-limited this request. Wait before trying again.',REFRESH_COOLDOWN:'Please wait ten seconds between refreshes.',REFRESH_BUSY:'A refresh is already running.',SESSION_REFRESH_LIMIT:'This session reached its ten-refresh limit. Restart the server to start a new bounded session.',PROVIDER_TIMEOUT:'The source timed out. Retry when the service is available.'};
function render(data){
 current=data;
 const captured=data.offers.some(o=>o.transport==='CONTEXT_MCP_CAPTURE');
 const fresh=data.offers.length===2&&data.offers.every(o=>o.fresh)&&!data.errors.length;
 $('mode').textContent=captured?'CONTEXT.DEV · SAVED MCP CAPTURE':fresh?'CONTEXT.DEV · FRESH RETRIEVAL':'CONTEXT.DEV · REFRESH REQUIRED';
 $('connection').textContent=data.connection.connected?'Refresh makes two fresh Context.dev requests. No background polling.':'Live refresh needs the server’s Context.dev connection; saved retrievals are labelled with their actual time.';
 $('refresh').disabled=fetching||data.connection.busy||data.connection.creditBlocked||data.connection.refreshesRemaining===0||data.connection.refreshAfterMs>0;
 if(cooldownTimer)clearTimeout(cooldownTimer);
 if(data.connection.refreshAfterMs>0)cooldownTimer=setTimeout(()=>load(),data.connection.refreshAfterMs+100);
 $('verdict').replaceChildren();const verdict=el('div','','verdict');verdict.append(el('div',data.winner?'↳':'!','mark'));
 const content=el('div','');content.append(el('h2',data.status==='REFUSE'?'Refresh evidence before choosing.':data.reason),el('p',data.rankingBasis));verdict.append(content);$('verdict').append(verdict);
 $('cards').replaceChildren();
 for(const id of ['gigantti','proshop']){
  const o=data.offers.find(v=>v.id===id),error=data.errors.find(v=>v.id===id);const card=el('article','','card'+(data.winner===id?' selected':'')+(!o?' error':''));
  card.append(el('p',!o?'SOURCE UNAVAILABLE':o.fresh?'RETRIEVED · ≤5 MIN':'HISTORICAL · REFRESH REQUIRED','eyebrow'),el('h3',id==='gigantti'?'Gigantti':'Proshop'));
  if(!o){card.append(el('p',messages[error?.code]??'No complete, matching product evidence. Refresh both sources.'),el('p',error?.code??'SOURCE_MISSING','muted'));$('cards').append(card);continue;}
  card.append(el('div',euro(o.priceCents),'price'),el('p','Ordinary listed item price · delivery excluded','price-label'));
  const facts=el('dl','');for(const [label,value] of [['Availability',o.availability],['Member price',o.memberPriceCents===null?'Not supplied':euro(o.memberPriceCents)+' · excluded'],['Shipping from',euro(o.shippingFromCents)],['Arrival date','Unknown · address required']])facts.append(el('dt',label),el('dd',value));card.append(facts);
  const link=el('a','Review the retailer’s listing ↗','source-link');link.href=o.url;link.target='_blank';link.rel='noopener noreferrer';card.append(link);
  const meta=el('div','','source-meta');const stamp=el('time',when(o.receivedAt));stamp.dateTime=o.receivedAt;meta.append(el('p','Product match · '+o.product.mpn+' / '+o.product.gtin),stamp,el('p','Request '+o.requestId),el('p','Retrieval '+(o.latencyMs/1000).toFixed(1)+'s · provider cache age 0ms'));card.append(meta);$('cards').append(card);
 }
 $('changes').replaceChildren();for(const c of data.changes)$('changes').append(el('li',`${c.id}: ${c.status}${c.fields.length?' ('+c.fields.join(', ')+')':''}`));
 $('evidence').textContent=JSON.stringify(data,null,2);$('download').disabled=!data.offers.length;
 if(expiryTimer)clearTimeout(expiryTimer);
 const remaining=data.offers.filter(o=>o.fresh).map(o=>300_000-o.ageMs);
 if(remaining.length)expiryTimer=setTimeout(()=>load(),Math.max(100,Math.min(...remaining)+100));
}
async function load(){if(fetching)return;try{const r=await fetch('/api/comparison',{cache:'no-store'});if(!r.ok)throw Error('Comparison unavailable');render(await r.json());}catch{$('activity').textContent='The local comparison server is unavailable. Reconnect and reload.';}}
$('refresh').addEventListener('click',async()=>{
 if(fetching)return;fetching=true;$('refresh').disabled=true;$('download').disabled=true;$('verdict').textContent='Retrieving new evidence. No current recommendation.';$('activity').textContent='Retrieving both retailer pages through Context.dev…';
 try {const r=await fetch('/api/refresh',{method:'POST',headers:{'Content-Type':'application/json','X-SupplyPulse-Refresh':'1'},body:'{}'});const body=await r.json();if(!r.ok){$('activity').textContent=messages[body.error]??'Refresh failed. Existing evidence has not been replaced.';}else{$('activity').textContent=body.errors.length?'Some source evidence failed. A recommendation is withheld.':body.changes.some(c=>c.status==='material')?'Material offer changes detected; the shortlist has been recalculated.':'Sources retrieved. No material change detected.';current=body;}}
 catch{$('activity').textContent='The local server could not complete this refresh. No purchase was sent.';}
 finally{fetching=false;await load();}
});
$('download').addEventListener('click',()=>{
 if(!current)return;const output=['SUPPLYPULSE — HUMAN REVIEW',`Comparison: ${current.asOf}`,current.reason,current.rankingBasis,...current.offers.map(o=>`${o.name}: ${euro(o.priceCents)}; ${o.availability}; retrieved ${o.receivedAt}; ${o.url}; request ${o.requestId}; evidence ${o.evidenceHash}`),...current.limitations,'No purchase authorized.','',JSON.stringify(current,null,2)].join('\n');
 const url=URL.createObjectURL(new Blob([output],{type:'text/plain;charset=utf-8'}));const a=el('a','');a.href=url;a.download='SupplyPulse-sourcing-memo.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
load();
