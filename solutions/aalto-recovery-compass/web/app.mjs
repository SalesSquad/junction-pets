import { actions,newSession,checkIn,proposeAction,chooseAction,previewShare,consentDraft,revoke,clearAll } from '/src/compass.mjs';
import { createVault, indexedDBBackend } from '/src/vault.mjs';
const byId=(id)=>document.getElementById(id);const label=(id,text)=>{byId(id).textContent=text;};
let session=newSession();let selected='pause';let revoked=false;
const choices=byId('choices');for(const [i,action] of actions.entries()){const el=document.createElement('label');el.className='choice';const input=document.createElement('input');input.type='radio';input.name='activity';input.value=action.id;input.checked=i===0;input.addEventListener('change',()=>selected=action.id);el.append(input);const info=document.createElement('span');info.textContent=action.title;el.append(info);choices.append(el);}
byId('checkin').addEventListener('click',()=>{if(revoked){session=newSession();revoked=false;}const r=checkIn(session,{energy:byId('energy').value,wish:selected});if(!r.ok)return;session=r.session;resetDraftUI();byId('vault-consent').checked=false;const p=proposeAction(session);label('action-title',p.proposal.title);label('action-body',p.proposal.description);byId('suggestion').hidden=false;byId('share').hidden=true;byId('suggestion').scrollIntoView({behavior:'smooth',block:'center'});});
byId('skip').addEventListener('click',()=>{byId('suggestion').hidden=true;byId('share').hidden=true;label('message','You do not need to choose an action.');});
byId('choose').addEventListener('click',()=>{const r=chooseAction(session,{confirmed:true});if(!r.ok)return;session=r.session;byId('share').hidden=false;byId('share').scrollIntoView({behavior:'smooth',block:'nearest'});});
function request(){const fields=[];if(byId('include-energy').checked)fields.push('energy');if(byId('include-action').checked)fields.push('chosenAction');return {fields,recipient:byId('recipient').value,explicitConsent:byId('consent').checked};}
byId('preview').addEventListener('click',()=>{const r=previewShare(session,request());label('preview-box',r.ok?JSON.stringify(r.preview,null,2):`No preview: ${r.reason?.replaceAll('_',' ').toLowerCase()}`);});
byId('consent-draft').addEventListener('click',()=>{const r=consentDraft(session,request());if(!r.ok){label('message',`Refused: ${r.reason?.replaceAll('_',' ').toLowerCase()}.`);return;}session=r.session;label('message','An unsent, local draft exists only in this tab. No clinician is connected.');label('preview-box',JSON.stringify(session.draft,null,2));});
// The vault never assigns restored state to the current M1 session.
const vault=createVault({backend:indexedDBBackend(),context:location.origin});
let generation=0, expiryTimer;
const vaultControls=['vault-save','vault-unlock','vault-delete','revoke','clear'];
function resetDraftUI(){byId('consent').checked=false;label('preview-box','');label('message','');byId('recipient').value='Example clinician';}
function lockView(){generation++;clearTimeout(expiryTimer);byId('vault-view').hidden=true;label('vault-action','');label('vault-preference','');byId('vault-passphrase').value='';}
function expiry(expiresAt){clearTimeout(expiryTimer);expiryTimer=setTimeout(()=>{lockView();runVault(async()=>{await vault.inspect();label('vault-status','Capsule expired; local purge completed.');});},Math.max(0,expiresAt-Date.now()));}
async function runVault(operation){const current=generation;for(const id of vaultControls)byId(id).disabled=true;try{await operation(current);}catch(error){label('vault-status',error.message);}finally{for(const id of vaultControls)byId(id).disabled=false;byId('vault-passphrase').value='';}}
byId('vault-save').addEventListener('click',()=>{
  if(!session.action || !session.checkin || session.erased || !byId('vault-consent').checked){label('vault-status','Choose an action and separately opt in before saving.');return;}
  const input={action:session.action.id,passphrase:byId('vault-passphrase').value,...(byId('vault-energy').checked?{energy:session.checkin.energy}:{})};
  lockView();byId('vault-consent').checked=false;
  runVault(async current=>{const saved=await vault.save(input);if(current!==generation)return;expiry(saved.expiresAt);label('vault-status','Encrypted capsule saved locally for seven days. Any previous capsule was replaced.');});
});
byId('vault-unlock').addEventListener('click',()=>{const passphrase=byId('vault-passphrase').value;lockView();runVault(async current=>{
  const saved=await vault.unlock(passphrase);if(current!==generation)return;
  const action=actions.find(a=>a.id===saved.session.action.id);
  label('vault-action',action.title);label('vault-preference',saved.includesEnergy?`Saved energy preference: ${saved.session.checkin.energy}`:'No energy preference saved.');
  byId('vault-view').hidden=false;expiry(saved.expiresAt);label('vault-status','Unlocked locally. This saved snapshot is separate from the current check-in and sharing controls.');
});});
byId('vault-lock').addEventListener('click',()=>{lockView();label('vault-status','Saved view locked. Explicitly unlock to view again.');});
function deleteVault(message){lockView();byId('vault-consent').checked=false;return runVault(async current=>{const deleted=await vault.delete();if(current===generation)label('vault-status',message+(deleted?.coordinated===false?' Web Locks unavailable: local saves are disabled; deletion was not coordinated with other tabs.':''));});}
byId('vault-delete').addEventListener('click',()=>deleteVault('Saved ciphertext deleted locally. No remote copy was sent.'));
byId('revoke').addEventListener('click',()=>{const r=revoke(session);if(r.ok)session=r.session;resetDraftUI();label('message','Unsent draft cleared from memory.');deleteVault('Consent revoked; saved ciphertext deleted locally.');});
byId('clear').addEventListener('click',()=>{session=clearAll(session).session??newSession();revoked=true;resetDraftUI();byId('share').hidden=true;byId('suggestion').hidden=true;label('action-title','');label('action-body','');byId('energy').value='prefer-not-to-say';selected='pause';for(const el of choices.querySelectorAll('input'))el.checked=el.value==='pause';byId('vault-energy').checked=false;deleteVault('Session memory erased and saved ciphertext deleted locally.');});
window.addEventListener('pagehide',()=>{lockView();session=newSession();revoked=false;resetDraftUI();byId('share').hidden=true;byId('suggestion').hidden=true;label('action-title','');label('action-body','');byId('vault-consent').checked=false;byId('vault-energy').checked=false;byId('energy').value='prefer-not-to-say';selected='pause';for(const el of choices.querySelectorAll('input'))el.checked=el.value==='pause';label('vault-status','Locked. Explicitly unlock any saved capsule.');});
function inspectVault(){runVault(async current=>{const saved=await vault.inspect();if(current!==generation)return;if(saved)expiry(saved.expiresAt);label('vault-status',saved?'A saved capsule is locked. Enter your passphrase and explicitly unlock.':'No valid saved capsule. Expired or malformed ciphertext, if present, was purged.');});}
window.addEventListener('pageshow',inspectVault);
