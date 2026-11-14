import { assess, exportProposal } from '/src/engine.mjs';
const ui = (id) => document.getElementById(id);
const text = (id,s) => {ui(id).textContent=s;};
const data = await (await fetch('/fixtures/regions.json',{cache:'no-store'})).json();
const indicator=ui('indicator'),focus=ui('focus'),peer=ui('peer'),exportButton=ui('export');
for (const item of data.indicators) {const option=document.createElement('option');option.value=item.id;option.textContent=item.label;indicator.append(option);}
for (const item of data.regions) {for (const select of [focus,peer]){const option=document.createElement('option');option.value=item.id;option.textContent=item.name;select.append(option);}}
peer.selectedIndex=1;let last;
const p=(parent,tag,s,cls='')=>{const el=document.createElement(tag);el.textContent=s;if(cls)el.className=cls;parent.append(el);return el;};
async function draw() {
  const r=await assess(data,{indicatorId:indicator.value,focusId:focus.value,peerId:peer.value});last=r;
  const status=r.status==='ACTION_REVIEW'?'Review warranted':r.status==='INSUFFICIENT_EVIDENCE'?'Uncertainty overlaps':r.status==='SUPPRESSED'?'Suppressed':r.status==='NO_ACTION_GAP'?'No focus gap':'Do not compare';
  text('badge',status);ui('badge').dataset.state=r.status;
  text('verdict',r.status==='ACTION_REVIEW'?`A meaningful fictional gap merits a human-led review.`:`This comparison cannot justify a regional intervention from the available inputs.`);
  text('reason',`Reason: ${r.reason?.replaceAll('_',' ').toLowerCase() || 'none'}. Real-world causal effects and Strategy Goal 3 wording remain unverified.`);
  const n=ui('numbers');n.replaceChildren();if(r.observations){for(const row of r.observations){const box=p(n,'div','','number');p(box,'div',row.region,'number-label');p(box,'strong',String(row.value),'number-value');p(box,'div',`Illustrative interval ${row.low}–${row.high} · n=${row.n}`,'number-detail');}}
  const a=ui('action');a.replaceChildren();if(r.proposedAction){p(a,'h3',r.proposedAction.title);p(a,'p',r.proposedAction.intervention);const grid=p(a,'div','','fact-grid');p(grid,'span',`Responsible: ${r.proposedAction.owner}`);p(grid,'span',`Monitor: ${r.proposedAction.measure}`);p(a,'p','Draft only · primary-source Goal 3 clause not verified · no clinical decisions.','caption');}else p(a,'p','No intervention draft can be issued while the comparison is unsupported. Inspect the source/period/uncertainty gates.','caption');
  exportButton.disabled=r.status!=='ACTION_REVIEW';
}
for (const select of [indicator,focus,peer]) select.addEventListener('change',draw);
exportButton.addEventListener('click',()=>{const result=exportProposal(last);if(!result.ok)return;const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='SYNTHETIC-care-equity-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),300);});
draw();
