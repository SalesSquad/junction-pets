import {Studio,REASONS,MAX_BYTES} from './model.mjs';
const $=id=>document.getElementById(id), studio=new Studio();
let busy=false;
const node=(tag,text,className)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;};
function sync(){
  const ready=studio.verified && !!studio.receipt;
  $('download').disabled=busy || !ready;$('run').disabled=busy || !studio.request;
  $('batch-state').textContent=ready?'REPLAY VERIFIED':studio.request?'READY TO RUN':'NOT RUN';
  $('verification').textContent=ready?'FULL REPLAY VERIFIED':'NO VERIFIED RECEIPT';
  $('empty').hidden=ready;$('outcomes').hidden=!ready;
  if(!ready){$('counts').replaceChildren();$('comparison').replaceChildren();$('episode-detail').replaceChildren();$('episode').replaceChildren();$('provenance').textContent='Run or import a receipt first.';}
}
function queue(){
  $('queue').replaceChildren();
  for(const [i,e] of (studio.request?.episodes ?? []).entries()){
    const card=node('fieldset',undefined,'brick');card.append(node('legend',e.id.replace('brick-','BRICK ').padEnd(8,' ')));
    const sketch=node('div',undefined,'brick-drawing');sketch.setAttribute('aria-hidden','true');for(let j=0;j<4;j++)sketch.append(node('i'));card.append(sketch);
    card.append(node('p',`Feed ${String(e.feedSlot).padStart(3,'0')} · ${e.fixtureId}`,'mono'));
    card.append(node('p',`Grip ${e.grip?'retained':'LOST'} · cameras ${e.cameraAgreement?'agree':'DISAGREE'} · capture age ${e.at} ms`,'muted'));
    const decision=node('select');decision.id=`decision-${i}`;
    for(const [value,label] of [['continue','Continue through gates'],['stop','STOP this brick']]){const o=node('option',label);o.value=value;decision.append(o);}decision.value=e.operator.decision;
    const reason=node('select');reason.id=`reason-${i}`;
    // Preserve a valid imported or M2-default reason exactly until explicitly edited.
    const choices=REASONS.includes(e.operator.reason)?REASONS:[e.operator.reason,...REASONS];
    for(const value of choices){const o=node('option',value);o.value=value;reason.append(o);}reason.value=e.operator.reason;
    const dl=node('label','Operator decision');dl.htmlFor=decision.id;const rl=node('label','Required reason');rl.htmlFor=reason.id;
    const edit=()=>{
      const selected=REASONS.includes(reason.value)?reason.value:(decision.value==='stop'?REASONS[3]:REASONS[0]);
      reason.value=selected;
      try{studio.edit(i,decision.value,selected);sync();$('message').textContent='Operator setting changed. Previous receipt cleared; run the batch again.';}catch{studio.invalidate();sync();$('message').textContent='Setting refused. Choose a decision and a listed reason.';}
    };
    decision.addEventListener('change',edit);reason.addEventListener('change',edit);
    card.append(dl,decision,rl,reason);$('queue').append(card);
  }
}
function detail(){
  const r=studio.receipt;if(!r)return;
  const id=$('episode').value,e=r.request.episodes.find(x=>x.id===id),steps=r.steps.filter(x=>x.episodeId===id);
  const inspection=steps.find(x=>x.stage==='inspection').data,decision=steps.find(x=>x.stage==='operator-decision').data;
  const row=r.evaluation.rows.find(x=>x.episodeId===id),box=$('episode-detail');box.replaceChildren();
  const route=decision.coreReceipt.final.bowl;
  box.append(node('p',`${id} / ${row.conservative.toUpperCase()}`,'eyebrow'),node('h3',route?`Software bowl → ${route.toUpperCase()}`:'No software bowl placement'),node('p',decision.reason));
  const dl=node('dl',undefined,'facts');
  const values=[['Feed slot',e.feedSlot],['Grip retained',String(e.grip)],['Camera agreement',String(e.cameraAgreement)],['Camera presence',`Top: ${inspection.cameras.top}; inspection: ${inspection.cameras.inspection}`],['Anomaly score',inspection.score.toFixed(2)],['Score interval',`${Math.max(0,inspection.score-inspection.uncertainty).toFixed(2)}–${Math.min(1,inspection.score+inspection.uncertainty).toFixed(2)} · gate threshold 0.50`],['Fixture confidence',`${inspection.confidence} · minimum 0.90`],['Capture age',`${inspection.captureAgeMs} ms · maximum 30000 ms`],['Operator',`${decision.decision.toUpperCase()} · ${e.operator.reason}`],['Naive software bowl (ignores interlocks)',row.baseline.toUpperCase()],['Synthetic safety hazard flagged',String(row.hazard)],['SIMULATED SCENE TRUTH',`${row.groundTruth.toUpperCase()} · post-run evaluation only; never a policy input`]];
  for(const [name,value] of values)dl.append(node('dt',name),node('dd',String(value)));box.append(dl);
  for(const [title,value] of [['Nested M1 coreReceipt',decision.coreReceipt],['Episode step hashes & provenance',steps]]){const d=node('details');d.append(node('summary',title),node('pre',JSON.stringify(value,null,2)));box.append(d);}
}
function results(){
  sync();const r=studio.receipt;if(!r)return;
  const rows=r.evaluation.rows;
  $('counts').replaceChildren();for(const outcome of ['good','defect','hold','stop']){const c=node('div',undefined,`count ${outcome}`);c.append(node('span',outcome.toUpperCase()),node('strong',String(rows.filter(x=>x.conservative===outcome).length)));$('counts').append(c);}
  const c=r.evaluation.conservative,b=r.evaluation.alwaysSortWithoutGate;
  const pct=v=>`${(v*100).toFixed(1)}%`,conditional=m=>m.conditionalCorrectness===null?'Undefined (0 sorted)':`${m.correctSorted}/${m.sorted} (${pct(m.conditionalCorrectness)})`;
  const measures=[['Sorted / all',`${c.sorted}/${c.total}`,`${b.sorted}/${b.total}`],['Held / stopped',`${c.held} / ${c.stopped}`,`${b.held} / ${b.stopped}`],['Unsafe sorted',c.unsafeSorted,b.unsafeSorted],['Coverage',pct(c.coverage),pct(b.coverage)],['Wrong among sorted',c.wrongSorted,b.wrongSorted],['Conditional correctness',conditional(c),conditional(b)]];
  $('comparison').replaceChildren();for(const [name,a,z] of measures){const tr=node('tr'),th=node('th',name);th.scope='row';tr.append(th,node('td',String(a)),node('td',String(z)));$('comparison').append(tr);}
  $('episode').replaceChildren();for(const e of r.request.episodes){const o=node('option',e.id);o.value=e.id;$('episode').append(o);}detail();
  $('provenance').textContent=JSON.stringify({provenance:r.provenance,inputDigest:r.inputDigest,root:r.root},null,2);
}
async function task(action,success){
  if(busy)return;busy=true;
  for(const el of document.querySelectorAll('button,input,select'))el.disabled=true;
  $('message').textContent='Replaying the complete receipt and nested M1 traces…';
  try{await action();queue();results();$('message').textContent=success;}
  catch{queue();sync();$('message').textContent='Operation refused. No verified receipt is available. Check the seed or import an intact M2 JSON receipt (maximum 2 MiB), then retry.';}
  finally{busy=false;for(const el of document.querySelectorAll('button,input,select'))el.disabled=false;sync();}
}
$('generate-form').addEventListener('submit',event=>{event.preventDefault();if(busy)return;try{studio.generate($('seed').value);queue();sync();$('message').textContent='Eight bricks generated. Review operator decisions before running.';}catch{queue();sync();$('message').textContent='Invalid seed. Enter a whole number from 0 to 4294967295.';}});
$('seed').addEventListener('input',()=>{studio.invalidate();studio.request=null;queue();sync();$('message').textContent='Seed changed. Generate a new batch before running.';});
$('run').addEventListener('click',()=>task(()=>studio.run(),'Synthetic batch complete. Full M2 replay and nested M1 integrity verified.'));
$('episode').addEventListener('change',detail);
$('import').addEventListener('change',()=>{
  const file=$('import').files[0];if(!file)return;
  task(async()=>{studio.invalidate();studio.request=null;if(file.size>MAX_BYTES)throw Error('Too large');await studio.importText(await file.text());$('seed').value=String(studio.request.seed);},'Imported receipt fully replayed. Original outcomes, failures and abstentions preserved.').finally(()=>{$('import').value='';});
});
$('download').addEventListener('click',()=>{
  try{const text=studio.exportText(),url=URL.createObjectURL(new Blob([text],{type:'application/json'})),a=node('a');a.href=url;a.download=`inspect-action-${studio.receipt.request.seed}-synthetic-batch.json`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);$('message').textContent='Receipt download requested. Your browser chooses the download destination.';}
  catch{$('message').textContent='No verified receipt to download.';sync();}
});
sync();
