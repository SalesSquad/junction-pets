const byId = id => document.getElementById(id);
const ui = {page:byId('page'), target:byId('target'), baseline:byId('baseline'),
  status:byId('status'), snapshot:byId('snapshot'), difference:byId('difference'),
  events:byId('events'), state:byId('snapshot-state'), diffState:byId('diff-state'),
  count:byId('count'), reverts:byId('reverts'), source:byId('source')};
let catalog;
const sourceSelect = byId('evidence-source');
const apiPath = path => path + '?source=' + sourceSelect.value;
const trustedMode = mode => ['SYNTHETIC_REPLAY_NO_MARIADB','REAL_LOCAL_SNAPSHOT_NO_MARIADB'].includes(mode);
let requestSerial = 0;
let catalogSerial = 0;
const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
};
const clear = n => n.replaceChildren();
const add = (p, tag, text, className) => p.append(el(tag,text,className));
const warn = message => {ui.status.textContent = message; ui.state.textContent = 'REFUSED'; ui.diffState.textContent = 'REFUSED';};
function fill(select, entries, oldValue) {
  clear(select);
  for (const [value,label] of entries) {
    const option = el('option', label);
    option.value = value; select.append(option);
  }
  if (oldValue && entries.some(([value]) => value === oldValue)) select.value = oldValue;
}
const currentPage = () => catalog.pages.find(p => p.page_id === ui.page.value);
function renderHistory() {
  const page = currentPage();
  if (!page) return;
  fill(ui.target, page.revisions.map(r => [r.revised_at, r.revised_at]), page.revisions.at(-1).revised_at);
  fill(ui.baseline, page.revisions.map(r => [r.revised_at, r.revised_at]), page.revisions[0].revised_at);
  clear(ui.events);
  ui.count.textContent = page.revisions.length + ' REVISIONS';
  for (const row of [...page.revisions].reverse()) {
    const li = el('li'), btn = el('button', undefined, 'event');
    btn.type = 'button';
    btn.append(el('strong', 'Revision ' + row.revision_id), el('small', row.revised_at));
    btn.addEventListener('click', () => {ui.target.value=row.revised_at; syncSelection(); void run();});
    li.append(btn); ui.events.append(li);
  }
  syncSelection();
}
function syncSelection() {
  for (const option of ui.baseline.options)
    option.disabled = Date.parse(option.value) > Date.parse(ui.target.value);
  if (Date.parse(ui.baseline.value) > Date.parse(ui.target.value))
    ui.baseline.value = currentPage().revisions[0].revised_at;
  for (const [i,button] of [...ui.events.querySelectorAll('button')].entries()) {
    const index=currentPage().revisions.length-1-i;
    button.setAttribute('aria-current', String(currentPage().revisions[index].revised_at===ui.target.value));
  }
}
function draw(result) {
  clear(ui.snapshot); clear(ui.difference);
  const s=result.snapshot, c=result.comparison;
  ui.state.textContent=s.status;
  if(s.status==='FOUND'){
    add(ui.snapshot,'p',s.title+' · Revision '+s.revision_id,'metadata');
    add(ui.snapshot,'p',s.text,'lead');
    add(ui.snapshot,'p','Edited '+s.revised_at+' · body SHA-256 '+s.sha256,'metadata');
    if(s.source_url){const citation=el('a','Open cited Wikipedia revision');citation.href=s.source_url;citation.target='_blank';citation.rel='noopener noreferrer';ui.snapshot.append(citation);}
    add(ui.snapshot,'p','Source: '+(s.source_url || 'Synthetic fixture — no Wikipedia URL')+' · '+s.source_integrity,'metadata');
  }else{
    add(ui.snapshot,'p',s.status==='NO_EVIDENCE'?'No revision exists at that time.':'Multiple revisions share the latest timestamp; selection refused.','lead');
    if(s.conflicting_ids) add(ui.snapshot,'p','Conflicting revision IDs: '+s.conflicting_ids.join(', '),'metadata');
  }
  ui.diffState.textContent=c?.status||'UNAVAILABLE';
  if(c?.status==='CHANGED' || c?.status==='UNCHANGED'){
    add(ui.difference,'p','From revision '+c.from_revision+' to '+c.to_revision+'. '+c.note,'metadata');
    add(ui.difference,'h3','Added words');
    const a=el('div',undefined,'tokens');
    for(const item of c.added) a.append(el('span',item,'token'));
    if(!c.added.length) a.append(el('span','None'));
    ui.difference.append(a);
    add(ui.difference,'h3','Removed words');
    const b=el('div',undefined,'tokens');
    for(const item of c.removed) b.append(el('span',item,'token removed'));
    if(!c.removed.length) b.append(el('span','None'));
    ui.difference.append(b);
  } else add(ui.difference,'p','Comparison refused: missing or ambiguous evidence.');
  ui.reverts.textContent=result.suspected_reverts.length ?
    result.suspected_reverts.length+' A–B–A revert candidate(s) in this as-of window. Human review required; not vandalism proof.' :
    'No A–B–A revert candidate in this as-of window. This does not certify accuracy.';
  ui.status.textContent='Historical view computed. No network source or database was consulted.';
}
async function run() {
  const serial = ++requestSerial;
  clear(ui.snapshot); clear(ui.difference);
  ui.reverts.textContent='Historical revert evidence pending this request.';
  ui.state.textContent='LOADING'; ui.diffState.textContent='LOADING';
  try {
    const req={page_id:ui.page.value, as_of:ui.target.value, compare_at:ui.baseline.value};
    ui.status.textContent='Inspecting the local historical boundary…';
    const response=await fetch(apiPath('/api/compare'),{method:'POST',headers:{'Content-Type':'application/json'},
      cache:'no-store',body:JSON.stringify(req)});
    const result=await response.json();
    if(serial !== requestSerial) return;
    if(!response.ok || !trustedMode(result.mode) || result.verified_live_source!==false)
      throw new Error(result.reason || 'Untrusted response');
    draw(result); syncSelection();
  }catch(err){
    if(serial !== requestSerial) return;
    clear(ui.snapshot); clear(ui.difference);
    ui.reverts.textContent='No reliable as-of revert finding for this request.';
    warn('No trustworthy result: '+err.message);
  }
}
byId('query').addEventListener('submit',event=>{event.preventDefault();void run();});
ui.page.addEventListener('change',()=>{renderHistory();void run();});
ui.target.addEventListener('change',()=>{syncSelection();void run();});
ui.baseline.addEventListener('change',()=>{void run();});
async function loadCatalog() {
const serial=++catalogSerial;
try {
  const response=await fetch(apiPath('/api/catalog'),{cache:'no-store'});
  const next=await response.json();
  if(serial!==catalogSerial)return;
  catalog=next;
  if(!response.ok||!trustedMode(catalog.mode)||catalog.live!==false||
      !Array.isArray(catalog.pages)||!catalog.pages.length) throw new Error('Untrusted catalog');
  fill(ui.page,catalog.pages.map(p=>[p.page_id,p.title+' · '+p.page_id]));
  ui.source.textContent='Dataset '+catalog.dataset_id+' · '+catalog.dataset_license+
    ' · '+catalog.provenance+'. Timeline titles and dates cover the entire local fixture.';
  byId('source-label').textContent=catalog.provenance;
  if(catalog.retrieved_at) ui.source.textContent+=' Retrieved '+catalog.retrieved_at+' · Snapshot '+catalog.snapshot_sha256+' · '+catalog.window+' · '+catalog.attribution+' Local metadata is not authenticated sponsor evidence.';
  renderHistory();await run();
}catch(err){if(serial!==catalogSerial)return;clear(ui.snapshot);clear(ui.difference);clear(ui.events);clear(ui.page);clear(ui.target);clear(ui.baseline);ui.source.textContent='No admitted source selected.';ui.reverts.textContent='No current finding.';warn('Snapshot unavailable: '+err.message);}
}
sourceSelect.addEventListener('change',()=>{++requestSerial;void loadCatalog();});
await loadCatalog();
