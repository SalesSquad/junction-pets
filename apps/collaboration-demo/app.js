const $=id=>document.getElementById(id);
const names=new Map();
const companions=new Map();
let atlasReady=false;
const cssInitials={
  'junction.openai-codex':'CX','junction.mariadb':'DB','junction.nvidia':'NV','junction.meta':'M',
};
let trace=null;
let shown=0;
let active=null;
let timer=null;

function canonicalJson(value){
  if(value===null || typeof value!=='object')return JSON.stringify(value);
  if(Array.isArray(value))return '['+value.map(canonicalJson).join(',')+']';
  return '{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+canonicalJson(value[key])).join(',')+'}';
}
async function verifyDigest(value,field){
  const expected=value?.[field];
  if(!globalThis.crypto?.subtle || !/^[a-f0-9]{64}$/.test(expected??''))throw new Error('Checksum verification unavailable');
  const content={...value};delete content[field];
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonicalJson(content)));
  const actual=Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('');
  if(actual!==expected)throw new Error('Checksum mismatch');
  // A self-contained checksum detects corruption, not provider or source authenticity.
}
const verifyTraceDigest=value=>verifyDigest(value,'traceSha256');

const element=(tag,className='',text='')=>{
  const item=document.createElement(tag);
  if(className)item.className=className;
  if(text)item.textContent=text;
  return item;
};
const append=(parent,...children)=>{for(const child of children)if(child)parent.append(child);return parent;};
const human=id=>names.get(id)??id;
const shortHash=value=>typeof value==='string'?value.slice(0,12)+'…':'unverified';
function notice(message){
  $('toast').textContent=message;$('toast').classList.add('show');
  clearTimeout(window.chibiToastTimeout);
  window.chibiToastTimeout=setTimeout(()=>$('toast').classList.remove('show'),2500);
}

function paintAvatar(logo){
  const index=Number(logo.dataset.artIndex);
  logo.classList.add('has-art');
  logo.style.backgroundPosition=`${index%6*20}% ${Math.floor(index/6)*20}%`;
}
function petAvatar(id){
  const person=companions.get(id);
  const initials=cssInitials[id]??person?.company?.slice(0,2).toUpperCase()??'?';
  const logo=element('span','pet-logo',initials);
  logo.setAttribute('aria-hidden','true'); // The adjacent text already names the companion.
  logo.style.setProperty('--pet-surface','#1a4c4b');
  logo.style.setProperty('--pet-accent','#b2f0d3');
  if(Number.isInteger(person?.artIndex)&&person.artIndex>=0&&person.artIndex<36){
    logo.dataset.artIndex=String(person.artIndex);
    if(atlasReady)paintAvatar(logo);
  }
  return logo;
}
function renderOrbitAvatars(){
  for(const [slot,id] of [['orbitDatabase','junction.mariadb'],['orbitGpu','junction.nvidia'],['orbitUx','junction.meta']]){
    const node=$(slot);node.replaceChildren(petAvatar(id));
    node.title=human(id);
  }
}
function renderPeople(){
  const rail=$('petRail');rail.replaceChildren();
  for(const person of trace.participants){
    const card=element('article','pet-card');
    const logo=petAvatar(person.id);
    const label=element('span','cap-count','SPECIALIST');
    const title=element('h3','',person.company);
    const description=element('p','',person.id==='junction.openai-codex'?'Coordinates the review and evidence.':person.id==='junction.mariadb'?'Analyses database questions.':person.id==='junction.nvidia'?'Designs reproducible GPU checks.':'Reviews consent and UX.');
    const role=element('small','','Independent companion');
    append(card,logo,label,title,description,role);rail.append(card);
  }
  $('participantCount').textContent=String(trace.participants.length);
  $('messageCount').textContent=String(trace.messages.length);
  $('traceMeta').textContent='Fixture SHA-256: '+shortHash(trace.traceSha256)+' · Source commit unverified';
}

function renderTimeline(){
  const timeline=$('timeline');timeline.replaceChildren();
  if(!shown){
    const empty=element('div','timeline-empty');append(empty,element('span','','↗'),element('h3','','Four specialists. One flow.'),element('p','','Press Play or Next handoff to inspect a deterministic, source-labeled collaboration trace.'));timeline.append(empty);
  }
  trace.messages.slice(0,shown).forEach((message,i)=>{
    const button=element('button','handoff'+(active===message.id?' active':''));
    button.type='button';button.setAttribute('aria-pressed',String(active===message.id));
    button.setAttribute('aria-label',`View handoff ${i+1}: ${human(message.request.from)} to ${human(message.request.to)}`);
    button.addEventListener('click',()=>selectMessage(message.id));
    const line=element('span','index',String(i+1).padStart(2,'0'));
    const avatars=element('span','handoff-icons');avatars.setAttribute('aria-hidden','true');
    append(avatars,petAvatar(message.request.from),element('span','handoff-arrow','→'),petAvatar(message.request.to));
    const middle=element('span','transfer');
    append(middle,element('strong','',human(message.request.from)+' → '+human(message.request.to)),element('small','',message.capability.title));
    append(button,line,avatars,middle,element('span','badge','SIMULATED'),element('span','arrow','↗'));
    timeline.append(button);
  });
  $('progressLabel').textContent=shown===trace.messages.length?'All handoffs revealed':`${shown} of ${trace.messages.length} handoffs`;
  $('next').disabled=shown===trace.messages.length;
}

