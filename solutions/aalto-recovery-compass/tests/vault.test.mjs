import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { pack, unpack, createVault, indexedDBBackend, TTL, ITERATIONS } from '../src/vault.mjs';
const context='http://127.0.0.1:4180', passphrase='fictional demo passphrase only', time=1_800_000_000_000;
const options={context,passphrase,now:time,crypto:webcrypto};
const sealed=()=>pack({...options,action:'pause',energy:'lower'});
// A single injected lock manager may be shared by multiple simulated tabs.
function testLock(){
  const queues=new Map();
  return (name,options,operation)=>{
    assert.equal(options.mode,'exclusive');
    const result=(queues.get(name)??Promise.resolve()).then(operation);
    queues.set(name,result.catch(()=>{}));return result;
  };
}
function fixture(){let record;let clock=time;const backend={read:async()=>structuredClone(record),write:async e=>{record=structuredClone(e);},delete:async()=>{record=undefined;}};return {vault:createVault({backend,context,crypto:webcrypto,now:()=>clock,requestLock:testLock()}),get:()=>record,set:e=>{record=e;},advance:()=>{clock+=TTL;}};}
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
  const vault=createVault({context,requestLock:testLock(),crypto:{},backend:{read:async()=>null}});await assert.rejects(vault.inspect(),/WebCrypto/);
  const failed=createVault({context,requestLock:testLock(),crypto:webcrypto,backend:{delete:async()=>{throw new Error('storage denied');}}});await assert.rejects(failed.delete(),/storage denied/);
});

test('denied IndexedDB getter does not break M1 module initialization',async()=>{
  const original=Object.getOwnPropertyDescriptor(globalThis,'indexedDB');
  try{Object.defineProperty(globalThis,'indexedDB',{configurable:true,get(){throw new Error('denied');}});const backend=indexedDBBackend();await assert.rejects(backend.read(),/IndexedDB/);}
  finally{if(original)Object.defineProperty(globalThis,'indexedDB',original);else delete globalThis.indexedDB;}
});

test('two instances share lock through delayed encryption and committed save before revoke',async()=>{
  const requestLock=testLock();let record,releaseEncryption,enteredEncryption;
  const encrypting=new Promise(resolve=>{enteredEncryption=resolve;});
  const gate=new Promise(resolve=>{releaseEncryption=resolve;});
  const events=[];let enteredWrite,releaseCommit;
  const writing=new Promise(resolve=>{enteredWrite=resolve;});
  const commit=new Promise(resolve=>{releaseCommit=resolve;});
  const backend={read:async()=>record,write:async e=>{enteredWrite();await commit;record=e;events.push('committed');},delete:async()=>{record=undefined;events.push('deleted');}};
  const delayedCrypto={getRandomValues:webcrypto.getRandomValues.bind(webcrypto),subtle:new Proxy(webcrypto.subtle,{get(target,name){
    if(name==='encrypt')return async(...args)=>{events.push('encrypting');enteredEncryption();await gate;return target.encrypt(...args);};
    const value=Reflect.get(target,name);return typeof value==='function'?value.bind(target):value;
  }})};
  const a=createVault({backend,context,crypto:delayedCrypto,now:()=>time,requestLock});
  const b=createVault({backend,context,crypto:webcrypto,now:()=>time,requestLock});
  const saving=a.save({action:'pause',passphrase});await encrypting;
  const deleting=b.delete();let revoked=false;deleting.then(()=>{revoked=true;});
  await new Promise(resolve=>setImmediate(resolve));assert.equal(revoked,false);assert.deepEqual(events,['encrypting']);
  releaseEncryption();await writing;assert.equal(revoked,false);assert.deepEqual(events,['encrypting']);
  releaseCommit();await Promise.all([saving,deleting]);
  assert.deepEqual(events,['encrypting','committed','deleted']);assert.equal(record,undefined);
});
test('missing production Web Locks refuses save before crypto or writes, but permits honest deletion',async()=>{
  const original=Object.getOwnPropertyDescriptor(globalThis,'navigator');
  let writes=0,deletes=0,cryptoCalls=0;
  try{
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:{}});
    const vault=createVault({context,crypto:{getRandomValues(){cryptoCalls++;}},backend:{write:async()=>{writes++;},delete:async()=>{deletes++;}}});
    await assert.rejects(vault.save({action:'pause',passphrase}),/Web Locks/);
    assert.equal(cryptoCalls,0);assert.equal(writes,0);
    assert.deepEqual(await vault.delete(),{coordinated:false});assert.equal(deletes,1);
  }finally{if(original)Object.defineProperty(globalThis,'navigator',original);else delete globalThis.navigator;}
});
test('production lock requests are bound, immediate and never fall back after denial',async()=>{
  const original=Object.getOwnPropertyDescriptor(globalThis,'navigator');
  const requests=[];let touched=0;
  const locks={request(name,options){assert.equal(this,locks);requests.push([name,options]);return Promise.reject(new Error('lock denied'));}};
  try{
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:{locks}});
    const backend={read:async()=>{touched++;},write:async()=>{touched++;},delete:async()=>{touched++;}};
    const vault=createVault({context,crypto:webcrypto,backend});
    const operations=[vault.save({action:'pause',passphrase}),vault.delete(),vault.inspect(),vault.unlock(passphrase)];
    assert.equal(requests.length,4);
    for(const result of operations)await assert.rejects(result,/lock denied/);
    assert.equal(touched,0);
    for(const request of requests)assert.deepEqual(request,['aalto-m343-capsule-v1:storage',{mode:'exclusive'}]);
  }finally{if(original)Object.defineProperty(globalThis,'navigator',original);else delete globalThis.navigator;}
});
