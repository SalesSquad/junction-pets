import {FIXTURE_IDS,loadFixture,createSession,apply,receipt,replayReceipt} from './core.mjs';
const $=id=>document.getElementById(id);
let session=createSession(FIXTURE_IDS[0]), started=performance.now(), serial=0, busy=false, snapshot;
for(const id of FIXTURE_IDS){const f=loadFixture(id),option=document.createElement('option'); option.value=id;option.textContent=`${id} · labelled ${f.label}`;$('fixture').append(option);}
function elapsed(){return Math.floor(performance.now()-started);}
async function render(){
  const f=session.fixture,s=session.state;
  $('score').textContent=f.score.toFixed(2);
  $('interval').textContent=`${Math.max(0,f.score-f.uncertainty).toFixed(2)}–${Math.min(1,f.score+f.uncertainty).toFixed(2)}`;
  $('confidence').textContent=`${Math.round(f.confidence*100)}%`;
  $('range').style.left=`${Math.max(0,f.score-f.uncertainty)*100}%`;
  $('range').style.width=`${(Math.min(1,f.score+f.uncertainty)-Math.max(0,f.score-f.uncertainty))*100}%`;
  $('phase').textContent=`${s.phase.toUpperCase()} / ${f.id}`;$('status').textContent=s.reason;
  $('top-status').textContent=f.cameras.top?'FIXTURE':'MISSING';$('inspection-status').textContent=f.cameras.inspection?'FIXTURE':'MISSING';
  const r=$('region');r.setAttribute('visibility',f.region?'visible':'hidden');if(f.region) for(const [k,v] of Object.entries(f.region))r.setAttribute(({w:'width',h:'height'})[k]||k,v);
  $('part-title').textContent=`Drawn ${f.label} fixture ${f.id}${f.region?', outlined synthetic defect region':''}`;
  $('region-description').textContent=f.region?`Synthetic region: x ${f.region.x}, y ${f.region.y}, width ${f.region.w}, height ${f.region.h} (100 × 80 card coordinates).`:'No marked defect region in this synthetic fixture.';
  const terminal=['stopped','routed'].includes(s.phase);
  for(const b of document.querySelectorAll('[data-action]')){const a=b.dataset.action;b.disabled=terminal || (a==='gate'&&s.phase!=='loaded') || (a==='reinspect'&&s.phase!=='uncertain') || (a==='review'&&!['uncertain','review'].includes(s.phase)) || (a==='route'&&s.phase!=='gated');}
  for(const bowl of document.querySelectorAll('[data-bowl]'))bowl.classList.toggle('selected',bowl.dataset.bowl===s.bowl);
  snapshot=await receipt(session);$('receipt').textContent=JSON.stringify(snapshot,null,2);
  $('steps').replaceChildren();
  if(!snapshot.steps.length){const li=document.createElement('li');li.textContent='Fixture loaded. No gate or placement performed.';$('steps').append(li);}
  for(const step of snapshot.steps){const li=document.createElement('li');li.textContent=`${step.sequence}. ${step.command.type} · ${step.state.phase} · ${step.command.at} ms`;$('steps').append(li);}
}
async function run(task){if(busy)return;busy=true;try{await task();await render();}catch(e){$('message').textContent=e.message;}finally{busy=false;}}
$('load').onclick=()=>run(async()=>{session=createSession($('fixture').value);started=performance.now();serial=0;$('message').textContent='New synthetic episode loaded.';});
for(const b of document.querySelectorAll('[data-action]'))b.onclick=()=>run(async()=>{session=apply(session,{id:`ui-${++serial}`,type:b.dataset.action,at:Math.max(session.state.now,elapsed())});});
$('export').onclick=()=>run(async()=>{
  const data=await receipt(session),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=`${session.fixture.id}-synthetic-receipt.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('message').textContent='Receipt downloaded to your browser’s download destination.';
});
$('import').onchange=()=>run(async()=>{
  const file=$('import').files[0];if(!file)return;if(file.size>262144)throw Error('Receipt exceeds 256 KiB limit');
  const restored=await replayReceipt(JSON.parse(await file.text()));session=restored;started=performance.now()-session.state.now;serial=session.commands.length;$('fixture').value=session.fixture.id;$('message').textContent='Receipt integrity verified and replayed. Original capture age preserved.';$('import').value='';
});
setInterval(()=>run(async()=>{
  if(!['stopped','routed'].includes(session.state.phase) && elapsed()>30000)session=apply(session,{id:`clock-${++serial}`,type:'tick',at:Math.max(elapsed(),session.state.now)});
  $('age').textContent=`Capture age: ${(Math.max(elapsed(),session.state.now)/1000).toFixed(1)} s · live local timer`;
}),1000);
await render();
