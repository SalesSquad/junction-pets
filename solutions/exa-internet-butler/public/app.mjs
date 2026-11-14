import {createCuration} from '/curation.mjs';
const $=id=>document.getElementById(id);
let packet=null, approved=null;
const notice=text=>{$('notice').textContent=text;};
function el(tag,text,className) {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function invalidate() {approved=null;$('ack').checked=false;$('approve').disabled=true;$('export').disabled=true;$('copy').disabled=true;$('approval').textContent='Not approved';updateNext();}
function updateNext() {if(!packet)return;const undone=packet.actions.find(a=>!a.done);$('next-step').textContent=approved?'Packet reviewed locally. Export it for your own next step.':undone?undone.text:'Review the draft and unresolved terms, then approve locally.';}
function sourceCard(s) {
  const box=el('article',undefined,'source');box.append(el('p',`${s.id} · ${s.mode}`,'eyebrow'),el('h3',s.title));
  const a=el('a',s.url);a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';box.append(a);
  box.append(el('p',`Observed: ${s.observedAt} · Publication: ${s.publishedAt||'UNKNOWN'} · ${s.freshness||'provider-reported date'}`,'meta'),el('p',s.provenance,'meta'));
  if(s.snapshotSHA256)box.append(el('p',`Snapshot text SHA-256: ${s.snapshotSHA256}`,'meta'));
  const d=el('details');d.append(el('summary','Inspect source text (untrusted evidence)'),el('p',s.text));box.append(d);return box;
}
function renderActions() {
  $('actions').replaceChildren(...packet.actions.map(a=>{const box=el('div',undefined,'action'),label=el('label',undefined,'check'),input=el('input');input.type='checkbox';input.checked=a.done;input.addEventListener('change',()=>{a.done=input.checked;invalidate();});label.append(input,el('span',a.text));box.append(label,el('small',a.kind==='user_supplied'?'USER-SUPPLIED · no source-based claim':`SUGGESTION · ${a.sourceIds.join(', ')}`));return box;}));
}
async function request(path,body) {const r=await fetch(path,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw new Error(data.error||'Request failed');return data;}
function clearWorkspace() {resetCuration();packet=null;approved=null;$('workspace').hidden=true;$('live-results').hidden=true;$('next-step').textContent='Choose a supported goal or connect Exa explicitly.';}
$('example').onclick=()=>{clearWorkspace();$('goal-input').value=$('goal-input').dataset.example;$('goal-input').focus();notice('Named replay selected. Prepare the packet to continue.');};
$('goal-input').addEventListener('input',()=>{if(packet||approved||curation||liveApproval)clearWorkspace();notice('Goal changed. Prepare a new packet.');});
$('goal-form').onsubmit=async e=>{
  e.preventDefault();clearWorkspace();$('build').disabled=true;notice('Preparing the dated source packet…');
  try {const data=await request('/api/packet',{goal:$('goal-input').value});if(data.state!=='EVIDENCE_READY'){notice(data.message);return;}
    packet=data;$('workspace').hidden=false;$('packet-mode').textContent=data.mode;$('packet-time').textContent=`Snapshot ${data.snapshot} · Packet prepared ${data.checkedAt}. This is a dated evidence replay, not a verification of current opportunities.`;
    $('sources').replaceChildren(...data.sources.map(sourceCard));
    $('claims').replaceChildren(...data.claims.map(c=>{const n=el('div',undefined,'claim');n.append(el('p',c.label),el('small',`${c.sourceId} · exact supporting excerpt: “${c.excerpt}”`));return n;}));
    $('gaps').replaceChildren(...data.discrepancies.map(g=>{const n=el('div',undefined,'gap');n.append(el('strong',`${g.kind} · ${g.sourceIds.join(', ')}`),el('p',g.detail));return n;}));
    renderActions();$('draft').value=data.draft;invalidate();notice('Packet ready. Review the evidence and open questions before using the draft.');$('evidence').focus();
  }catch(err){notice(err.message);}finally{$('build').disabled=false;}
};
$('add-action').onsubmit=e=>{e.preventDefault();const text=$('own-action').value.trim();if(!text||!packet)return;packet.actions.push({id:`user-${packet.actions.length}`,text,kind:'user_supplied',sourceIds:[],done:false});$('own-action').value='';renderActions();invalidate();};
$('draft').addEventListener('input',()=>{if(packet){packet.draft=$('draft').value;invalidate();}});
$('ack').onchange=()=>{$('approve').disabled=!$('ack').checked; if(!$('ack').checked)invalidate();};
$('approve').onclick=()=>{if(!packet||!$('ack').checked)return;approved={at:new Date().toISOString(),scope:'LOCAL_REVIEW_ONLY',executesRealWorldTask:false};$('approval').textContent='Approved locally · no task executed';$('export').disabled=false;$('copy').disabled=false;updateNext();};
function exported() {return {...packet,draft:$('draft').value,approval:approved,externalEffects:[],warning:'Local approval does NOT execute any real-world task. Recheck stale/unknown terms. User edits are user-supplied, not verified source facts.'};}
$('export').onclick=()=>{if(!approved)return;const blob=new Blob([JSON.stringify(exported(),null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='fieldnote-exa-opportunity.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('Packet exported locally. No task was executed.');};
$('copy').onclick=async()=>{if(!approved)return;try{await navigator.clipboard.writeText(JSON.stringify(exported(),null,2));notice('Source packet and draft copied. Nothing was sent.');}catch{notice('Clipboard unavailable. Use Export packet instead.');}};
$('live').onclick=async()=>{
  const consent=$('live-consent').checked;if(!consent){notice('Approve sending this goal to Exa before requesting live evidence.');return;}
  clearWorkspace();$('live').disabled=true;notice('Requesting one bounded Search → Contents lookup…');
  try {const result=await request('/api/live',{goal:$('goal-input').value,consent});$('live-results').hidden=false;$('live-message').textContent=`${result.mode}: ${result.message}`;$('live-sources').replaceChildren(...(result.sources||[]).map(sourceCard));notice('Live lookup finished. Returned text has not been turned into verified facts or an approved plan.');if(result.mode==='LIVE'&&result.state==='LIVE_EVIDENCE_ONLY')startCuration(result,$('goal-input').value);$('live-results').focus();}catch(err){notice(err.message);}finally{$('live').disabled=false;$('live-consent').checked=false;}
};
try {const r=await fetch('/api/status');if(!r.ok)throw new Error();const s=await r.json();$('goal-input').dataset.example=s.goal;$('goal-input').value=s.goal;$('provider-status').textContent=s.liveConfigured?'Environment key configured. API NOT VERIFIED until actual Search + Contents responses with source dates.':'Connection needed: EXA_API_KEY absent. LIVE NOT VERIFIED. No credential discovery or credit redemption.';}catch{notice('Local server unavailable. Start the server, then reload this tab.');}

let curation=null,liveApproval=null;
function resetCuration(){curation=null;liveApproval=null;$('curation').hidden=true;$('curation-records').replaceChildren();}
function invalidateLive(){liveApproval=null;$('curation-ack').checked=false;$('curation-export').disabled=true;$('curation-copy').disabled=true;$('curation-state').textContent='Not approved · USER_CURATED_NOT_VERIFIED';}
function startCuration(response,goal){
 curation=createCuration(response,goal);$('curation').hidden=false;
 $('curation-records').replaceChildren(...response.sources.map(s=>{
 const box=el('fieldset'),legend=el('legend',s.id+' · '+s.title);box.append(legend);
 const label=el('label'),pick=el('input');pick.type='checkbox';pick.dataset.sourceId=s.id;label.append(pick,el('span',' Include this source'));box.append(label);
 for(const [key,title,max] of [['excerpt','Exact excerpt (copy from source text above)',4000],['observation','Your interpretation / observation · USER_CURATED_NOT_VERIFIED',2000],['nextAction','Meaningful next action linked to this source · USER_CURATED_NOT_VERIFIED',2000]]){
 const l=el('label',title),t=el('textarea');t.rows=3;t.maxLength=max;t.dataset.field=key;l.append(t);box.append(l);
 }return box;
 }));
 $('curation-draft').value='';$('curation-uncertainties').value='';invalidateLive();
}
function liveInput(){return {goal:$('goal-input').value,records:[...$('curation-records').children].filter(b=>b.querySelector('input').checked).map(b=>({sourceId:b.querySelector('input').dataset.sourceId,...Object.fromEntries([...b.querySelectorAll('textarea')].map(t=>[t.dataset.field,t.value]))})),draft:$('curation-draft').value,uncertainties:$('curation-uncertainties').value};}
$('curation').addEventListener('input',e=>{if(e.target.id!=='curation-ack')invalidateLive();});
$('curation').addEventListener('change',e=>{if(e.target.id!=='curation-ack')invalidateLive();});
$('curation-ack').onchange=()=>{if(!$('curation-ack').checked)invalidateLive();};
$('curation-approve').onclick=()=>{try{liveApproval=curation.approve(liveInput(),$('curation-ack').checked);$('curation-state').textContent='Approved LOCAL_ONLY · no action executed';$('curation-export').disabled=false;$('curation-copy').disabled=false;notice('Exact excerpts validated. Human interpretation remains unverified.');}catch(e){invalidateLive();notice(e.message);}};
$('curation-export').onclick=()=>{try{const p=curation.exportPacket(liveInput(),liveApproval),url=URL.createObjectURL(new Blob([JSON.stringify(p,null,2)],{type:'application/json'})),a=el('a');a.href=url;a.download='exa-human-curated-local-only.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('Complete packet exported locally. Nothing sent.');}catch(e){invalidateLive();notice(e.message);}};
$('curation-copy').onclick=async()=>{try{const p=curation.exportPacket(liveInput(),liveApproval);await navigator.clipboard.writeText(JSON.stringify(p,null,2));notice('Complete packet copied. Nothing sent.');}catch(e){notice(e.message+' Use export if clipboard is unavailable.');}};