function detailField(label,value){
  const container=element('div');append(container,element('span','',label),element('strong','',value));return container;
}
function link(url){
  try{
    const parsed=new URL(url);if(parsed.protocol!=='https:')return null;
    const a=element('a','source-link',parsed.hostname+parsed.pathname);
    a.href=parsed.href;a.target='_blank';a.rel='noopener noreferrer';return a;
  }catch{return null;}
}
function renderDetail(){
  const region=$('detail');region.replaceChildren();
  if(!active){
    const empty=element('div','detail-empty');append(empty,element('span','','↗'),element('h3','','Pick a handoff'),element('p','','Each task shows declared recipient scope, a bounded synthetic fixture and traceable evidence.'));region.append(empty);return;
  }
  const message=trace.messages.find(m=>m.id===active);
  if(!message)return;
  append(region,element('span','kicker',`TASK ${message.index} / SYNTHETIC MESSAGE`),element('h3','',message.response.title),element('p','detail-description',message.request.context.summary));
  const grid=element('div','detail-grid');append(grid,
    detailField('From',human(message.request.from)),
    detailField('To',human(message.request.to)),
    detailField('Capability',message.request.capabilityId),
    detailField('Evidence',message.policy.result),
  );region.append(grid);
  region.append(element('h4','','ILLUSTRATIVE OUTPUT — NOT GENERATED BY AI'));
  const bullets=element('ul');for(const bullet of message.response.bullets)bullets.append(element('li','',bullet));region.append(bullets);
  region.append(element('h4','','DECLARED OFFICIAL REFERENCES — NOT RETRIEVED'));
  const references=message.provenance.referenceUrls;
  if(!references.length)region.append(element('p','detail-description','No reference URL in manifest'));
  for(const url of references){const a=link(url);if(a)region.append(a);}
  region.append(element('p','digest','Manifest SHA-256 '+shortHash(message.provenance.petManifestSha256)+' · Context '+shortHash(message.request.context.digest)));
  region.append(element('p','boundary-note','Every grant is a synthetic fixture. Real inter-pet calls require Chibi identity, consent, Cedar policy, exact task receipts and human approval for privileged actions.'));
}
function selectMessage(id){active=id;renderTimeline();renderDetail();}
function next(){
  if(!trace||shown>=trace.messages.length){stop();return;}
  shown+=1;active=trace.messages[shown-1].id;renderTimeline();renderDetail();
  if(shown===trace.messages.length){stop();notice('Synthetic handoffs complete. Human review is still pending.');}
}
function stop(){
  if(timer){clearInterval(timer);timer=null;}
  $('play').disabled=false;
}
function reset(){stop();shown=0;active=null;renderTimeline();renderDetail();}
function play(){
  if(!trace)return;
  reset();$('play').disabled=true;next();
  if(shown<trace.messages.length)timer=setInterval(next,1500);
}
function failure(reason){
  stop();$('play').disabled=true;$('next').disabled=true;
  const box=element('div','timeline-empty');append(box,element('span','','!'),element('h3','','Trace unavailable'),element('p','',reason));$('timeline').replaceChildren(box);
  $('progressLabel').textContent='No verified demo fixture';
  const card=element('div','detail-empty');append(card,element('h3','','Run the generator'),element('p','','Use node scripts/pet-collaboration-demo.mjs then serve dist/collaboration-demo over HTTP. No live agent run is claimed.'));$('detail').replaceChildren(card);
}
let solutionTeams=[];
let teamProjectionSha='';
function renderTeam(id,updateUrl=false){
  const team=solutionTeams.find(candidate=>candidate.id===id);
  if(!team)return;
  $('solutionPicker').value=id;
  const pane=$('solutionTeam');pane.replaceChildren();
  const summary=element('div','team-summary');
  append(summary,element('span','kicker','SOURCE-DECLARED TEAM'),element('h3','',team.title),
    element('p','',team.challengeSlugs.join(' · ')+' · Stage: '+team.stage+' · No host grant or execution'));
  pane.append(summary);
  const rail=element('div','team-rail');
  for(const member of team.members){
    const card=element('article','team-member');
    const body=element('div','team-member-copy');
    append(body,element('span','team-badge',member.capabilityUses.length?'PLANNED SKILL':'DECLARED PET'),
      element('h4','',member.displayName),
      element('p','team-company',member.company),
      element('p','',member.capabilityUses.length
        ?member.capabilityUses.map(use=>use.title).join(' · ')
        :'No peer capability planned'));
    append(card,petAvatar(member.petId),body);
    rail.append(card);
  }
  pane.append(rail);
  const heading=element('h4','team-routes-heading','Potential peer assistance — no dispatch');
  pane.append(heading);
  const routes=element('ol','team-routes');
  const anchor=team.members[0];
  for(const peer of team.members.slice(1)){
    const item=element('li','team-route');
    append(item,element('strong','',anchor.company+' → '+peer.company),
      element('span','team-badge','PROPOSED'),
      element('p','',peer.capabilityUses.map(use=>use.purpose).join(' ')||'No declared request capability'));
    routes.append(item);
  }
  if(routes.children.length)pane.append(routes);
  else pane.append(element('p','team-no-routes','Only one pet is currently linked to this solution. No peer route is claimed.'));
  $('teamMeta').textContent='Manifest projection SHA-256: '+shortHash(teamProjectionSha)+' · Not a signed Chibi receipt';
  if(updateUrl){
    const url=new URL(window.location.href);
    url.searchParams.set('solution',id);
    window.history.pushState(null,'',url);
  }
}
async function loadSolutionTeams(){
  const pane=$('solutionTeam'),picker=$('solutionPicker');
  try{
    const response=await fetch('./solution-teams.json',{cache:'no-store'});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const value=await response.json();
    if(value.executionMode!=='declared-memberships-no-dispatch'||!Array.isArray(value.teams)
      ||value.teams.some(team=>!Array.isArray(team.members)||!Array.isArray(team.challengeSlugs)
        ||team.members.some(member=>typeof member.petId!=='string'||!Array.isArray(member.capabilityUses))))
      throw new Error('Invalid non-executable team projection');
    await verifyDigest(value,'projectionSha256');
    solutionTeams=value.teams;
    teamProjectionSha=value.projectionSha256;
    picker.replaceChildren();
    for(const team of solutionTeams){
      const option=element('option','',team.title);option.value=team.id;picker.append(option);
      for(const member of team.members)companions.set(member.petId,member);
    }
    if(!solutionTeams.length){pane.textContent='No source-declared solution teams yet.';return;}
    picker.disabled=false;
    const defaultTeam=solutionTeams.find(team=>team.members.length>1)??solutionTeams[0];
    const requested=new URL(window.location.href).searchParams.get('solution');
    renderTeam(solutionTeams.some(team=>team.id===requested)?requested:defaultTeam.id);
    picker.addEventListener('change',()=>renderTeam(picker.value,true));
    window.addEventListener('popstate',()=>{
      const wanted=new URL(window.location.href).searchParams.get('solution');
      renderTeam(solutionTeams.some(team=>team.id===wanted)?wanted:defaultTeam.id);
    });
  }catch(error){
    picker.disabled=true;
    pane.textContent='Solution teams unavailable: '+(error instanceof Error?error.message:'unknown source error');
    $('teamMeta').textContent='The independent synthetic Council replay remains available above.';
  }
}

