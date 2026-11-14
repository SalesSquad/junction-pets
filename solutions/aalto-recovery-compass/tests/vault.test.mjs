import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { pack, unpack, createVault, indexedDBBackend, TTL, ITERATIONS } from '../src/vault.mjs';
const context='http://127.0.0.1:4180', passphrase='fictional demo passphrase only', time=1_800_000_000_000;
const options={context,passphrase,now:time,crypto:webcrypto};
const sealed=()=>pack({...options,action:'pause',energy:'lower'});
function fixture(){let record;let clock=time;const backend={read:async()=>structuredClone(record),write:async e=>{record=structuredClone(e);},delete:async()=>{record=undefined;}};return {vault:createVault({backend,context,crypto:webcrypto,now:()=>clock}),get:()=>record,set:e=>{record=e;},advance:()=>{clock+=TTL;}};}
test('AES-GCM roundtrip rederives public session, minimal fields, unique salt/IV',async()=>{
  const e=await sealed(), other=await sealed();assert.equal(ITERATIONS>=200000,true);assert.notEqual(e.iv,other.iv);assert.notEqual(e.salt,other.salt);assert.equal(e.iv.length,24);assert.equal(e.salt.length,32);
  const r=await unpack(e,options);assert.equal(r.session.action.id,'pause');assert.equal(r.session.checkin.energy,'lower');assert.equal(r.session.draft,null);assert.equal(r.session.dataReleaseAuthorized,false);assert.equal(r.includesEnergy,true);
  assert.deepEqual(Object.keys(e).sort(),['ciphertext','context','createdAt','expiresAt','iterations','iv','salt','version']);assert.equal(JSON.stringify(e).includes(passphrase),false);assert.equal(JSON.stringify(e).includes('pause'),false);
});
test('wrong passphrase and ciphertext, salt, IV modification fail closed',async()=>{
  const e=await sealed();await assert.rejects(unpack(e,{...options,passphrase:'another wrong passphrase'}));
  for(const field of ['ciphertext','salt','iv']){const altered={...e,[field]:(e[field][0]==='0'?'1':'0')+e[field].slice(1)};await assert.rejects(unpack(altered,options));}
});
test('strict envelope: extra fields, bounds, version, expiry, bytes, context',async()=>{
  const e=await sealed();
  for(const patch of [{draft:{}},{version:'v2'},{iterations:1},{createdAt:time+1},{expiresAt:time+TTL+1},{iv:'00'},{salt:'zz'.repeat(16)},{ciphertext:'aa'.repeat(513)},{ciphertext:'a'.repeat(33)},{context:'https://elsewhere.example'}])await assert.rejects(unpack({...e,...patch},options));
  await assert.rejects(unpack(e,{...options,now:time+TTL}));
  // Rewriting the visible context cannot rebind the authenticated ciphertext.
  await assert.rejects(unpack({...e,context:'http://localhost:4180'},{...options,context:'http://localhost:4180'}));
  // Plausible shifted TTL metadata still fails its encrypted duplicate comparison.
  await assert.rejects(unpack({...e,createdAt:time-1,expiresAt:time+TTL-1},options));
});
test('pack accepts only a public selected action and coarse preference',async()=>{
  for(const patch of [{action:'diagnosis'},{energy:'clinical score'},{energy:null},{passphrase:'short'},{now:-1},{crypto:{}},{context:'null'}])await assert.rejects(pack({...options,action:'pause',...patch}));
  const r=await unpack(await pack({...options,action:'outdoors'}),options);assert.equal(r.includesEnergy,false);assert.equal(r.session.checkin.energy,'prefer-not-to-say');
});
test('authenticated payload rejects unexpected fields and invalid choice',async()=>{
  const e=await sealed();
  const material=await webcrypto.subtle.importKey('raw',new TextEncoder().encode(passphrase),'PBKDF2',false,['deriveKey']);
  const key=await webcrypto.subtle.deriveKey({name:'PBKDF2',salt:Buffer.from(e.salt,'hex'),iterations:ITERATIONS,hash:'SHA-256'},material,{name:'AES-GCM',length:256},false,['encrypt']);
  for(const patch of [{draft:{recipient:'Nobody'}},{action:'diagnose'},{energy:99},{expiresAt:time+TTL-1}]){
    const payload={action:'pause',energy:'lower',createdAt:time,expiresAt:time+TTL,...patch};
    const ciphertext=await webcrypto.subtle.encrypt({name:'AES-GCM',iv:Buffer.from(e.iv,'hex'),additionalData:new TextEncoder().encode(`aalto-m343-capsule-v1\n${context}\nselected-action-only`),tagLength:128},key,new TextEncoder().encode(JSON.stringify(payload)));
    await assert.rejects(unpack({...e,ciphertext:Buffer.from(ciphertext).toString('hex')},options));
  }
});
test('adapter rewrite, reopen locked metadata, expiry purge, revoke/delete',async()=>{
  const f=fixture();await f.vault.save({action:'pause',passphrase,draft:{recipient:'not saved'},consentDraft:{}});
  assert.deepEqual(await f.vault.inspect(),{expiresAt:time+TTL});assert.equal(JSON.stringify(f.get()).includes('recipient'),false);
  await f.vault.save({action:'movement',passphrase});assert.equal((await f.vault.unlock(passphrase)).session.action.id,'movement');
  await assert.rejects(f.vault.unlock('another wrong passphrase'));assert.ok(f.get());
  await f.vault.delete();assert.equal(f.get(),undefined);await assert.rejects(f.vault.unlock(passphrase));
  await f.vault.save({action:'pause',passphrase});f.advance();assert.equal(await f.vault.inspect(),null);assert.equal(f.get(),undefined);
  f.set({unexpected:'plaintext'});assert.equal(await f.vault.inspect(),null);assert.equal(f.get(),undefined);
});
test('queued deletion cannot be overtaken by an in-progress save',async()=>{
  const f=fixture();const saving=f.vault.save({action:'pause',passphrase});const deleting=f.vault.delete();await Promise.all([saving,deleting]);assert.equal(f.get(),undefined);
});
test('missing browser APIs and failed storage operations report failure',async()=>{
  const backend=indexedDBBackend(null);await assert.rejects(backend.read(),/IndexedDB/);await assert.rejects(backend.delete(),/IndexedDB/);
  const vault=createVault({context,crypto:{},backend:{read:async()=>null}});await assert.rejects(vault.inspect(),/WebCrypto/);
  const failed=createVault({context,crypto:webcrypto,backend:{delete:async()=>{throw new Error('storage denied');}}});await assert.rejects(failed.delete(),/storage denied/);
});

test('denied IndexedDB getter does not break M1 module initialization',async()=>{
  const original=Object.getOwnPropertyDescriptor(globalThis,'indexedDB');
  try{Object.defineProperty(globalThis,'indexedDB',{configurable:true,get(){throw new Error('denied');}});const backend=indexedDBBackend();await assert.rejects(backend.read(),/IndexedDB/);}
  finally{if(original)Object.defineProperty(globalThis,'indexedDB',original);else delete globalThis.indexedDB;}
});
