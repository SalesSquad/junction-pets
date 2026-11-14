// Small behavior harness, not a claim of actual-browser/IndexedDB qualification.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import * as compass from '../src/compass.mjs';
const code=readFileSync(new URL('../web/app.mjs',import.meta.url),'utf8').replace(/^import .*;\n/gm,'');
function fixture(){
  const nodes=new Map(),events=new Map(),calls=[];
  const element=()=>({value:'',checked:false,hidden:true,disabled:false,textContent:'',children:[],listeners:new Map(),append(x){this.children.push(x);},addEventListener(n,fn){this.listeners.set(n,fn);},scrollIntoView(){},querySelectorAll(){return this.children.map(x=>x.children[0]);}});
  const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
  get('energy').value='steady';get('recipient').value='Example clinician';get('include-action').checked=true;
  const vault={inspect:async()=>null,save:async x=>{calls.push(x);return {expiresAt:Date.now()+10000};},unlock:async()=>({session:compass.chooseAction(compass.checkIn(compass.newSession(),{energy:'lower',wish:'outdoors'}).session,{confirmed:true}).session,includesEnergy:true,expiresAt:Date.now()+10000}),delete:async()=>{}};
  const context={...compass,createVault:()=>vault,indexedDBBackend:()=>({}),document:{getElementById:get,createElement:element},window:{addEventListener:(n,fn)=>events.set(n,fn)},location:{origin:'http://127.0.0.1:4180'},Date,setTimeout:()=>1,clearTimeout:()=>{}};
  vm.runInNewContext(code,context);
  const click=id=>get(id).listeners.get('click')();
  const tick=()=>new Promise(resolve=>setImmediate(resolve));
  return {get,events,vault,calls,click,tick};
}
test('saved view never becomes current sharing authorization, save opts in separately',async()=>{
  const f=fixture();f.get('vault-passphrase').value='fictional passphrase';f.click('vault-unlock');await f.tick();assert.equal(f.get('vault-view').hidden,false);assert.match(f.get('vault-action').textContent,/daylight/);
  f.click('choose');assert.equal(f.get('share').hidden,true);
  f.click('vault-save');await f.tick();assert.equal(f.calls.length,0);
  f.click('checkin');f.click('choose');f.click('vault-save');await f.tick();assert.equal(f.calls.length,0);
  f.get('vault-consent').checked=true;f.get('vault-passphrase').value='fictional passphrase';f.click('vault-save');await f.tick();assert.equal(f.calls.length,1);assert.deepEqual(Object.keys(f.calls[0]).sort(),['action','passphrase']);assert.equal(f.get('vault-passphrase').value,'');
});
test('new check-in clears draft controls, erase clears memory despite failed deletion',async()=>{
  const f=fixture();f.click('checkin');f.click('choose');f.get('consent').checked=true;f.click('consent-draft');assert.match(f.get('preview-box').textContent,/UNSENT/);
  f.click('checkin');assert.equal(f.get('consent').checked,false);assert.equal(f.get('preview-box').textContent,'');
  f.vault.delete=async()=>{throw new Error('Deletion not confirmed: storage denied.');};f.click('clear');await f.tick();assert.equal(f.get('share').hidden,true);assert.equal(f.get('suggestion').hidden,true);assert.equal(f.get('vault-view').hidden,true);assert.match(f.get('vault-status').textContent,/Deletion not confirmed/);assert.equal(f.get('vault-delete').disabled,false);
  f.click('choose');assert.equal(f.get('share').hidden,true);f.click('checkin');f.click('choose');assert.equal(f.get('share').hidden,false);
});
test('pagehide clears plaintext and ignores in-flight unlock completion; pageshow stays locked',async()=>{
  const f=fixture();let finish;f.vault.unlock=()=>new Promise(resolve=>{finish=resolve;});f.get('vault-passphrase').value='fictional passphrase';f.click('vault-unlock');f.events.get('pagehide')();finish({session:compass.chooseAction(compass.checkIn(compass.newSession(),{energy:'lower',wish:'outdoors'}).session,{confirmed:true}).session,includesEnergy:true,expiresAt:Date.now()+10000});await f.tick();
  assert.equal(f.get('vault-view').hidden,true);assert.equal(f.get('vault-action').textContent,'');assert.equal(f.get('vault-passphrase').value,'');f.events.get('pageshow')();await f.tick();assert.equal(f.get('vault-view').hidden,true);
});
test('revocation clears draft and requests ciphertext deletion',async()=>{
  const f=fixture();let deleted=0;f.vault.delete=async()=>{deleted++;};f.click('checkin');f.click('choose');f.get('consent').checked=true;f.click('consent-draft');f.click('revoke');await f.tick();assert.equal(deleted,1);assert.equal(f.get('preview-box').textContent,'');assert.equal(f.get('consent').checked,false);
});

test('deletion without Web Locks explains missing cross-tab coordination',async()=>{
  const f=fixture();f.vault.delete=async()=>({coordinated:false});f.click('vault-delete');await f.tick();
  assert.match(f.get('vault-status').textContent,/deleted locally/);
  assert.match(f.get('vault-status').textContent,/local saves are disabled; deletion was not coordinated with other tabs/);
});
