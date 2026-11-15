const $=id=>document.getElementById(id);
async function request(path,input){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)}),data=await r.json();
  if(!r.ok){const error=new Error(data.error||'Request failed.');error.status=r.status;throw error;}return data;
}
function download(name,data){
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function installWorkspace({state,inspect,restored}){
  let comparison=null,active=false;
  const identity=()=>({drawingId:state.drawing?.id,answerId:state.answerId});
  function render(){
    const r=state.review,c=r?.current,ready=!!state.answerId&&!active;
    $('review-status').textContent=c?`${c.status==='corrected'?'Reviewer correction':'Confirmation recorded'}: ${c.answer} · ${c.reviewer} · review revision ${r.revision}. Engine result above is unchanged.`:ready?'No human review recorded.':'Ask a question to start a source-bound review.';
    const history=$('review-history');history.replaceChildren();
    for(const event of (r?.events??[]).slice(-10)){const item=document.createElement('li');item.textContent=`${event.revision}: ${event.kind} · ${event.reviewer}${event.state?.answer?' · '+event.state.answer:''}`;history.appendChild(item);}
    $('confirm-answer').disabled=!ready||state.result?.status!=='supported';$('correct-answer').disabled=!ready;
    $('undo-review').disabled=!ready||!r?.canUndo;$('redo-review').disabled=!ready||!r?.canRedo;$('export-evidence').disabled=!ready;
  }
  async function review(kind){
    if(!state.answerId||active)return;active=true;render();const id=identity();
    try{
      const command={operationId:crypto.randomUUID(),sourceRevision:state.review.sourceRevision,expectedRevision:state.review.revision,kind,reviewer:$('reviewer-name').value.trim()};
      if(kind==='confirm'||kind==='correct')command.note=$('review-note').value;
      if(kind==='correct'){command.answer=$('review-answer').value;command.entityIds=$('review-ids').value.split(',').map(s=>s.trim()).filter(Boolean);}
      const data=await request('/api/review',{...id,command});
      if(state.answerId===id.answerId){state.review=data.review;$('review-message').textContent='Review recorded locally. Export to preserve it beyond this session.';}
    }catch(e){
      $('review-message').textContent=e.message;
      if(e.status===409){try{const data=await request('/api/review-read',id);if(state.answerId===id.answerId)state.review=data.review;$('review-message').textContent+=' Current review refreshed; check it before retrying.';}catch{}}
    }finally{active=false;render();}
  }
  for(const [id,kind] of [['confirm-answer','confirm'],['correct-answer','correct'],['undo-review','undo'],['redo-review','redo']])$(id).addEventListener('click',()=>review(kind));
  $('use-selected-evidence').addEventListener('click',()=>{
    if(!state.selected){$('review-message').textContent='Select a source entity or citation first.';return;}
    const ids=new Set($('review-ids').value.split(',').map(s=>s.trim()).filter(Boolean));ids.add(state.selected);$('review-ids').value=[...ids].join(', ');
  });
  $('export-evidence').addEventListener('click',async()=>{
    try{const {packet}=await request('/api/export-evidence',{...identity(),expectedReviewRevision:state.review.revision});download('stoa-evidence-'+packet.integrity.sha256.slice(0,12)+'.json',packet);$('review-message').textContent='Export contains selected source excerpts and locally declared review history. Keep it under the source licence.';}
    catch(e){$('review-message').textContent=e.message;}
  });
  $('restore-review-button').addEventListener('click',()=>$('restore-review-file').click());
  $('restore-review-file').addEventListener('change',async event=>{
    try{
      const file=event.target.files?.[0];if(!file)return;if(file.size>16*1024*1024)throw new Error('Review packet exceeds 16 MiB.');
      const id=state.drawing?.id,packet=JSON.parse(await file.text()),data=await request('/api/restore-review',{drawingId:id,packet});
      if(state.drawing?.id!==id)throw new Error('Source changed while restoring. Restore again on the correct source.');
      state.answerId=data.answerId;state.result=data.result;state.review=data.review;$('question').value=packet.payload.question;restored();
      $('review-message').textContent='Review restored against the same source and engine. Reviewer names remain locally declared.';
    }catch(e){$('review-message').textContent=e.message;}finally{event.target.value='';}
  });
  function modeChanged(){
    const primitive=$('revision-mode').value==='primitives';
    $('revision-layer-field').hidden=!primitive;$('revision-distance-field').hidden=!primitive;
    $('revision-alignment-field').hidden=$('revision-mode').value==='ifc';
    comparison=null;$('comparison-results').replaceChildren();$('comparison-status').textContent='';$('export-comparison').disabled=true;
  }
  for(const id of ['revision-mode','revision-layer','revision-distance','revision-aligned'])$(id).addEventListener('change',modeChanged);
  $('revision-before').addEventListener('change',()=>{ $('revision-aligned').checked=false; modeChanged(); });
  async function sources(){
    const response=await fetch('/api/sources');if(!response.ok)return;const data=await response.json(),select=$('revision-before');select.replaceChildren();
    const empty=document.createElement('option');empty.value='';empty.textContent='Choose earlier source';select.appendChild(empty);
    for(const s of data.sources.filter(s=>s.id!==state.drawing?.id)){
      const option=document.createElement('option');option.value=s.id;option.textContent=`${s.filename} · ${s.revision.slice(0,10)}${s.synthetic?' · synthetic':''}`;select.appendChild(option);
    }
    $('revision-aligned').checked=false;
    $('revision-mode').value=state.drawing?.format==='IFC STEP'?'ifc':'rooms';modeChanged();comparison=null;$('comparison-results').replaceChildren();$('export-comparison').disabled=true;$('comparison-status').textContent='';
    $('review-answer').value='';$('review-ids').value='';$('review-note').value='';
  }
  $('compare-revisions').addEventListener('click',async()=>{
    $('compare-revisions').disabled=true;const current=state.drawing?.id;
    try{
      const data=await request('/api/compare',{beforeId:$('revision-before').value,afterId:current,options:{mode:$('revision-mode').value,layer:$('revision-layer').value,alignmentDeclared:$('revision-aligned').checked,toleranceMetres:Number($('revision-distance').value)}});
      if(state.drawing?.id!==current)throw new Error('Current source changed. Compare again.');
      comparison=data.comparison;const p=comparison.payload,changed=p.changes.filter(c=>c.status!=='unchanged');
      $('comparison-status').textContent=Object.entries(p.summary).map(([k,v])=>`${k.replaceAll('_',' ')}: ${v}`).join(' · ')+`. Showing ${Math.min(changed.length,200)} of ${changed.length} changes. Matching and alignment are not independently verified.`;
      const list=$('comparison-results');list.replaceChildren();
      for(const c of changed.slice(0,200)){
        const row=document.createElement('div');row.className='comparison-row';const text=document.createElement('span');
        text.textContent=`${c.key||c.beforeId||c.afterId}: ${c.status.replaceAll('_',' ')}${c.areaDelta!=null?` · ${c.beforeArea} → ${c.afterArea} m² (${c.areaDelta>=0?'+':''}${c.areaDelta})`:''}${c.reason?' · '+c.reason:''}`;row.appendChild(text);
        if(c.afterId){const button=document.createElement('button');button.type='button';button.textContent='Inspect current source';button.addEventListener('click',()=>inspect(c.afterId));row.appendChild(button);}list.appendChild(row);
      }
      $('export-comparison').disabled=false;
    }catch(e){comparison=null;$('export-comparison').disabled=true;$('comparison-results').replaceChildren();$('comparison-status').textContent=e.message;}
    finally{$('compare-revisions').disabled=false;}
  });
  $('export-comparison').addEventListener('click',()=>{if(comparison)download('stoa-revision-comparison.json',comparison);});
  render();return {render,sources};
}