async function setup(){
  $('play').addEventListener('click',play);
  $('next').addEventListener('click',()=>{stop();next();});
  $('reset').addEventListener('click',reset);
  try{
    const response=await fetch('./trace.json',{cache:'no-store'});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const parsed=await response.json();
    if(parsed.protocol!=='junction.pet-collaboration/v1'||parsed.executionMode!=='synthetic-no-model-no-tools'||!Array.isArray(parsed.messages)||!Array.isArray(parsed.participants)||parsed.messages.length<1||parsed.participants.length<2)throw new Error('Invalid or non-synthetic trace');
    if(parsed.messages.some(m=>m.policy?.externalEffects!==false||m.response?.kind!=='synthetic-example'||m.policy?.hostAuthorization!==false))throw new Error('Untrusted provider execution claim');
    await verifyTraceDigest(parsed);
    trace=parsed;
    for(const person of trace.participants){names.set(person.id,person.company);companions.set(person.id,person);}
    renderPeople();renderOrbitAvatars();reset();
    // Show initials until the *local* canonical atlas has actually loaded.
    const atlas=new Image();
    atlas.addEventListener('load',()=>{
      atlasReady=true;
      for(const avatar of document.querySelectorAll('.pet-logo[data-art-index]'))paintAvatar(avatar);
    });
    atlas.src='./company-mascots.png';
    notice('Deterministic fixture loaded · source commit not verified.');
  }catch(error){failure(error instanceof Error?error.message:'Unknown load error');}
  await loadSolutionTeams(); // Independent of the synthetic trace's availability.
}
setup();
