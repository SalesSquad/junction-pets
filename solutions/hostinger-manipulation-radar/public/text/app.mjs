const $=id=>document.getElementById(id);
const el=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
$('example').onclick=()=>{$('material').value='Act now before it is too late. Everyone who questions this offer is working against you. An unnamed expert guarantees it will solve every problem, but the evidence will be published later.';$('consent').checked=false;};
fetch('/api/status').then(r=>r.json()).then(s=>{$('connection').textContent=s.aiRouter==='NOT_CONFIGURED'?'AI review is not configured on this server.':'Hostinger AI Router configured · model '+s.model+' · '+s.dailyRequestLimit+' requests/day. A successful review verifies one live request.';}).catch(()=>{$('connection').textContent='Service status unavailable.';});
$('review').onclick=async()=>{
  $('result').replaceChildren();
  if(!$('consent').checked){$('status').textContent='Confirm the provider transfer before reviewing text.';return;}
  $('review').disabled=true;$('status').textContent='Reviewing the submitted material…';
  try {
    const response=await fetch('/api/interpret',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:$('material').value,consent:true})});
    const r=await response.json();
    if(!response.ok)throw Error(({HOSTINGER_AI_ROUTER_NOT_CONFIGURED:'Hostinger AI Router is not configured yet.',DAILY_DEMO_LIMIT:'The shared daily demonstration limit has been reached.',ONE_REVIEW_AT_A_TIME:'Another review is running. Try again shortly.',TEXT_MUST_BE_20_TO_4000_BYTES:'Use 20–4,000 UTF-8 bytes of material.'})[r.error]||'Review unavailable: '+r.error);
    const node=$('result');node.append(el('h2','Quoted evidence · '+r.provider),el('p','Model: '+r.model+' · Truth: '+r.truth+' · Intent: '+r.intent));
    for(const t of r.techniques){const card=el('article','');card.className='cluster';card.append(el('h3',t.name),el('blockquote',t.excerpt),el('p',t.explanation));node.append(card);}
    if(!r.techniques.length)node.append(el('p','No supported technique returned. This does not establish that the material is accurate or harmless.'));
    node.append(el('h3','Alternative explanation'),el('p',r.alternativeExplanation),el('h3','Missing context'),el('p',r.missingContext),el('p',r.warning));
    $('status').textContent='Review complete. '+r.droppedUnsupported+' unsupported excerpts or techniques rejected.';
  }catch(e){$('status').textContent=e.message;}
  finally{$('review').disabled=false;}
};
